import os
import json
import uuid
import hashlib
import boto3
import redis

from datetime import datetime, timezone
from botocore.exceptions import ClientError


# ---------------------------------------------------------
# ENVIRONMENT VARIABLES
# ---------------------------------------------------------

AWS_REGION = os.environ.get(
    "AWS_REGION",
    "us-east-1"
)

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]

MODEL_ID = os.environ["MODEL_ID"]

DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]

REDIS_ENDPOINT = os.environ["REDIS_ENDPOINT"]


# ---------------------------------------------------------
# MODE / COST CONTROL
# ---------------------------------------------------------

DEFAULT_MODE = os.environ.get(
    "DEFAULT_MODE",
    "rag"
).strip().lower()


DIRECT_AI_ENABLED = (
    os.environ.get(
        "DIRECT_AI_ENABLED",
        "false"
    ).strip().lower()
    in ("true", "1", "yes", "on")
)


# Safety: only allow known modes.

if DEFAULT_MODE not in (
    "rag",
    "direct"
):

    DEFAULT_MODE = "rag"


# If Direct AI is disabled,
# RAG must always be the effective default.

if (
    DEFAULT_MODE == "direct"
    and not DIRECT_AI_ENABLED
):

    DEFAULT_MODE = "rag"


CACHE_TTL = 3600


# ---------------------------------------------------------
# STARTUP LOGGING
# ---------------------------------------------------------

print(
    "Noxora configuration:"
)

print(
    f"AWS_REGION={AWS_REGION}"
)

print(
    f"DEFAULT_MODE={DEFAULT_MODE}"
)

print(
    f"DIRECT_AI_ENABLED={DIRECT_AI_ENABLED}"
)


# ---------------------------------------------------------
# AWS CLIENTS
# ---------------------------------------------------------

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)


history_table = dynamodb.Table(
    DYNAMODB_TABLE
)


redis_client = redis.Redis(
    host=REDIS_ENDPOINT,
    port=6379,
    ssl=True,
    decode_responses=True
)


bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=AWS_REGION
)


bedrock_agent_client = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION
)


# ---------------------------------------------------------
# CORS RESPONSE
# ---------------------------------------------------------

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
            json.dumps(body)

    }


# ---------------------------------------------------------
# REDIS CACHE
# ---------------------------------------------------------

def get_cache_key(
    question: str
):

    normalized_question = (
        question
        .strip()
        .lower()
    )


    question_hash = hashlib.sha256(
        normalized_question.encode(
            "utf-8"
        )
    ).hexdigest()


    return (
        f"qa:{question_hash}"
    )


def get_cached_answer(
    question: str
):

    try:

        cache_key = get_cache_key(
            question
        )


        cached_data = (
            redis_client.get(
                cache_key
            )
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
    question: str,
    result: dict
):

    try:

        cache_key = get_cache_key(
            question
        )


        redis_client.set(
            cache_key,
            json.dumps(result),
            ex=CACHE_TTL
        )


        print(
            f"Cached answer with key: {cache_key}"
        )


    except Exception as e:

        print(
            f"Redis SET error: {str(e)}"
        )


# ---------------------------------------------------------
# BEDROCK RAG
# ---------------------------------------------------------

def query_knowledge_base(
    question: str
):

    try:

        # -------------------------------------------------
        # CHECK REDIS
        # -------------------------------------------------

        cached_result = (
            get_cached_answer(
                question
            )
        )


        if cached_result:

            print(
                "CACHE HIT"
            )


            cached_result["cache"] = (
                "hit"
            )


            cached_result["mode"] = (
                "rag"
            )


            return cached_result


        print(
            "CACHE MISS"
        )


        # -------------------------------------------------
        # KNOWLEDGE BASE RETRIEVAL
        # -------------------------------------------------

        response = (
            bedrock_agent_client.retrieve(

                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                retrievalQuery={
                    "text":
                        question
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
                .get(
                    "content",
                    {}
                )
                .get(
                    "text",
                    ""
                )
            )


            source = (
                result
                .get(
                    "location",
                    {}
                )
                .get(
                    "s3Location",
                    {}
                )
                .get(
                    "uri",
                    "Unknown"
                )
            )


            contexts.append({

                "text":
                    text,

                "source":
                    source

            })


        # -------------------------------------------------
        # COMBINE CONTEXT
        # -------------------------------------------------

        context_text = "\n\n".join(

            [
                context["text"]
                for context in contexts
            ]

        )


        # -------------------------------------------------
        # CLAUDE PROMPT
        # -------------------------------------------------

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


        # -------------------------------------------------
        # CALL CLAUDE
        # -------------------------------------------------

        response_claude = (
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
        )


        response_body = json.loads(

            response_claude[
                "body"
            ].read()

        )


        answer = (
            response_body[
                "content"
            ][0]["text"]
        )


        result = {

            "answer":
                answer,

            "citations":
                contexts,

            "cache":
                "miss",

            "mode":
                "rag"

        }


        # -------------------------------------------------
        # SAVE TO REDIS
        # -------------------------------------------------

        cache_answer(
            question,
            result
        )


        return result


    except ClientError as e:

        error_code = (
            e.response[
                "Error"
            ]["Code"]
        )


        error_message = str(e)


        print(
            f"Bedrock error: "
            f"{error_code} - "
            f"{error_message}"
        )


        return {

            "answer":
                (
                    f"Error: "
                    f"{error_code} - "
                    f"{error_message}"
                ),

            "citations":
                [],

            "cache":
                "error",

            "mode":
                "rag"

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
                "error",

            "mode":
                "rag"

        }


# ---------------------------------------------------------
# DIRECT CLAUDE
# ---------------------------------------------------------

def query_claude_directly(
    question: str
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

        response = (
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
        )


        response_body = json.loads(

            response[
                "body"
            ].read()

        )


        return (
            response_body[
                "content"
            ][0]["text"]
        )


    except ClientError as e:

        return (
            f"Error calling Claude: "
            f"{str(e)}"
        )


    except Exception as e:

        return (
            f"Error calling Claude: "
            f"{str(e)}"
        )


# ---------------------------------------------------------
# DYNAMODB QUERY HISTORY
# ---------------------------------------------------------

def save_query_history(
    question,
    answer,
    mode,
    citations
):

    history_table.put_item(

        Item={

            "query_id":
                str(
                    uuid.uuid4()
                ),

            "timestamp":
                (
                    datetime
                    .now(
                        timezone.utc
                    )
                    .isoformat()
                ),

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

        print(
            "Fetching query history..."
        )


        response = (
            history_table.scan(
                Limit=20
            )
        )


        items = response.get(
            "Items",
            []
        )


        # Newest first

        items.sort(

            key=lambda x:
                x.get(
                    "timestamp",
                    ""
                ),

            reverse=True

        )


        print(
            "History records found: "
            f"{len(items)}"
        )


        return cors_response(

            200,

            {
                "history":
                    items
            }

        )


    except ClientError as e:

        error_code = (
            e.response[
                "Error"
            ]["Code"]
        )


        error_message = str(e)


        print(
            "DynamoDB history error: "
            f"{error_code} - "
            f"{error_message}"
        )


        return cors_response(

            500,

            {
                "error":
                    error_message
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


# ---------------------------------------------------------
# DETERMINE EFFECTIVE MODE
# ---------------------------------------------------------

def get_effective_mode(
    requested_mode
):

    requested_mode = (
        str(
            requested_mode or ""
        )
        .strip()
        .lower()
    )


    # Unknown mode -> default

    if requested_mode not in (
        "rag",
        "direct"
    ):

        requested_mode = (
            DEFAULT_MODE
        )


    # Direct AI disabled -> force RAG

    if (
        requested_mode == "direct"
        and not DIRECT_AI_ENABLED
    ):

        print(
            "Direct AI requested but disabled. "
            "Forcing RAG mode."
        )


        return "rag"


    return requested_mode


# ---------------------------------------------------------
# LAMBDA HANDLER
# ---------------------------------------------------------

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


    # -----------------------------------------------------
    # OPTIONS / CORS
    # -----------------------------------------------------

    if (
        event.get(
            "httpMethod"
        ) == "OPTIONS"
    ):

        return cors_response(

            200,

            {
                "message":
                    "CORS preflight successful"
            }

        )


    # -----------------------------------------------------
    # GET /query/history
    # -----------------------------------------------------

    if (
        event.get(
            "httpMethod"
        ) == "GET"
    ):

        return get_query_history()


    # -----------------------------------------------------
    # PROCESS REQUEST BODY
    # -----------------------------------------------------

    if (
        "body" in event
        and event["body"] is not None
    ):

        body = event["body"]


        if isinstance(
            body,
            str
        ):

            try:

                body = json.loads(
                    body
                )


            except json.JSONDecodeError:

                return cors_response(

                    400,

                    {
                        "error":
                            "Invalid JSON body"
                    }

                )


        if body is not None:

            event = body


    # -----------------------------------------------------
    # QUESTION VALIDATION
    # -----------------------------------------------------

    if (
        "question"
        not in event
    ):

        return cors_response(

            400,

            {
                "error":
                    "Missing required field: question"
            }

        )


question = event["question"]


    if not isinstance(
        question,
        str
    ):

        return cors_response(

            400,

            {
                "error":
                    "Question must be a string"
            }

        )


    if not question.strip():

        return cors_response(

            400,

            {
                "error":
                    "Question cannot be empty"
            }

        )


    # -----------------------------------------------------
    # REQUESTED MODE
    # -----------------------------------------------------

    requested_mode = (
        event.get(
            "mode",
            DEFAULT_MODE
        )
    )


    # -----------------------------------------------------
    # EFFECTIVE MODE
    # -----------------------------------------------------

    mode = get_effective_mode(
        requested_mode
    )


    print(
        f"Requested mode: "
        f"{requested_mode}"
    )


    print(
        f"Effective mode: "
        f"{mode}"
    )


    # -----------------------------------------------------
    # RAG MODE
    # -----------------------------------------------------

    if mode == "rag":

        result = (
            query_knowledge_base(
                question
            )
        )


        save_query_history(

            question=
                question,

            answer=
                result["answer"],

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
                    result["answer"],

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


    # -----------------------------------------------------
    # DIRECT MODE
    # -----------------------------------------------------

    if mode == "direct":

        answer = (
            query_claude_directly(
                question
            )
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


    # -----------------------------------------------------
    # FALLBACK
    # -----------------------------------------------------

    return cors_response(

        500,

        {
            "error":
                "Unable to determine request mode"
        }

    )
