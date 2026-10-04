import os
import json
import uuid
import hashlib
import time
import re
import boto3
import redis
from botocore.exceptions import ClientError


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
        "false"
    ).strip().lower()
    in ("true", "1", "yes")
)

CACHE_TTL = 3600

MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# ============================================================
# AWS CLIENTS
# ============================================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

history_table = dynamodb.Table(
    DYNAMODB_TABLE
)

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)

# Used for direct Claude invocation
bedrock_runtime_client = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION
)

# Used for RetrieveAndGenerate
bedrock_agent_runtime_client = boto3.client(
    "bedrock-agent-runtime",
    region_name=AWS_REGION
)

# Used for Knowledge Base ingestion
bedrock_agent_client = boto3.client(
    "bedrock-agent",
    region_name=AWS_REGION
)

# IMPORTANT:
# This is the correct client for get_inference_profile()
bedrock_client = boto3.client(
    "bedrock",
    region_name=AWS_REGION
)


# ============================================================
# REDIS / VALKEY
# ============================================================

redis_client = redis.Redis(
    host=REDIS_ENDPOINT,
    port=6379,
    ssl=True,
    decode_responses=True
)


# ============================================================
# CORS
# ============================================================

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": (
        "Content-Type,Authorization,X-Requested-With"
    ),
    "Access-Control-Allow-Methods": (
        "GET,POST,OPTIONS"
    ),
    "Content-Type": "application/json"
}


# ============================================================
# RESPONSE HELPERS
# ============================================================

def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=str)
    }


def parse_body(event):
    """
    Safely parse API Gateway body.

    Handles:
    - POST requests with JSON body
    - Lambda direct invocation
    - base64 encoded body
    """

    body = event.get("body")

    if body is None:
        return {}

    if isinstance(body, dict):
        return body

    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    try:
        return json.loads(body)
    except Exception:
        return {}


# ============================================================
# MODEL / INFERENCE PROFILE
# ============================================================

def get_rag_model_arn():
    """
    Convert MODEL_ID into the modelArn required by
    Bedrock RetrieveAndGenerate.

    Example environment variable:

        MODEL_ID=
        us.anthropic.claude-haiku-4-5-20251001-v1:0

    The "us." prefix means this is an inference profile ID,
    not a normal foundation model ID.

    IMPORTANT:
    get_inference_profile() belongs to the "bedrock" client,
    NOT "bedrock-agent".
    """

    # --------------------------------------------------------
    # Already an ARN
    # --------------------------------------------------------

    if MODEL_ID.startswith("arn:"):
        return MODEL_ID

    # --------------------------------------------------------
    # Cross-region / global inference profile
    # --------------------------------------------------------

    inference_profile_prefixes = (
        "us.",
        "eu.",
        "apac.",
        "au.",
        "jp.",
        "global."
    )

    if MODEL_ID.startswith(inference_profile_prefixes):

        print(
            f"Resolving inference profile: {MODEL_ID}"
        )

        try:
            result = bedrock_client.get_inference_profile(
                inferenceProfileIdentifier=MODEL_ID
            )

            inference_profile_arn = result.get(
                "inferenceProfileArn"
            )

            if not inference_profile_arn:
                raise RuntimeError(
                    "Bedrock returned no inferenceProfileArn "
                    f"for MODEL_ID: {MODEL_ID}"
                )

            print(
                f"Resolved inference profile ARN: "
                f"{inference_profile_arn}"
            )

            return inference_profile_arn

        except ClientError as e:

            print(
                "Failed to resolve inference profile: "
                f"{str(e)}"
            )

            raise RuntimeError(
                "Could not resolve Bedrock inference profile "
                f"for MODEL_ID: {MODEL_ID}. "
                f"Original error: {str(e)}"
            )

    # --------------------------------------------------------
    # Normal foundation model ID
    # --------------------------------------------------------

    model_arn = (
        f"arn:aws:bedrock:"
        f"{AWS_REGION}"
        f"::foundation-model/"
        f"{MODEL_ID}"
    )

    print(
        f"Using foundation model ARN: {model_arn}"
    )

    return model_arn


# ============================================================
# CACHE
# ============================================================

def create_cache_key(mode, question):

    normalized_question = (
        question.strip()
        .lower()
    )

    question_hash = hashlib.sha256(
        normalized_question.encode("utf-8")
    ).hexdigest()

    return f"qa:{mode}:{question_hash}"


def get_cached_answer(mode, question):

    try:

        cache_key = create_cache_key(
            mode,
            question
        )

        cached = redis_client.get(
            cache_key
        )

        if not cached:
            return None

        print(
            f"Cache HIT: {cache_key}"
        )

        return json.loads(cached)

    except Exception as e:

        print(
            f"Redis GET error: {str(e)}"
        )

        return None


def cache_answer(
    mode,
    question,
    answer
):

    try:

        cache_key = create_cache_key(
            mode,
            question
        )

        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(answer)
        )

        print(
            f"Cached answer: {cache_key}"
        )

    except Exception as e:

        print(
            f"Redis SET error: {str(e)}"
        )


# ============================================================
# HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    sources
):

    try:

        query_id = str(
            uuid.uuid4()
        )

        timestamp = int(
            time.time()
        )

        history_table.put_item(
            Item={
                "query_id": query_id,
                "timestamp": timestamp,
                "question": question,
                "answer": answer,
                "mode": mode,
                "sources": sources
            }
        )

        print(
            f"Saved history: {query_id}"
        )

    except Exception as e:

        print(
            f"DynamoDB history error: {str(e)}"
        )


def get_history():

    try:

        result = history_table.scan()

        items = result.get(
            "Items",
            []
        )

        # Newest first
        items.sort(
            key=lambda x: int(
                x.get(
                    "timestamp",
                    0
                )
            ),
            reverse=True
        )

        return items

    except Exception as e:

        print(
            f"DynamoDB history read error: {str(e)}"
        )

        raise


# ============================================================
# RAG QUERY
# ============================================================

def query_knowledge_base(question):

    print(
        f"Running RAG query: {question}"
    )

    model_arn = get_rag_model_arn()

    print(
        f"Knowledge Base ID: {KNOWLEDGE_BASE_ID}"
    )

    print(
        f"Using model ARN: {model_arn}"
    )

    result = (
        bedrock_agent_runtime_client
        .retrieve_and_generate(
            input={
                "text": question
            },
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {

                    "knowledgeBaseId":
                        KNOWLEDGE_BASE_ID,

                    "modelArn":
                        model_arn,

                    "retrievalConfiguration": {

                        "vectorSearchConfiguration": {

                            "numberOfResults": 5

                        }

                    }

                }

            }
        )
    )

    answer = (
        result
        .get("output", {})
        .get("text", "")
    )

    citations = result.get(
        "citations",
        []
    )

    sources = []

    for citation in citations:

        retrieved_references = citation.get(
            "retrievedReferences",
            []
        )

        for reference in retrieved_references:

            location = reference.get(
                "location",
                {}
            )

            s3_location = location.get(
                "s3Location",
                {}
            )

            uri = s3_location.get(
                "uri"
            )

            source_text = (
                reference
                .get("content", {})
                .get("text", "")
            )

            filename = None

            if uri:
                filename = uri.split("/")[-1]

            sources.append(
                {
                    "uri": uri,
                    "filename": filename,
                    "text": source_text
                }
            )

    return {
        "answer": answer,
        "sources": sources
    }


# ============================================================
# DIRECT AI QUERY
# ============================================================

def query_direct_ai(question):

    print(
        f"Running Direct AI query: {question}"
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
                "role":
                    "user",

                "content": [

                    {
                        "type":
                            "text",

                        "text":
                            question
                    }

                ]
            }

        ]

    }

    response_data = (
        bedrock_runtime_client
        .invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                request_body
            )
        )
    )

    body = json.loads(
        response_data["body"].read()
    )

    answer = ""

    content = body.get(
        "content",
        []
    )

    for item in content:

        if item.get("type") == "text":

            answer += item.get(
                "text",
                ""
            )

    return {
        "answer": answer,
        "sources": []
    }


# ============================================================
# MODE HANDLING
# ============================================================

def resolve_mode(requested_mode):

    requested_mode = (
        requested_mode or
        DEFAULT_MODE
    ).strip().lower()

    if requested_mode not in (
        "rag",
        "direct"
    ):
        requested_mode = DEFAULT_MODE

    # Direct AI is disabled
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


# ============================================================
# QUERY HANDLER
# ============================================================

def handle_query(event):

    body = parse_body(event)

    question = body.get(
        "question",
        ""
    )

    requested_mode = body.get(
        "mode",
        DEFAULT_MODE
    )

    if not isinstance(question, str):

        return response(
            400,
            {
                "error":
                    "Question must be text."
            }
        )

    question = question.strip()

    if not question:

        return response(
            400,
            {
                "error":
                    "Question is required."
            }
        )

    mode = resolve_mode(
        requested_mode
    )

    print(
        f"Requested mode: {requested_mode}"
    )

    print(
        f"Actual mode: {mode}"
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cached = get_cached_answer(
        mode,
        question
    )

    if cached:

        cached["cached"] = True

        return response(
            200,
            cached
        )

    # --------------------------------------------------------
    # QUERY
    # --------------------------------------------------------

    if mode == "direct":

        result = query_direct_ai(
            question
        )

    else:

        result = query_knowledge_base(
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

    # --------------------------------------------------------
    # RESPONSE DATA
    # --------------------------------------------------------

    result_data = {

        "question":
            question,

        "answer":
            answer,

        "mode":
            mode,

        "sources":
            sources,

        "cached":
            False

    }

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cache_answer(
        mode,
        question,
        result_data
    )

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    save_history(
        question,
        answer,
        mode,
        sources
    )

    return response(
        200,
        result_data
    )


# ============================================================
# PDF FILENAME SANITIZATION
# ============================================================

def sanitize_filename(filename):

    filename = (
        filename or
        "document.pdf"
    )

    filename = os.path.basename(
        filename
    )

    # Remove unsafe characters
    filename = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        filename
    )

    # Make sure extension is PDF
    if not filename.lower().endswith(".pdf"):

        filename += ".pdf"

    return filename


# ============================================================
# CREATE PRESIGNED UPLOAD URL
# ============================================================

def create_upload_url(event):

    body = parse_body(event)

    filename = body.get(
        "filename"
    )

    content_type = body.get(
        "contentType"
    )

    file_size = body.get(
        "size"
    )

    if not filename:

        return response(
            400,
            {
                "error":
                    "filename is required."
            }
        )

    filename = sanitize_filename(
        filename
    )

    # --------------------------------------------------------
    # PDF validation
    # --------------------------------------------------------

    if not filename.lower().endswith(
        ".pdf"
    ):

        return response(
            400,
            {
                "error":
                    "Only PDF files are allowed."
            }
        )

    # --------------------------------------------------------
    # Content type validation
    # --------------------------------------------------------

    if content_type:

        if content_type.lower() != (
            "application/pdf"
        ):

            return response(
                400,
                {
                    "error":
                        "Content-Type must be "
                        "application/pdf."
                }
            )

    # --------------------------------------------------------
    # Size validation
    # --------------------------------------------------------

    try:

        file_size = int(
            file_size
        )

    except Exception:

        return response(
            400,
            {
                "error":
                    "Valid file size is required."
            }
        )

    if file_size <= 0:

        return response(
            400,
            {
                "error":
                    "File cannot be empty."
            }
        )

    if file_size > MAX_UPLOAD_SIZE:

        return response(
            400,
            {
                "error":
                    "PDF size cannot exceed 10 MB."
            }
        )

    # --------------------------------------------------------
    # S3 key
    # --------------------------------------------------------

    unique_id = str(
        uuid.uuid4()
    )

    key = (
        f"uploads/"
        f"{unique_id}-"
        f"{filename}"
    )

    # --------------------------------------------------------
    # Presigned PUT URL
    # --------------------------------------------------------

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

            ExpiresIn=300
        )
    )

    print(
        f"Created upload URL for: {key}"
    )

    return response(
        200,
        {
            "uploadUrl":
                upload_url,

            "key":
                key,

            "filename":
                filename
        }
    )


# ============================================================
# COMPLETE UPLOAD + START KNOWLEDGE BASE INGESTION
# ============================================================

def complete_upload(event):

    body = parse_body(event)

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
                "error":
                    "key is required."
            }
        )

    # Security check
    if not key.startswith(
        "uploads/"
    ):

        return response(
            400,
            {
                "error":
                    "Invalid upload key."
            }
        )

    # --------------------------------------------------------
    # Verify object exists
    # --------------------------------------------------------

    try:

        head = s3_client.head_object(
            Bucket=UPLOAD_BUCKET,
            Key=key
        )

    except ClientError as e:

        print(
            f"S3 verification failed: {str(e)}"
        )

        return response(
            400,
            {
                "error":
                    "Uploaded PDF was not found in S3."
            }
        )

    actual_size = head.get(
        "ContentLength",
        0
    )

    if actual_size > MAX_UPLOAD_SIZE:

        return response(
            400,
            {
                "error":
                    "Uploaded PDF exceeds 10 MB."
            }
        )

    # --------------------------------------------------------
    # Verify content type
    # --------------------------------------------------------

    actual_content_type = head.get(
        "ContentType",
        ""
    )

    if actual_content_type.lower() != (
        "application/pdf"
    ):

        return response(
            400,
            {
                "error":
                    "Uploaded object is not a PDF."
            }
        )

    # --------------------------------------------------------
    # Start Knowledge Base ingestion
    # --------------------------------------------------------

    try:

        ingestion = (
            bedrock_agent_client
            .start_ingestion_job(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    KNOWLEDGE_BASE_DATA_SOURCE_ID
            )
        )

    except ClientError as e:

        print(
            "Knowledge Base ingestion error: "
            f"{str(e)}"
        )

        return response(
            500,
            {
                "error":
                    "PDF uploaded, but Knowledge "
                    "Base ingestion could not be started.",

                "details":
                    str(e)
            }
        )

    ingestion_job = ingestion.get(
        "ingestionJob",
        {}
    )

    ingestion_job_id = ingestion_job.get(
        "ingestionJobId"
    )

    status = ingestion_job.get(
        "status"
    )

    print(
        "Started ingestion job: "
        f"{ingestion_job_id}"
    )

    return response(
        200,
        {
            "message":
                "PDF uploaded successfully. "
                "Knowledge Base ingestion started.",

            "key":
                key,

            "filename":
                filename,

            "ingestionJobId":
                ingestion_job_id,

            "status":
                status
        }
    )


# ============================================================
# KNOWLEDGE BASE INGESTION STATUS
# ============================================================

def get_upload_status(event):

    body = parse_body(event)

    ingestion_job_id = body.get(
        "ingestionJobId"
    )

    if not ingestion_job_id:

        return response(
            400,
            {
                "error":
                    "ingestionJobId is required."
            }
        )

    try:

        result = (
            bedrock_agent_client
            .get_ingestion_job(
                knowledgeBaseId=
                    KNOWLEDGE_BASE_ID,

                dataSourceId=
                    KNOWLEDGE_BASE_DATA_SOURCE_ID,

                ingestionJobId=
                    ingestion_job_id
            )
        )

    except ClientError as e:

        print(
            f"Ingestion status error: {str(e)}"
        )

        return response(
            500,
            {
                "error":
                    "Could not get ingestion status.",

                "details":
                    str(e)
            }
        )

    ingestion_job = result.get(
        "ingestionJob",
        {}
    )

    return response(
        200,
        {
            "ingestionJobId":
                ingestion_job.get(
                    "ingestionJobId"
                ),

            "status":
                ingestion_job.get(
                    "status"
                ),

            "startedAt":
                ingestion_job.get(
                    "startedAt"
                ),

            "updatedAt":
                ingestion_job.get(
                    "updatedAt"
                ),

            "statistics":
                ingestion_job.get(
                    "statistics",
                    {}
                ),

            "failureReasons":
                ingestion_job.get(
                    "failureReasons",
                    []
                )
        }
    )


# ============================================================
# HISTORY HANDLER
# ============================================================

def handle_history():

    try:

        items = get_history()

        return response(
            200,
            {
                "history":
                    items
            }
        )

    except Exception as e:

        return response(
            500,
            {
                "error":
                    "Could not retrieve history.",

                "details":
                    str(e)
            }
        )


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print(
        "================================================"
    )

    print(
        "Noxora Lambda request"
    )

    print(
        f"Event: {json.dumps(event, default=str)}"
    )

    print(
        "================================================"
    )

    try:

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
            or
            "POST"
        )

        path = event.get(
            "path"
        )

        if not path:

            path = (
                event
                .get(
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

        print(
            f"Method: {http_method}"
        )

        print(
            f"Path: {path}"
        )

        # ====================================================
        # CORS PREFLIGHT
        # ====================================================

        if http_method.upper() == "OPTIONS":

            return {
                "statusCode": 204,
                "headers": CORS_HEADERS,
                "body": ""
            }

        # ====================================================
        # HISTORY
        # ====================================================

        if (
            http_method.upper() == "GET"
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

            return handle_history()

        # ====================================================
        # UPLOAD - CREATE PRESIGNED URL
        # ====================================================

        if (
            http_method.upper() == "POST"
            and path.endswith(
                "/upload"
            )
            and not path.endswith(
                "/upload/complete"
            )
            and not path.endswith(
                "/upload/status"
            )
        ):

            return create_upload_url(
                event
            )

        # ====================================================
        # UPLOAD COMPLETE
        # ====================================================

        if (
            http_method.upper() == "POST"
            and path.endswith(
                "/upload/complete"
            )
        ):

            return complete_upload(
                event
            )

        # ====================================================
        # UPLOAD STATUS
        # ====================================================

        if (
            http_method.upper() == "POST"
            and path.endswith(
                "/upload/status"
            )
        ):

            return get_upload_status(
                event
            )

        # ====================================================
        # QUERY
        # ====================================================

        if (
            http_method.upper() == "POST"
            and path.endswith(
                "/query"
            )
        ):

            return handle_query(
                event
            )

        # ====================================================
        # UNKNOWN ROUTE
        # ====================================================

        return response(
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

    except Exception as e:

        print(
            "================================================"
        )

        print(
            "UNHANDLED ERROR"
        )

        print(
            repr(e)
        )

        print(
            "================================================"
        )

        return response(
            500,
            {
                "error":
                    f"{type(e).__name__}: {str(e)}"
            }
        )
