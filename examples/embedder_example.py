#!/usr/bin/env python3
"""Example usage of the embedding engine.

This example demonstrates how to use both OpenAI and local embedders
to generate embeddings for documentation chunks.
"""

import asyncio
import os
from aise.knowledge_engine.embedder import OpenAIEmbedder, LocalEmbedder


async def main():
    """Demonstrate embedder usage."""
    
    # Sample texts to embed
    texts = [
        "AWS Lambda is a serverless compute service.",
        "Amazon S3 provides object storage through a web service interface.",
        "EC2 instances are virtual servers in Amazon's Elastic Compute Cloud."
    ]
    
    print("=" * 60)
    print("Embedding Engine Example")
    print("=" * 60)
    
    # Example 1: Using OpenAI embeddings (requires API key)
    print("\n1. OpenAI Embeddings")
    print("-" * 60)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            embedder = OpenAIEmbedder(api_key=api_key)
            embeddings = await embedder.embed(texts)
            
            print(f"✓ Generated {len(embeddings)} embeddings")
            print(f"  Embedding dimension: {len(embeddings[0])}")
            print(f"  First embedding (first 5 values): {embeddings[0][:5]}")
        except Exception as e:
            print(f"✗ Error: {e}")
    else:
        print("⊘ Skipped (OPENAI_API_KEY not set)")
    
    # Example 2: Using local sentence-transformers embeddings
    print("\n2. Local Sentence-Transformers Embeddings")
    print("-" * 60)
    
    try:
        embedder = LocalEmbedder(model_name="all-MiniLM-L6-v2")
        embeddings = await embedder.embed(texts)
        
        print(f"✓ Generated {len(embeddings)} embeddings")
        print(f"  Embedding dimension: {len(embeddings[0])}")
        print(f"  First embedding (first 5 values): {embeddings[0][:5]}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Example 3: Batch processing
    print("\n3. Batch Processing")
    print("-" * 60)
    
    try:
        # Create many texts to demonstrate batching
        large_batch = [f"Sample text number {i}" for i in range(250)]
        
        embedder = LocalEmbedder(batch_size=100)
        embeddings = await embedder.embed(large_batch)
        
        print(f"✓ Processed {len(large_batch)} texts in batches of 100")
        print(f"  Generated {len(embeddings)} embeddings")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
