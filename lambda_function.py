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
# HTTP RESPONSE
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
# DECIMAL CONVERSION FOR DYNAMODB
# ============================================================

def convert_floats_to_decimal(value):

    if isinstance(value, float):

        return Decimal(
            str(value)
        )

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

    return value


# ============================================================
# REDIS CACHE HELPERS
# ============================================================

def get_cache_key(
    question,
    mode
):

    raw_key = (
        f"{mode}:{question.strip().lower()}"
    )

    return (
        "qa:"
        + hashlib.sha256(
            raw_key.encode("utf-8")
        ).hexdigest()
    )


def get_cached_answer(
    question,
    mode
):

    if redis_client is None:
        return None

    try:

        key = get_cache_key(
            question,
            mode
        )

        cached = redis_client.get(
            key
        )

        if cached:

            logger.info(
                "Cache HIT"
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
    question,
    mode,
    data
):

    if redis_client is None:
        return

    try:

        key = get_cache_key(
            question,
            mode
        )

        redis_client.setex(
            key,
            CACHE_TTL,
            json.dumps(
                data,
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


def clear_rag_cache():

    if redis_client is None:
        return

    try:

        keys = redis_client.keys(
            "qa:rag:*"
        )

        if keys:

            redis_client.delete(
                *keys
            )

            logger.info(
                "Cleared %s RAG cache entries",
                len(keys)
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
    cached=False,
    sources=None
):

    try:

        table = dynamodb.Table(
            DYNAMODB_TABLE
        )

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

        table.put_item(
            Item=convert_floats_to_decimal(
                item
            )
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


def get_history():

    try:

        table = dynamodb.Table(
            DYNAMODB_TABLE
        )

        result = table.scan()

        items = result.get(
            "Items",
            []
        )

        # Handle pagination
        while "LastEvaluatedKey" in result:

            result = table.scan(
                ExclusiveStartKey=
                result["LastEvaluatedKey"]
            )

            items.extend(
                result.get(
                    "Items",
                    []
                )
            )

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
            "Failed to retrieve history"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# BEDROCK SOURCE EXTRACTION
# ============================================================

def extract_source_info(
    result
):

    try:

        content = result.get(
            "content",
            {}
        )

        text_content = content.get(
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

        s3_location = location.get(
            "s3Location",
            {}
        )

        web_location = location.get(
            "webLocation",
            {}
        )

        s3_uri = s3_location.get(
            "uri"
        )

        web_url = web_location.get(
            "url"
        )

        source = {

            "text": text_content,

            "score": score,

            "source": (
                s3_uri
                or web_url
                or "Unknown"
            )
        }

        return source

    except Exception as e:

        logger.warning(
            "Failed to extract source: %s",
            str(e)
        )

        return {
            "text": "",
            "score": None,
            "source": "Unknown"
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

    request_body = {

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

        body=json.dumps(
            request_body
        ),

        contentType=
            "application/json",

        accept=
            "application/json"
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
# DIRECT AI QUERY
# ============================================================

def query_direct_ai(
    question
):

    prompt = f"""
You are a helpful AI assistant.

Answer the user's question accurately
and clearly.

If you are uncertain, say so.

User question:
{question}
"""

    answer = invoke_claude(
        prompt
    )

    return {
        "answer": answer,
        "sources": []
    }


# ============================================================
# KNOWLEDGE BASE QUERY
# ============================================================

def query_knowledge_base(
    question
):

    logger.info(
        "Querying Knowledge Base: %s",
        KNOWLEDGE_BASE_ID
    )

    # IMPORTANT:
    # Managed Knowledge Bases require
    # managedSearchConfiguration.
    #
    # vectorSearchConfiguration is NOT supported
    # for managed Knowledge Bases.

    retrieve_response = (
        bedrock_agent_runtime.retrieve(

            knowledgeBaseId=
                KNOWLEDGE_BASE_ID,

            retrievalQuery={
                "text": question
            },

            retrievalConfiguration={

                "managedSearchConfiguration": {

                    "numberOfResults":
                        MAX_RAG_RESULTS
                }
            }
        )
    )

    results = retrieve_response.get(
        "retrievalResults",
        []
    )

    logger.info(
        "Retrieved %s documents",
        len(results)
    )

    sources = []

    context_parts = []

    for result in results:

        source = extract_source_info(
            result
        )

        sources.append(
            source
        )

        text_content = source.get(
            "text",
            ""
        )

        if text_content:

            context_parts.append(
                text_content
            )

    if not context_parts:

        return {
            "answer": (
                "I couldn't find relevant "
                "information in the uploaded "
                "documents."
            ),
            "sources": sources
        }

    context = "\n\n---\n\n".join(
        context_parts
    )

    prompt = f"""
You are a document question-answering
assistant.

Answer the user's question using ONLY
the information contained in the provided
context.

If the answer cannot be found in the
context, clearly say that the information
is not available in the uploaded documents.

Do not invent information.

Keep the answer clear and concise.

Context:
{context}

User question:
{question}
"""

    answer = invoke_claude(
        prompt
    )

    return {
        "answer": answer,
        "sources": sources
    }


# ============================================================
# QUERY HANDLER
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

    mode = str(
        body.get(
            "mode",
            DEFAULT_MODE
        )
    ).strip().lower()

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

        return response(
            400,
            {
                "success": False,
                "error":
                    "Invalid mode. "
                    "Use 'rag' or 'direct'."
            }
        )

    if (
        mode == "direct"
        and not DIRECT_AI_ENABLED
    ):

        return response(
            403,
            {
                "success": False,
                "error":
                    "Direct AI mode is disabled."
            }
        )

    # ========================================================
    # CACHE CHECK
    # ========================================================

    cached_data = get_cached_answer(
        question,
        mode
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

    # ========================================================
    # GENERATE ANSWER
    # ========================================================

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

        # ====================================================
        # CACHE RESULT
        # ====================================================

        cache_data = {
            "answer": answer,
            "sources": sources
        }

        set_cached_answer(
            question,
            mode,
            cache_data
        )

        # ====================================================
        # SAVE HISTORY
        # ====================================================

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

    if content_type != (
        "application/pdf"
    ):

        return response(
            400,
            {
                "success": False,
                "error":
                    "Content type must be "
                    "application/pdf."
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
                        "File size must be greater than zero."
                }
            )

        if file_size > MAX_UPLOAD_SIZE:

            return response(
                400,
                {
                    "success": False,
                    "error":
                        f"File exceeds maximum "
                        f"size of "
                        f"{MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                }
            )

    # Generate a unique root-level S3 key
    safe_filename = os.path.basename(
        filename
    )

    key = (
        f"{uuid.uuid4()}-"
        f"{safe_filename}"
    )

    try:

        presigned_url = (
            s3_client.generate_presigned_url(

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

        logger.info(
            "Generated presigned URL for: %s",
            key
        )

        return response(
            200,
            {
                "success": True,

                "uploadUrl":
                    presigned_url,

                "key":
                    key,

                "filename":
                    safe_filename,

                "expiresIn":
                    900
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to generate upload URL"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )


# ============================================================
# COMPLETE UPLOAD + START BEDROCK INGESTION
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
                "error":
                    "S3 key is required."
            }
        )

    # ========================================================
    # VERIFY S3 OBJECT
    # ========================================================

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
                    "error":
                        "Uploaded file is empty."
                }
            )

        if file_size > MAX_UPLOAD_SIZE:

            return response(
                400,
                {
                    "success": False,
                    "error":
                        "Uploaded file exceeds "
                        "maximum allowed size."
                }
            )

        logger.info(
            "Verified uploaded object: "
            "s3://%s/%s (%s bytes)",
            UPLOAD_BUCKET,
            key,
            file_size
        )

    except Exception as e:

        logger.exception(
            "S3 object verification failed"
        )

        return response(
            400,
            {
                "success": False,
                "error":
                    "Uploaded file could not "
                    "be verified: "
                    + str(e)
            }
        )

    # ========================================================
    # START BEDROCK INGESTION
    # ========================================================

    try:

        logger.info(
            "Starting Knowledge Base ingestion..."
        )

        ingestion_response = (
            bedrock_agent.start_ingestion_job(

                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
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
            "status"
        )

        logger.info(
            "Ingestion job started: "
            "%s | status=%s",
            ingestion_job_id,
            status
        )

        # New document means existing RAG
        # cache entries may now be stale.
        clear_rag_cache()

        # IMPORTANT:
        #
        # We DO NOT wait for ingestion here.
        #
        # start_ingestion_job() starts an asynchronous
        # Bedrock ingestion process. Lambda can return
        # immediately while Bedrock continues processing
        # the document in the background.

        return response(
            200,
            {
                "success": True,

                "message":
                    "PDF uploaded successfully. "
                    "Knowledge Base synchronization "
                    "started in the background.",

                "key":
                    key,

                "filename":
                    filename
                    or os.path.basename(key),

                "ingestionJobId":
                    ingestion_job_id,

                "status":
                    status,

                "fileSize":
                    file_size
            }
        )

    except Exception as e:

        logger.exception(
            "Failed to start ingestion job"
        )

        return response(
            500,
            {
                "success": False,
                "error":
                    "PDF uploaded, but Knowledge "
                    "Base ingestion could not be started: "
                    + str(e)
            }
        )


# ============================================================
# GET INGESTION STATUS
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
                "error":
                    "ingestionJobId is required."
            }
        )

    try:

        result = (
            bedrock_agent.get_ingestion_job(

                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    KNOWLEDGE_BASE_DATA_SOURCE_ID,

                ingestionJobId=
                    ingestion_job_id
            )
        )

        ingestion_job = (
            result.get(
                "ingestionJob",
                {}
            )
        )

        status = ingestion_job.get(
            "status"
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

                "ingestionJobId":
                    ingestion_job_id,

                "status":
                    status,

                "statistics":
                    statistics,

                "failureReasons":
                    failure_reasons
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
# DATA SOURCE INFORMATION
# ============================================================

def get_data_source_info():

    try:

        result = (
            bedrock_agent.get_data_source(

                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
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

    try:

        # ====================================================
        # HTTP METHOD
        # ====================================================

        http_method = (
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
        )

        # ====================================================
        # PATH
        # ====================================================

        path = event.get(
            "path"
        )

        if not path:

            path = (
                event.get(
                    "requestContext",
                    {}
                )
                .get(
                    "http",
                    {}
                )
                .get(
                    "path",
                    ""
                )
            )

        # API Gateway sometimes sends
        # stage-prefixed paths.
        #
        # Example:
        # /dev/query
        #
        # Normalize them.

        if path.startswith(
            "/dev/"
        ):

            path = path[
                len("/dev") :
            ]

        logger.info(
            "HTTP method=%s path=%s",
            http_method,
            path
        )

        # ====================================================
        # CORS PREFLIGHT
        # ====================================================

        if http_method == "OPTIONS":

            return response(
                200,
                {
                    "success": True
                }
            )

        # ====================================================
        # PARSE BODY
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
                            "error":
                                "Request body "
                                "must contain valid JSON."
                        }
                    )

        elif isinstance(
            body,
            dict
        ):

            pass

        else:

            body = {}

        # ====================================================
        # POST /query
        # ====================================================

        if (
            http_method == "POST"
            and path == "/query"
        ):

            return handle_query(
                body
            )

        # ====================================================
        # GET /query/history
        # ====================================================

        if (
            http_method == "GET"
            and path == "/query/history"
        ):

            return get_history()

        # ====================================================
        # POST /upload
        # ====================================================

        if (
            http_method == "POST"
            and path == "/upload"
        ):

            action = str(
                body.get(
                    "action",
                    ""
                )
            ).strip().lower()

            # -----------------------------------------------
            # CREATE PRESIGNED URL
            # -----------------------------------------------

            if action in (
                "create",
                "presigned_url",
                "start"
            ):

                return create_upload_url(
                    body
                )

            # -----------------------------------------------
            # COMPLETE UPLOAD
            # -----------------------------------------------

            if action in (
                "complete",
                "finish"
            ):

                return complete_upload(
                    body
                )

            # -----------------------------------------------
            # CHECK INGESTION STATUS
            # -----------------------------------------------

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

                    "error":
                        "Invalid upload action.",

                    "supportedActions": [
                        "create",
                        "complete",
                        "status"
                    ]
                }
            )

        # ====================================================
        # GET /upload/data-source
        # ====================================================

        if (
            http_method == "GET"
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
                "error":
                    f"Route not found: "
                    f"{http_method} {path}"
            }
        )

    except Exception as e:

        logger.exception(
            "Unhandled Lambda exception"
        )

        return response(
            500,
            {
                "success": False,
                "error": str(e)
            }
        )
