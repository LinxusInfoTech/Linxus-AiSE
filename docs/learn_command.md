# Learn Command Documentation

The `aise learn` command allows you to crawl and learn from documentation websites, making the knowledge available for the AI Support Engineer to reference when answering questions.

## Commands

### List Available Sources

List all pre-configured documentation sources:

```bash
aise learn list
```

This displays a table showing:
- Source name
- Display name
- Category (Cloud, Container, IaC, etc.)
- Estimated size and page count
- Current status (Not Learned, Learning, Learned, Error)
- Whether the source is recommended

### Enable Pre-configured Source

Enable and learn from a pre-configured documentation source:

```bash
aise learn enable <source_name>
```

Example:
```bash
aise learn enable aws
```

### Learn from Custom URL

Learn from a custom documentation URL:

```bash
aise learn url --url <url> --source-name <name>
```

Example:
```bash
aise learn url --url https://docs.example.com --source-name example-docs
```

## What Happens During Learning

When you run a learn command, the system:

1. **Crawls** the documentation website
   - Respects robots.txt and rate limits
   - Follows links up to configured max depth
   - Limits total pages crawled to prevent runaway crawling

2. **Extracts** content from each page
   - Removes navigation, ads, and other non-content elements
   - Converts HTML to clean Markdown
   - Preserves heading structure for context

3. **Chunks** the content
   - Splits text into semantic chunks with configurable size
   - Maintains heading context for each chunk
   - Overlaps chunks to preserve context at boundaries

4. **Generates embeddings**
   - Creates vector embeddings for each chunk
   - Uses OpenAI or local sentence-transformers model
   - Enables semantic search across documentation

5. **Stores** in vector database
   - Saves chunks and embeddings to ChromaDB
   - Records metadata in PostgreSQL
   - Makes knowledge available for retrieval

## Progress Display

The command shows real-time progress with:
- Crawling progress (pages discovered and crawled)
- Extraction and chunking progress
- Embedding generation progress
- Storage progress

## Final Statistics

After completion, displays:
- Total pages crawled
- Total chunks created
- Average chunk size
- Estimated token count
- Source name for future reference

## Configuration

The learning process is controlled by configuration settings:

- `KNOWLEDGE_CRAWL_MAX_DEPTH`: Maximum depth to follow links (default: 3)
- `MAX_CRAWL_PAGES`: Maximum pages to crawl (default: 1000)
- `KNOWLEDGE_CHUNK_SIZE`: Target chunk size in characters (default: 1000)
- `KNOWLEDGE_CHUNK_OVERLAP`: Overlap between chunks (default: 150)
- `EMBEDDING_MODEL`: Provider to use ("openai" or "sentence-transformers")
- `LOCAL_EMBEDDING_MODEL`: Model name for local embeddings (default: "all-MiniLM-L6-v2")

## Requirements

- OpenAI API key (if using OpenAI embeddings)
- PostgreSQL database (for metadata)
- ChromaDB (for vector storage)
- Internet connection (for crawling)

## Error Handling

The command handles errors gracefully:
- Invalid URLs are rejected with clear error messages
- Network errors during crawling are logged but don't stop the process
- Failed pages are skipped and reported in logs
- Configuration errors are caught early with helpful messages
