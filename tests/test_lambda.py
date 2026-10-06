import json
import os
import sys
from unittest.mock import MagicMock

import pytest


# ------------------------------------------------------------
# Test environment
# ------------------------------------------------------------

os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["KNOWLEDGE_BASE_ID"] = "test-kb"
os.environ["KNOWLEDGE_BASE_DATA_SOURCE_ID"] = "test-ds"
os.environ["MODEL_ID"] = "test-model"
os.environ["UPLOAD_BUCKET"] = "test-upload-bucket"
os.environ["DYNAMODB_TABLE"] = "test-history"
os.environ.pop("REDIS_ENDPOINT", None)


# ------------------------------------------------------------
# Import Lambda
# ------------------------------------------------------------

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "src")
    )
)

import lambda_function


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def parse_body(result):
    return json.loads(result["body"])


# ============================================================
# RESPONSE TESTS
# ============================================================

def test_response_returns_expected_structure():
    result = lambda_function.response(
        200,
        {
            "success": True,
            "message": "test"
        }
    )

    assert result["statusCode"] == 200
    assert result["headers"]["Content-Type"] == "application/json"
    assert result["headers"]["Access-Control-Allow-Origin"] == "*"

    body = parse_body(result)

    assert body["success"] is True
    assert body["message"] == "test"


# ============================================================
# CACHE KEY TESTS
# ============================================================

def test_create_cache_key_normalizes_question():
    key = lambda_function.create_cache_key(
        "  What is AWS Bedrock?  ",
        "rag"
    )

    assert key == "bedrock-qa:rag:what is aws bedrock?"


def test_create_cache_key_separates_modes():
    rag_key = lambda_function.create_cache_key(
        "What is AWS?",
        "rag"
    )

    direct_key = lambda_function.create_cache_key(
        "What is AWS?",
        "direct"
    )

    assert rag_key != direct_key
    assert rag_key.startswith("bedrock-qa:rag:")
    assert direct_key.startswith("bedrock-qa:direct:")


# ============================================================
# QUERY VALIDATION
# ============================================================

def test_handle_query_rejects_empty_question():
    result = lambda_function.handle_query({})

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Question is required."


def test_handle_query_rejects_whitespace_question():
    result = lambda_function.handle_query(
        {
            "question": "   "
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Question is required."


def test_handle_query_defaults_invalid_mode_to_rag(monkeypatch):
    expected = {
        "answer": "RAG answer",
        "sources": [],
        "cached": False
    }

    mocked = MagicMock(return_value=expected)

    monkeypatch.setattr(
        lambda_function,
        "handle_rag_question",
        mocked
    )

    result = lambda_function.handle_query(
        {
            "question": "What is AWS?",
            "mode": "invalid-mode"
        }
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True
    assert body["mode"] == "rag"
    assert body["answer"] == "RAG answer"

    mocked.assert_called_once_with("What is AWS?")


# ============================================================
# QUERY ROUTING
# ============================================================

def test_handle_query_routes_to_rag(monkeypatch):
    mocked = MagicMock(
        return_value={
            "answer": "RAG answer",
            "sources": [
                {
                    "source": "document.pdf",
                    "score": 0.95
                }
            ],
            "cached": False
        }
    )

    monkeypatch.setattr(
        lambda_function,
        "handle_rag_question",
        mocked
    )

    result = lambda_function.handle_query(
        {
            "question": "Explain the document",
            "mode": "rag"
        }
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True
    assert body["mode"] == "rag"
    assert body["answer"] == "RAG answer"
    assert body["cached"] is False
    assert len(body["sources"]) == 1

    mocked.assert_called_once_with(
        "Explain the document"
    )


def test_handle_query_routes_to_direct(monkeypatch):
    mocked = MagicMock(
        return_value={
            "answer": "Direct answer",
            "sources": [],
            "cached": False
        }
    )

    monkeypatch.setattr(
        lambda_function,
        "handle_direct_question",
        mocked
    )

    result = lambda_function.handle_query(
        {
            "question": "What is Python?",
            "mode": "direct"
        }
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True
    assert body["mode"] == "direct"
    assert body["answer"] == "Direct answer"
    assert body["sources"] == []

    mocked.assert_called_once_with(
        "What is Python?"
    )


def test_handle_query_returns_500_when_processing_fails(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "handle_rag_question",
        MagicMock(
            side_effect=Exception("Bedrock failure")
        )
    )

    result = lambda_function.handle_query(
        {
            "question": "Test question",
            "mode": "rag"
        }
    )

    assert result["statusCode"] == 500

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Bedrock failure"


# ============================================================
# RAG QUESTION
# ============================================================

def test_handle_rag_question_returns_cached_answer(monkeypatch):
    cached = {
        "answer": "Cached answer",
        "sources": [
            {
                "source": "test.pdf",
                "score": 0.9
            }
        ]
    }

    monkeypatch.setattr(
        lambda_function,
        "get_cached_answer",
        MagicMock(return_value=cached)
    )

    query_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "query_knowledge_base",
        query_mock
    )

    result = lambda_function.handle_rag_question(
        "What is AWS?"
    )

    assert result["answer"] == "Cached answer"
    assert result["sources"] == cached["sources"]
    assert result["cached"] is True

    query_mock.assert_not_called()


def test_handle_rag_question_handles_no_retrieval_results(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "get_cached_answer",
        MagicMock(return_value=None)
    )

    monkeypatch.setattr(
        lambda_function,
        "query_knowledge_base",
        MagicMock(return_value=[])
    )

    save_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "save_history",
        save_mock
    )

    result = lambda_function.handle_rag_question(
        "Unknown question"
    )

    assert (
        result["answer"]
        == "I couldn't find relevant information in the Knowledge Base."
    )

    assert result["sources"] == []
    assert result["cached"] is False

    save_mock.assert_called_once()


def test_handle_rag_question_builds_context_and_generates_answer(monkeypatch):
    retrieval_results = [
        {
            "content": {
                "text": "AWS Lambda is a serverless compute service."
            },
            "location": {
                "s3Location": {
                    "uri": "s3://test-bucket/lambda.pdf"
                }
            },
            "score": 0.95
        }
    ]

    monkeypatch.setattr(
        lambda_function,
        "get_cached_answer",
        MagicMock(return_value=None)
    )

    monkeypatch.setattr(
        lambda_function,
        "query_knowledge_base",
        MagicMock(
            return_value=retrieval_results
        )
    )

    invoke_mock = MagicMock(
        return_value="Lambda is a serverless compute service."
    )

    monkeypatch.setattr(
        lambda_function,
        "invoke_claude",
        invoke_mock
    )

    monkeypatch.setattr(
        lambda_function,
        "set_cached_answer",
        MagicMock()
    )

    monkeypatch.setattr(
        lambda_function,
        "save_history",
        MagicMock()
    )

    result = lambda_function.handle_rag_question(
        "What is Lambda?"
    )

    assert result["answer"] == (
        "Lambda is a serverless compute service."
    )

    assert result["cached"] is False

    assert len(result["sources"]) == 1

    assert (
        result["sources"][0]["source"]
        == "s3://test-bucket/lambda.pdf"
    )

    invoke_mock.assert_called_once()

    prompt = invoke_mock.call_args.args[0]

    assert "AWS Lambda is a serverless compute service." in prompt
    assert "What is Lambda?" in prompt
    assert "Do not invent facts." in prompt


# ============================================================
# DIRECT QUESTION
# ============================================================

def test_handle_direct_question_returns_cached_answer(monkeypatch):
    cached = {
        "answer": "Cached direct answer",
        "sources": []
    }

    monkeypatch.setattr(
        lambda_function,
        "get_cached_answer",
        MagicMock(return_value=cached)
    )

    invoke_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "invoke_claude",
        invoke_mock
    )

    result = lambda_function.handle_direct_question(
        "What is Python?"
    )

    assert result["answer"] == "Cached direct answer"
    assert result["sources"] == []
    assert result["cached"] is True

    invoke_mock.assert_not_called()


def test_handle_direct_question_invokes_claude(monkeypatch):
    monkeypatch.setattr(
        lambda_function,
        "get_cached_answer",
        MagicMock(return_value=None)
    )

    invoke_mock = MagicMock(
        return_value="Python is a programming language."
    )

    monkeypatch.setattr(
        lambda_function,
        "invoke_claude",
        invoke_mock
    )

    monkeypatch.setattr(
        lambda_function,
        "set_cached_answer",
        MagicMock()
    )

    monkeypatch.setattr(
        lambda_function,
        "save_history",
        MagicMock()
    )

    result = lambda_function.handle_direct_question(
        "What is Python?"
    )

    assert (
        result["answer"]
        == "Python is a programming language."
    )

    assert result["sources"] == []
    assert result["cached"] is False

    invoke_mock.assert_called_once()

    prompt = invoke_mock.call_args.args[0]

    assert "What is Python?" in prompt


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def test_extract_source_info():
    citation = {
        "location": {
            "s3Location": {
                "uri": "s3://documents/test.pdf"
            }
        },
        "score": 0.91,
        "metadata": {
            "page": 3
        }
    }

    result = lambda_function.extract_source_info(
        citation
    )

    assert result["source"] == (
        "s3://documents/test.pdf"
    )

    assert result["score"] == 0.91

    assert result["metadata"]["page"] == 3


def test_extract_source_info_handles_missing_data():
    result = lambda_function.extract_source_info({})

    assert result["source"] is None
    assert result["score"] is None
    assert result["metadata"] == {}


# ============================================================
# CACHE
# ============================================================

def test_get_cached_answer_returns_none_when_redis_unavailable(
    monkeypatch
):
    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        None
    )

    result = lambda_function.get_cached_answer(
        "test-key"
    )

    assert result is None


def test_get_cached_answer_returns_json(monkeypatch):
    redis_mock = MagicMock()

    redis_mock.get.return_value = json.dumps(
        {
            "answer": "cached"
        }
    )

    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        redis_mock
    )

    result = lambda_function.get_cached_answer(
        "test-key"
    )

    assert result == {
        "answer": "cached"
    }

    redis_mock.get.assert_called_once_with(
        "test-key"
    )


def test_get_cached_answer_handles_redis_failure(monkeypatch):
    redis_mock = MagicMock()

    redis_mock.get.side_effect = Exception(
        "Redis unavailable"
    )

    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        redis_mock
    )

    result = lambda_function.get_cached_answer(
        "test-key"
    )

    assert result is None


def test_set_cached_answer_does_nothing_without_redis(
    monkeypatch
):
    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        None
    )

    # Should not raise an exception.
    lambda_function.set_cached_answer(
        "test-key",
        {
            "answer": "test"
        }
    )


def test_set_cached_answer_calls_redis(monkeypatch):
    redis_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        redis_mock
    )

    data = {
        "answer": "test"
    }

    lambda_function.set_cached_answer(
        "test-key",
        data
    )

    redis_mock.setex.assert_called_once()

    args = redis_mock.setex.call_args.args

    assert args[0] == "test-key"
    assert args[1] == lambda_function.CACHE_TTL

    stored_data = json.loads(args[2])

    assert stored_data == data


def test_clear_rag_cache(monkeypatch):
    redis_mock = MagicMock()

    redis_mock.keys.return_value = [
        "bedrock-qa:rag:question1",
        "bedrock-qa:rag:question2"
    ]

    monkeypatch.setattr(
        lambda_function,
        "redis_client",
        redis_mock
    )

    lambda_function.clear_rag_cache()

    redis_mock.keys.assert_called_once_with(
        "bedrock-qa:rag:*"
    )

    redis_mock.delete.assert_called_once_with(
        "bedrock-qa:rag:question1",
        "bedrock-qa:rag:question2"
    )


# ============================================================
# UPLOAD VALIDATION
# ============================================================

def test_create_upload_url_requires_filename():
    result = lambda_function.create_upload_url({})

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Filename is required."


def test_create_upload_url_rejects_non_pdf():
    result = lambda_function.create_upload_url(
        {
            "filename": "document.txt"
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == (
        "Only PDF files are allowed."
    )


def test_create_upload_url_rejects_wrong_content_type():
    result = lambda_function.create_upload_url(
        {
            "filename": "document.pdf",
            "contentType": "text/plain"
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == (
        "Content-Type must be application/pdf."
    )


def test_create_upload_url_rejects_empty_file():
    result = lambda_function.create_upload_url(
        {
            "filename": "document.pdf",
            "contentType": "application/pdf",
            "fileSize": 0
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == "File cannot be empty."


def test_create_upload_url_rejects_file_over_10mb():
    result = lambda_function.create_upload_url(
        {
            "filename": "document.pdf",
            "contentType": "application/pdf",
            "fileSize": (
                lambda_function.MAX_UPLOAD_SIZE + 1
            )
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == (
        "Maximum file size is 10 MB."
    )


def test_create_upload_url_rejects_invalid_file_size():
    result = lambda_function.create_upload_url(
        {
            "filename": "document.pdf",
            "contentType": "application/pdf",
            "fileSize": "abc"
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == "Invalid file size."


def test_create_upload_url_generates_presigned_url(
    monkeypatch
):
    s3_mock = MagicMock()

    s3_mock.generate_presigned_url.return_value = (
        "https://example.com/presigned-upload"
    )

    monkeypatch.setattr(
        lambda_function,
        "s3_client",
        s3_mock
    )

    result = lambda_function.create_upload_url(
        {
            "filename": "my document.pdf",
            "contentType": "application/pdf",
            "fileSize": 1024
        }
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True

    assert body["uploadUrl"] == (
        "https://example.com/presigned-upload"
    )

    assert body["filename"] == "my document.pdf"
    assert body["expiresIn"] == 900

    assert body["key"].endswith(
        "my_document.pdf"
    )

    s3_mock.generate_presigned_url.assert_called_once()

    call_kwargs = (
        s3_mock.generate_presigned_url.call_args.kwargs
    )

    assert call_kwargs["ClientMethod"] == "put_object"

    assert (
        call_kwargs["Params"]["Bucket"]
        == lambda_function.UPLOAD_BUCKET
    )

    assert (
        call_kwargs["Params"]["ContentType"]
        == "application/pdf"
    )

    assert call_kwargs["ExpiresIn"] == 900


# ============================================================
# COMPLETE UPLOAD
# ============================================================

def test_complete_upload_requires_key():
    result = lambda_function.complete_upload({})

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Upload key is required."


def test_complete_upload_rejects_non_pdf_key():
    result = lambda_function.complete_upload(
        {
            "key": "documents/test.txt"
        }
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["error"] == (
        "Only PDF uploads are supported."
    )


def test_complete_upload_clears_rag_cache(monkeypatch):
    clear_cache_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "clear_rag_cache",
        clear_cache_mock
    )

    result = lambda_function.complete_upload(
        {
            "key": "documents/test.pdf",
            "filename": "test.pdf"
        }
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True
    assert body["sync"] == "pending"

    clear_cache_mock.assert_called_once()


# ============================================================
# HISTORY
# ============================================================

def test_save_history_writes_to_dynamodb(monkeypatch):
    table_mock = MagicMock()

    monkeypatch.setattr(
        lambda_function,
        "history_table",
        table_mock
    )

    lambda_function.save_history(
        question="What is AWS?",
        answer="AWS is a cloud platform.",
        mode="rag",
        cached=False,
        sources=[]
    )

    table_mock.put_item.assert_called_once()

    item = (
        table_mock.put_item
        .call_args.kwargs["Item"]
    )

    assert item["question"] == "What is AWS?"
    assert item["answer"] == (
        "AWS is a cloud platform."
    )
    assert item["mode"] == "rag"
    assert item["cached"] is False
    assert item["sources"] == []
    assert "query_id" in item
    assert "timestamp" in item


def test_save_history_does_not_raise_when_dynamodb_fails(
    monkeypatch
):
    table_mock = MagicMock()

    table_mock.put_item.side_effect = Exception(
        "DynamoDB unavailable"
    )

    monkeypatch.setattr(
        lambda_function,
        "history_table",
        table_mock
    )

    # History failures should not break the request.
    lambda_function.save_history(
        "question",
        "answer",
        "rag"
    )


def test_get_history_returns_newest_first(monkeypatch):
    table_mock = MagicMock()

    table_mock.scan.return_value = {
        "Items": [
            {
                "timestamp": "2026-01-01T10:00:00+00:00",
                "question": "Old"
            },
            {
                "timestamp": "2026-01-02T10:00:00+00:00",
                "question": "New"
            }
        ]
    }

    monkeypatch.setattr(
        lambda_function,
        "history_table",
        table_mock
    )

    result = lambda_function.get_history()

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True

    assert (
        body["history"][0]["question"]
        == "New"
    )

    assert (
        body["history"][1]["question"]
        == "Old"
    )


def test_get_history_handles_dynamodb_failure(monkeypatch):
    table_mock = MagicMock()

    table_mock.scan.side_effect = Exception(
        "DynamoDB unavailable"
    )

    monkeypatch.setattr(
        lambda_function,
        "history_table",
        table_mock
    )

    result = lambda_function.get_history()

    assert result["statusCode"] == 500

    body = parse_body(result)

    assert body["success"] is False


# ============================================================
# KNOWLEDGE BASE
# ============================================================

def test_query_knowledge_base(monkeypatch):
    bedrock_mock = MagicMock()

    bedrock_mock.retrieve.return_value = {
        "retrievalResults": [
            {
                "content": {
                    "text": "Test document content"
                },
                "score": 0.92
            }
        ]
    }

    monkeypatch.setattr(
        lambda_function,
        "bedrock_agent_runtime",
        bedrock_mock
    )

    result = lambda_function.query_knowledge_base(
        "What is this?"
    )

    assert len(result) == 1
    assert (
        result[0]["content"]["text"]
        == "Test document content"
    )

    bedrock_mock.retrieve.assert_called_once()

    call_kwargs = (
        bedrock_mock.retrieve.call_args.kwargs
    )

    assert (
        call_kwargs["knowledgeBaseId"]
        == lambda_function.KNOWLEDGE_BASE_ID
    )

    assert (
        call_kwargs["retrievalQuery"]["text"]
        == "What is this?"
    )


# ============================================================
# CLAUDE INVOCATION
# ============================================================

def test_invoke_claude(monkeypatch):
    bedrock_mock = MagicMock()

    response_body = {
        "content": [
            {
                "type": "text",
                "text": "Hello from Claude."
            }
        ]
    }

    body_mock = MagicMock()

    body_mock.read.return_value = json.dumps(
        response_body
    ).encode("utf-8")

    bedrock_mock.invoke_model.return_value = {
        "body": body_mock
    }

    monkeypatch.setattr(
        lambda_function,
        "bedrock_runtime",
        bedrock_mock
    )

    result = lambda_function.invoke_claude(
        "Say hello."
    )

    assert result == "Hello from Claude."

    bedrock_mock.invoke_model.assert_called_once()

    call_kwargs = (
        bedrock_mock.invoke_model.call_args.kwargs
    )

    assert (
        call_kwargs["modelId"]
        == lambda_function.MODEL_ID
    )

    request_body = json.loads(
        call_kwargs["body"]
    )

    assert (
        request_body["anthropic_version"]
        == "bedrock-2023-05-31"
    )

    assert (
        request_body["messages"][0]["role"]
        == "user"
    )


def test_invoke_claude_returns_empty_string_for_empty_content(
    monkeypatch
):
    bedrock_mock = MagicMock()

    body_mock = MagicMock()

    body_mock.read.return_value = json.dumps(
        {
            "content": []
        }
    ).encode("utf-8")

    bedrock_mock.invoke_model.return_value = {
        "body": body_mock
    }

    monkeypatch.setattr(
        lambda_function,
        "bedrock_runtime",
        bedrock_mock
    )

    result = lambda_function.invoke_claude(
        "Test"
    )

    assert result == ""


# ============================================================
# LAMBDA HANDLER / ROUTING
# ============================================================

def test_lambda_handler_options():
    result = lambda_function.lambda_handler(
        {
            "httpMethod": "OPTIONS"
        },
        None
    )

    assert result["statusCode"] == 200

    body = parse_body(result)

    assert body["success"] is True


def test_lambda_handler_invalid_json():
    result = lambda_function.lambda_handler(
        {
            "httpMethod": "POST",
            "path": "/query",
            "body": "{invalid-json"
        },
        None
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Invalid JSON body."


def test_lambda_handler_query_route(monkeypatch):
    query_mock = MagicMock(
        return_value=lambda_function.response(
            200,
            {
                "success": True,
                "answer": "test"
            }
        )
    )

    monkeypatch.setattr(
        lambda_function,
        "handle_query",
        query_mock
    )

    result = lambda_function.lambda_handler(
        {
            "httpMethod": "POST",
            "path": "/dev/query",
            "body": json.dumps(
                {
                    "question": "test"
                }
            )
        },
        None
    )

    assert result["statusCode"] == 200

    query_mock.assert_called_once_with(
        {
            "question": "test"
        }
    )


def test_lambda_handler_history_route(monkeypatch):
    history_mock = MagicMock(
        return_value=lambda_function.response(
            200,
            {
                "success": True,
                "history": []
            }
        )
    )

    monkeypatch.setattr(
        lambda_function,
        "get_history",
        history_mock
    )

    result = lambda_function.lambda_handler(
        {
            "httpMethod": "GET",
            "path": "/dev/query/history"
        },
        None
    )

    assert result["statusCode"] == 200

    history_mock.assert_called_once()


def test_lambda_handler_unknown_route():
    result = lambda_function.lambda_handler(
        {
            "httpMethod": "GET",
            "path": "/unknown"
        },
        None
    )

    assert result["statusCode"] == 404

    body = parse_body(result)

    assert body["success"] is False
    assert body["error"] == "Route not found."


# ============================================================
# UPLOAD ROUTING
# ============================================================

def test_lambda_handler_upload_create(monkeypatch):
    upload_mock = MagicMock(
        return_value=lambda_function.response(
            200,
            {
                "success": True,
                "uploadUrl": "test-url"
            }
        )
    )

    monkeypatch.setattr(
        lambda_function,
        "create_upload_url",
        upload_mock
    )

    body = {
        "action": "create",
        "filename": "test.pdf"
    }

    result = lambda_function.lambda_handler(
        {
            "httpMethod": "POST",
            "path": "/upload",
            "body": json.dumps(body)
        },
        None
    )

    assert result["statusCode"] == 200

    upload_mock.assert_called_once_with(
        body
    )


def test_lambda_handler_upload_complete(monkeypatch):
    complete_mock = MagicMock(
        return_value=lambda_function.response(
            200,
            {
                "success": True
            }
        )
    )

    monkeypatch.setattr(
        lambda_function,
        "complete_upload",
        complete_mock
    )

    body = {
        "action": "complete",
        "key": "test.pdf"
    }

    result = lambda_function.lambda_handler(
        {
            "httpMethod": "POST",
            "path": "/upload",
            "body": json.dumps(body)
        },
        None
    )

    assert result["statusCode"] == 200

    complete_mock.assert_called_once_with(
        body
    )


def test_lambda_handler_unknown_upload_action():
    result = lambda_function.lambda_handler(
        {
            "httpMethod": "POST",
            "path": "/upload",
            "body": json.dumps(
                {
                    "action": "unknown"
                }
            )
        },
        None
    )

    assert result["statusCode"] == 400

    body = parse_body(result)

    assert body["success"] is False
    assert (
        body["error"]
        == "Unknown upload action: unknown"
    )
