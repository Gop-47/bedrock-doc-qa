import json
import os
import sys
from unittest.mock import MagicMock


# ---------------------------------------------------------
# Test environment
# ---------------------------------------------------------

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("KNOWLEDGE_BASE_ID", "test-kb")
os.environ.setdefault("KNOWLEDGE_BASE_DATA_SOURCE_ID", "test-ds")
os.environ.setdefault("DYNAMODB_TABLE", "test-history")
os.environ.setdefault("UPLOAD_BUCKET", "test-bucket")
os.environ.setdefault(
    "MODEL_ID",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
os.environ.setdefault("REDIS_ENDPOINT", "localhost")
os.environ.setdefault("DEFAULT_MODE", "rag")
os.environ.setdefault("DIRECT_AI_ENABLED", "false")


# ---------------------------------------------------------
# Mock boto3 before importing Lambda
# ---------------------------------------------------------

mock_boto3 = MagicMock()

sys.modules["boto3"] = mock_boto3

mock_boto3.client.return_value = MagicMock()
mock_boto3.resource.return_value = MagicMock()


# Import Lambda after mocks are configured
from src import lambda_function


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def api_event(
    path="/health",
    method="GET",
    body=None
):
    return {
        "resource": path,
        "path": path,
        "httpMethod": method,
        "headers": {},
        "queryStringParameters": None,
        "pathParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False
    }


# ---------------------------------------------------------
# Health check tests
# ---------------------------------------------------------

def test_health_endpoint():
    """
    Lambda health endpoint should return HTTP 200.
    """

    event = api_event(
        path="/health",
        method="GET"
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response is not None
    assert response["statusCode"] == 200


# ---------------------------------------------------------
# Query validation tests
# ---------------------------------------------------------

def test_empty_question_is_rejected():
    """
    Empty questions should not reach Bedrock.
    """

    event = api_event(
        path="/query",
        method="POST",
        body={
            "question": ""
        }
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response["statusCode"] in [400, 422]


def test_missing_question_is_rejected():
    """
    Missing question field should return a client error.
    """

    event = api_event(
        path="/query",
        method="POST",
        body={}
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response["statusCode"] in [400, 422]


def test_whitespace_question_is_rejected():
    """
    Whitespace-only questions should be rejected.
    """

    event = api_event(
        path="/query",
        method="POST",
        body={
            "question": "   "
        }
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response["statusCode"] in [400, 422]


# ---------------------------------------------------------
# Mode validation
# ---------------------------------------------------------

def test_invalid_mode_is_rejected():
    """
    Unsupported AI modes should be rejected.
    """

    event = api_event(
        path="/query",
        method="POST",
        body={
            "question": "What is AWS Lambda?",
            "mode": "invalid-mode"
        }
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response["statusCode"] in [400, 422]


# ---------------------------------------------------------
# Upload validation
# ---------------------------------------------------------

def test_upload_endpoint_exists():
    """
    Upload route should be handled by the Lambda.
    """

    event = api_event(
        path="/upload",
        method="POST",
        body={}
    )

    response = lambda_function.lambda_handler(
        event,
        None
    )

    assert response is not None
    assert "statusCode" in response
