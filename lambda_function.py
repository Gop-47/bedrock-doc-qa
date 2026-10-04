import os
import json
import uuid
import hashlib
import re
from datetime import datetime, timezone

import boto3
import redis
from botocore.exceptions import ClientError


# ============================================================
# CONFIGURATION
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]

KNOWLEDGE_BASE_DATA_SOURCE_ID = os.environ.get(
    "KNOWLEDGE_BASE_DATA_SOURCE_ID",
    "SRASBTFSWJ"
)

# Keep the model in the existing environment variable.
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
    in ("true", "1", "yes", "on")
)

CACHE_TTL = int(
    os.environ.get(
        "CACHE_TTL",
        "3600"
    )
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024


if DEFAULT_MODE not in ("rag", "direct"):
    DEFAULT_MODE = "rag"

if DEFAULT_MODE == "direct" and not DIRECT_AI_ENABLED:
    DEFAULT_MODE = "rag"


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

bedrock_client = boto3.client(
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
        "body": json.dumps(
            body,
            default=str
        )
    }


def get_http_method(event):
    return (
        event.get("requestContext", {})
        .get("http", {})
        .get("method")
        or event.get("httpMethod")
        or ""
    ).upper()


def get_path(event):
    return (
        event.get("rawPath")
        or event.get("path")
        or ""
    )


def get_request_body(event):
    body = event.get("body")

    if body is None:
        return {}

    if isinstance(body, dict):
        return body

    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(
            body
        ).decode("utf-8")

    try:
        return json.loads(body)

    except (
        json.JSONDecodeError,
        TypeError
    ):
        return {}


# ============================================================
# MODE
# ============================================================

def get_effective_mode(requested_mode):

    requested_mode = (
        requested_mode
        or DEFAULT_MODE
    ).strip().lower()

    if requested_mode not in (
        "rag",
        "direct"
    ):
        requested_mode = DEFAULT_MODE

    # Direct AI can only be used when explicitly enabled.
    if (
        requested_mode == "direct"
        and not DIRECT_AI_ENABLED
    ):
        return "rag"

    return requested_mode


# ============================================================
# REDIS CACHE
# ============================================================

def get_cache_key(mode, question):

    question_hash = hashlib.sha256(
        question.strip().lower().encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        f"qa:{mode}:{question_hash}"
    )


def get_cached_answer(
    mode,
    question
):

    try:

        cache_key = get_cache_key(
            mode,
            question
        )

        cached = redis_client.get(
            cache_key
        )

        if not cached:
            return None

        return json.loads(cached)

    except Exception as exc:

        print(
            f"Redis GET error: "
            f"{type(exc).__name__}: {exc}"
        )

        return None


def cache_answer(
    mode,
    question,
    data
):

    try:

        cache_key = get_cache_key(
            mode,
            question
        )

        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(data)
        )

    except Exception as exc:

        print(
            f"Redis SET error: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# BEDROCK MODEL ARN RESOLUTION
# ============================================================

def get_rag_model_arn():

    """
    RetrieveAndGenerate requires modelArn.

    If MODEL_ID is already an ARN, use it directly.

    If MODEL_ID is a normal foundation model ID, construct
    the foundation-model ARN.

    If MODEL_ID starts with a cross-region inference profile
    prefix such as:

        us.anthropic.claude-haiku-4-5-20251001-v1:0

    find the corresponding inference profile automatically.
    """

    # --------------------------------------------------------
    # Already an ARN
    # --------------------------------------------------------

    if MODEL_ID.startswith("arn:"):
        return MODEL_ID

    # --------------------------------------------------------
    # Cross-region inference profile
    # --------------------------------------------------------

    if MODEL_ID.startswith(
        (
            "us.",
            "eu.",
            "apac.",
            "global."
        )
    ):

        print(
            "MODEL_ID appears to be an "
            "inference profile ID."
        )

        print(
            f"Looking up inference profile: "
            f"{MODEL_ID}"
        )

        try:

            paginator = (
                bedrock_client
                .get_paginator(
                    "list_inference_profiles"
                )
            )

            for page in paginator.paginate():

                profiles = page.get(
                    "inferenceProfileSummaries",
                    []
                )

                for profile in profiles:

                    profile_id = profile.get(
                        "inferenceProfileId",
                        ""
                    )

                    profile_name = profile.get(
                        "inferenceProfileName",
                        ""
                    )

                    profile_arn = profile.get(
                        "inferenceProfileArn"
                    )

                    models = profile.get(
                        "models",
                        []
                    )

                    # First try exact inference profile ID.
                    if profile_id == MODEL_ID:
                        if profile_arn:
                            print(
                                "Found inference profile ARN:"
                            )
                            print(
                                profile_arn
                            )

                            return profile_arn

                    # Then compare model ARNs / IDs.
                    for model in models:

                        model_arn = model.get(
                            "modelArn",
                            ""
                        )

                        if (
                            MODEL_ID in model_arn
                            or profile_name == MODEL_ID
                        ):

                            if profile_arn:

                                print(
                                    "Found matching "
                                    "inference profile:"
                                )

                                print(
                                    profile_arn
                                )

                                return profile_arn

        except Exception as exc:

            print(
                "Could not resolve inference "
                f"profile: {type(exc).__name__}: {exc}"
            )

        raise RuntimeError(
            "Could not find an inference profile "
            f"for MODEL_ID: {MODEL_ID}. "
            "Check that the model is available in "
            f"{AWS_REGION} and that the Lambda role "
            "can call bedrock:ListInferenceProfiles."
        )

    # --------------------------------------------------------
    # Normal foundation model
    # --------------------------------------------------------

    return (
        f"arn:aws:bedrock:"
        f"{AWS_REGION}"
        f"::foundation-model/"
        f"{MODEL_ID}"
    )


# ============================================================
# RAG
# ============================================================

def query_knowledge_base(question):

    model_arn = get_rag_model_arn()

    print(
        "Running Knowledge Base query"
    )

    print(
        f"Knowledge Base ID: "
        f"{KNOWLEDGE_BASE_ID}"
    )

    print(
        f"Model ARN: "
        f"{model_arn}"
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

    output = result.get(
        "output",
        {}
    )

    answer = output.get(
        "text",
        ""
    )

    sources = []

    for citation in result.get(
        "citations",
        []
    ):

        for reference in citation.get(
            "retrievedReferences",
            []
        ):

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

            filename = (
                uri.split("/")[-1]
                if uri
                else "Document"
            )

            content = reference.get(
                "content",
                {}
            )

            source_text = content.get(
                "text",
                ""
            )

            sources.append({
                "filename": filename,
                "uri": uri,
                "text": source_text
            })

    return {
        "answer": answer,
        "sources": sources
    }


# ============================================================
# DIRECT AI
# ============================================================

def query_claude_directly(question):

    body = {
        "anthropic_version":
            "bedrock-2023-05-31",

        "max_tokens": 1000,

        "temperature": 0.2,

        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": question
                    }
                ]
            }
        ]
    }

    result = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    response_body = json.loads(
        result["body"].read()
    )

    answer_parts = []

    for item in response_body.get(
        "content",
        []
    ):

        if item.get("type") == "text":

            answer_parts.append(
                item.get(
                    "text",
                    ""
                )
            )

    return {
        "answer": "\n".join(
            answer_parts
        ).strip(),

        "sources": []
    }


# ============================================================
# DYNAMODB HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    sources
):

    query_id = str(
        uuid.uuid4()
    )

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    mode_label = (
        "DIRECT AI"
        if mode == "direct"
        else "KNOWLEDGE BASE"
    )

    item = {
        "query_id": query_id,
        "timestamp": timestamp,
        "question": question,
        "answer": answer,
        "mode": mode,
        "mode_label": mode_label,
        "sources": sources or []
    }

    try:

        history_table.put_item(
            Item=item
        )

    except Exception as exc:

        print(
            "DynamoDB history error: "
            f"{type(exc).__name__}: {exc}"
        )

    return item


def get_history():

    try:

        result = history_table.scan()

        items = result.get(
            "Items",
            []
        )

        items.sort(
            key=lambda item: item.get(
                "timestamp",
                ""
            ),
            reverse=True
        )

        return items[:50]

    except Exception as exc:

        print(
            "DynamoDB history read error: "
            f"{type(exc).__name__}: {exc}"
        )

        raise


# ============================================================
# S3 UPLOAD
# ============================================================

def sanitize_filename(filename):

    filename = os.path.basename(
        filename
    )

    filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename
    )

    return filename


def validate_pdf_metadata(
    filename,
    content_type,
    size
):

    if not filename:
        raise ValueError(
            "Filename is required."
        )

    safe_name = sanitize_filename(
        filename
    )

    if not safe_name.lower().endswith(
        ".pdf"
    ):
        raise ValueError(
            "Only PDF files are allowed."
        )

    if (
        content_type
        and content_type.lower()
        != "application/pdf"
    ):
        raise ValueError(
            "File Content-Type must be "
            "application/pdf."
        )

    try:

        size = int(size)

    except (
        TypeError,
        ValueError
    ):

        raise ValueError(
            "Invalid file size."
        )

    if size <= 0:
        raise ValueError(
            "File is empty."
        )

    if size > MAX_UPLOAD_SIZE:
        raise ValueError(
            "PDF size must be 10 MB or less."
        )

    return safe_name


# ============================================================
# CREATE PRESIGNED URL
# ============================================================

def create_upload_url(body):

    filename = body.get(
        "filename"
    )

    content_type = body.get(
        "contentType",
        "application/pdf"
    )

    size = body.get(
        "size"
    )

    safe_name = validate_pdf_metadata(
        filename,
        content_type,
        size
    )

    object_key = (
        f"uploads/"
        f"{uuid.uuid4()}-"
        f"{safe_name}"
    )

    upload_url = (
        s3_client
        .generate_presigned_url(
            "put_object",
            Params={
                "Bucket": UPLOAD_BUCKET,
                "Key": object_key,
                "ContentType":
                    "application/pdf"
            },
            ExpiresIn=300
        )
    )

    return {
        "uploadUrl": upload_url,
        "key": object_key,
        "filename": safe_name,
        "bucket": UPLOAD_BUCKET,
        "expiresIn": 300
    }


# ============================================================
# COMPLETE UPLOAD + START INGESTION
# ============================================================

def complete_upload(body):

    object_key = body.get(
        "key"
    )

    filename = body.get(
        "filename"
    )

    if not object_key:
        raise ValueError(
            "S3 object key is required."
        )

    if not object_key.startswith(
        "uploads/"
    ):
        raise ValueError(
            "Invalid upload object key."
        )

    # --------------------------------------------------------
    # Confirm the browser actually uploaded the object
    # --------------------------------------------------------

    try:

        head = s3_client.head_object(
            Bucket=UPLOAD_BUCKET,
            Key=object_key
        )

    except ClientError as exc:

        print(
            f"S3 HeadObject error: {exc}"
        )

        raise ValueError(
            "Uploaded PDF could not be found "
            "in S3. Please try uploading again."
        )

    uploaded_size = head.get(
        "ContentLength",
        0
    )

    if uploaded_size <= 0:
        raise ValueError(
            "Uploaded PDF is empty."
        )

    if uploaded_size > MAX_UPLOAD_SIZE:
        raise ValueError(
            "Uploaded PDF exceeds the 10 MB limit."
        )

    # --------------------------------------------------------
    # Start Knowledge Base ingestion
    # --------------------------------------------------------

    print(
        "Starting Knowledge Base ingestion"
    )

    print(
        f"KB: {KNOWLEDGE_BASE_ID}"
    )

    print(
        f"Data Source: "
        f"{KNOWLEDGE_BASE_DATA_SOURCE_ID}"
    )

    result = (
        bedrock_agent_client
        .start_ingestion_job(
            knowledgeBaseId=
                KNOWLEDGE_BASE_ID,

            dataSourceId=
                KNOWLEDGE_BASE_DATA_SOURCE_ID
        )
    )

    ingestion_job = result.get(
        "ingestionJob",
        {}
    )

    ingestion_job_id = (
        ingestion_job.get(
            "ingestionJobId"
        )
    )

    status = ingestion_job.get(
        "status"
    )

    return {
        "message": (
            "PDF uploaded successfully. "
            "Knowledge Base ingestion started."
        ),

        "filename":
            filename
            or object_key.split("/")[-1],

        "key":
            object_key,

        "bucket":
            UPLOAD_BUCKET,

        "ingestionJobId":
            ingestion_job_id,

        "ingestionStatus":
            status
    }


# ============================================================
# INGESTION STATUS
# ============================================================

def get_ingestion_status(body):

    ingestion_job_id = body.get(
        "ingestionJobId"
    )

    if not ingestion_job_id:
        raise ValueError(
            "ingestionJobId is required."
        )

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

    job = result.get(
        "ingestionJob",
        {}
    )

    return {
        "ingestionJobId":
            job.get(
                "ingestionJobId"
            ),

        "status":
            job.get(
                "status"
            ),

        "startedAt":
            (
                job.get(
                    "startedAt"
                ).isoformat()
                if job.get("startedAt")
                else None
            ),

        "updatedAt":
            (
                job.get(
                    "updatedAt"
                ).isoformat()
                if job.get("updatedAt")
                else None
            ),

        "statistics":
            job.get(
                "statistics",
                {}
            )
    }


# ============================================================
# QUERY
# ============================================================

def handle_query(body):

    question = (
        body.get("question")
        or ""
    ).strip()

    if not question:
        raise ValueError(
            "Question is required."
        )

    requested_mode = body.get(
        "mode",
        DEFAULT_MODE
    )

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

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cached = get_cached_answer(
        mode,
        question
    )

    if cached:

        print(
            "Returning cached answer."
        )

        cached["cached"] = True
        cached["mode"] = mode

        return cached

    # --------------------------------------------------------
    # QUERY
    # --------------------------------------------------------

    if mode == "rag":

        result = query_knowledge_base(
            question
        )

    else:

        result = query_claude_directly(
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
    # CACHE
    # --------------------------------------------------------

    cache_data = {
        "answer": answer,
        "sources": sources,
        "mode": mode
    }

    cache_answer(
        mode,
        question,
        cache_data
    )

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    history = save_history(
        question,
        answer,
        mode,
        sources
    )

    return {
        "answer":
            answer,

        "sources":
            sources,

        "mode":
            mode,

        "modeLabel":
            history.get(
                "mode_label"
            ),

        "queryId":
            history.get(
                "query_id"
            ),

        "timestamp":
            history.get(
                "timestamp"
            ),

        "cached":
            False
    }


# ============================================================
# LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print(
        "Received event:",
        json.dumps(
            event,
            default=str
        )
    )

    method = get_http_method(
        event
    )

    path = get_path(
        event
    )

    print(
        f"HTTP method: {method}"
    )

    print(
        f"Path: {path}"
    )

    # --------------------------------------------------------
    # CORS PREFLIGHT
    # --------------------------------------------------------

    if method == "OPTIONS":

        return {
            "statusCode": 204,
            "headers": CORS_HEADERS,
            "body": ""
        }

    try:

        body = get_request_body(
            event
        )

        # ====================================================
        # HISTORY
        # ====================================================

        if (
            method == "GET"
            and (
                path.endswith(
                    "/query/history"
                )
                or path.endswith(
                    "/history"
                )
            )
        ):

            return response(
                200,
                {
                    "history":
                        get_history()
                }
            )

        # ====================================================
        # CREATE UPLOAD URL
        # ====================================================

        if (
            method == "POST"
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

            return response(
                200,
                create_upload_url(
                    body
                )
            )

        # ====================================================
        # COMPLETE UPLOAD
        # ====================================================

        if (
            method == "POST"
            and path.endswith(
                "/upload/complete"
            )
        ):

            return response(
                200,
                complete_upload(
                    body
                )
            )

        # ====================================================
        # INGESTION STATUS
        # ====================================================

        if (
            method == "POST"
            and path.endswith(
                "/upload/status"
            )
        ):

            return response(
                200,
                get_ingestion_status(
                    body
                )
            )

        # ====================================================
        # QUERY
        # ====================================================

        if (
            method == "POST"
            and path.endswith(
                "/query"
            )
        ):

            return response(
                200,
                handle_query(
                    body
                )
            )

        # ====================================================
        # NOT FOUND
        # ====================================================

        return response(
            404,
            {
                "error":
                    "Route not found.",

                "path":
                    path,

                "method":
                    method
            }
        )

    except ValueError as exc:

        print(
            f"Validation error: {exc}"
        )

        return response(
            400,
            {
                "error":
                    str(exc)
            }
        )

    except ClientError as exc:

        print(
            f"AWS ClientError: {exc}"
        )

        error_message = (
            exc.response
            .get("Error", {})
            .get(
                "Message",
                str(exc)
            )
        )

        return response(
            500,
            {
                "error":
                    error_message
            }
        )

    except Exception as exc:

        print(
            "Unhandled Lambda error: "
            f"{type(exc).__name__}: {exc}"
        )

        return response(
            500,
            {
                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{str(exc)}"
                    )
            }
        )
