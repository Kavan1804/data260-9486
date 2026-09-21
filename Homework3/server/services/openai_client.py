import os
from openai import OpenAI

def get_client() -> OpenAI:
    # OPENAI_API_KEY should be set in the environment
    return OpenAI()

def response_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def embedding_model() -> str:
    return os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
