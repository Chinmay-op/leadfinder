import os
from openai import OpenAI, AzureOpenAI

api_key = os.getenv("AZURE_OPENAI_KEY")

models_to_test = [
    "Kimi-K2.5",
    "gpt-5-chat",
    "Llama-4-Maverick-17B-128E-Instruct-FP8",
    "gpt-4.1"
]

print("Starting comprehensive tests for all models and configurations...\n")

for model in models_to_test:
    print(f"========== Testing Model: {model} ==========")
    
    # Method 1: Standard OpenAI Client
    print("Method 1: Standard OpenAI client (base_url: .../v1/)")
    try:
        client_std = OpenAI(
            base_url="https://coder-resource.services.ai.azure.com/openai/v1/",
            api_key=api_key
        )
        completion = client_std.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Return the word 'SUCCESS' if you receive this message."}],
            timeout=10
        )
        print(f"[SUCCESS] {model} responded via Method 1: {completion.choices[0].message.content.strip()}\n")
    except Exception as e:
        print(f"[FAILED] Method 1 error: {e}\n")

    # Method 2: AzureOpenAI Client
    print("Method 2: AzureOpenAI client (api_version: 2024-12-01-preview)")
    try:
        client_azure = AzureOpenAI(
            azure_endpoint="https://coder-resource.services.ai.azure.com/",
            api_key=api_key,
            api_version="2024-12-01-preview"
        )
        completion = client_azure.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Return the word 'SUCCESS' if you receive this message."}],
            timeout=10
        )
        print(f"[SUCCESS] {model} responded via Method 2: {completion.choices[0].message.content.strip()}\n")
    except Exception as e:
        print(f"[FAILED] Method 2 error: {e}\n")
    
