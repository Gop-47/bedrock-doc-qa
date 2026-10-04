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
                "vectorSearchConfiguration": {
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

    try:

        if mode == "rag":

            result = (
                handle_rag_question(
                    question
                )
            )

        else:

            result = (
                handle_direct_question(
                    question
                )
            )

        elapsed = (
            time.time() -
            start_time
        )

        logger.info(
            "Question completed in %.2f seconds",
            elapsed
        )

        return response(
            200,
            {
                "success": True,
                "question": question,
                "answer":
                    result.get(
                        "answer",
                        ""
                    ),
                "mode": mode,
                "cached":
                    result.get(
                        "cached",
                        False
                    ),
                "sources":
                    result.get(
                        "sources",
                        []
                    )
            }
        )

    except Exception as e:

        logger.exception(
            "Question processing failed"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )

# ============================================================
# CREATE UPLOAD URL
# ============================================================

def create_upload_url(
    body
):
    filename = (
        body.get(
            "filename",
            ""
        )
        .strip()
    )

    content_type = (
        body.get(
            "contentType",
            "application/pdf"
        )
        .strip()
        .lower()
    )

    file_size = body.get(
        "fileSize"
    )

    if not filename:

        return response(
            400,
            {
                "success": False,
                "error":
                    "Filename is required."
            }
        )

    if not filename.lower().endswith(
        ".pdf"
    ):

        return response(
            400,
            {
                "success": False,
                "error":
                    "Only PDF files are allowed."
            }
        )

    if content_type != "application/pdf":

        return response(
            400,
            {
                "success": False,
                "error":
                    "Content-Type must be application/pdf."
            }
        )

    if file_size is not None:

        try:

            file_size = int(
                file_size
            )

        except Exception:

            return response(
                400,
                {
                    "success": False,
                    "error":
                        "Invalid file size."
                }
            )

        if file_size <= 0:

            return response(
                400,
                {
                    "success": False,
                    "error":
                        "File cannot be empty."
                }
            )

        if file_size > MAX_UPLOAD_SIZE:

            return response(
                400,
                {
                    "success": False,
                    "error":
                        "Maximum file size is 10 MB."
                }
            )

    # --------------------------------------------------------
    # Make filename safe
    # --------------------------------------------------------

    safe_filename = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        filename
    )

    key = (
        f"{uuid.uuid4()}-"
        f"{safe_filename}"
    )

    logger.info(
        "Creating presigned URL for: %s",
        key
    )

    upload_url = (
        s3_client
        .generate_presigned_url(
            ClientMethod="put_object",

            Params={
                "Bucket":
                    UPLOAD_BUCKET,

                "Key":
                    key,

                "ContentType":
                    "application/pdf"
            },

            ExpiresIn=900
        )
    )

    return response(
        200,
        {
            "success": True,
            "uploadUrl": upload_url,
            "key": key,
            "filename": filename,
            "expiresIn": 900
        }
    )

# ============================================================
# COMPLETE UPLOAD
# ============================================================

def complete_upload(
    body
):
    """
    IMPORTANT:

    This function intentionally does NOT call:

        s3_client.head_object()

    The browser already completed the direct S3 PUT.

    The S3 ObjectCreated event independently invokes:

        bedrock-doc-qa-kb-sync

    That Lambda starts the Bedrock Knowledge Base
    ingestion asynchronously.

    Therefore this API must return immediately.
    """

    key = (
        body.get(
            "key",
            ""
        )
        .strip()
    )

    filename = (
        body.get(
            "filename",
            ""
        )
        .strip()
    )

    if not key:

        return response(
            400,
            {
                "success": False,
                "error":
                    "Upload key is required."
            }
        )

    if not key.lower().endswith(
        ".pdf"
    ):

        return response(
            400,
            {
                "success": False,
                "error":
                    "Only PDF uploads are supported."
            }
        )

    logger.info(
        "Upload confirmation received: key=%s filename=%s",
        key,
        filename
    )

    # --------------------------------------------------------
    # DO NOT call head_object here.
    #
    # The S3 PUT already succeeded in the browser.
    #
    # S3 ObjectCreated will trigger the KB sync Lambda.
    # --------------------------------------------------------

    # New PDF means old RAG answers may be stale.
    clear_rag_cache()

    logger.info(
        "Upload confirmation completed immediately."
    )

    logger.info(
        "KB synchronization will happen asynchronously."
    )

    return response(
        200,
        {
            "success": True,

            "message":
                "PDF uploaded successfully. "
                "Knowledge Base synchronization "
                "will start automatically in the background.",

            "key":
                key,

            "filename":
                filename or key.split("/")[-1],

            "sync":
                "pending"
        }
    )

# ============================================================
# OPTIONAL UPLOAD STATUS
# ============================================================

def get_upload_status(
    body
):
    """
    Kept for compatibility.

    The current frontend does NOT need to call this.
    """

    ingestion_job_id = (
        body.get(
            "ingestionJobId"
        )
    )

    if not ingestion_job_id:

        return response(
            400,
            {
                "success": False,
                "error":
                    "ingestionJobId is required."
            }
        )

    try:

        bedrock_agent = boto3.client(
            "bedrock-agent",
            region_name=REGION
        )

        result = (
            bedrock_agent
            .get_ingestion_job(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    DATA_SOURCE_ID,

                ingestionJobId=
                    ingestion_job_id
            )
        )

        job = result.get(
            "ingestionJob",
            {}
        )

        return response(
            200,
            {
                "success": True,
                "status":
                    job.get(
                        "status"
                    ),
                "job":
                    job
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to get ingestion status"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )

# ============================================================
# DATA SOURCE INFO
# ============================================================

def get_data_source_info():
    try:

        bedrock_agent = boto3.client(
            "bedrock-agent",
            region_name=REGION
        )

        result = (
            bedrock_agent
            .get_data_source(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    DATA_SOURCE_ID
            )
        )

        return response(
            200,
            {
                "success": True,
                "dataSource":
                    result.get(
                        "dataSource",
                        {}
                    )
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to get data source"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )

# ============================================================
# MAIN HANDLER
# ============================================================

def lambda_handler(
    event,
    context
):

    logger.info(
        "Lambda event received: %s",
        json.dumps(
            event,
            default=str
        )
    )

    try:

        # ----------------------------------------------------
        # HTTP METHOD
        # ----------------------------------------------------

        http_method = (
            event.get(
                "httpMethod"
            )
            or
            event.get(
                "requestContext",
                {}
            )
            .get(
                "http",
                {}
            )
            .get(
                "method"
            )
            or ""
        ).upper()

        # ----------------------------------------------------
        # OPTIONS / CORS
        # ----------------------------------------------------

        if http_method == "OPTIONS":

            return response(
                200,
                {
                    "success": True
                }
            )

        # ----------------------------------------------------
        # PATH
        # ----------------------------------------------------

        path = (
            event.get(
                "path"
            )
            or
            event.get(
                "rawPath"
            )
            or
            ""
        )

        # ----------------------------------------------------
        # BODY
        # ----------------------------------------------------

        raw_body = event.get(
            "body"
        )

        if raw_body:

            if isinstance(
                raw_body,
                str
            ):

                try:

                    body = json.loads(
                        raw_body
                    )

                except json.JSONDecodeError:

                    return response(
                        400,
                        {
                            "success": False,
                            "error":
                                "Invalid JSON body."
                        }
                    )

            elif isinstance(
                raw_body,
                dict
            ):

                body = raw_body

            else:

                body = {}

        else:

            body = {}

        # ----------------------------------------------------
        # QUERY
        # ----------------------------------------------------

        if (
            path.endswith("/query")
            and
            http_method == "POST"
        ):

            return handle_query(
                body
            )

        # ----------------------------------------------------
        # HISTORY
        # ----------------------------------------------------

        if (
            path.endswith(
                "/query/history"
            )
            and
            http_method == "GET"
        ):

            return get_history()

        # ----------------------------------------------------
        # UPLOAD
        # ----------------------------------------------------

        if (
            path.endswith("/upload")
            and
            http_method == "POST"
        ):

            action = (
                body.get(
                    "action",
                    "create"
                )
                .strip()
                .lower()
            )

            if action == "create":

                return create_upload_url(
                    body
                )

            if action == "complete":

                return complete_upload(
                    body
                )

            if action == "status":

                return get_upload_status(
                    body
                )

            return response(
                400,
                {
                    "success": False,
                    "error":
                        f"Unknown upload action: {action}"
                }
            )

        # ----------------------------------------------------
        # DATA SOURCE
        # ----------------------------------------------------

        if (
            path.endswith(
                "/data-source"
            )
            and
            http_method == "GET"
        ):

            return get_data_source_info()

        # ----------------------------------------------------
        # UNKNOWN ROUTE
        # ----------------------------------------------------

        return response(
            404,
            {
                "success": False,
                "error":
                    "Route not found.",
                "path":
                    path,
                "method":
                    http_method
            }
        )

    except Exception as e:

        logger.exception(
            "Unhandled Lambda error"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )
