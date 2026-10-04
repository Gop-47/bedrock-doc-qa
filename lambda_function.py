import os
import json
import uuid
import hashlib
import logging
from decimal import Decimal
from datetime import datetime, timezone

import boto3
import redis


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

AWS_REGION = os.environ.get(
    "AWS_REGION",
    "us-east-1"
)

KNOWLEDGE_BASE_ID = os.environ.get(
    "KNOWLEDGE_BASE_ID",
    "PPJG45JPD3"
)

KNOWLEDGE_BASE_DATA_SOURCE_ID = os.environ.get(
    "KNOWLEDGE_BASE_DATA_SOURCE_ID",
    "SRASBTFSWJ"
)

MODEL_ID = os.environ.get(
    "MODEL_ID",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)

DYNAMODB_TABLE = os.environ.get(
    "DYNAMODB_TABLE",
    "bedrock-qa-history"
)

REDIS_ENDPOINT = os.environ.get(
    "REDIS_ENDPOINT",
    ""
)

UPLOAD_BUCKET = os.environ.get(
    "UPLOAD_BUCKET",
    "bedrock-doc-qa-documents-gopi"
)

DEFAULT_MODE = os.environ.get(
    "DEFAULT_MODE",
    "rag"
)

DIRECT_AI_ENABLED = (
    os.environ.get(
        "DIRECT_AI_ENABLED",
        "true"
    ).lower()
    == "true"
)

CACHE_TTL = int(
    os.environ.get(
        "CACHE_TTL",
        "3600"
    )
)

MAX_UPLOAD_SIZE = int(
    os.environ.get(
        "MAX_UPLOAD_SIZE",
        str(10 * 1024 * 1024)
    )
)

MAX_RAG_RESULTS = int(
    os.environ.get(
        "MAX_RAG_RESULTS",
        "5"
    )
)


# ============================================================
# CORS
# ============================================================

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": (
        "Content-Type,X-Amz-Date,Authorization,"
        "X-Api-Key,X-Amz-Security-Token"
    ),
    "Access-Control-Allow-Methods": (
        "GET,POST,OPTIONS"
    ),
    "Content-Type": "application/json"
}


# ============================================================
# AWS CLIENTS
# ============================================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

table = dynamodb.Table(
    DYNAMODB_TABLE
)

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION
)

bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=AWS_REGION
)

# NOTE:
# bedrock-agent client is no longer required here for
# upload ingestion.
#
# The NEW Lambda handles StartIngestionJob.


# ============================================================
# REDIS
# ============================================================

redis_client = None

if REDIS_ENDPOINT:

    try:

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
# RESPONSE HELPER
# ============================================================

def response(status_code, body):

    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(
            body,
            default=str
        )
    }


# ============================================================
# HISTORY
# ============================================================

def get_history():

    try:

        items = []

        scan_kwargs = {}

        while True:

            result = table.scan(
                **scan_kwargs
            )

            items.extend(
                result.get(
                    "Items",
                    []
                )
            )

            last_key = result.get(
                "LastEvaluatedKey"
            )

            if not last_key:
                break

            scan_kwargs[
                "ExclusiveStartKey"
            ] = last_key

        # Newest first
        items.sort(
            key=lambda x: str(
                x.get(
                    "timestamp",
                    ""
                )
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
            "Failed to get history"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def extract_source_info(result):

    content = result.get(
        "content",
        {}
    )

    location = result.get(
        "location",
        {}
    )

    text_content = content.get(
        "text",
        ""
    )

    score = result.get(
        "score"
    )

    source = "Unknown"

    s3_location = location.get(
        "s3Location"
    )

    web_location = location.get(
        "webLocation"
    )

    if s3_location:

        source = s3_location.get(
            "uri",
            "Unknown"
        )

    elif web_location:

        source = web_location.get(
            "url",
            "Unknown"
        )

    return {
        "text": text_content,
        "score": score,
        "source": source
    }


# ============================================================
# CLAUDE INVOCATION
# ============================================================

def invoke_claude(prompt):

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    logger.info(
        "Invoking Bedrock model: %s",
        MODEL_ID
    )

    result = bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )

    response_body = json.loads(
        result["body"].read()
    )

    content = response_body.get(
        "content",
        []
    )

    if not content:

        raise ValueError(
            "Bedrock returned empty response"
        )

    return content[0].get(
        "text",
        ""
    )


# ============================================================
# KNOWLEDGE BASE RETRIEVAL
# ============================================================

def query_knowledge_base(question):

    logger.info(
        "Querying Knowledge Base: %s",
        question
    )

    result = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalConfiguration={
            "managedSearchConfiguration": {
                "numberOfResults": MAX_RAG_RESULTS
            }
        },
        retrievalQuery={
            "text": question
        }
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
# CACHE HELPERS
# ============================================================

def create_cache_key(question, mode):

    raw_key = (
        f"{mode}:"
        f"{question.strip().lower()}"
    )

    return (
        "qa:"
        + hashlib.sha256(
            raw_key.encode("utf-8")
        ).hexdigest()
    )


def get_cached_answer(cache_key):

    if not redis_client:
        return None

    try:

        cached = redis_client.get(
            cache_key
        )

        if cached:

            logger.info(
                "Cache hit: %s",
                cache_key
            )

            return json.loads(
                cached
            )

    except Exception as e:

        logger.warning(
            "Redis GET failed: %s",
            str(e)
        )

    return None


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
            "Cache stored: %s",
            cache_key
        )

    except Exception as e:

        logger.warning(
            "Redis SET failed: %s",
            str(e)
        )


def clear_rag_cache():

    if not redis_client:
        return

    try:

        keys = redis_client.keys(
            "qa:*"
        )

        if keys:

            redis_client.delete(
                *keys
            )

            logger.info(
                "Cleared %d cached answers",
                len(keys)
            )

    except Exception as e:

        logger.warning(
            "Failed to clear Redis cache: %s",
            str(e)
        )


# ============================================================
# SAVE HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    sources=None,
    cached=False
):

    try:

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        query_id = str(
            uuid.uuid4()
        )

        item = {
            "query_id": query_id,
            "timestamp": timestamp,
            "question": question,
            "answer": answer,
            "mode": mode,
            "cached": cached
        }

        if sources is not None:

            item["sources"] = sources

        table.put_item(
            Item=item
        )

        logger.info(
            "History saved: %s",
            query_id
        )

    except Exception as e:

        logger.warning(
            "Failed to save history: %s",
            str(e)
        )


# ============================================================
# QUERY HANDLER
# ============================================================

def handle_query(body):

    question = body.get(
        "question",
        ""
    ).strip()

    mode = body.get(
        "mode",
        DEFAULT_MODE
    ).lower()

    if not question:

        return response(
            400,
            {
                "success": False,
                "error": "Question is required"
            }
        )

    if mode not in [
        "rag",
        "direct"
    ]:

        mode = DEFAULT_MODE

    if (
        mode == "direct"
        and not DIRECT_AI_ENABLED
    ):

        return response(
            400,
            {
                "success": False,
                "error": "Direct AI mode is disabled"
            }
        )

    # ========================================================
    # CACHE
    # ========================================================

    cache_key = create_cache_key(
        question,
        mode
    )

    cached_data = get_cached_answer(
        cache_key
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

        save_history(
            question,
            answer,
            mode,
            sources,
            cached=True
        )

        return response(
            200,
            {
                "success": True,
                "question": question,
                "answer": answer,
                "mode": mode,
                "sources": sources,
                "cached": True
            }
        )

    # ========================================================
    # DIRECT AI
    # ========================================================

    if mode == "direct":

        prompt = f"""
Answer the following question clearly and accurately.

Question:
{question}
"""

        answer = invoke_claude(
            prompt
        )

        sources = []

    # ========================================================
    # RAG
    # ========================================================

    else:

        retrieval_results = (
            query_knowledge_base(
                question
            )
        )

        sources = [
            extract_source_info(
                item
            )
            for item in retrieval_results
        ]

        context_parts = []

        for item in sources:

            text_content = item.get(
                "text",
                ""
            )

            if text_content:

                context_parts.append(
                    text_content
                )

        context = "\n\n".join(
            context_parts
        )

        if not context:

            answer = (
                "I couldn't find relevant "
                "information in the Knowledge Base."
            )

        else:

            prompt = f"""
You are a helpful AI assistant.

Answer the user's question using ONLY
the provided context.

If the answer cannot be found in the
context, clearly say that the information
is not available in the provided documents.

Context:
{context}

Question:
{question}
"""

            answer = invoke_claude(
                prompt
            )

    # ========================================================
    # CACHE RESULT
    # ========================================================

    cache_data = {
        "answer": answer,
        "sources": sources
    }

    set_cached_answer(
        cache_key,
        cache_data
    )

    # ========================================================
    # SAVE HISTORY
    # ========================================================

    save_history(
        question,
        answer,
        mode,
        sources,
        cached=False
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return response(
        200,
        {
            "success": True,
            "question": question,
            "answer": answer,
            "mode": mode,
            "sources": sources,
            "cached": False
        }
    )


# ============================================================
# CREATE PRESIGNED UPLOAD URL
# ============================================================

def create_upload_url(body):

    filename = body.get(
        "filename",
        ""
    )

    content_type = body.get(
        "contentType",
        ""
    )

    file_size = body.get(
        "fileSize"
    )

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not filename:

        return response(
            400,
            {
                "success": False,
                "error": "Filename is required"
            }
        )

    if not filename.lower().endswith(
        ".pdf"
    ):

        return response(
            400,
            {
                "success": False,
                "error": "Only PDF files are allowed"
            }
        )

    # --------------------------------------------------------
    # Validate content type
    # --------------------------------------------------------

    if content_type != "application/pdf":

        return response(
            400,
            {
                "success": False,
                "error": "Content-Type must be application/pdf"
            }
        )

    # --------------------------------------------------------
    # Validate file size if supplied
    # --------------------------------------------------------

    if file_size is not None:

        try:

            file_size = int(
                file_size
            )

        except (TypeError, ValueError):

            return response(
                400,
                {
                    "success": False,
                    "error": "Invalid file size"
                }
            )

        if file_size <= 0:

            return response(
                400,
                {
                    "success": False,
                    "error": "File is empty"
                }
            )

        if file_size > MAX_UPLOAD_SIZE:

            return response(
                400,
                {
                    "success": False,
                    "error": (
                        "File exceeds the "
                        "10 MB limit"
                    )
                }
            )

    # --------------------------------------------------------
    # Safe filename
    # --------------------------------------------------------

    safe_filename = os.path.basename(
        filename
    )

    # --------------------------------------------------------
    # Unique S3 key
    # --------------------------------------------------------

    key = (
        f"{uuid.uuid4()}-"
        f"{safe_filename}"
    )

    logger.info(
        "Generating presigned upload URL: %s",
        key
    )

    # --------------------------------------------------------
    # Generate presigned URL
    # --------------------------------------------------------

    presigned_url = (
        s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": UPLOAD_BUCKET,
                "Key": key,
                "ContentType": "application/pdf"
            },
            ExpiresIn=900
        )
    )

    return response(
        200,
        {
            "success": True,
            "uploadUrl": presigned_url,
            "key": key,
            "filename": safe_filename,
            "expiresIn": 900
        }
    )


# ============================================================
# COMPLETE UPLOAD
# ============================================================

def complete_upload(body):

    try:

        key = body.get(
            "key"
        )

        filename = body.get(
            "filename"
        )

        if not key:

            return response(
                400,
                {
                    "success": False,
                    "error": "Missing upload key"
                }
            )

        # ----------------------------------------------------
        # Verify object exists in S3
        # ----------------------------------------------------

        logger.info(
            "Checking uploaded S3 object: %s",
            key
        )

        head = s3_client.head_object(
            Bucket=UPLOAD_BUCKET,
            Key=key
        )

        file_size = head.get(
            "ContentLength",
            0
        )

        # ----------------------------------------------------
        # Validate size
        # ----------------------------------------------------

        if file_size <= 0:

            return response(
                400,
                {
                    "success": False,
                    "error": "Uploaded file is empty"
                }
            )

        if file_size > MAX_UPLOAD_SIZE:

            return response(
                400,
                {
                    "success": False,
                    "error": (
                        "File exceeds the "
                        "10 MB limit"
                    )
                }
            )

        logger.info(
            "S3 upload confirmed successfully: "
            "bucket=%s key=%s size=%s",
            UPLOAD_BUCKET,
            key,
            file_size
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # DO NOT START BEDROCK INGESTION HERE.
        #
        # S3 ObjectCreated event will automatically
        # invoke the NEW Knowledge Base Sync Lambda.
        # ----------------------------------------------------

        # Clear cached RAG answers because a new document
        # has been uploaded.
        clear_rag_cache()

        return response(
            200,
            {
                "success": True,
                "message": (
                    "PDF uploaded successfully. "
                    "Knowledge Base synchronization "
                    "will start automatically."
                ),
                "key": key,
                "filename": (
                    filename
                    or os.path.basename(key)
                ),
                "fileSize": file_size,
                "sync": "pending"
            }
        )

    except Exception as e:

        logger.exception(
            "Upload completion failed"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# GET UPLOAD STATUS
# ============================================================

def get_upload_status(body):

    """
    Kept for compatibility with the existing API.

    The old upload Lambda no longer starts ingestion,
    so this endpoint should only be used if an ingestion
    job ID is supplied.

    The actual ingestion job is now created by the NEW
    S3-triggered Lambda.
    """

    ingestion_job_id = body.get(
        "ingestionJobId"
    )

    if not ingestion_job_id:

        return response(
            400,
            {
                "success": False,
                "error": (
                    "ingestionJobId is required. "
                    "Ingestion is started asynchronously "
                    "by the S3-triggered Lambda."
                )
            }
        )

    try:

        # Import the client here because this Lambda
        # no longer needs it for normal upload processing.
        bedrock_agent = boto3.client(
            "bedrock-agent",
            region_name=AWS_REGION
        )

        result = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=KNOWLEDGE_BASE_DATA_SOURCE_ID,
            ingestionJobId=ingestion_job_id
        )

        ingestion_job = result.get(
            "ingestionJob",
            {}
        )

        return response(
            200,
            {
                "success": True,
                "ingestionJobId": ingestion_job_id,
                "status": ingestion_job.get(
                    "status"
                ),
                "statistics": ingestion_job.get(
                    "statistics",
                    {}
                ),
                "failureReasons": ingestion_job.get(
                    "failureReasons",
                    []
                )
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
            region_name=AWS_REGION
        )

        result = (
            bedrock_agent.get_data_source(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                dataSourceId=(
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
                )
            )
        )

        data_source = result.get(
            "dataSource",
            {}
        )

        return response(
            200,
            {
                "success": True,
                "dataSource": data_source
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to get data source info"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# MAIN LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    logger.info(
        "Received event: %s",
        json.dumps(
            event,
            default=str
        )
    )

    try:

        # ====================================================
        # HTTP METHOD
        # ====================================================

        request_context = event.get(
            "requestContext",
            {}
        )

        http_info = request_context.get(
            "http",
            {}
        )

        method = (
            http_info.get("method")
            or event.get(
                "httpMethod"
            )
            or "GET"
        ).upper()

        # ====================================================
        # PATH
        # ====================================================

        path = (
            event.get(
                "rawPath"
            )
            or event.get(
                "path"
            )
            or "/"
        )

        # Remove stage prefix if present
        if path.startswith("/dev/"):

            path = path[4:]

        elif path == "/dev":

            path = "/"

        if not path.startswith("/"):

            path = "/" + path

        logger.info(
            "Request: %s %s",
            method,
            path
        )

        # ====================================================
        # OPTIONS
        # ====================================================

        if method == "OPTIONS":

            return response(
                200,
                {
                    "success": True
                }
            )

        # ====================================================
        # REQUEST BODY
        # ====================================================

        body = event.get(
            "body"
        )

        if body:

            if isinstance(
                body,
                str
            ):

                try:

                    body = json.loads(
                        body
                    )

                except json.JSONDecodeError:

                    return response(
                        400,
                        {
                            "success": False,
                            "error": (
                                "Invalid JSON body"
                            )
                        }
                    )

        elif isinstance(
            body,
            dict
        ):

            body = body

        else:

            body = {}

        # ====================================================
        # POST /query
        # ====================================================

        if (
            method == "POST"
            and path == "/query"
        ):

            return handle_query(
                body
            )

        # ====================================================
        # GET /query/history
        # ====================================================

        if (
            method == "GET"
            and path == "/query/history"
        ):

            return get_history()

        # ====================================================
        # POST /upload
        # ====================================================

        if (
            method == "POST"
            and path == "/upload"
        ):

            action = body.get(
                "action"
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
                    "error": (
                        "Invalid upload action. "
                        "Use create, complete, or status."
                    )
                }
            )

        # ====================================================
        # GET /upload/data-source
        # ====================================================

        if (
            method == "GET"
            and path == "/upload/data-source"
        ):

            return get_data_source_info()

        # ====================================================
        # NOT FOUND
        # ====================================================

        return response(
            404,
            {
                "success": False,
                "error": (
                    f"Route not found: "
                    f"{method} {path}"
                )
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
