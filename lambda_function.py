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
        "Content-Type,"
        "X-Amz-Date,"
        "Authorization,"
        "X-Api-Key,"
        "X-Amz-Security-Token"
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

bedrock_agent = boto3.client(
    "bedrock-agent",
    region_name=AWS_REGION
)


# ============================================================
# DYNAMODB
# ============================================================

table = dynamodb.Table(
    DYNAMODB_TABLE
)


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
            socket_connect_timeout=3,
            socket_timeout=3
        )

        redis_client.ping()

        logger.info(
            "Redis connection successful"
        )

    except Exception as e:

        logger.warning(
            "Redis connection failed: %s",
            str(e)
        )

        redis_client = None


# ============================================================
# RESPONSE HELPER
# ============================================================

def response(
    status_code,
    body
):

    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(
            body,
            default=str
        )
    }


# ============================================================
# DECIMAL HELPER
# ============================================================

def convert_floats_to_decimal(obj):

    if isinstance(
        obj,
        float
    ):

        return Decimal(
            str(obj)
        )

    if isinstance(
        obj,
        dict
    ):

        return {
            key: convert_floats_to_decimal(
                value
            )
            for key, value in obj.items()
        }

    if isinstance(
        obj,
        list
    ):

        return [
            convert_floats_to_decimal(
                item
            )
            for item in obj
        ]

    return obj


# ============================================================
# REDIS CACHE KEY
# ============================================================

def generate_cache_key(
    question,
    mode
):

    normalized_question = (
        question
        .strip()
        .lower()
    )

    raw_key = (
        f"{mode}:"
        f"{normalized_question}"
    )

    return (
        "bedrock:"
        + hashlib.sha256(
            raw_key.encode("utf-8")
        ).hexdigest()
    )


# ============================================================
# REDIS GET
# ============================================================

def get_cached_answer(
    question,
    mode
):

    if not redis_client:
        return None

    try:

        key = generate_cache_key(
            question,
            mode
        )

        cached = redis_client.get(
            key
        )

        if cached:

            logger.info(
                "Cache hit"
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


# ============================================================
# REDIS SET
# ============================================================

def cache_answer(
    question,
    mode,
    result
):

    if not redis_client:
        return

    try:

        key = generate_cache_key(
            question,
            mode
        )

        redis_client.setex(
            key,
            CACHE_TTL,
            json.dumps(
                result,
                default=str
            )
        )

        logger.info(
            "Answer cached"
        )

    except Exception as e:

        logger.warning(
            "Redis SET failed: %s",
            str(e)
        )


# ============================================================
# CLEAR RAG CACHE
# ============================================================

def clear_rag_cache():

    if not redis_client:
        return

    try:

        keys = redis_client.keys(
            "bedrock:rag:*"
        )

        if keys:

            redis_client.delete(
                *keys
            )

            logger.info(
                "Cleared %s RAG cache keys",
                len(keys)
            )

    except Exception as e:

        logger.warning(
            "Could not clear RAG cache: %s",
            str(e)
        )


# ============================================================
# SAVE HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    cached,
    sources
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

        item = convert_floats_to_decimal(
            item
        )

        table.put_item(
            Item=item
        )

        logger.info(
            "History saved: %s",
            query_id
        )

    except Exception as e:

        logger.error(
            "Failed to save history: %s",
            str(e)
        )


# ============================================================
# GET HISTORY
# ============================================================

def get_history():

    try:

        result = table.scan()

        items = result.get(
            "Items",
            []
        )

        while "LastEvaluatedKey" in result:

            result = table.scan(
                ExclusiveStartKey=result[
                    "LastEvaluatedKey"
                ]
            )

            items.extend(
                result.get(
                    "Items",
                    []
                )
            )

        items.sort(
            key=lambda x: x.get(
                "timestamp",
                ""
            ),
            reverse=True
        )

        return response(
            200,
            {
                "success": True,
                "items": items,
                "count": len(items)
            }
        )

    except Exception as e:

        logger.exception(
            "History retrieval failed"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# EXTRACT SOURCE INFO
# ============================================================

def extract_source_info(
    result
):

    try:

        content = result.get(
            "content",
            {}
        )

        text = content.get(
            "text",
            ""
        )

        location = result.get(
            "location",
            {}
        )

        s3_location = location.get(
            "s3Location",
            {}
        )

        web_location = location.get(
            "webLocation",
            {}
        )

        uri = (
            s3_location.get(
                "uri"
            )
            or web_location.get(
                "url"
            )
            or ""
        )

        score = result.get(
            "score"
        )

        return {
            "text": text,
            "score": score,
            "uri": uri
        }

    except Exception as e:

        logger.warning(
            "Source extraction failed: %s",
            str(e)
        )

        return {
            "text": "",
            "score": None,
            "uri": ""
        }


# ============================================================
# INVOKE CLAUDE
# ============================================================

def invoke_claude(
    prompt
):

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1200,
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

    result = bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(
            request_body
        ),
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

        return "No answer generated."

    return content[0].get(
        "text",
        "No answer generated."
    )


# ============================================================
# RAG QUERY
# ============================================================

def query_knowledge_base(
    question
):

    logger.info(
        "Querying Knowledge Base: %s",
        KNOWLEDGE_BASE_ID
    )

    retrieve_response = (
        bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                "text": question
            },
            retrievalConfiguration={
                "vectorSearchConfiguration": {
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
        "Retrieved %s results",
        len(retrieval_results)
    )

    sources = []

    context_parts = []

    for result in retrieval_results:

        source = extract_source_info(
            result
        )

        sources.append(
            source
        )

        text = source.get(
            "text",
            ""
        )

        if text:

            context_parts.append(
                text
            )

    context = "\n\n---\n\n".join(
        context_parts
    )

    if not context:

        return {
            "answer": (
                "I could not find relevant "
                "information in the uploaded "
                "documents."
            ),
            "sources": []
        }

    prompt = f"""
You are a document question-answering assistant.

Answer the user's question using ONLY the
provided document context.

If the answer cannot be found in the context,
clearly say that the information is not available
in the uploaded documents.

Do not invent facts.

Keep the answer clear and concise.

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{question}

ANSWER:
"""

    answer = invoke_claude(
        prompt
    )

    return {
        "answer": answer,
        "sources": sources
    }


# ============================================================
# DIRECT AI QUERY
# ============================================================

def query_direct_ai(
    question
):

    prompt = f"""
You are a helpful AI assistant.

Answer the user's question accurately and clearly.

USER QUESTION:
{question}

ANSWER:
"""

    answer = invoke_claude(
        prompt
    )

    return {
        "answer": answer,
        "sources": []
    }


# ============================================================
# MODE RESOLUTION
# ============================================================

def resolve_mode(
    requested_mode
):

    mode = str(
        requested_mode
        or DEFAULT_MODE
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

        logger.warning(
            "Direct AI disabled, falling back to RAG"
        )

        mode = "rag"

    return mode


# ============================================================
# HANDLE QUERY
# ============================================================

def handle_query(
    body
):

    question = str(
        body.get(
            "question",
            ""
        )
    ).strip()

    if not question:

        return response(
            400,
            {
                "success": False,
                "error": "Question is required"
            }
        )

    mode = resolve_mode(
        body.get(
            "mode"
        )
    )

    logger.info(
        "Question received. mode=%s question=%s",
        mode,
        question
    )

    cached_result = get_cached_answer(
        question,
        mode
    )

    if cached_result:

        answer = cached_result.get(
            "answer",
            ""
        )

        sources = cached_result.get(
            "sources",
            []
        )

        save_history(
            question=question,
            answer=answer,
            mode=mode,
            cached=True,
            sources=sources
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

    try:

        if mode == "rag":

            result = query_knowledge_base(
                question
            )

        else:

            result = query_direct_ai(
                question
            )

        answer = result.get(
            "answer",
            ""
        )

        sources = result.get(
            "sources",
            []
        )

        cache_data = {
            "answer": answer,
            "sources": sources
        }

        cache_answer(
            question,
            mode,
            cache_data
        )

        save_history(
            question=question,
            answer=answer,
            mode=mode,
            cached=False,
            sources=sources
        )

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
# CREATE PRESIGNED UPLOAD URL
# ============================================================

def create_upload_url(
    body
):

    filename = str(
        body.get(
            "filename",
            ""
        )
    ).strip()

    content_type = str(
        body.get(
            "contentType",
            "application/pdf"
        )
    ).strip()

    file_size = body.get(
        "fileSize"
    )

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
                "error": "Only PDF files are supported"
            }
        )

    try:

        file_size = int(
            file_size
        )

    except Exception:

        return response(
            400,
            {
                "success": False,
                "error": "Valid fileSize is required"
            }
        )

    if file_size <= 0:

        return response(
            400,
            {
                "success": False,
                "error": "File size must be greater than zero"
            }
        )

    if file_size > MAX_UPLOAD_SIZE:

        return response(
            400,
            {
                "success": False,
                "error": (
                    "File exceeds the maximum "
                    "allowed size of 10 MB"
                )
            }
        )

    key = (
        f"{uuid.uuid4()}-"
        f"{filename}"
    )

    try:

        upload_url = (
            s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": UPLOAD_BUCKET,
                    "Key": key,
                    "ContentType": content_type
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
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# COMPLETE UPLOAD
# ============================================================

def complete_upload(
    body
):

    key = str(
        body.get(
            "key",
            ""
        )
    ).strip()

    filename = str(
        body.get(
            "filename",
            ""
        )
    ).strip()

    if not key:

        return response(
            400,
            {
                "success": False,
                "error": "Upload key is required"
            }
        )

    try:

        head = s3_client.head_object(
            Bucket=UPLOAD_BUCKET,
            Key=key
        )

        file_size = head.get(
            "ContentLength",
            0
        )

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
                    "error": "Uploaded file exceeds 10 MB"
                }
            )

    except Exception as e:

        logger.exception(
            "Uploaded object not found"
        )

        return response(
            404,
            {
                "success": False,
                "error": (
                    "Uploaded file was not found: "
                    + str(e)
                )
            }
        )

    try:

        ingestion_response = (
            bedrock_agent.start_ingestion_job(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                dataSourceId=KNOWLEDGE_BASE_DATA_SOURCE_ID
            )
        )

        ingestion_job = (
            ingestion_response.get(
                "ingestionJob",
                {}
            )
        )

        ingestion_job_id = (
            ingestion_job.get(
                "ingestionJobId"
            )
        )

        status = ingestion_job.get(
            "status",
            "STARTING"
        )

        clear_rag_cache()

        logger.info(
            "Ingestion started. job=%s status=%s",
            ingestion_job_id,
            status
        )

        return response(
            200,
            {
                "success": True,
                "message": (
                    "Upload completed and "
                    "knowledge base ingestion started"
                ),
                "key": key,
                "filename": filename,
                "ingestionJobId": ingestion_job_id,
                "status": status
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to start ingestion"
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

def get_upload_status(
    body
):

    ingestion_job_id = str(
        body.get(
            "ingestionJobId",
            ""
        )
    ).strip()

    if not ingestion_job_id:

        return response(
            400,
            {
                "success": False,
                "error": (
                    "ingestionJobId is required"
                )
            }
        )

    try:

        result = (
            bedrock_agent.get_ingestion_job(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                dataSourceId=KNOWLEDGE_BASE_DATA_SOURCE_ID,
                ingestionJobId=ingestion_job_id
            )
        )

        ingestion_job = result.get(
            "ingestionJob",
            {}
        )

        statistics = ingestion_job.get(
            "statistics",
            {}
        )

        failure_reasons = ingestion_job.get(
            "failureReasons",
            []
        )

        return response(
            200,
            {
                "success": True,
                "ingestionJobId": ingestion_job_id,
                "status": ingestion_job.get(
                    "status"
                ),
                "statistics": statistics,
                "failureReasons": failure_reasons
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
# DATA SOURCE DEBUG INFO
# ============================================================

def get_data_source_info():

    try:

        result = (
            bedrock_agent.get_data_source(
                knowledgeBaseId=KNOWLEDGE_BASE_ID,
                dataSourceId=KNOWLEDGE_BASE_DATA_SOURCE_ID
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
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# MAIN LAMBDA HANDLER
# ============================================================

def lambda_handler(
    event,
    context
):

    logger.info(
        "Received event: %s",
        json.dumps(
            event,
            default=str
        )
    )

    # --------------------------------------------------------
    # HTTP METHOD
    # --------------------------------------------------------

    method = (
        event.get(
            "httpMethod"
        )
        or event.get(
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
        or "GET"
    ).upper()

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------

    path = (
        event.get(
            "path"
        )
        or event.get(
            "rawPath"
        )
        or event.get(
            "requestContext",
            {}
        )
        .get(
            "resourcePath",
            ""
        )
    )

    path = path.rstrip(
        "/"
    )

    logger.info(
        "Request method=%s path=%s",
        method,
        path
    )

    # --------------------------------------------------------
    # OPTIONS / CORS
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
                        "error": "Invalid JSON body"
                    }
                )

        elif not isinstance(
            body,
            dict
        ):

            body = {}

    else:

        body = {}

    # ========================================================
    # QUERY
    # POST /query
    # ========================================================

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

    # ========================================================
    # QUERY HISTORY
    # GET /query/history
    # ========================================================

    if (
        method == "GET"
        and (
            path.endswith(
                "/query/history"
            )
            or path == "/query/history"
        )
    ):

        return get_history()

    # ========================================================
    # UPLOAD
    #
    # IMPORTANT:
    #
    # API Gateway has ONLY:
    #
    # POST /upload
    #
    # Therefore:
    #
    # create:
    # {
    #     "action": "create",
    #     "filename": "...",
    #     "contentType": "application/pdf",
    #     "fileSize": 123
    # }
    #
    # complete:
    # {
    #     "action": "complete",
    #     "key": "...",
    #     "filename": "..."
    # }
    #
    # status:
    # {
    #     "action": "status",
    #     "ingestionJobId": "..."
    # }
    #
    # ========================================================

    if (
        method == "POST"
        and (
            path.endswith(
                "/upload"
            )
            or path == "/upload"
        )
    ):

        action = str(
            body.get(
                "action",
                "create"
            )
        ).strip().lower()

        logger.info(
            "Upload action: %s",
            action
        )

        # ----------------------------------------------------
        # CREATE PRESIGNED URL
        # ----------------------------------------------------

        if action in (
            "create",
            "presigned_url",
            "start"
        ):

            return create_upload_url(
                body
            )

        # ----------------------------------------------------
        # COMPLETE UPLOAD
        # ----------------------------------------------------

        if action in (
            "complete",
            "finish"
        ):

            return complete_upload(
                body
            )

        # ----------------------------------------------------
        # INGESTION STATUS
        # ----------------------------------------------------

        if action in (
            "status",
            "check_status"
        ):

            return get_upload_status(
                body
            )

        return response(
            400,
            {
                "success": False,
                "error": "Invalid upload action",
                "supportedActions": [
                    "create",
                    "complete",
                    "status"
                ]
            }
        )

    # ========================================================
    # DATA SOURCE DEBUG
    # GET /upload/data-source
    # ========================================================

    if (
        method == "GET"
        and path.endswith(
            "/upload/data-source"
        )
    ):

        return get_data_source_info()

    # ========================================================
    # NOT FOUND
    # ========================================================

    return response(
        404,
        {
            "success": False,
            "error": "Route not found",
            "method": method,
            "path": path
        }
    )
