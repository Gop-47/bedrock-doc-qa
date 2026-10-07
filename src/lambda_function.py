import os
import json
import logging
import uuid
import re
import time
from datetime import datetime, timezone

import boto3

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ============================================================
# ENVIRONMENT
# ============================================================

REGION = os.environ.get(
    "AWS_REGION",
    "us-east-1"
)

KNOWLEDGE_BASE_ID = os.environ.get(
    "KNOWLEDGE_BASE_ID",
    "PPJG45JPD3"
)

DATA_SOURCE_ID = os.environ.get(
    "KNOWLEDGE_BASE_DATA_SOURCE_ID",
    "SRASBTFSWJ"
)

MODEL_ID = os.environ.get(
    "MODEL_ID",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)

UPLOAD_BUCKET = os.environ.get(
    "UPLOAD_BUCKET",
    "bedrock-doc-qa-documents-gopi"
)

DYNAMODB_TABLE = os.environ.get(
    "DYNAMODB_TABLE",
    "bedrock-qa-history"
)

REDIS_ENDPOINT = os.environ.get(
    "REDIS_ENDPOINT"
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024

MAX_RAG_RESULTS = int(
    os.environ.get(
        "MAX_RAG_RESULTS",
        "5"
    )
)

CACHE_TTL = int(
    os.environ.get(
        "CACHE_TTL",
        "3600"
    )
)

# ============================================================
# AWS CLIENTS
# ============================================================

s3_client = boto3.client(
    "s3",
    region_name=REGION
)

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=REGION
)

bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=REGION
)

dynamodb = boto3.resource(
    "dynamodb",
    region_name=REGION
)

history_table = dynamodb.Table(
    DYNAMODB_TABLE
)

# ============================================================
# REDIS
# ============================================================

redis_client = None

if REDIS_ENDPOINT:
    try:
        import redis

        redis_client = redis.Redis(
            host=REDIS_ENDPOINT,
            port=6379,
            ssl=True,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2
        )

        redis_client.ping()

        logger.info(
            "Redis connection successful"
        )

    except Exception as e:
        logger.warning(
            "Redis unavailable: %s",
            str(e)
        )

        redis_client = None

# ============================================================
# CORS
# ============================================================

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers":
        "Content-Type,Authorization",
    "Access-Control-Allow-Methods":
        "OPTIONS,GET,POST,PUT"
}

# ============================================================
# RESPONSE
# ============================================================

def response(
    status_code,
    body
):
    return {
        "statusCode": status_code,
        "headers": {
            **CORS_HEADERS,
            "Content-Type": "application/json"
        },
        "body": json.dumps(
            body,
            default=str
        )
    }

# ============================================================
# HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    cached=False,
    sources=None
):
    try:
        query_id = str(
            uuid.uuid4()
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        item = {
            "query_id": query_id,
            "timestamp": timestamp,
            "question": question,
            "answer": answer,
            "mode": mode,
            "cached": cached,
            "sources": sources or []
        }

        history_table.put_item(
            Item=item
        )

        logger.info(
            "History saved: %s",
            query_id
        )

    except Exception as e:
        # History failure must NOT break
        # a successful question response.
        logger.exception(
            "Failed to save history: %s",
            str(e)
        )

# ============================================================
# GET HISTORY
# ============================================================

def get_history():
    try:

        result = history_table.scan()

        items = result.get(
            "Items",
            []
        )

        # Handle pagination
        while "LastEvaluatedKey" in result:

            result = history_table.scan(
                ExclusiveStartKey=
                    result["LastEvaluatedKey"]
            )

            items.extend(
                result.get(
                    "Items",
                    []
                )
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

        return response(
            200,
            {
                "success": True,
                "history": items
            }
        )

    except Exception as e:

        logger.exception(
            "History error"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )

# ============================================================
# SOURCE INFORMATION
# ============================================================

def extract_source_info(
    citation
):
    try:

        location = (
            citation
            .get("location", {})
        )

        s3_location = (
            location
            .get("s3Location", {})
        )

        uri = s3_location.get(
            "uri"
        )

        metadata = citation.get(
            "metadata",
            {}
        )

        score = citation.get(
            "score"
        )

        return {
            "source": uri,
            "score": score,
            "metadata": metadata
        }

    except Exception as e:

        logger.warning(
            "Unable to extract source: %s",
            str(e)
        )

        return {
            "source": None,
            "score": None,
            "metadata": {}
        }

# ============================================================
# CLAUDE INVOCATION
# ============================================================

def invoke_claude(
    prompt
):
    logger.info(
        "Invoking Bedrock model: %s",
        MODEL_ID
    )

    start_time = time.time()

    body = {
        "anthropic_version":
            "bedrock-2023-05-31",

        "max_tokens":
            1000,

        "temperature":
            0.2,

        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    result = bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )

    elapsed = (
        time.time() -
        start_time
    )

    logger.info(
        "Claude invocation completed in %.2f seconds",
        elapsed
    )

    response_body = json.loads(
        result["body"].read()
    )

    content = response_body.get(
        "content",
        []
    )

    if not content:
        return ""

    text_parts = []

    for item in content:

        if item.get("type") == "text":

            text_parts.append(
                item.get(
                    "text",
                    ""
                )
            )

    return "\n".join(
        text_parts
    ).strip()

# ============================================================
# KNOWLEDGE BASE RETRIEVAL
# ============================================================

def query_knowledge_base(
    question
):
    logger.info(
        "Starting Knowledge Base retrieval"
    )

    start_time = time.time()

    result = (
        bedrock_agent_runtime
        .retrieve(
            knowledgeBaseId=
                KNOWLEDGE_BASE_ID,

            retrievalConfiguration={
                "managedSearchConfiguration": {
                    "numberOfResults":
                        MAX_RAG_RESULTS
                }
            },

            retrievalQuery={
                "text": question
            }
        )
    )

    elapsed = (
        time.time() -
        start_time
    )

    logger.info(
        "Knowledge Base retrieval completed in %.2f seconds",
        elapsed
    )

    results = result.get(
        "retrievalResults",
        []
    )

    logger.info(
        "Knowledge Base returned %d results",
        len(results)
    )

    return results

# ============================================================
# CACHE KEY
# ============================================================

def create_cache_key(
    question,
    mode
):
    normalized = (
        question
        .strip()
        .lower()
    )

    return (
        f"bedrock-qa:"
        f"{mode}:"
        f"{normalized}"
    )

# ============================================================
# CACHE GET
# ============================================================

def get_cached_answer(
    cache_key
):
    if not redis_client:
        return None

    try:

        value = redis_client.get(
            cache_key
        )

        if not value:
            return None

        logger.info(
            "Redis cache HIT"
        )

        return json.loads(
            value
        )

    except Exception as e:

        logger.warning(
            "Redis GET failed: %s",
            str(e)
        )

        return None

# ============================================================
# CACHE SET
# ============================================================

def set_cached_answer(
    cache_key,
    data
):
    if not redis_client:
        return

    try:

        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(
                data,
                default=str
            )
        )

        logger.info(
            "Redis cache SET"
        )

    except Exception as e:

        logger.warning(
            "Redis SET failed: %s",
            str(e)
        )

# ============================================================
# CLEAR CACHE
# ============================================================

def clear_rag_cache():
    if not redis_client:
        return

    try:

        keys = redis_client.keys(
            "bedrock-qa:rag:*"
        )

        if keys:

            redis_client.delete(
                *keys
            )

            logger.info(
                "Cleared %d RAG cache entries",
                len(keys)
            )

    except Exception as e:

        logger.warning(
            "Failed to clear RAG cache: %s",
            str(e)
        )

# ============================================================
# RAG QUESTION
# ============================================================

def handle_rag_question(
    question
):
    cache_key = create_cache_key(
        question,
        "rag"
    )

    cached_data = (
        get_cached_answer(
            cache_key
        )
    )

    if cached_data:

        answer = cached_data.get(
            "answer",
            ""
        )

        sources = cached_data.get(
            "sources",
            []
        )

        return {
            "answer": answer,
            "sources": sources,
            "cached": True
        }

    retrieval_results = (
        query_knowledge_base(
            question
        )
    )

    if not retrieval_results:

        answer = (
            "I couldn't find relevant "
            "information in the Knowledge Base."
        )

        result = {
            "answer": answer,
            "sources": [],
            "cached": False
        }

        save_history(
            question,
            answer,
            "rag",
            False,
            []
        )

        return result

    # --------------------------------------------------------
    # Build context
    # --------------------------------------------------------

    context_parts = []
    sources = []

    for index, item in enumerate(
        retrieval_results
    ):

        text_content = (
            item.get(
                "content",
                {}
            )
            .get(
                "text",
                ""
            )
        )

        if text_content:

            context_parts.append(
                f"[Context {index + 1}]\n"
                f"{text_content}"
            )

        source_info = (
            extract_source_info(
                item
            )
        )

        if source_info.get(
            "source"
        ):

            sources.append(
                source_info
            )

    context = "\n\n".join(
        context_parts
    )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are a helpful document question-answering assistant.

Answer the user's question using ONLY the information
provided in the Knowledge Base context below.

If the answer cannot be determined from the context,
say that the information was not found in the documents.

Do not invent facts.

Be clear and concise.

Knowledge Base Context:
-----------------------
{context}
-----------------------

User Question:
{question}
"""

    answer = invoke_claude(
        prompt
    )

    if not answer:

        answer = (
            "I couldn't generate an answer "
            "from the Knowledge Base."
        )

    result = {
        "answer": answer,
        "sources": sources,
        "cached": False
    }

    set_cached_answer(
        cache_key,
        result
    )

    save_history(
        question,
        answer,
        "rag",
        False,
        sources
    )

    return result

# ============================================================
# DIRECT QUESTION
# ============================================================

def handle_direct_question(
    question
):
    cache_key = create_cache_key(
        question,
        "direct"
    )

    cached_data = (
        get_cached_answer(
            cache_key
        )
    )

    if cached_data:

        answer = cached_data.get(
            "answer",
            ""
        )

        return {
            "answer": answer,
            "sources": [],
            "cached": True
        }

    prompt = f"""
You are a helpful AI assistant.

Answer the following question accurately
and clearly.

Question:
{question}
"""

    answer = invoke_claude(
        prompt
    )

    result = {
        "answer": answer,
        "sources": [],
        "cached": False
    }

    set_cached_answer(
        cache_key,
        result
    )

    save_history(
        question,
        answer,
        "direct",
        False,
        []
    )

    return result

# ============================================================
# QUERY
# ============================================================

def handle_query(
    body
):
    question = (
        body.get(
            "question",
            ""
        )
        .strip()
    )

    mode = (
        body.get(
            "mode",
            "rag"
        )
        .strip()
        .lower()
    )

    if not question:

        return response(
            400,
            {
                "success": False,
                "error":
                    "Question is required."
            }
        )

    if mode not in (
        "rag",
        "direct"
    ):

        mode = "rag"

    logger.info(
        "Question received: %s",
        question
    )

    logger.info(
        "Question mode: %s",
        mode
    )

    start_time = time.time()
