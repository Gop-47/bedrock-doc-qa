import os
import json
import uuid
import boto3

from datetime import datetime, timezone
from botocore.exceptions import ClientError


# ==========================================
# Configuration
# ==========================================

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ID = os.environ["MODEL_ID"]
DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]


# ==========================================
# AWS Clients
# ==========================================

dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION
)

history_table = dynamodb.Table(DYNAMODB_TABLE)

bedrock_client = boto3.client(
    service_name="bedrock-runtime",
    region_name=AWS_REGION
)

bedrock_agent_client = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name=AWS_REGION
)


# ==========================================
# RAG - Knowledge Base + Claude
# ==========================================

def query_knowledge_base(question: str) -> dict:
    try:
        # Retrieve relevant documents from Knowledge Base
        response = bedrock_agent_client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                "text": question
            },
        )

        # Extract retrieved chunks
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

        # Build context string
        context_text = "\n\n".join(
            [c["text"] for c in contexts]
        )

        # Prompt Claude using retrieved context
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

        # Call Claude
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

        return {
            "answer": answer,
            "citations": contexts
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = str(e)

        return {
            "answer": f"Error: {error_code} - {error_message}",
            "citations": []
        }


# ==========================================
# Direct Claude
# ==========================================

def query_claude_directly(question: str) -> str:
    """
    Query Claude directly without using
    the Knowledge Base.
    """

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

def save_query_history(question, answer, mode, citations):
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
    """
    Lambda entry point.

    RAG mode:
    {
        "question": "...",
        "mode": "rag"
    }

    Direct mode:
    {
        "question": "...",
        "mode": "direct"
    }

    Default mode is RAG.
    """

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
    # RAG Mode
    # ==========================================

    if mode == "rag":

        result = query_knowledge_base(question)

        # Save query to DynamoDB
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
                "citations": result["citations"]
            }, indent=2)
        }


    # ==========================================
    # Direct Mode
    # ==========================================

    else:

        answer = query_claude_directly(question)

        # Save query to DynamoDB
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
                "answer": answer
            }, indent=2)
        }
