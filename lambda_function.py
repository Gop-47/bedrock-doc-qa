import os
import json
import uuid
import hashlib
import boto3
import redis

from datetime import datetime, timezone
from botocore.exceptions import ClientError


# ==========================================
# Configuration
# ==========================================

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ID = os.environ["MODEL_ID"]
DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
REDIS_ENDPOINT = os.environ["REDIS_ENDPOINT"]

# Cache expiration: 1 hour
CACHE_TTL = 3600


# ==========================================
# AWS Clients
# ==========================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

history_table = dynamodb.Table(DYNAMODB_TABLE)

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


# ==========================================
# Redis - Cache Key
# ==========================================

def get_cache_key(question: str) -> str:
    normalized_question = question.strip().lower()

    question_hash = hashlib.sha256(
        normalized_question.encode("utf-8")
    ).hexdigest()

    return f"qa:{question_hash}"


# ==========================================
# Redis - Get Cached Answer
# ==========================================

def get_cached_answer(question: str):
    try:
        cache_key = get_cache_key(question)

        cached_data = redis_client.get(cache_key)

        if cached_data:
            return json.loads(cached_data)

        return None

    except Exception as e:
        print(f"Redis GET error: {str(e)}")
        return None


# ==========================================
# Redis - Save Answer
# ==========================================

def cache_answer(question: str, result: dict):
    try:
        cache_key = get_cache_key(question)

        redis_client.set(
            cache_key,
            json.dumps(result),
            ex=CACHE_TTL
        )

        print(f"Cached answer with key: {cache_key}")

    except Exception as e:
        print(f"Redis SET error: {str(e)}")


# ==========================================
# RAG - Knowledge Base + Claude
# ==========================================

def query_knowledge_base(question: str) -> dict:
    try:
        # ==========================================
        # Check Redis cache first
        # ==========================================

        cached_result = get_cached_answer(question)

        if cached_result:
            print("CACHE HIT")

            cached_result["cache"] = "hit"

            return cached_result

        print("CACHE MISS")

        # ==========================================
        # Retrieve relevant documents
        # ==========================================

        response = bedrock_agent_client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                "text": question
            },
        )

        # ==========================================
        # Extract retrieved chunks
        # ==========================================

        contexts = []

        for result in response["retrievalResults"]:

            text = result["content"]["text"]

            source = (
                result.get("location", {})
                .get("s3Location", {})
                .get("uri", "Unknown")
            )

            contexts.append({
                "text": text,
                "source": source
            })

        # ==========================================
        # Build context
        # ==========================================

        context_text = "\n\n".join(
            [c["text"] for c in contexts]
        )

        # ==========================================
        # Prompt Claude
        # ==========================================

        prompt = f"""Use the following context from documents to answer the question.
If the answer is not in the context say "I cannot find this in the provided documents."

Context:
{context_text}

Question: {question}

Answer:"""

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        # ==========================================
        # Call Claude
        # ==========================================

        response_claude = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body)
        )

        response_body = json.loads(
            response_claude["body"].read()
        )

        answer = response_body["content"][0]["text"]

        result = {
            "answer": answer,
            "citations": contexts,
            "cache": "miss"
        }

        # ==========================================
        # Save result to Redis
        # ==========================================

        cache_answer(
            question,
            result
        )

        return result

    except ClientError as e:

        error_code = e.response["Error"]["Code"]
        error_message = str(e)

        return {
            "answer": f"Error: {error_code} - {error_message}",
            "citations": [],
            "cache": "error"
        }


# ==========================================
# Direct Claude
# ==========================================

def query_claude_directly(question: str) -> str:

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.7,
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }

    try:

        response = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body)
        )

        response_body = json.loads(
            response["body"].read()
        )

        return response_body["content"][0]["text"]

    except ClientError as e:

        return f"Error calling Claude: {str(e)}"


# ==========================================
# DynamoDB - Save Query History
# ==========================================

def save_query_history(
    question,
    answer,
    mode,
    citations
):

    history_table.put_item(
        Item={
            "query_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "answer": answer,
            "mode": mode,
            "citations": citations
        }
    )


# ==========================================
# Lambda Handler
# ==========================================

def lambda_handler(event, context):

    # ==========================================
    # Validate input
    # ==========================================

    if "question" not in event:

        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Missing required field: question"
            })
        }

    question = event["question"]
    mode = event.get("mode", "rag")

    if not question.strip():

        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Question cannot be empty"
            })
        }

    # ==========================================
    # RAG mode
    # ==========================================

    if mode == "rag":

        result = query_knowledge_base(question)

        save_query_history(
            question=question,
            answer=result["answer"],
            mode=mode,
            citations=result["citations"]
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "question": question,
                "mode": "rag",
                "answer": result["answer"],
                "citations": result["citations"],
                "cache": result.get("cache", "unknown")
            }, indent=2)
        }

    # ==========================================
    # Direct mode
    # ==========================================

    else:

        answer = query_claude_directly(question)

        save_query_history(
            question=question,
            answer=answer,
            mode="direct",
            citations=[]
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "question": question,
                "mode": "direct",
                "answer": answer,
                "cache": "not_used"
            }, indent=2)
        }
