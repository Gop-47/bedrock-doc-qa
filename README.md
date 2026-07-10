# 🤖 AWS Bedrock Document Q&A System

An AI-powered Q&A API built on AWS using Amazon Bedrock and Claude.
Ask any question via REST API and get intelligent answers powered by Claude AI.

## 🏗️ Architecture

Client (Postman / Any App)
│
POST /ask
│
▼
API Gateway (REST API)
│
▼
AWS Lambda (Python 3.12)
│
▼
Amazon Bedrock (Claude Haiku)
│
▼
Intelligent Answer returned to Client

## 🚀 Features

- Natural language Q&A via REST API
- Powered by Anthropic Claude on AWS Bedrock
- Serverless — scales automatically, zero server management
- Pay per request — no idle compute costs
- Input validation and structured error handling
- Sub-second response times on average

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Compute | AWS Lambda (Python 3.12) |
| AI Model | Anthropic Claude Haiku via Amazon Bedrock |
| API Layer | AWS API Gateway (REST) |
| Security | AWS IAM Role-based access |
| Language | Python 3.12 |

## 📡 API Reference
### Ask a Question

**Endpoint**
POST /ask
**Request Body**
```json
{
  "question": "Your question here"
}
```

**Success Response (200)**
```json
{
  "statusCode": 200,
  "body": {
    "question": "Explain the difference between SQS and SNS in AWS",
    "answer": "SQS is a message queue service used for decoupling applications asynchronously. SNS is a pub/sub notification service that pushes messages to multiple subscribers simultaneously. Use SQS when you need reliable async processing. Use SNS when you need to broadcast messages to multiple consumers at once. They are often used together — SNS fans out to multiple SQS queues."
  }
}
```

**Error Response (400)**
```json
{
  "statusCode": 400,
  "body": {
    "error": "Missing required field: question"
  }
}
```

## 🔧 How to Deploy

### Prerequisites
- AWS Account with Bedrock access enabled
- IAM permissions for Lambda and API Gateway

### Step 1 — Create Lambda Function
AWS Console → Lambda → Create Function
Runtime: Python 3.12
Architecture: x86_64
Timeout: 30 seconds
Memory: 256 MB

### Step 2 — Add IAM Permission
Lambda → Configuration → Permissions
→ Click execution role
→ Attach policy: AmazonBedrockFullAccess

### Step 3 — Deploy Code
Copy src/lambda_function.py content
Paste into Lambda code editor
Click Deploy

### Step 4 — Create API Gateway
API Gateway → Create REST API
Create Resource: /ask
Create Method: POST
Integration: Lambda Proxy
Deploy to stage: prod

### Step 5 — Test with Postman
POST https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/ask
Content-Type: application/json
Body:
{
"question": "What is AWS Lambda?"
}

## 📁 Project Structure
bedrock-doc-qa/
├── src/
│   └── lambda_function.py    ← Main Lambda handler
├── README.txt
└── requirements.txt
## 💡 Sample Questions to Try

```json
{ "question": "Explain microservices architecture in simple terms" }
{ "question": "What is the difference between RTO and RPO?" }
{ "question": "When should I use Spot instances vs Reserved instances?" }
{ "question": "Explain VPC subnets and when to use public vs private" }
{ "question": "What is RAG in AI and how does it work?" }
```

## 🔜 Phase 2 — RAG Implementation (In Progress)

Extending this project to answer questions from your own documents:

- 📄 PDF upload to S3
- ✂️ Automatic text extraction and chunking
- 🔢 Titan Embeddings for vector generation
- 🔍 OpenSearch Serverless for vector similarity search
- 🧠 Context-aware answers grounded in your documents
- 🌐 Full API with document management endpoints

## 🎯 Why I Built This

I built this project to demonstrate practical AI engineering skills on AWS — specifically how to integrate large language models into production serverless architectures using AWS Bedrock. This is Phase 1 of a larger RAG-based document intelligence system.

This project showcases:
- AWS Lambda and API Gateway integration
- Amazon Bedrock model invocation
- Serverless architecture design
- Production-grade error handling
- Infrastructure as Code readiness (CloudFormation coming in Phase 2)

## 👨‍💻 Author

**Gopikrishna Ashok**
Senior Software Engineer — .NET | Node.js| AWS | Microservices | AI Engineering

[LinkedIn](https://linkedin.com/in/gopikrishnaashok) · [GitHub](https://github.com/Gop-47/bedrock-doc-qa
)
