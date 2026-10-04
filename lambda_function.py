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
# ENVIRONMENT VARIABLES
# ============================================================

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
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

CACHE_TTL = 3600
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


# ============================================================
# NORMALIZE MODE
# ============================================================

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

bedrock_agent_client = boto3.client(
    "bedrock-agent-runtime",
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
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json"
}


# ============================================================
# RESPONSE HELPERS
# ============================================================

def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body)
    }


# ============================================================
# REQUEST BODY
# ============================================================

def get_request_body(event):
    body = event.get("body")

    if body is None:
        return {}

    if isinstance(body, dict):
        return body

    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    if not body:
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


# ============================================================
# MODE
# ============================================================

def get_effective_mode(requested_mode=None):
    """
    RAG is always the safe/default mode.

    Direct AI can only be used when:
        DIRECT_AI_ENABLED=true
    """

    mode = (
        requested_mode
        or DEFAULT_MODE
        or "rag"
    ).strip().lower()

    if mode not in ("rag", "direct"):
        mode = "rag"

    if mode == "direct" and not DIRECT_AI_ENABLED:
        mode = "rag"

    return mode


# ============================================================
# QUESTION CACHE
# ============================================================

def create_cache_key(question, mode):
    normalized_question = question.strip().lower()

    question_hash = hashlib.sha256(
        normalized_question.encode("utf-8")
    ).hexdigest()

    return f"qa:{mode}:{question_hash}"


# ============================================================
# REDIS GET
# ============================================================

def get_cached_answer(question, mode):
    cache_key = create_cache_key(
        question,
        mode
    )

    try:
        cached = redis_client.get(cache_key)

        if cached:
            return json.loads(cached)

    except Exception as exc:
        print(f"Redis GET error: {exc}")

    return None


# ============================================================
# REDIS SET
# ============================================================

def cache_answer(question, mode, data):
    cache_key = create_cache_key(
        question,
        mode
    )

    try:
        redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(data)
        )

    except Exception as exc:
        print(f"Redis SET error: {exc}")


# ============================================================
# RAG QUERY
# ============================================================

def query_knowledge_base(question):
    print(
        f"Querying Knowledge Base: "
        f"{KNOWLEDGE_BASE_ID}"
    )

    response_data = bedrock_agent_client.retrieve_and_generate(
        input={
            "text": question
        },
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                "modelArn": (
                    f"arn:aws:bedrock:{AWS_REGION}:"
                    f"::foundation-model/{MODEL_ID}"
                )
            }
        }
    )

    output = (
        response_data
        .get("output", {})
        .get("text", "")
    )

    citations = []

    for citation in response_data.get(
        "citations",
        []
    ):
        retrieved_references = (
            citation
            .get("retrievedReferences", [])
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

            text = reference.get(
                "content",
                {}
            ).get(
                "text",
                ""
            )

            citations.append({
                "uri": uri,
                "text": text
            })

    return {
        "answer": output,
        "sources": citations
    }


# ============================================================
# DIRECT CLAUDE QUERY
# ============================================================

def query_claude_directly(question):
    """
    Direct AI mode.

    No Knowledge Base.
    No citations.
    """

    prompt = f"""
You are Noxora, an AI knowledge assistant.

Answer the user's question clearly and accurately.

If you are uncertain, say so rather than inventing facts.

User question:
{question}
""".strip()

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

    response_data = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(request_body),
        contentType="application/json",
        accept="application/json"
    )

    response_body = json.loads(
        response_data["body"].read()
    )

    answer = ""

    content = response_body.get(
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
        "answer": answer.strip(),
        "sources": []
    }


# ============================================================
# SAVE HISTORY
# ============================================================

def save_history(
    question,
    answer,
    mode,
    sources
):
    query_id = str(uuid.uuid4())

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    mode_label = (
        "KNOWLEDGE BASE"
        if mode == "rag"
        else "DIRECT AI"
    )

    item = {
        "query_id": query_id,
        "timestamp": timestamp,
        "question": question,
        "answer": answer,
        "mode": mode,
        "mode_label": mode_label,
        "sources": sources
    }

    try:
        history_table.put_item(
            Item=item
        )

    except Exception as exc:
        print(
            f"DynamoDB history error: {exc}"
        )

    return item


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

        while "LastEvaluatedKey" in result:
            result = history_table.scan(
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
            key=lambda item: item.get(
                "timestamp",
                ""
            ),
            reverse=True
        )

        return items[:50]

    except Exception as exc:
        print(
            f"DynamoDB scan error: {exc}"
        )

        return []


# ============================================================
# SANITIZE FILE NAME
# ============================================================

def sanitize_filename(filename):
    filename = os.path.basename(
        filename
    )

    filename = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        filename
    )

    return filename


# ============================================================
# CREATE PRESIGNED PDF UPLOAD URL
# ============================================================

def create_upload_url(body):
    filename = str(
        body.get(
            "filename",
            ""
        )
    ).strip()

    content_type = str(
        body.get(
            "contentType",
            ""
        )
    ).strip().lower()

    size = body.get(
        "size"
    )

    # --------------------------------------------------------
    # Filename validation
    # --------------------------------------------------------

    if not filename:
        return response(
            400,
            {
                "error": "Filename is required."
            }
        )

    safe_filename = sanitize_filename(
        filename
    )

    if not safe_filename.lower().endswith(
        ".pdf"
    ):
        return response(
            400,
            {
                "error": "Only PDF files are allowed."
            }
        )

    # --------------------------------------------------------
    # Content-Type validation
    # --------------------------------------------------------

    if content_type != "application/pdf":
        return response(
            400,
            {
                "error": (
                    "Only application/pdf "
                    "files are allowed."
                )
            }
        )

    # --------------------------------------------------------
    # File size validation
    # --------------------------------------------------------

    try:
        size = int(size)
    except (TypeError, ValueError):
        return response(
            400,
            {
                "error": "Invalid file size."
            }
        )

    if size <= 0:
        return response(
            400,
            {
                "error": "File is empty."
            }
        )

    if size > MAX_UPLOAD_SIZE:
        return response(
            400,
            {
                "error": (
                    "PDF size must be "
                    "10 MB or smaller."
                )
            }
        )

    # --------------------------------------------------------
    # Generate unique S3 key
    # --------------------------------------------------------

    object_key = (
        f"uploads/"
        f"{uuid.uuid4()}-"
        f"{safe_filename}"
    )

    # --------------------------------------------------------
    # Generate presigned PUT URL
    # --------------------------------------------------------

    try:
        upload_url = (
            s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": UPLOAD_BUCKET,
                    "Key": object_key,
                    "ContentType": "application/pdf"
                },
                ExpiresIn=300
            )
        )

    except ClientError as exc:
        print(
            f"S3 presigned URL error: {exc}"
        )

        return response(
            500,
            {
                "error": (
                    "Unable to create "
                    "upload URL."
                )
            }
        )

    return response(
        200,
        {
            "uploadUrl": upload_url,
            "key": object_key,
            "filename": safe_filename
        }
    )


# ============================================================
# QUERY HANDLER
# ============================================================

def handle_query(body):
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
                "error": "Question is required."
            }
        )

    requested_mode = body.get(
        "mode"
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
        question,
        mode
    )

    if cached:
        print(
            "Returning cached response."
        )

        return response(
            200,
            {
                "question": question,
                "answer": cached.get(
                    "answer",
                    ""
                ),
                "sources": cached.get(
                    "sources",
                    []
                ),
                "mode": mode,
                "cached": True
            }
        )

    # --------------------------------------------------------
    # RAG
    # --------------------------------------------------------

    if mode == "rag":

        result = query_knowledge_base(
            question
        )

    # --------------------------------------------------------
    # DIRECT AI
    # --------------------------------------------------------

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

    cache_answer(
        question,
        mode,
        {
            "answer": answer,
            "sources": sources
        }
    )

    # --------------------------------------------------------
    # SAVE HISTORY
    # --------------------------------------------------------

    save_history(
        question,
        answer,
        mode,
        sources
    )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return response(
        200,
        {
            "question": question,
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "cached": False
        }
    )


# ============================================================
# MAIN LAMBDA HANDLER
# ============================================================

def lambda_handler(event, context):

    print(
        "Incoming event:",
        json.dumps(event)
    )

    try:

        # ----------------------------------------------------
        # HTTP method
        # ----------------------------------------------------

        request_context = event.get(
            "requestContext",
            {}
        )

        http_data = request_context.get(
            "http",
            {}
        )

        method = (
            http_data.get("method")
            or event.get(
                "httpMethod",
                ""
            )
        ).upper()

        # ----------------------------------------------------
        # Path
        # ----------------------------------------------------

        path = (
            event.get(
                "rawPath"
            )
            or event.get(
                "path",
                ""
            )
        )

        print(
            f"Method: {method}"
        )

        print(
            f"Path: {path}"
        )

        # ----------------------------------------------------
        # CORS preflight
        # ----------------------------------------------------

        if method == "OPTIONS":
            return response(
                200,
                {
                    "message": "OK"
                }
            )

        # ----------------------------------------------------
        # GET HISTORY
        # ----------------------------------------------------

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
            items = get_history()

            return response(
                200,
                {
                    "history": items
                }
            )

        # ----------------------------------------------------
        # POST UPLOAD
        # ----------------------------------------------------

        if (
            method == "POST"
            and path.endswith(
                "/upload"
            )
        ):
            body = get_request_body(
                event
            )

            return create_upload_url(
                body
            )

        # ----------------------------------------------------
        # POST QUERY
        # ----------------------------------------------------

        if (
            method == "POST"
            and path.endswith(
                "/query"
            )
        ):
            body = get_request_body(
                event
            )

            return handle_query(
                body
            )

        # ----------------------------------------------------
        # Unknown route
        # ----------------------------------------------------

        return response(
            404,
            {
                "error": (
                    "Route not found."
                )
            }
        )

    except Exception as exc:

        print(
            "Unhandled Lambda error:",
            repr(exc)
        )

        return response(
            500,
            {
                "error": (
                    "Internal server error."
                )
            }
        )
