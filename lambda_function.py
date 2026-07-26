import json
import boto3
from botocore.exceptions import ClientError

# Initialize clients
bedrock_client = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

bedrock_agent_client = boto3.client(
    service_name='bedrock-agent-runtime',
    region_name='us-east-1'
)

# Your Knowledge Base ID — we'll add this next
KNOWLEDGE_BASE_ID = "PPJG45JPD3"
MODEL_ID = "us.anthropic.claude-haiku-4-5-2025001-v1:0"

def query_knowledge_base(question: str) -> dict:
    try:
        # First just RETRIEVE — no generation
        response = bedrock_agent_client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                "text": question
            },
        )

        # Extract retrieved chunks
        contexts = []
        for result in response['retrievalResults']:
            text = result['content']['text']
            source = result.get('location', {}).get('s3Location', {}).get('uri', 'Unknown')
            contexts.append({
                'text': text,
                'source': source
            })

        # Build context string
        context_text = "\n\n".join([c['text'] for c in contexts])

        # Now ask Claude directly with the context
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

        response_claude = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        response_body = json.loads(response_claude['body'].read())
        answer = response_body['content'][0]['text']

        return {
            'answer': answer,
            'citations': contexts
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = str(e)
        return {
            'answer': f"Error: {error_code} - {error_message}",
            'citations': []
        }
def query_claude_directly(question: str) -> str:
    """
    Fallback — query Claude directly without Knowledge Base
    Used for general questions not in your documents
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
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except ClientError as e:
        return f"Error calling Claude: {str(e)}"

def lambda_handler(event, context):
    """
    Lambda entry point

    Two modes:
    1. RAG mode: { "question": "...", "mode": "rag" }
       → Searches your documents first, then answers
    
    2. Direct mode: { "question": "...", "mode": "direct" }
       → Asks Claude directly without documents
    
    Default mode is "rag"
    """

    # Validate input
    if 'question' not in event:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Missing required field: question'
            })
        }

    question = event['question']
    mode = event.get('mode', 'rag')

    if not question.strip():
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Question cannot be empty'
            })
        }

    if mode == 'rag':
        # Query Knowledge Base + Claude
        result = query_knowledge_base(question)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'question': question,
                'mode': 'rag',
                'answer': result['answer'],
                'citations': result['citations']
            }, indent=2)
        }
    else:
        # Query Claude directly
        answer = query_claude_directly(question)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'question': question,
                'mode': 'direct',
                'answer': answer
            }, indent=2)
        }
