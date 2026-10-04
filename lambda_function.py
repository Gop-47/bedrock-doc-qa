# =========================================================
# NOXORA — AI KNOWLEDGE ASSISTANT
# Lambda backend
#
# Features:
# - RAG with Bedrock Knowledge Base
# - Direct AI with server-side enable/disable
# - Redis / Valkey cache
# - DynamoDB query history
# - PDF upload to existing S3 bucket
# - PDF validation
# - Bedrock Knowledge Base ingestion
# - CORS
# - API validation
# =========================================================

import os
import json
import uuid
import hashlib
import mimetypes

import boto3
import redis

from datetime import datetime, timezone
from botocore.exceptions import ClientError


# =========================================================
# ENVIRONMENT VARIABLES
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


# =========================================================
# S3 DOCUMENT UPLOAD CONFIGURATION
# =========================================================

DOCUMENT_BUCKET = os.environ.get(
    "DOCUMENT_BUCKET",
    "bedrock-doc-qa-documents-gopi"
)

DOCUMENT_PREFIX = os.environ.get(
    "DOCUMENT_PREFIX",
    ""
).strip("/")


# Maximum upload size.
# 10 MB.

MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# =========================================================
# MODE CONFIGURATION
# =========================================================

DEFAULT_MODE = os.environ.get(
    "DEFAULT_MODE",
    "rag"
).strip().lower()


DIRECT_AI_ENABLED = (
    os.environ.get(
        "DIRECT_AI_ENABLED",
        "false"
    ).strip().lower()
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
# CACHE CONFIGURATION
# =========================================================

CACHE_TTL = 3600


# =========================================================
# AWS CLIENTS
# =========================================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)


history_table = dynamodb.Table(
    DYNAMODB_TABLE
)


bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=AWS_REGION
)


bedrock_agent_client = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION
)


bedrock_agent_control_client = boto3.client(
    service_name="bedrock-agent",
    region_name=AWS_REGION
)


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)


# =========================================================
# REDIS / VALKEY
# =========================================================

redis_client = redis.Redis(
    host=REDIS_ENDPOINT,
    port=6379,
    ssl=True,
    decode_responses=True
)


# =========================================================
# CORS RESPONSE
# =========================================================

def cors_response(
    status_code,
    body
):
    return {
        "statusCode": status_code,

        "headers": {
            "Access-Control-Allow-Origin": "*",

            "Access-Control-Allow-Headers": (
                "Content-Type,"
                "X-Amz-Date,"
                "Authorization,"
                "X-Api-Key,"
                "X-Amz-Security-Token"
            ),

            "Access-Control-Allow-Methods":
                "OPTIONS,GET,POST"
        },

        "body": json.dumps(
            body,
            default=str
        )
    }


# =========================================================
# ERROR RESPONSE
# =========================================================

def error_response(
    status_code,
    error_type,
    message
):
    return cors_response(
        status_code,
        {
            "error": {
                "type": error_type,
                "message": message
            }
        }
    )


# =========================================================
# MODE
# =========================================================

def get_effective_mode(
    requested_mode
):
    if requested_mode is None:
        requested_mode = DEFAULT_MODE

    if not isinstance(
        requested_mode,
        str
    ):
        return DEFAULT_MODE

    requested_mode = (
        requested_mode
        .strip()
        .lower()
    )

    if requested_mode not in (
        "rag",
        "direct"
    ):
        return None

    if (
        requested_mode == "direct"
        and not DIRECT_AI_ENABLED
    ):
        return "rag"

    return requested_mode


# =========================================================
# REDIS CACHE KEY
# =========================================================

def get_cache_key(
    question,
    mode="rag"
):
    normalized_question = (
        question
        .strip()
        .lower()
    )

    normalized_mode = (
        mode
        .strip()
        .lower()
    )

    cache_input = (
        f"{normalized_mode}:"
        f"{normalized_question}"
    )

    question_hash = hashlib.sha256(
        cache_input.encode("utf-8")
    ).hexdigest()

    return (
        f"qa:"
        f"{normalized_mode}:"
        f"{question_hash}"
    )


# =========================================================
# GET CACHE
# =========================================================

def get_cached_answer(
    question,
    mode="rag"
):
    try:

        cache_key = get_cache_key(
            question,
            mode
        )

        cached_data = redis_client.get(
            cache_key
        )

        if cached_data:

            result = json.loads(
                cached_data
            )

            result["cache"] = "hit"

            print(
                f"REDIS CACHE HIT: "
                f"{cache_key}"
            )

            return result

        print(
            f"REDIS CACHE MISS: "
            f"{cache_key}"
        )

        return None

    except Exception as e:

        print(
            f"Redis GET error: {str(e)}"
        )

        return None


# =========================================================
# SET CACHE
# =========================================================

def cache_answer(
    question,
    mode,
    result
):
    try:

        cache_key = get_cache_key(
            question,
            mode
        )

        redis_client.set(
            cache_key,
            json.dumps(result),
            ex=CACHE_TTL
        )

        print(
            f"Redis cached answer: "
            f"{cache_key}"
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

        cached_result = get_cached_answer(
            question,
            "rag"
        )

        if cached_result:
            return cached_result


        print(
            "Querying Bedrock Knowledge Base..."
        )


        response = (
            bedrock_agent_client.retrieve(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                retrievalQuery={
                    "text": question
                }
            )
        )


        contexts = []


        for result in response.get(
            "retrievalResults",
            []
        ):

            text = (
                result
                .get("content", {})
                .get("text", "")
            )

            source = (
                result
                .get("location", {})
                .get("s3Location", {})
                .get(
                    "uri",
                    "Unknown source"
                )
            )


            if text:

                contexts.append(
                    {
                        "text": text,
                        "source": source
                    }
                )


        context_text = "\n\n".join(
            context["text"]
            for context in contexts
        )


        prompt = f"""
You are Noxora, an AI knowledge assistant.

Use the following context from the provided
documents to answer the user's question.

Important instructions:

1. Answer using the provided context.
2. Do not invent information.
3. If the answer is not present in the context,
   say exactly:

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
                    "role": "user",
                    "content": prompt
                }
            ]
        }


        response_claude = (
            bedrock_client.invoke_model(
                modelId=MODEL_ID,

                contentType=
                    "application/json",

                accept=
                    "application/json",

                body=json.dumps(
                    request_body
                )
            )
        )


        response_body = json.loads(
            response_claude[
                "body"
            ].read()
        )


        answer = (
            response_body
            .get("content", [{}])[0]
            .get("text", "")
        )


        if not answer:

            raise RuntimeError(
                "Claude returned an empty answer."
            )


        result = {
            "answer": answer,

            "citations": contexts,

            "cache": "miss"
        }


        cache_answer(
            question,
            "rag",
            result
        )


        return result


    except ClientError as e:

        error_code = (
            e.response
            .get("Error", {})
            .get(
                "Code",
                "AWS_ERROR"
            )
        )

        error_message = (
            e.response
            .get("Error", {})
            .get(
                "Message",
                str(e)
            )
        )


        print(
            "Bedrock RAG error: "
            f"{error_code} - "
            f"{error_message}"
        )


        return {
            "answer":
                "Unable to query the knowledge base right now.",

            "citations": [],

            "cache": "error",

            "error": {
                "type":
                    error_code,

                "message":
                    error_message
            }
        }


    except Exception as e:

        print(
            f"Knowledge Base error: {str(e)}"
        )


        return {
            "answer":
                "Unable to process the knowledge base request.",

            "citations": [],

            "cache": "error",

            "error": {
                "type":
                    "KNOWLEDGE_BASE_ERROR",

                "message":
                    str(e)
            }
        }


# =========================================================
# DIRECT CLAUDE
# =========================================================

def query_claude_directly(
    question
):
    try:

        cached_result = get_cached_answer(
            question,
            "direct"
        )

        if cached_result:
            return cached_result


        request_body = {
            "anthropic_version":
                "bedrock-2023-05-31",

            "max_tokens":
                1000,

            "temperature":
                0.7,

            "messages": [
                {
                    "role": "user",
                    "content":
                        question
                }
            ]
        }


        response = (
            bedrock_client.invoke_model(
                modelId=MODEL_ID,

                contentType=
                    "application/json",

                accept=
                    "application/json",

                body=json.dumps(
                    request_body
                )
            )
        )


        response_body = json.loads(
            response[
                "body"
            ].read()
        )


        answer = (
            response_body
            .get("content", [{}])[0]
            .get("text", "")
        )


        if not answer:

            raise RuntimeError(
                "Claude returned an empty answer."
            )


        result = {
            "answer": answer,

            "citations": [],

            "cache": "miss"
        }


        cache_answer(
            question,
            "direct",
            result
        )


        return result


    except ClientError as e:

        error_code = (
            e.response
            .get("Error", {})
            .get(
                "Code",
                "AWS_ERROR"
            )
        )

        error_message = (
            e.response
            .get("Error", {})
            .get(
                "Message",
                str(e)
            )
        )


        print(
            "Direct AI error: "
            f"{error_code} - "
            f"{error_message}"
        )


        return {
            "answer":
                "Unable to contact Claude right now.",

            "citations": [],

            "cache": "error",

            "error": {
                "type":
                    error_code,

                "message":
                    error_message
            }
        }


    except Exception as e:

        print(
            f"Direct Claude error: {str(e)}"
        )


        return {
            "answer":
                "Unable to process the Direct AI request.",

            "citations": [],

            "cache": "error",

            "error": {
                "type":
                    "DIRECT_AI_ERROR",

                "message":
                    str(e)
            }
        }


# =========================================================
# DYNAMODB SAVE HISTORY
# =========================================================

def save_query_history(
    question,
    answer,
    mode,
    citations
):
    try:

        history_table.put_item(
            Item={
                "query_id":
                    str(uuid.uuid4()),

                "timestamp":
                    datetime
                    .now(timezone.utc)
                    .isoformat(),

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


        print(
            "Query history saved."
        )


        return True


    except Exception as e:

        print(
            f"History save error: {str(e)}"
        )

        return False


# =========================================================
# DYNAMODB GET HISTORY
# =========================================================

def get_query_history():

    try:

        response = history_table.scan(
            Limit=20
        )

        items = response.get(
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


        return error_response(
            500,

            "HISTORY_ERROR",

            "Unable to load query history."
        )


# =========================================================
# SANITIZE FILE NAME
# =========================================================

def sanitize_filename(
    filename
):
    """
    Keep only a safe filename.
    """

    if not isinstance(
        filename,
        str
    ):
        return None


    filename = filename.strip()


    if not filename:
        return None


    filename = filename.replace(
        "\\",
        "/"
    )


    filename = filename.split(
        "/"
    )[-1]


    allowed_chars = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "._- "
    )


    cleaned = "".join(
        char
        for char in filename
        if char in allowed_chars
    )


    cleaned = cleaned.strip(
        " ."
    )


    if not cleaned:
        return None


    return cleaned


# =========================================================
# VALIDATE PDF
# =========================================================

def validate_pdf_upload(
    filename,
    file_size
):

    if not filename:

        return (
            False,
            "Please select a PDF file."
        )


    if not filename.lower().endswith(
        ".pdf"
    ):

        return (
            False,
            "Only PDF files are allowed."
        )


    if file_size is None:

        return (
            False,
            "File size is required."
        )


    if not isinstance(
        file_size,
        int
    ):

        return (
            False,
            "Invalid file size."
        )


    if file_size <= 0:

        return (
            False,
            "The selected file is empty."
        )


    if file_size > MAX_UPLOAD_SIZE:

        return (
            False,
            "PDF file must be 10 MB or smaller."
        )


    return (
        True,
        None
    )


# =========================================================
# CREATE S3 UPLOAD
# =========================================================

def create_upload_request(
    filename,
    file_size
):
    """
    Generate a presigned S3 POST.

    S3 itself enforces:
    - PDF content type
    - maximum size
    """

    safe_filename = sanitize_filename(
        filename
    )


    if not safe_filename:

        return error_response(
            400,

            "INVALID_FILENAME",

            "Invalid file name."
        )


    valid, error_message = (
        validate_pdf_upload(
            safe_filename,
            file_size
        )
    )


    if not valid:

        return error_response(
            400,

            "INVALID_PDF",

            error_message
        )


    # -----------------------------------------------------
    # Unique object key
    # -----------------------------------------------------

    unique_id = str(
        uuid.uuid4()
    )


    if DOCUMENT_PREFIX:

        object_key = (
            f"{DOCUMENT_PREFIX}/"
            f"{unique_id}-{safe_filename}"
        )

    else:

        object_key = (
            f"{unique_id}-"
            f"{safe_filename}"
        )


    # -----------------------------------------------------
    # Generate presigned POST
    # -----------------------------------------------------

    try:

        presigned_post = (
            s3_client.generate_presigned_post(
                Bucket=DOCUMENT_BUCKET,

                Key=object_key,

                Fields={
                    "Content-Type":
                        "application/pdf"
                },

                Conditions=[
                    {
                        "Content-Type":
                            "application/pdf"
                    },

                    [
                        "content-length-range",
                        1,
                        MAX_UPLOAD_SIZE
                    ]
                ],

                ExpiresIn=900
            )
        )


        return cors_response(
            200,
            {
                "upload": {
                    "url":
                        presigned_post["url"],

                    "fields":
                        presigned_post["fields"],

                    "key":
                        object_key,

                    "filename":
                        safe_filename,

                    "expires_in":
                        900
                }
            }
        )


    except ClientError as e:

        print(
            "S3 presigned upload error: "
            f"{str(e)}"
        )


        return error_response(
            500,

            "UPLOAD_URL_ERROR",

            "Unable to prepare the PDF upload."
        )


    except Exception as e:

        print(
            f"Upload preparation error: {str(e)}"
        )


        return error_response(
            500,

            "UPLOAD_URL_ERROR",

            "Unable to prepare the PDF upload."
        )


# =========================================================
# FIND KNOWLEDGE BASE DATA SOURCE
# =========================================================

def find_s3_data_source():
    """
    Find the S3 data source connected to
    the configured Knowledge Base.
    """

    try:

        response = (
            bedrock_agent_control_client
            .list_data_sources(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID
            )
        )


        data_sources = response.get(
            "dataSourceSummaries",
            []
        )


        for data_source in data_sources:

            data_source_id = (
                data_source
                .get("dataSourceId")
            )


            if not data_source_id:
                continue


            try:

                details = (
                    bedrock_agent_control_client
                    .get_data_source(
                        knowledgeBaseId=
                            KNOWLEDGE_BASE_ID,

                        dataSourceId=
                            data_source_id
                    )
                )


                data_source_config = (
                    details
                    .get(
                        "dataSource",
                        {}
                    )
                    .get(
                        "dataSourceConfiguration",
                        {}
                    )
                )


                s3_config = (
                    data_source_config
                    .get(
                        "s3Configuration"
                    )
                )


                if not s3_config:
                    continue


                bucket_arn = (
                    s3_config
                    .get(
                        "bucketArn",
                        ""
                    )
                )


                expected_bucket_arn = (
                    f"arn:aws:s3:::{DOCUMENT_BUCKET}"
                )


                if bucket_arn == (
                    expected_bucket_arn
                ):

                    print(
                        "Found matching "
                        "Knowledge Base S3 data source: "
                        f"{data_source_id}"
                    )


                    return data_source_id


            except Exception as e:

                print(
                    "Unable to inspect data source "
                    f"{data_source_id}: {str(e)}"
                )


        return None


    except Exception as e:

        print(
            f"Unable to list data sources: {str(e)}"
        )

        return None


# =========================================================
# START KNOWLEDGE BASE INGESTION
# =========================================================

def start_ingestion_job():

    try:

        data_source_id = (
            find_s3_data_source()
        )


        if not data_source_id:

            print(
                "No matching S3 data source found."
            )


            return {
                "success":
                    False,

                "error":
                    "Knowledge Base S3 data source not found."
            }


        response = (
            bedrock_agent_control_client
            .start_ingestion_job(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    data_source_id,

                description=
                    "Noxora document upload ingestion"
            )
        )


        ingestion_job = (
            response
            .get(
                "ingestionJob",
                {}
            )
        )


        ingestion_job_id = (
            ingestion_job
            .get(
                "ingestionJobId"
            )
        )


        status = (
            ingestion_job
            .get(
                "status",
                "STARTING"
            )
        )


        print(
            "Knowledge Base ingestion started: "
            f"{ingestion_job_id}"
        )


        return {
            "success":
                True,

            "data_source_id":
                data_source_id,

            "ingestion_job_id":
                ingestion_job_id,

            "status":
                status
        }


    except ClientError as e:

        print(
            "Ingestion ClientError: "
            f"{str(e)}"
        )


        return {
            "success":
                False,

            "error":
                str(e)
        }


    except Exception as e:

        print(
            "Ingestion error: "
            f"{str(e)}"
        )


        return {
            "success":
                False,

            "error":
                str(e)
        }


# =========================================================
# VERIFY UPLOAD + START INGESTION
# =========================================================

def complete_upload(
    object_key,
    filename
):

    if not object_key:

        return error_response(
            400,

            "INVALID_UPLOAD",

            "Missing uploaded file key."
        )


    # -----------------------------------------------------
    # Security validation
    # -----------------------------------------------------

    if not object_key.endswith(
        ".pdf"
    ):

        return error_response(
            400,

            "INVALID_PDF",

            "Only PDF files can be processed."
        )


    expected_prefix = (
        f"{DOCUMENT_PREFIX}/"
        if DOCUMENT_PREFIX
        else ""
    )


    # Only allow objects created by
    # this application.

    if expected_prefix:

        if not object_key.startswith(
            expected_prefix
        ):

            return error_response(
                400,

                "INVALID_UPLOAD",

                "Invalid upload location."
            )


    try:

        # -------------------------------------------------
        # Verify object exists
        # -------------------------------------------------

        head = s3_client.head_object(
            Bucket=DOCUMENT_BUCKET,
            Key=object_key
        )


        actual_size = head.get(
            "ContentLength",
            0
        )


        actual_content_type = head.get(
            "ContentType",
            ""
        )


        if actual_size <= 0:

            return error_response(
                400,

                "INVALID_PDF",

                "Uploaded PDF is empty."
            )


        if actual_size > MAX_UPLOAD_SIZE:

            # Delete invalid oversized object.

            try:

                s3_client.delete_object(
                    Bucket=
                        DOCUMENT_BUCKET,

                    Key=
                        object_key
                )

            except Exception:
                pass


            return error_response(
                400,

                "FILE_TOO_LARGE",

                "PDF file must be 10 MB or smaller."
            )


        # -------------------------------------------------
        # Content type verification
        # -------------------------------------------------

        if actual_content_type != (
            "application/pdf"
        ):

            return error_response(
                400,

                "INVALID_PDF",

                "Uploaded file is not a valid PDF upload."
            )


        # -------------------------------------------------
        # Start ingestion
        # -------------------------------------------------

        ingestion = (
            start_ingestion_job()
        )


        if not ingestion.get(
            "success"
        ):

            return cors_response(
                202,

                {
                    "success":
                        True,

                    "filename":
                        filename
                        or object_key,

                    "key":
                        object_key,

                    "status":
                        "uploaded",

                    "message":
                        (
                            "PDF uploaded successfully, "
                            "but Knowledge Base ingestion "
                            "could not be started automatically."
                        ),

                    "ingestion":
                        ingestion
                }
            )


        return cors_response(
            200,

            {
                "success":
                    True,

                "filename":
                    filename
                    or object_key,

                "key":
                    object_key,

                "size":
                    actual_size,

                "status":
                    "processing",

                "message":
                    (
                        "PDF uploaded successfully. "
                        "Knowledge Base ingestion has started."
                    ),

                "ingestion":
                    ingestion
            }
        )


    except ClientError as e:

        print(
            "S3 verification error: "
            f"{str(e)}"
        )


        return error_response(
            400,

            "UPLOAD_NOT_FOUND",

            "The uploaded PDF could not be verified."
        )


    except Exception as e:

        print(
            f"Upload completion error: {str(e)}"
        )


        return error_response(
            500,

            "UPLOAD_COMPLETE_ERROR",

            "Unable to process the uploaded PDF."
        )


# =========================================================
# PARSE REQUEST BODY
# =========================================================

def parse_request_body(
    event
):

    if (
        "body" not in event
        or event["body"] is None
    ):

        return event


    body = event["body"]


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


    if isinstance(
        body,
        dict
    ):

        return body


    return None


# =========================================================
# QUERY HANDLER
# =========================================================

def handle_query(
    body
):

    # -----------------------------------------------------
    # Question validation
    # -----------------------------------------------------

    if "question" not in body:

        return error_response(
            400,

            "QUESTION_REQUIRED",

            "Missing required field: question."
        )


    question = body.get(
        "question"
    )


    if not isinstance(
        question,
        str
    ):

        return error_response(
            400,

            "INVALID_QUESTION",

            "Question must be a string."
        )


    question = question.strip()


    if not question:

        return error_response(
            400,

            "EMPTY_QUESTION",

            "Question cannot be empty."
        )


    if len(question) < 2:

        return error_response(
            400,

            "INVALID_QUESTION",

            "Question must contain at least 2 characters."
        )


    if len(question) > 2000:

        return error_response(
            400,

            "INVALID_QUESTION",

            "Question cannot exceed 2,000 characters."
        )


    # -----------------------------------------------------
    # Mode
    # -----------------------------------------------------

    requested_mode = body.get(
        "mode"
    )


    effective_mode = get_effective_mode(
        requested_mode
    )


    if effective_mode is None:

        return error_response(
            400,

            "INVALID_MODE",

            "Mode must be either 'rag' or 'direct'."
        )


    print(
        f"Requested mode: {requested_mode}"
    )

    print(
        f"Effective mode: {effective_mode}"
    )

    print(
        f"Direct AI enabled: {DIRECT_AI_ENABLED}"
    )


    # -----------------------------------------------------
    # RAG
    # -----------------------------------------------------

    if effective_mode == "rag":

        result = query_knowledge_base(
            question
        )


        if result.get(
            "cache"
        ) == "error":

            return error_response(
                500,

                result
                .get(
                    "error",
                    {}
                )
                .get(
                    "type",
                    "RAG_ERROR"
                ),

                "Unable to process your knowledge base request."
            )


        answer = result.get(
            "answer",
            ""
        )


        citations = result.get(
            "citations",
            []
        )


        cache_status = result.get(
            "cache",
            "unknown"
        )


        save_query_history(
            question=
                question,

            answer=
                answer,

            mode=
                "rag",

            citations=
                citations
        )


        return cors_response(
            200,

            {
                "question":
                    question,

                "mode":
                    "rag",

                "answer":
                    answer,

                "citations":
                    citations,

                "cache":
                    cache_status
            }
        )


    # -----------------------------------------------------
    # DIRECT AI
    # -----------------------------------------------------

    if effective_mode == "direct":

        if not DIRECT_AI_ENABLED:

            return error_response(
                403,

                "DIRECT_AI_DISABLED",

                "Direct AI is currently disabled."
            )


        result = query_claude_directly(
            question
        )


        if result.get(
            "cache"
        ) == "error":

            return error_response(
                500,

                result
                .get(
                    "error",
                    {}
                )
                .get(
                    "type",
                    "DIRECT_AI_ERROR"
                ),

                "Unable to process the Direct AI request."
            )


        answer = result.get(
            "answer",
            ""
        )


        cache_status = result.get(
            "cache",
            "unknown"
        )


        save_query_history(
            question=
                question,

            answer=
                answer,

            mode=
                "direct",

            citations=[]
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
                    cache_status
            }
        )


    return error_response(
        400,

        "INVALID_MODE",

        "Unable to determine AI mode."
    )


# =========================================================
# UPLOAD REQUEST
# =========================================================

def handle_upload_request(
    body
):

    filename = body.get(
        "filename"
    )

    file_size = body.get(
        "size"
    )


    return create_upload_request(
        filename,
        file_size
    )


# =========================================================
# UPLOAD COMPLETE REQUEST
# =========================================================

def handle_upload_complete(
    body
):

    object_key = body.get(
        "key"
    )

    filename = body.get(
        "filename"
    )


    return complete_upload(
        object_key,
        filename
    )


# =========================================================
# LAMBDA HANDLER
# =========================================================

def lambda_handler(
    event,
    context
):

    print(
        "================================================="
    )

    print(
        "NOXORA LAMBDA REQUEST"
    )

    print(
        json.dumps(
            event,
            default=str
        )
    )

    print(
        "================================================="
    )


    # =====================================================
    # HTTP METHOD
    # =====================================================

    http_method = event.get(
        "httpMethod"
    )


    if not http_method:

        request_context = event.get(
            "requestContext",
            {}
        )

        http = request_context.get(
            "http",
            {}
        )

        http_method = http.get(
            "method"
        )


    if http_method:

        http_method = (
            http_method
            .upper()
        )


    # =====================================================
    # CORS
    # =====================================================

    if http_method == "OPTIONS":

        return cors_response(
            200,
            {
                "message":
                    "CORS preflight successful"
            }
        )


    # =====================================================
    # GET HISTORY
    # =====================================================

    if http_method == "GET":

        return get_query_history()


    # =====================================================
    # POST
    # =====================================================

    if (
        http_method
        and http_method != "POST"
    ):

        return error_response(
            405,

            "METHOD_NOT_ALLOWED",

            "Only POST requests are supported."
        )


    # =====================================================
    # BODY
    # =====================================================

    body = parse_request_body(
        event
    )


    if body is None:

        return error_response(
            400,

            "INVALID_JSON",

            "Request body must contain valid JSON."
        )


    if not isinstance(
        body,
        dict
    ):

        return error_response(
            400,

            "INVALID_REQUEST",

            "Request body must be a JSON object."
        )


    # =====================================================
    # ACTION
    # =====================================================

    action = body.get(
        "action"
    )


    # -----------------------------------------------------
    # UPLOAD URL
    # -----------------------------------------------------

    if action == "upload":

        return handle_upload_request(
            body
        )


    # -----------------------------------------------------
    # UPLOAD COMPLETE
    # -----------------------------------------------------

    if action == "upload_complete":

        return handle_upload_complete(
            body
        )


    # -----------------------------------------------------
    # NORMAL QUERY
    # -----------------------------------------------------

    return handle_query(
        body
    )
