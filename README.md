# 🤖 Noxora — AI Knowledge Assistant

An AI-powered document intelligence and Q&A platform built on **AWS Bedrock, Claude, Knowledge Bases, Lambda, S3, DynamoDB, Redis, Docker, and API Gateway**.

Noxora allows users to upload PDF documents and ask natural-language questions about their content. The system uses **Retrieval-Augmented Generation (RAG)** to retrieve relevant information from uploaded documents and generate grounded answers using Anthropic Claude through Amazon Bedrock.

It also supports a **Direct AI mode** for general-purpose questions without document retrieval.

---

# ✨ Features

- 📄 Upload PDF documents directly from the browser
- 🔐 Secure browser-to-S3 uploads using pre-signed URLs
- 🧠 Retrieval-Augmented Generation using Amazon Bedrock Knowledge Bases
- 🤖 Anthropic Claude via Amazon Bedrock
- 🔍 Document-grounded answers with source references
- ⚡ Redis/ElastiCache response caching
- 🗂️ DynamoDB-powered query history
- 🔄 Automatic document ingestion using S3 events
- ☁️ Fully serverless AWS backend
- 🐳 Dockerized Python Lambda
- 📦 Amazon ECR container deployment
- 🔀 RAG Mode and Direct AI Mode
- 🌐 Static frontend hosted on Amazon S3
- 🚨 Input validation and user-friendly error handling
- 📊 CloudWatch logging and monitoring
- 🔐 IAM-based AWS access control
- ⚙️ Asynchronous Knowledge Base ingestion
- 💾 Previous questions can be restored from history without triggering a new AI request

---

# 🏗️ Architecture

```text
                         ┌──────────────────────┐
                         │   Noxora Frontend    │
                         │      Amazon S3       │
                         └──────────┬───────────┘
                                    │
                                    │ HTTPS
                                    ▼
                         ┌──────────────────────┐
                         │    API Gateway       │
                         │      REST API        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────┐
                    │        AWS Lambda           │
                    │       Python 3.12           │
                    │         Docker              │
                    └──────┬──────┬──────┬────────┘
                           │      │      │
             ┌─────────────┘      │      └──────────────┐
             ▼                    ▼                     ▼
      ┌──────────────┐    ┌──────────────┐     ┌──────────────┐
      │   Bedrock    │    │    Redis /   │     │  DynamoDB    │
      │ Knowledge    │    │  ElastiCache │     │   History    │
      │    Base      │    │    Cache     │     │              │
      └──────┬───────┘    └──────────────┘     └──────────────┘
             │
             ▼
      ┌──────────────┐
      │    Claude    │
      │    Haiku     │
      │  via Bedrock │
      └──────────────┘


PDF Upload Flow
───────────────

Browser
   │
   │ Request pre-signed URL
   ▼
API Gateway
   │
   ▼
Lambda
   │
   ▼
Pre-signed S3 URL
   │
   ▼
Browser ───────────────► S3 Document Bucket
                              │
                              │ ObjectCreated
                              ▼
                       KB Sync Lambda
                              │
                              ▼
                    Bedrock Knowledge Base
                              │
                              ▼
                         Vector Index
```

---

# 🔄 How Noxora Works

## 1. Document Upload

```text
User selects PDF
       ↓
Frontend validates file
       ↓
POST /upload
       ↓
Lambda generates pre-signed S3 URL
       ↓
Browser uploads PDF directly to S3
       ↓
S3 ObjectCreated event
       ↓
KB Sync Lambda
       ↓
StartIngestionJob
       ↓
Bedrock Knowledge Base indexes document
```

The application does **not** send the PDF through the API server.

Instead, the backend generates a temporary pre-signed S3 URL and the browser uploads the document directly to S3.

This reduces backend data transfer and avoids exposing AWS credentials to the frontend.

---

# 🧠 RAG Question Flow

When a user asks a question in **Knowledge Base mode**:

```text
User Question
      ↓
Frontend
      ↓
API Gateway
      ↓
Lambda
      ↓
Redis Cache
      │
      ├── Cache Hit ──────► Return cached answer
      │
      └── Cache Miss
              ↓
       Bedrock Knowledge Base
              ↓
       Relevant document chunks
              ↓
          Claude Haiku
              ↓
          AI Answer
              ↓
       Store in Redis
              ↓
       Store in DynamoDB
              ↓
       Return Answer + Sources
```

The answer is generated using information retrieved from the uploaded documents.

---

# 🤖 AI Modes

Noxora supports two AI modes.

## 📚 Knowledge Base Mode

Uses Retrieval-Augmented Generation.

```text
Question
   ↓
Knowledge Base Retrieval
   ↓
Relevant Document Chunks
   ↓
Claude
   ↓
Grounded Answer + Sources
```

This mode is designed for questions about uploaded documents.

Example:

```text
"What are the main security requirements mentioned in the document?"
```

---

## ⚡ Direct AI Mode

Direct AI mode sends the question directly to Claude without retrieving information from the Knowledge Base.

```text
Question
   ↓
Claude via Bedrock
   ↓
Answer
```

This mode is useful for general AI questions that do not depend on uploaded documents.

Direct AI can also be disabled through the backend configuration when cost control is preferred.

---

# ⚡ Redis Caching

Noxora uses **Redis/ElastiCache** to reduce repeated Bedrock requests.

```text
Question
   ↓
Generate Cache Key
   ↓
Redis
   │
   ├── HIT ──► Return cached response
   │
   └── MISS
          ↓
      Bedrock
          ↓
      Store result in Redis
```

Caching provides two major benefits:

- Reduces unnecessary Bedrock requests
- Improves response time for repeated questions

The cache key also considers the AI mode so that RAG and Direct AI responses are not incorrectly mixed.

When new documents are uploaded, relevant cached responses are cleared to prevent stale document-based answers.

---

# 🗂️ Query History

Noxora stores query history in **Amazon DynamoDB**.

The history includes information such as:

- Question
- Answer
- AI mode
- Cache status
- Sources
- Timestamp
- Query information

The frontend provides a history drawer where users can:

- View previous questions
- Restore previous answers
- See the mode used
- See source information
- See cache status

Selecting an old question restores the stored result instead of making another Bedrock request.

---

# 📄 Document Processing

Uploaded documents are stored in a dedicated S3 document bucket.

```text
PDF
 ↓
S3
 ↓
ObjectCreated Event
 ↓
KB Sync Lambda
 ↓
Bedrock StartIngestionJob
 ↓
Knowledge Base
 ↓
Vector Search
```

The ingestion process is asynchronous.

The upload API does not wait for the entire Knowledge Base ingestion process to finish.

This makes the upload experience faster and separates document upload from document processing.

---

# 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Hosting | Amazon S3 |
| API | Amazon API Gateway |
| Compute | AWS Lambda |
| Runtime | Python 3.12 |
| Containerization | Docker |
| Container Registry | Amazon ECR |
| AI Platform | Amazon Bedrock |
| LLM | Anthropic Claude Haiku |
| RAG | Amazon Bedrock Knowledge Bases |
| Document Storage | Amazon S3 |
| Cache | Redis / Amazon ElastiCache |
| History | Amazon DynamoDB |
| Security | AWS IAM |
| Monitoring | Amazon CloudWatch |

---

# ☁️ AWS Services Used

## Amazon S3

Used for:

- Static frontend hosting
- PDF document storage
- Direct browser uploads
- S3 ObjectCreated events

## Amazon API Gateway

Provides the REST API layer between the frontend and Lambda.

## AWS Lambda

Python 3.12 Lambda functions handle:

- Questions
- AI mode selection
- Bedrock requests
- Query history
- Upload URL generation
- Document ingestion triggering

The primary Lambda is deployed as a Docker container.

## Amazon Bedrock

Provides access to Anthropic Claude models.

## Amazon Bedrock Knowledge Bases

Provides the RAG layer for document retrieval.

## Amazon DynamoDB

Stores query history and response metadata.

## Amazon ElastiCache / Redis

Provides response caching for repeated questions.

## Amazon ECR

Stores the Docker image used by the Lambda function.

## AWS IAM

Controls access between Lambda and AWS services.

## Amazon CloudWatch

Used for Lambda logs, debugging, errors, and operational monitoring.

---

# 📡 API Reference

Base URL:

```text
https://lwrgo5ikf8.execute-api.us-east-1.amazonaws.com/dev
```

## Ask a Question

```http
POST /query
```

Example request:

```json
{
  "question": "What are the main security requirements?",
  "mode": "rag"
}
```

Example response:

```json
{
  "question": "What are the main security requirements?",
  "answer": "The document identifies several security requirements...",
  "mode": "rag",
  "cached": false,
  "sources": [
    {
      "document": "security.pdf",
      "score": 0.89
    }
  ]
}
```

---

## Get Query History

```http
GET /query/history
```

Returns previously stored questions and answers from DynamoDB.

---

## Upload Document

```http
POST /upload
```

Used to initiate a secure PDF upload.

The backend validates the request and generates a pre-signed S3 upload URL.

The browser then uploads the PDF directly to S3.

---

# 🔐 Security

The project follows AWS security best practices including:

- IAM role-based permissions
- No AWS credentials exposed to the browser
- Pre-signed URLs for direct S3 uploads
- Temporary upload authorization
- Separate frontend and document S3 buckets
- Server-side validation
- PDF type validation
- File size validation
- Restricted AWS service permissions
- API input validation

PDF uploads are restricted to:

```text
Maximum size: 10 MB
File type: PDF
```

---

# 🚨 Error Handling

The application validates and handles errors across the complete request flow.

Examples include:

- Empty questions
- Invalid AI mode
- Invalid PDF files
- Unsupported file types
- Files larger than 10 MB
- Empty files
- Failed S3 uploads
- Failed Bedrock requests
- Knowledge Base errors
- Redis errors
- DynamoDB errors
- Invalid API responses
- Network failures

The frontend displays user-friendly error messages rather than exposing raw AWS errors.

---

# 🐳 Docker & Lambda Deployment

The Lambda backend is deployed as a Docker container.

```text
Source Code
     ↓
Docker Build
     ↓
Docker Image
     ↓
Amazon ECR
     ↓
AWS Lambda
```

### Build

```bash
docker build --no-cache -t bedrock-doc-qa .
```

### Tag

```bash
docker tag bedrock-doc-qa:latest \
917301404773.dkr.ecr.us-east-1.amazonaws.com/bedrock-doc-qa:latest
```

### Authenticate with ECR

```bash
aws ecr get-login-password --region us-east-1 | \
docker login \
--username AWS \
--password-stdin \
917301404773.dkr.ecr.us-east-1.amazonaws.com
```

### Push Image

```bash
docker push \
917301404773.dkr.ecr.us-east-1.amazonaws.com/bedrock-doc-qa:latest
```

### Update Lambda

```bash
aws lambda update-function-code \
--function-name bedrock-doc-qa \
--image-uri 917301404773.dkr.ecr.us-east-1.amazonaws.com/bedrock-doc-qa:latest \
--region us-east-1
```

---

# ⚙️ Environment Configuration

The backend uses environment variables for AWS resources and application configuration.

Example:

```text
AWS_REGION=us-east-1

KNOWLEDGE_BASE_ID=PPJG45JPD3

KNOWLEDGE_BASE_DATA_SOURCE_ID=SRASBTFSWJ

DYNAMODB_TABLE=bedrock-qa-history

UPLOAD_BUCKET=bedrock-doc-qa-documents-gopi

MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

REDIS_ENDPOINT=<redis-endpoint>

DEFAULT_MODE=rag

DIRECT_AI_ENABLED=false
```

Sensitive values and infrastructure-specific configuration should not be committed to source control.

---

# 📁 Project Structure

```text
bedrock-doc-qa/
│
├── src/
│   ├── lambda_function.py
│   └── ...
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── Dockerfile
├── requirements.txt
├── README.md
└── ...
```

The exact structure may evolve as additional backend functionality is added.

---

# 🧪 Example Questions

### AWS

```json
{
  "question": "What is the difference between SQS and SNS?"
}
```

### RAG

```json
{
  "question": "What are the main requirements mentioned in the uploaded document?",
  "mode": "rag"
}
```

### Architecture

```json
{
  "question": "Explain the architecture described in this document."
}
```

### General AI

```json
{
  "question": "Explain microservices architecture in simple terms.",
  "mode": "direct"
}
```

---

# 📊 End-to-End Project Flow

## Document Flow

```text
User
 ↓
Select PDF
 ↓
Frontend Validation
 ↓
POST /upload
 ↓
Generate Pre-signed URL
 ↓
Direct Browser → S3 Upload
 ↓
S3 ObjectCreated
 ↓
KB Sync Lambda
 ↓
StartIngestionJob
 ↓
Bedrock Knowledge Base
 ↓
Document Available for RAG
```

## Question Flow

```text
User
 ↓
Frontend
 ↓
API Gateway
 ↓
Lambda
 ↓
Redis Cache
 │
 ├── HIT ──► Return Cached Answer
 │
 └── MISS
       ↓
Bedrock Knowledge Base
       ↓
Relevant Chunks
       ↓
Claude
       ↓
Generated Answer
       ↓
Redis
       ↓
DynamoDB
       ↓
Frontend
       ↓
Answer + Sources
```

---

# 📈 What This Project Demonstrates

This project demonstrates practical experience with:

## Generative AI

- Amazon Bedrock
- Anthropic Claude
- Prompt-based AI interaction
- Retrieval-Augmented Generation
- Knowledge Bases

## AWS

- Lambda
- API Gateway
- S3
- DynamoDB
- ElastiCache / Redis
- ECR
- IAM
- CloudWatch

## Backend Engineering

- REST APIs
- Python
- Serverless architecture
- Asynchronous processing
- Event-driven architecture
- Caching
- Input validation
- Error handling

## DevOps / Containers

- Docker
- Containerized Lambda
- Amazon ECR
- AWS CLI deployment
- Environment-based configuration

## Frontend

- HTML
- CSS
- JavaScript
- S3 static hosting
- REST API integration
- Direct S3 uploads
- Upload progress handling
- Interactive query history

---

# 🧠 Key Engineering Concepts Demonstrated

The project goes beyond simply calling an LLM API.

It demonstrates:

```text
LLM Integration
       +
RAG
       +
Knowledge Base
       +
Serverless Architecture
       +
Event-Driven Processing
       +
Caching
       +
Persistent History
       +
Containerized Lambda
       +
Secure File Uploads
       +
Cloud Monitoring
```

This makes the project representative of a practical **AI-enabled cloud application** rather than a basic chatbot.

---

# 🔧 Important Implementation Details

## Inference Profile Support

The project uses an Amazon Bedrock inference profile for Claude.

The backend converts the configured model/inference-profile ID into the appropriate Bedrock inference-profile ARN when performing Knowledge Base retrieval and generation.

This allows the RAG flow to work with the configured Claude inference profile.

---

# 📌 Current Project Status

**Status: ✅ Completed**

The project currently supports:

- ✅ PDF upload
- ✅ Secure pre-signed S3 upload
- ✅ S3 event-driven processing
- ✅ Knowledge Base ingestion
- ✅ RAG-based Q&A
- ✅ Claude via Amazon Bedrock
- ✅ Direct AI mode
- ✅ Redis caching
- ✅ DynamoDB query history
- ✅ Source references
- ✅ Dockerized Lambda
- ✅ ECR deployment
- ✅ API Gateway
- ✅ S3 frontend hosting
- ✅ CloudWatch logging
- ✅ IAM-based access control
- ✅ Frontend error handling
- ✅ Interactive history drawer

---

# 🎯 Why I Built This

I built Noxora to gain hands-on experience building a **production-style Generative AI application on AWS**.

The goal was to understand how an AI application moves beyond a simple LLM API call into a complete cloud architecture involving:

- Document ingestion
- RAG
- Vector-based knowledge retrieval
- Serverless APIs
- Event-driven processing
- Caching
- Persistent storage
- Secure file uploads
- Dockerized workloads
- AWS IAM
- Cloud monitoring

The project combines **Generative AI, AWS Cloud, backend engineering, DevOps, and modern application architecture** into a single end-to-end system.

---

# 👨‍💻 Author

**Gopikrishna Ashok**

Senior Software Engineer

`.NET` · `Node.js` · `AWS` · `DevOps` · `Microservices` · `Generative AI` · `RAG`

---

## ⭐ Project

**Noxora — AI Knowledge Assistant**

Built with ❤️ using AWS Bedrock, Claude, Python, Docker, and serverless AWS services.
