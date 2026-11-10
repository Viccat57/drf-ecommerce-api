import os
import json
import urllib.request
from rag_app.models import Product
from pgvector.django import CosineDistance

def generate_embedding(text: str) -> list[float]:
    base_url = os.environ.get("AI_BASE_URL", "http://ollama:11434")
    model = os.environ.get("AI_EMBED_MODEL", "nomic-embed-text")
    url = f"{base_url}/api/embed"
    payload = json.dumps({"model": model, "input": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]

def search_products(query: str, limit: int = 5):
    query_embedding = generate_embedding(query)
    return (
        Product.objects
        .filter(
            active=True,
            stock__gt=0,
            brand__active=True,
            category__active=True,
        )
        .annotate(distance=CosineDistance('embedding', query_embedding))
        .order_by('distance')[:limit]
    )