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

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]

KNOWLEDGE_BASE_DATA_SOURCE_ID = os.environ.get(
    "KNOWLEDGE_BASE_DATA_SOURCE_ID",
    "SRASBTFSWJ"
)

MODEL_ID = os.environ["MODEL_ID"]

DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]

REDIS_ENDPOINT = os.environ["REDIS_ENDPOINT"]

UPLOAD_BUCKET = os.environ.get(
    "UPLOAD_BUCKET",
    "bedrock-doc-qa-documents-gopi"
)

DEFAULT_MODE = os.environ.get(
    "DEFAULT_MODE",
    "rag"
).strip().lower()

DIRECT_AI_ENABLED = (
    os.environ.get(
        "DIRECT_AI_ENABLED",
        "true"
    ).strip().lower()
    == "true"
)

CACHE_TTL = int(
    os.environ.get(
        "CACHE_TTL",
        "3600"
    )
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024

MAX_RAG_RESULTS = int(
    os.environ.get(
        "MAX_RAG_RESULTS",
        "5"
    )
)


# ============================================================
# AWS CLIENTS
# ============================================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

dynamodb_table = dynamodb.Table(
    DYNAMODB_TABLE
)

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)

bedrock_runtime_client = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION
)

bedrock_agent_runtime_client = boto3.client(
    "bedrock-agent-runtime",
    region_name=AWS_REGION
)

bedrock_agent_client = boto3.client(
    "bedrock-agent",
    region_name=AWS_REGION
)


# ============================================================
# REDIS
# ============================================================

redis_client = None

try:
    redis_client = redis.Redis(
        host=REDIS_ENDPOINT,
        port=6379,
        ssl=True,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )

    redis_client.ping()

    logger.info(
        "Redis connection successful: %s",
        REDIS_ENDPOINT
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
# DECIMAL CONVERSION
# ============================================================

def convert_floats_to_decimal(value):
    """
    DynamoDB does not support Python float.

    Convert all floats recursively to Decimal.
    """

    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: convert_floats_to_decimal(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            convert_floats_to_decimal(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            convert_floats_to_decimal(item)
            for item in value
        ]

    return value


# ============================================================
# CACHE HELPERS
# ============================================================

def normalize_question(question):
    return " ".join(
        question.strip().lower().split()
    )


def create_cache_key(question, mode):
    normalized = normalize_question(question)

    question_hash = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()

    return f"qa:{mode}:{question_hash}"


def get_cached_result(question, mode):

    if redis_client is None:
        return None

    try:
        cache_key = create_cache_key(
            question,
            mode
        )

        cached = redis_client.get(
            cache_key
        )

        if not cached:
            return None

        logger.info(
            "Cache HIT: %s",
            cache_key
        )

        return json.loads(cached)

    except Exception as e:

        logger.warning(
            "Redis GET failed: %s",
            str(e)
        )

        return None


def set_cached_result(
    question,
    mode,
    result
):

    if redis_client is None:
        return

    try:

        cache_key = create_cache_key(
            question,
            mode
        )

        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(
                result,
                default=str
            )
        )

        logger.info(
            "Cache SET: %s",
            cache_key
        )

    except Exception as e:

        logger.warning(
            "Redis SET failed: %s",
            str(e)
        )


def clear_rag_cache():

    if redis_client is None:
        return

    try:

        pattern = "qa:rag:*"

        deleted = 0

        for key in redis_client.scan_iter(
            match=pattern,
            count=100
        ):

            redis_client.delete(key)

            deleted += 1

        logger.info(
            "Cleared RAG cache entries: %s",
            deleted
        )

    except Exception as e:

        logger.warning(
            "Failed to clear RAG cache: %s",
            str(e)
        )


# ============================================================
# DYNAMODB HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    sources,
    cached=False
):

    try:

        item = {
            "query_id": str(
                uuid.uuid4()
            ),

            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),

            "question": question,

            "answer": answer,

            "mode": mode,

            "cached": cached,

            "sources": sources or []
        }

        # IMPORTANT:
        # Bedrock relevance scores are floats.
        # DynamoDB requires Decimal.

        item = convert_floats_to_decimal(
            item
        )

        dynamodb_table.put_item(
            Item=item
        )

        logger.info(
            "History saved successfully"
        )

    except Exception as e:

        # Do NOT fail a successful AI request
        # just because history failed.

        logger.exception(
            "Failed to save history: %s",
            str(e)
        )


def get_history(limit=50):

    try:

        result = dynamodb_table.scan(
            Limit=limit
        )

        items = result.get(
            "Items",
            []
        )

        items.sort(
            key=lambda x: x.get(
                "timestamp",
                ""
            ),
            reverse=True
        )

        return items[:limit]

    except Exception as e:

        logger.exception(
            "Failed to retrieve history: %s",
            str(e)
        )

        return []


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def extract_source_info(result):

    content = result.get(
        "content",
        {}
    )

    text = content.get(
        "text",
        ""
    )

    score = result.get(
        "score"
    )

    location = result.get(
        "location",
        {}
    )

    source_uri = ""

    if isinstance(
        location,
        dict
    ):

        s3_location = location.get(
            "s3Location"
        )

        if isinstance(
            s3_location,
            dict
        ):

            source_uri = s3_location.get(
                "uri",
                ""
            )

        if not source_uri:

            web_location = location.get(
                "webLocation"
            )

            if isinstance(
                web_location,
                dict
            ):

                source_uri = web_location.get(
                    "url",
                    ""
                )

    return {
        "text": text,
        "score": score,
        "uri": source_uri
    }


# ============================================================
# RAG QUERY
# ============================================================

def query_knowledge_base(question):

    logger.info(
        "=========================================="
    )

    logger.info(
        "Running Managed Knowledge Base RAG"
    )

    logger.info(
        "Question: %s",
        question
    )

    logger.info(
        "Knowledge Base ID: %s",
        KNOWLEDGE_BASE_ID
    )

    logger.info(
        "Data Source ID: %s",
        KNOWLEDGE_BASE_DATA_SOURCE_ID
    )

    logger.info(
        "Model ID: %s",
        MODEL_ID
    )

    logger.info(
        "=========================================="
    )

    try:

        # ----------------------------------------------------
        # RETRIEVE
        # ----------------------------------------------------

        retrieve_response = (
            bedrock_agent_runtime_client.retrieve(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,

                retrievalQuery={
                    "text": question
                },

                retrievalConfiguration={
                    "managedSearchConfiguration": {
                        "numberOfResults": MAX_RAG_RESULTS
                    }
                }
            )
        )

        retrieval_results = (
            retrieve_response.get(
                "retrievalResults",
                []
            )
        )

        logger.info(
            "Retrieved chunks: %s",
            len(retrieval_results)
        )

        # ----------------------------------------------------
        # DETAILED RETRIEVAL DEBUG
        # ----------------------------------------------------

        sources = []

        context_parts = []

        for index, result in enumerate(
            retrieval_results,
            start=1
        ):

            source_info = extract_source_info(
                result
            )

            text = source_info["text"]

            score = source_info["score"]

            uri = source_info["uri"]

            logger.info(
                "========== RESULT %s ==========",
                index
            )

            logger.info(
                "Score: %s",
                score
            )

            logger.info(
                "URI: %s",
                uri
            )

            logger.info(
                "Text length: %s",
                len(text)
            )

            logger.info(
                "Text preview: %s",
                text[:500]
            )

            if text:

                context_parts.append(
                    text
                )

            sources.append({
                "name": (
                    uri.split("/")[-1]
                    if uri
                    else f"Source {index}"
                ),

                "uri": uri,

                "score": score
            })

        # ----------------------------------------------------
        # NO RESULTS
        # ----------------------------------------------------

        if not retrieval_results:

            logger.warning(
                "Knowledge Base returned ZERO chunks"
            )

            return {
                "answer": (
                    "I could not find relevant "
                    "information in the uploaded "
                    "documents."
                ),

                "sources": []
            }

        # ----------------------------------------------------
        # NO TEXT
        # ----------------------------------------------------

        if not context_parts:

            logger.warning(
                "Retrieved results contained no text"
            )

            return {
                "answer": (
                    "I found matching sources, "
                    "but could not extract text "
                    "from them."
                ),

                "sources": sources
            }

        # ----------------------------------------------------
        # BUILD CONTEXT
        # ----------------------------------------------------

        context = "\n\n--- SOURCE CHUNK ---\n\n".join(
            context_parts
        )

        # Avoid excessively large prompts.

        max_context_chars = 30000

        if len(context) > max_context_chars:

            context = context[
                :max_context_chars
            ]

        # ----------------------------------------------------
        # PROMPT
        # ----------------------------------------------------

        prompt = f"""
You are answering a question using ONLY
the information contained in the provided
document context.

Do not use outside knowledge.

If the answer cannot be found in the
context, clearly say that the information
is not available in the uploaded documents.

Be accurate and concise.

DOCUMENT CONTEXT:
-----------------

{context}

-----------------

QUESTION:
{question}

ANSWER:
"""

        # ----------------------------------------------------
        # CLAUDE REQUEST
        # ----------------------------------------------------

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",

            "max_tokens": 1000,

            "temperature": 0.2,

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

        logger.info(
            "Calling Bedrock model..."
        )

        model_response = (
            bedrock_runtime_client.invoke_model(
                modelId=MODEL_ID,

                body=json.dumps(
                    request_body
                ),

                contentType="application/json",

                accept="application/json"
            )
        )

        response_body = json.loads(
            model_response["body"].read()
        )

        # ----------------------------------------------------
        # EXTRACT CLAUDE RESPONSE
        # ----------------------------------------------------

        answer = ""

        content = response_body.get(
            "content",
            []
        )

        for block in content:

            if (
                isinstance(block, dict)
                and block.get("type") == "text"
            ):

                answer += block.get(
                    "text",
                    ""
                )

        answer = answer.strip()

        if not answer:

            answer = (
                "The AI model returned "
                "an empty response."
            )

        logger.info(
            "RAG answer generated successfully"
        )

        return {
            "answer": answer,

            "sources": sources
        }

    except Exception as e:

        logger.exception(
            "Knowledge Base query failed: %s",
            str(e)
        )

        raise


# ============================================================
# DIRECT AI QUERY
# ============================================================

def query_direct_ai(question):

    logger.info(
        "Running Direct AI mode"
    )

    logger.info(
        "Question: %s",
        question
    )

    prompt = f"""
Answer the following question clearly
and accurately.

Question:
{question}
"""

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",

        "max_tokens": 1000,

        "temperature": 0.3,

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

    model_response = (
        bedrock_runtime_client.invoke_model(
            modelId=MODEL_ID,

            body=json.dumps(
                request_body
            ),

            contentType="application/json",

            accept="application/json"
        )
    )

    response_body = json.loads(
        model_response["body"].read()
    )

    answer = ""

    for block in response_body.get(
        "content",
        []
    ):

        if (
            isinstance(block, dict)
            and block.get("type") == "text"
        ):

            answer += block.get(
                "text",
                ""
            )

    answer = answer.strip()

    if not answer:

        answer = (
            "The AI model returned "
            "an empty response."
        )

    return {
        "answer": answer,
        "sources": []
    }


# ============================================================
# MODE RESOLUTION
# ============================================================

def resolve_mode(mode):

    mode = (
        mode or DEFAULT_MODE
    ).strip().lower()

    if mode not in (
        "rag",
        "direct"
    ):

        mode = DEFAULT_MODE

    if (
        mode == "direct"
        and not DIRECT_AI_ENABLED
    ):

        logger.info(
            "Direct AI disabled. "
            "Falling back to RAG."
        )

        mode = "rag"

    return mode


# ============================================================
# QUERY HANDLER
# ============================================================

def handle_query(body):

    question = (
        body.get(
            "question",
            ""
        )
        if isinstance(body, dict)
        else ""
    )

    question = question.strip()

    if not question:

        return response(
            400,
            {
                "error": "Question is required"
            }
        )

    requested_mode = (
        body.get(
            "mode",
            DEFAULT_MODE
        )
        if isinstance(body, dict)
        else DEFAULT_MODE
    )

    mode = resolve_mode(
        requested_mode
    )

    logger.info(
        "Query mode: %s",
        mode
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cached_result = get_cached_result(
        question,
        mode
    )

    if cached_result:

        result = {
            "question": question,

            "answer": cached_result.get(
                "answer",
                ""
            ),

            "mode": mode,

            "sources": cached_result.get(
                "sources",
                []
            ),

            "cached": True
        }

        # Save history even for cache hits.

        save_history(
            question=question,

            answer=result["answer"],

            mode=mode,

            sources=result["sources"],

            cached=True
        )

        return response(
            200,
            result
        )

    # --------------------------------------------------------
    # EXECUTE QUERY
    # --------------------------------------------------------

    try:

        if mode == "rag":

            result_data = query_knowledge_base(
                question
            )

        else:

            result_data = query_direct_ai(
                question
            )

    except Exception as e:

        logger.exception(
            "Question processing failed"
        )

        return response(
            500,
            {
                "error": (
                    "Question processing failed"
                ),

                "details": str(e)
            }
        )

    answer = result_data.get(
        "answer",
        ""
    )

    sources = result_data.get(
        "sources",
        []
    )

    result = {
        "question": question,

        "answer": answer,

        "mode": mode,

        "sources": sources,

        "cached": False
    }

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    set_cached_result(
        question,
        mode,
        {
            "answer": answer,
            "sources": sources
        }
    )

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    save_history(
        question=question,

        answer=answer,

        mode=mode,

        sources=sources,

        cached=False
    )

    return response(
        200,
        result
    )


# ============================================================
# CREATE PRESIGNED UPLOAD URL
# ============================================================

def create_upload_url(body):

    filename = (
        body.get(
            "filename",
            ""
        )
        if isinstance(body, dict)
        else ""
    )

    content_type = (
        body.get(
            "contentType",
            "application/pdf"
        )
        if isinstance(body, dict)
        else "application/pdf"
    )

    file_size = (
        body.get(
            "fileSize",
            0
        )
        if isinstance(body, dict)
        else 0
    )

    filename = filename.strip()

    if not filename:

        return response(
            400,
            {
                "error": "Filename is required"
            }
        )

    if not filename.lower().endswith(
        ".pdf"
    ):

        return response(
            400,
            {
                "error": "Only PDF files are supported"
            }
        )

    try:

        file_size = int(
            file_size or 0
        )

    except Exception:

        file_size = 0

    if file_size <= 0:

        return response(
            400,
            {
                "error": "Invalid file size"
            }
        )

    if file_size > MAX_UPLOAD_SIZE:

        return response(
            400,
            {
                "error": (
                    "File exceeds the 10 MB limit"
                )
            }
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # NO uploads/ PREFIX
    # --------------------------------------------------------

    unique_name = (
        f"{uuid.uuid4()}-{filename}"
    )

    s3_key = unique_name

    logger.info(
        "Creating presigned URL"
    )

    logger.info(
        "Bucket: %s",
        UPLOAD_BUCKET
    )

    logger.info(
        "Key: %s",
        s3_key
    )

    try:

        upload_url = (
            s3_client.generate_presigned_url(
                ClientMethod="put_object",

                Params={
                    "Bucket": UPLOAD_BUCKET,

                    "Key": s3_key,

                    "ContentType": "application/pdf"
                },

                ExpiresIn=900
            )
        )

        return response(
            200,
            {
                "success": True,

                "uploadUrl": upload_url,

                "key": s3_key,

                "filename": filename,

                "bucket": UPLOAD_BUCKET,

                "expiresIn": 900
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to create upload URL"
        )

        return response(
            500,
            {
                "error": (
                    "Failed to create upload URL"
                ),

                "details": str(e)
            }
        )


# ============================================================
# COMPLETE UPLOAD + START INGESTION
# ============================================================

def complete_upload(body):

    key = (
        body.get(
            "key",
            ""
        )
        if isinstance(body, dict)
        else ""
    )

    filename = (
        body.get(
            "filename",
            ""
        )
        if isinstance(body, dict)
        else ""
    )

    key = key.strip()

    if not key:

        return response(
            400,
            {
                "error": "S3 key is required"
            }
        )

    # --------------------------------------------------------
    # SECURITY
    # --------------------------------------------------------
    #
    # We deliberately DO NOT require uploads/.
    #
    # Only allow a simple object key and prevent:
    #   ../
    #   absolute paths
    #
    # --------------------------------------------------------

    if (
        ".." in key
        or key.startswith("/")
        or key.endswith("/")
    ):

        return response(
            400,
            {
                "error": "Invalid S3 key"
            }
        )

    logger.info(
        "=========================================="
    )

    logger.info(
        "COMPLETING PDF UPLOAD"
    )

    logger.info(
        "Bucket: %s",
        UPLOAD_BUCKET
    )

    logger.info(
        "Key: %s",
        key
    )

    logger.info(
        "Filename: %s",
        filename
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # VERIFY S3 OBJECT
    # --------------------------------------------------------

    try:

        head = s3_client.head_object(
            Bucket=UPLOAD_BUCKET,
            Key=key
        )

    except Exception as e:

        logger.exception(
            "S3 object verification failed"
        )

        return response(
            400,
            {
                "error": (
                    "Uploaded PDF was not found "
                    "in S3"
                ),

                "details": str(e)
            }
        )

    content_length = head.get(
        "ContentLength",
        0
    )

    content_type = head.get(
        "ContentType",
        ""
    )

    logger.info(
        "S3 ContentLength: %s",
        content_length
    )

    logger.info(
        "S3 ContentType: %s",
        content_type
    )

    # --------------------------------------------------------
    # VALIDATE SIZE
    # --------------------------------------------------------

    if content_length <= 0:

        return response(
            400,
            {
                "error": (
                    "Uploaded PDF is empty"
                )
            }
        )

    if content_length > MAX_UPLOAD_SIZE:

        return response(
            400,
            {
                "error": (
                    "Uploaded PDF exceeds "
                    "10 MB limit"
                )
            }
        )

    # --------------------------------------------------------
    # START INGESTION
    # --------------------------------------------------------

    try:

        logger.info(
            "Starting Knowledge Base ingestion..."
        )

        logger.info(
            "Knowledge Base ID: %s",
            KNOWLEDGE_BASE_ID
        )

        logger.info(
            "Data Source ID: %s",
            KNOWLEDGE_BASE_DATA_SOURCE_ID
        )

        ingestion_response = (
            bedrock_agent_client.start_ingestion_job(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,

                dataSourceId=(
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
                ),

                description=(
                    f"Sync PDF: "
                    f"{filename or key}"
                )
            )
        )

        ingestion_job = (
            ingestion_response[
                "ingestionJob"
            ]
        )

        ingestion_job_id = (
            ingestion_job[
                "ingestionJobId"
            ]
        )

        ingestion_status = (
            ingestion_job.get(
                "status"
            )
        )

        logger.info(
            "=========================================="
        )

        logger.info(
            "INGESTION STARTED"
        )

        logger.info(
            "Job ID: %s",
            ingestion_job_id
        )

        logger.info(
            "Status: %s",
            ingestion_status
        )

        logger.info(
            "=========================================="
        )

        # Clear old RAG answers because a new
        # document has entered the ingestion pipeline.

        clear_rag_cache()

        return response(
            200,
            {
                "success": True,

                "message": (
                    "PDF uploaded successfully. "
                    "Knowledge Base ingestion started."
                ),

                "bucket": UPLOAD_BUCKET,

                "key": key,

                "filename": filename,

                "ingestionJobId": ingestion_job_id,

                "status": ingestion_status
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to start Knowledge Base ingestion"
        )

        return response(
            500,
            {
                "error": (
                    "PDF uploaded to S3, but "
                    "Knowledge Base ingestion "
                    "could not be started."
                ),

                "details": str(e),

                "bucket": UPLOAD_BUCKET,

                "key": key
            }
        )


# ============================================================
# INGESTION STATUS
# ============================================================

def get_upload_status(body):

    ingestion_job_id = (
        body.get(
            "ingestionJobId",
            ""
        )
        if isinstance(body, dict)
        else ""
    )

    ingestion_job_id = (
        ingestion_job_id.strip()
    )

    if not ingestion_job_id:

        return response(
            400,
            {
                "error": (
                    "ingestionJobId is required"
                )
            }
        )

    try:

        logger.info(
            "Checking ingestion job: %s",
            ingestion_job_id
        )

        result = (
            bedrock_agent_client.get_ingestion_job(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,

                dataSourceId=(
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
                ),

                ingestionJobId=ingestion_job_id
            )
        )

        job = result[
            "ingestionJob"
        ]

        status = job.get(
            "status"
        )

        statistics = job.get(
            "statistics",
            {}
        )

        failure_reasons = job.get(
            "failureReasons",
            []
        )

        logger.info(
            "=========================================="
        )

        logger.info(
            "INGESTION STATUS"
        )

        logger.info(
            "Job ID: %s",
            ingestion_job_id
        )

        logger.info(
            "Status: %s",
            status
        )

        logger.info(
            "Statistics: %s",
            json.dumps(
                statistics,
                default=str
            )
        )

        if failure_reasons:

            logger.error(
                "Failure reasons: %s",
                json.dumps(
                    failure_reasons,
                    default=str
                )
            )

        logger.info(
            "=========================================="
        )

        started_at = job.get(
            "startedAt"
        )

        updated_at = job.get(
            "updatedAt"
        )

        return response(
            200,
            {
                "success": True,

                "ingestionJobId": (
                    ingestion_job_id
                ),

                "status": status,

                "startedAt": (
                    started_at.isoformat()
                    if started_at
                    else None
                ),

                "updatedAt": (
                    updated_at.isoformat()
                    if updated_at
                    else None
                ),

                "statistics": statistics,

                "failureReasons": (
                    failure_reasons
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
                "error": (
                    "Failed to get ingestion status"
                ),

                "details": str(e)
            }
        )


# ============================================================
# KNOWLEDGE BASE INFO / DEBUG
# ============================================================

def get_data_source_info():

    try:

        result = (
            bedrock_agent_client.get_data_source(
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
            "Failed to get data source"
        )

        return response(
            500,
            {
                "error": (
                    "Failed to get data source"
                ),

                "details": str(e)
            }
        )


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    logger.info(
        "=========================================="
    )

    logger.info(
        "Lambda request received"
    )

    logger.info(
        "HTTP method: %s",
        event.get(
            "requestContext",
            {}
        ).get(
            "http",
            {}
        ).get(
            "method"
        )
    )

    logger.info(
        "Path: %s",
        event.get(
            "rawPath"
        )
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # HTTP METHOD
    # --------------------------------------------------------

    request_context = event.get(
        "requestContext",
        {}
    )

    http = request_context.get(
        "http",
        {}
    )

    method = (
        http.get(
            "method"
        )
        or event.get(
            "httpMethod",
            ""
        )
    ).upper()

    path = (
        event.get(
            "rawPath"
        )
        or event.get(
            "path",
            ""
        )
    )

    # --------------------------------------------------------
    # CORS
    # --------------------------------------------------------

    if method == "OPTIONS":

        return response(
            200,
            {
                "success": True
            }
        )

    # --------------------------------------------------------
    # PARSE BODY
    # --------------------------------------------------------

    body = event.get(
        "body"
    )

    if body:

        try:

            if event.get(
                "isBase64Encoded",
                False
            ):

                import base64

                body = base64.b64decode(
                    body
                ).decode(
                    "utf-8"
                )

            body = json.loads(
                body
            )

        except Exception as e:

            logger.warning(
                "Invalid JSON body: %s",
                str(e)
            )

            return response(
                400,
                {
                    "error": (
                        "Invalid JSON body"
                    )
                }
            )

    else:

        body = {}

    # ========================================================
    # ROUTING
    # ========================================================

    try:

        # ----------------------------------------------------
        # HISTORY
        # ----------------------------------------------------

        if (
            method == "GET"
            and (
                path.endswith(
                    "/history"
                )
                or path == "/history"
            )
        ):

            history = get_history()

            return response(
                200,
                {
                    "success": True,

                    "items": history,

                    "count": len(history)
                }
            )

        # ----------------------------------------------------
        # CREATE UPLOAD URL
        # ----------------------------------------------------

        if (
            method == "POST"
            and (
                path.endswith(
                    "/upload"
                )
                or path == "/upload"
            )
        ):

            return create_upload_url(
                body
            )

        # ----------------------------------------------------
        # COMPLETE UPLOAD
        # ----------------------------------------------------

        if (
            method == "POST"
            and (
                path.endswith(
                    "/upload/complete"
                )
                or path == "/upload/complete"
            )
        ):

            return complete_upload(
                body
            )

        # ----------------------------------------------------
        # INGESTION STATUS
        # ----------------------------------------------------

        if (
            method == "POST"
            and (
                path.endswith(
                    "/upload/status"
                )
                or path == "/upload/status"
            )
        ):

            return get_upload_status(
                body
            )

        # ----------------------------------------------------
        # DATA SOURCE DEBUG
        # ----------------------------------------------------

        if (
            method == "GET"
            and (
                path.endswith(
                    "/upload/data-source"
                )
                or path == "/upload/data-source"
            )
        ):

            return get_data_source_info()

        # ----------------------------------------------------
        # QUERY
        # ----------------------------------------------------

        if (
            method == "POST"
            and (
                path.endswith(
                    "/query"
                )
                or path == "/query"
            )
        ):

            return handle_query(
                body
            )

        # ----------------------------------------------------
        # UNKNOWN ROUTE
        # ----------------------------------------------------

        return response(
            404,
            {
                "error": "Route not found",

                "method": method,

                "path": path
            }
        )

    except Exception as e:

        logger.exception(
            "Unhandled Lambda error"
        )

        return response(
            500,
            {
                "error": (
                    "Internal server error"
                ),

                "details": str(e)
            }
        )
