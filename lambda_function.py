import os
import json
import uuid
import hashlib
import re

import boto3
import redis

from datetime import datetime, timezone
from botocore.exceptions import ClientError


# =========================================================
# CONFIGURATION
# =========================================================

AWS_REGION = os.environ.get(
    "AWS_REGION",
    "us-east-1"
)

KNOWLEDGE_BASE_ID = os.environ[
    "KNOWLEDGE_BASE_ID"
]

MODEL_ID = os.environ[
    "MODEL_ID"
]

DYNAMODB_TABLE = os.environ[
    "DYNAMODB_TABLE"
]

REDIS_ENDPOINT = os.environ[
    "REDIS_ENDPOINT"
]

UPLOAD_BUCKET = os.environ.get(
    "UPLOAD_BUCKET",
    "bedrock-doc-qa-documents-gopi"
)


CACHE_TTL = 3600

MAX_UPLOAD_SIZE = (
    10 * 1024 * 1024
)


# =========================================================
# AI MODE CONFIGURATION
# =========================================================

DEFAULT_MODE = os.environ.get(
    "DEFAULT_MODE",
    "rag"
).strip().lower()


DIRECT_AI_ENABLED = (
    os.environ.get(
        "DIRECT_AI_ENABLED",
        "false"
    )
    .strip()
    .lower()
    in (
        "true",
        "1",
        "yes",
        "on"
    )
)


if DEFAULT_MODE not in (
    "rag",
    "direct"
):
    DEFAULT_MODE = "rag"


if (
    DEFAULT_MODE == "direct"
    and not DIRECT_AI_ENABLED
):

    DEFAULT_MODE = "rag"


# =========================================================
# AWS CLIENTS
# =========================================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)


history_table =
    dynamodb.Table(
        DYNAMODB_TABLE
    )


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)


bedrock_client = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION
)


bedrock_agent_client = boto3.client(
    "bedrock-agent-runtime",
    region_name=AWS_REGION
)


# =========================================================
# REDIS
# =========================================================

redis_client = redis.Redis(
    host=REDIS_ENDPOINT,
    port=6379,
    ssl=True,
    decode_responses=True
)


# =========================================================
# CORS
# =========================================================

def cors_response(
    status_code,
    body
):

    return {

        "statusCode":
            status_code,

        "headers": {

            "Access-Control-Allow-Origin":
                "*",

            "Access-Control-Allow-Headers":
                (
                    "Content-Type,"
                    "X-Amz-Date,"
                    "Authorization,"
                    "X-Api-Key,"
                    "X-Amz-Security-Token"
                ),

            "Access-Control-Allow-Methods":
                "OPTIONS,GET,POST"
        },

        "body":
            json.dumps(
                body,
                default=str
            )
    }


# =========================================================
# CACHE
# =========================================================

def get_cache_key(
    question,
    mode="rag"
):

    normalized_question =
        question.strip().lower()

    question_hash =
        hashlib.sha256(
            normalized_question.encode(
                "utf-8"
            )
        ).hexdigest()

    return (
        f"qa:{mode}:{question_hash}"
    )


def get_cached_answer(
    question,
    mode="rag"
):

    try:

        cache_key =
            get_cache_key(
                question,
                mode
            )

        cached_data =
            redis_client.get(
                cache_key
            )


        if cached_data:

            return json.loads(
                cached_data
            )


        return None


    except Exception as e:

        print(
            f"Redis GET error: {str(e)}"
        )

        return None


def cache_answer(
    question,
    mode,
    result
):

    try:

        cache_key =
            get_cache_key(
                question,
                mode
            )


        redis_client.set(
            cache_key,

            json.dumps(
                result
            ),

            ex=CACHE_TTL
        )


        print(
            f"Cached answer: {cache_key}"
        )


    except Exception as e:

        print(
            f"Redis SET error: {str(e)}"
        )


# =========================================================
# RAG
# =========================================================

def query_knowledge_base(
    question
):

    try:

        cached_result =
            get_cached_answer(
                question,
                "rag"
            )


        if cached_result:

            print(
                "CACHE HIT"
            )

            cached_result["cache"] =
                "hit"

            return cached_result


        print(
            "CACHE MISS"
        )


        response =
            bedrock_agent_client.retrieve(

                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                retrievalQuery={
                    "text": question
                }

            )


        contexts = []


        for result in response.get(
            "retrievalResults",
            []
        ):

            text =
                result.get(
                    "content",
                    {}
                ).get(
                    "text",
                    ""
                )


            source =
                result.get(
                    "location",
                    {}
                ).get(
                    "s3Location",
                    {}
                ).get(
                    "uri",
                    "Unknown"
                )


            contexts.append({

                "text":
                    text,

                "source":
                    source

            })


        context_text =
            "\n\n".join(
                context["text"]
                for context in contexts
            )


        prompt = f"""
Use the following context from documents to answer the question.

If the answer is not in the context say:

"I cannot find this in the provided documents."

Context:

{context_text}

Question:

{question}

Answer:
"""


        request_body = {

            "anthropic_version":
                "bedrock-2023-05-31",

            "max_tokens":
                1000,

            "temperature":
                0.7,

            "messages": [

                {

                    "role":
                        "user",

                    "content":
                        prompt

                }

            ]

        }


        response_claude =
            bedrock_client.invoke_model(

                modelId=
                    MODEL_ID,

                contentType=
                    "application/json",

                accept=
                    "application/json",

                body=
                    json.dumps(
                        request_body
                    )

            )


        response_body =
            json.loads(
                response_claude[
                    "body"
                ].read()
            )


        answer =
            response_body[
                "content"
            ][0]["text"]


        result = {

            "answer":
                answer,

            "citations":
                contexts,

            "cache":
                "miss"

        }


        cache_answer(
            question,
            "rag",
            result
        )


        return result


    except ClientError as e:

        error_code =
            e.response[
                "Error"
            ]["Code"]

        error_message =
            str(e)


        print(
            f"Bedrock error: "
            f"{error_code} - "
            f"{error_message}"
        )


        return {

            "answer":
                f"Error: {error_code} - "
                f"{error_message}",

            "citations":
                [],

            "cache":
                "error"

        }


    except Exception as e:

        print(
            f"Knowledge Base error: "
            f"{str(e)}"
        )


        return {

            "answer":
                f"Error: {str(e)}",

            "citations":
                [],

            "cache":
                "error"

        }


# =========================================================
# DIRECT AI
# =========================================================

def query_claude_directly(
    question
):

    request_body = {

        "anthropic_version":
            "bedrock-2023-05-31",

        "max_tokens":
            1000,

        "temperature":
            0.7,

        "messages": [

            {

                "role":
                    "user",

                "content":
                    question

            }

        ]

    }


    try:

        response =
            bedrock_client.invoke_model(

                modelId=
                    MODEL_ID,

                contentType=
                    "application/json",

                accept=
                    "application/json",

                body=
                    json.dumps(
                        request_body
                    )

            )


        response_body =
            json.loads(
                response[
                    "body"
                ].read()
            )


        return response_body[
            "content"
        ][0]["text"]


    except ClientError as e:

        return (
            "Error calling Claude: "
            f"{str(e)}"
        )


    except Exception as e:

        return (
            "Error calling Claude: "
            f"{str(e)}"
        )


# =========================================================
# HISTORY
# =========================================================

def save_query_history(
    question,
    answer,
    mode,
    citations
):

    history_table.put_item(

        Item={

            "query_id":
                str(uuid.uuid4()),

            "timestamp":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "question":
                question,

            "answer":
                answer,

            "mode":
                mode,

            "citations":
                citations

        }

    )


def get_query_history():

    try:

        response =
            history_table.scan(
                Limit=20
            )


        items =
            response.get(
                "Items",
                []
            )


        items.sort(

            key=lambda x:
                x.get(
                    "timestamp",
                    ""
                ),

            reverse=True

        )


        return cors_response(

            200,

            {
                "history":
                    items
            }

        )


    except Exception as e:

        print(
            f"History error: {str(e)}"
        )


        return cors_response(

            500,

            {
                "error":
                    str(e)
            }

        )


# =========================================================
# SAFE FILE NAME
# =========================================================

def sanitize_filename(
    filename
):

    filename =
        os.path.basename(
            filename
        )


    filename =
        re.sub(
            r"[^a-zA-Z0-9._-]",
            "_",
            filename
        )


    if not filename:
        filename = "document.pdf"


    return filename


# =========================================================
# PDF UPLOAD
# =========================================================

def create_upload_url(
    body
):

    filename =
        body.get(
            "filename"
        )


    content_type =
        body.get(
            "contentType"
        )


    size =
        body.get(
            "size"
        )


    # -----------------------------------------------------
    # Required fields
    # -----------------------------------------------------

    if not filename:

        return cors_response(

            400,

            {
                "error":
                    "Filename is required."
            }

        )


    # -----------------------------------------------------
    # PDF extension
    # -----------------------------------------------------

    if not filename.lower().endswith(
        ".pdf"
    ):

        return cors_response(

            400,

            {
                "error":
                    "Only PDF files are allowed."
            }

        )


    # -----------------------------------------------------
    # MIME
    # -----------------------------------------------------

    if (
        content_type
        and content_type
        != "application/pdf"
    ):

        return cors_response(

            400,

            {
                "error":
                    "Only application/pdf files are allowed."
            }

        )


    # -----------------------------------------------------
    # Size
    # -----------------------------------------------------

    try:

        size =
            int(size)

    except (
        TypeError,
        ValueError
    ):

        return cors_response(

            400,

            {
                "error":
                    "Invalid file size."
            }

        )


    if size <= 0:

        return cors_response(

            400,

            {
                "error":
                    "File cannot be empty."
            }

        )


    if size > MAX_UPLOAD_SIZE:

        return cors_response(

            400,

            {
                "error":
                    "PDF must be smaller than 10 MB."
            }

        )


    # -----------------------------------------------------
    # Safe key
    # -----------------------------------------------------

    safe_name =
        sanitize_filename(
            filename
        )


    object_key =
        (
            "uploads/"
            f"{uuid.uuid4().hex}-"
            f"{safe_name}"
        )


    # -----------------------------------------------------
    # Presigned URL
    # -----------------------------------------------------

    try:

        upload_url =
            s3_client.generate_presigned_url(

                "put_object",

                Params={

                    "Bucket":
                        UPLOAD_BUCKET,

                    "Key":
                        object_key,

                    "ContentType":
                        "application/pdf"

                },

                ExpiresIn=300

            )


        print(
            f"Generated upload URL "
            f"for {object_key}"
        )


        return cors_response(

            200,

            {

                "message":
                    "Upload URL created.",

                "uploadUrl":
                    upload_url,

                "key":
                    object_key,

                "filename":
                    safe_name

            }

        )


    except Exception as e:

        print(
            f"S3 presigned URL error: "
            f"{str(e)}"
        )


        return cors_response(

            500,

            {
                "error":
                    "Unable to create S3 upload URL."
            }

        )


# =========================================================
# GET PATH
# =========================================================

def get_request_path(
    event
):

    return (
        event.get(
            "rawPath"
        )
        or event.get(
            "path"
        )
        or event.get(
            "resource"
        )
        or ""
    )


# =========================================================
# GET BODY
# =========================================================

def get_request_body(
    event
):

    body =
        event.get(
            "body"
        )


    if body is None:

        return event


    if isinstance(
        body,
        dict
    ):

        return body


    if isinstance(
        body,
        str
    ):

        try:

            return json.loads(
                body
            )

        except json.JSONDecodeError:

            return None


    return None


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(
    event,
    context
):

    print(
        "Received event:"
    )


    print(
        json.dumps(
            event,
            default=str
        )
    )


    http_method =
        event.get(
            "httpMethod",
            ""
        ).upper()


    path =
        get_request_path(
            event
        )


    print(
        f"Method: {http_method}"
    )


    print(
        f"Path: {path}"
    )


    # =====================================================
    # OPTIONS
    # =====================================================

    if (
        http_method ==
        "OPTIONS"
    ):

        return cors_response(

            200,

            {
                "message":
                    "CORS preflight successful"
            }

        )


    # =====================================================
    # HISTORY
    # =====================================================

    if (
        http_method == "GET"
        and (
            path.endswith(
                "/query/history"
            )
            or
            path.endswith(
                "/history"
            )
        )
    ):

        return get_query_history()


    # =====================================================
    # UPLOAD
    # =====================================================

    if (
        http_method == "POST"
        and path.endswith(
            "/upload"
        )
    ):

        body =
            get_request_body(
                event
            )


        if body is None:

            return cors_response(

                400,

                {
                    "error":
                        "Invalid JSON body."
                }

            )


        return create_upload_url(
            body
        )


    # =====================================================
    # QUERY
    # =====================================================

    if (
        http_method == "POST"
        and path.endswith(
            "/query"
        )
    ):

        body =
            get_request_body(
                event
            )


        if body is None:

            return cors_response(

                400,

                {
                    "error":
                        "Invalid JSON body."
                }

            )


        question =
            body.get(
                "question"
            )


        if (
            not isinstance(
                question,
                str
            )
        ):

            return cors_response(

                400,

                {
                    "error": {

                        "type":
                            "INVALID_QUESTION",

                        "message":
                            "Question must be a string."

                    }
                }

            )


        question =
            question.strip()


        if not question:

            return cors_response(

                400,

                {
                    "error": {

                        "type":
                            "EMPTY_QUESTION",

                        "message":
                            "Question cannot be empty."

                    }
                }

            )


        if len(question) > 2000:

            return cors_response(

                400,

                {
                    "error": {

                        "type":
                            "INVALID_QUESTION",

                        "message":
                            "Question must be under 2,000 characters."

                    }
                }

            )


        requested_mode =
            body.get(
                "mode",
                DEFAULT_MODE
            )


        if requested_mode not in (
            "rag",
            "direct"
        ):

            requested_mode =
                DEFAULT_MODE


        # -------------------------------------------------
        # Direct AI protection
        # -------------------------------------------------

        if (
            requested_mode ==
            "direct"
            and not DIRECT_AI_ENABLED
        ):

            actual_mode =
                "rag"

        else:

            actual_mode =
                requested_mode


        print(
            f"Requested mode: "
            f"{requested_mode}"
        )


        print(
            f"Actual mode: "
            f"{actual_mode}"
        )


        # -------------------------------------------------
        # RAG
        # -------------------------------------------------

        if actual_mode == "rag":

            result =
                query_knowledge_base(
                    question
                )


            save_query_history(

                question=
                    question,

                answer=
                    result[
                        "answer"
                    ],

                mode=
                    "rag",

                citations=
                    result.get(
                        "citations",
                        []
                    )

            )


            return cors_response(

                200,

                {

                    "question":
                        question,

                    "mode":
                        "rag",

                    "answer":
                        result[
                            "answer"
                        ],

                    "citations":
                        result.get(
                            "citations",
                            []
                        ),

                    "cache":
                        result.get(
                            "cache",
                            "unknown"
                        )

                }

            )


        # -------------------------------------------------
        # DIRECT AI
        # -------------------------------------------------

        answer =
            query_claude_directly(
                question
            )


        save_query_history(

            question=
                question,

            answer=
                answer,

            mode=
                "direct",

            citations=
                []

        )


        return cors_response(

            200,

            {

                "question":
                    question,

                "mode":
                    "direct",

                "answer":
                    answer,

                "citations":
                    [],

                "cache":
                    "not_used"

            }

        )


    # =====================================================
    # UNKNOWN ROUTE
    # =====================================================

    return cors_response(

        404,

        {

            "error":
                "Route not found.",

            "path":
                path,

            "method":
                http_method

        }

    )
