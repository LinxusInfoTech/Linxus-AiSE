# aise/cli/commands/learn.py
"""aise learn command for documentation learning.

This module provides CLI commands for managing documentation sources,
including listing available sources and enabling pre-configured sources.

Example usage:
    $ aise learn list
    $ aise learn enable aws
    $ aise learn url https://docs.example.com --source-name example
"""

import typer
import asyncio
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich import box
import structlog

from aise.knowledge_engine.sources import get_registry, SourceCategory
from aise.knowledge_engine.crawler import DocumentCrawler
from aise.knowledge_engine.extractor import ContentExtractor
from aise.knowledge_engine.chunker import TextChunker
from aise.knowledge_engine.embedder import OpenAIEmbedder, LocalEmbedder
from aise.knowledge_engine.vector_store import ChromaDBVectorStore
from aise.knowledge_engine.metadata_store import MetadataStore
from aise.core.config import get_config, load_config
from aise.core.exceptions import KnowledgeEngineError

logger = structlog.get_logger(__name__)
console = Console()

# Create learn subcommand app
learn_app = typer.Typer(
    name="learn",
    help="Documentation learning commands",
    no_args_is_help=True
)


@learn_app.command()
def list():
    """List available pre-configured documentation sources."""
    asyncio.run(_list_async())


async def _list_async():
    """Async implementation of list command."""
    try:
        registry = get_registry()
        sources = registry.list_sources()
        
        if not sources:
            console.print("[yellow]No documentation sources found matching criteria[/yellow]")
            return
        
        # Initialize metadata store to get status
        config = load_config()
        metadata_store = MetadataStore(config)
        await metadata_store.initialize()
        
        # Get all learned sources
        learned_sources = await metadata_store.list_all_sources()
        learned_source_names = {s["source_name"] for s in learned_sources}
        
        # Create table
        table = Table(
            title="Available Documentation Sources",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        
        table.add_column("Name", style="green", no_wrap=True)
        table.add_column("Display Name", style="white")
        table.add_column("Category", style="blue")
        table.add_column("Size (MB)", justify="right", style="yellow")
        table.add_column("Pages", justify="right", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("Recommended", justify="center")
        
        # Add rows with actual status
        for source in sources:
            # Determine status
            if source.name in learned_source_names:
                status = "[green]Learned[/green]"
            else:
                status = "[dim]Not Learned[/dim]"
            
            table.add_row(
                source.name,
                source.display_name,
                source.category.value,
                str(source.estimated_size_mb),
                str(source.estimated_pages),
                status,
                "✓" if source.recommended else ""
            )
        
        console.print(table)
        console.print(f"\n[dim]Total sources: {len(sources)}[/dim]")
        console.print(f"[dim]Learned sources: {len(learned_source_names)}[/dim]")
        console.print("\n[cyan]To enable a source:[/cyan] aise learn enable <source_name>")
        
        await metadata_store.close()
        
    except Exception as e:
        logger.error("list_sources_failed", error=str(e))
        console.print(f"[red]Error listing sources: {str(e)}[/red]")
        raise typer.Exit(1)


@learn_app.command()
def enable(source_name: str):
    """Enable and learn from a pre-configured documentation source."""
    asyncio.run(_enable_async(source_name))


async def _enable_async(source_name: str):
    """Async implementation of enable command."""
    try:
        registry = get_registry()
        
        # Get source from registry
        source = registry.get_source(source_name)
        
        if not source:
            console.print(f"[red]Source '{source_name}' not found in registry[/red]")
            console.print("\n[cyan]Available sources:[/cyan]")
            console.print("Run 'aise learn list' to see all available sources")
            raise typer.Exit(1)
        
        # Display source information
        console.print(f"\n[cyan]Enabling documentation source:[/cyan] {source.display_name}")
        console.print(f"[dim]URL:[/dim] {source.url}")
        console.print(f"[dim]Category:[/dim] {source.category.value}")
        console.print(f"[dim]Estimated size:[/dim] {source.estimated_size_mb} MB ({source.estimated_pages} pages)")
        
        # Call the learning pipeline with the source URL and name
        await _learn_url_async(source.url, source.name)
        
        logger.info(
            "source_enabled",
            source_name=source_name,
            url=source.url,
            status="completed"
        )
        
    except KnowledgeEngineError as e:
        logger.error("enable_source_failed", source_name=source_name, error=str(e))
        console.print(f"[red]Error enabling source: {str(e)}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.error("enable_source_unexpected_error", source_name=source_name, error=str(e))
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        raise typer.Exit(1)


@learn_app.command(name="url")
def learn_url(
    url: str = typer.Option(..., "--url", help="URL to crawl and learn from"),
    source_name: str = typer.Option(..., "--source-name", help="Name for this documentation source")
):
    """Learn from a custom documentation URL."""
    asyncio.run(_learn_url_async(url, source_name))


async def _learn_url_async(url: str, source_name: str):
    """Async implementation of learn URL command."""
    try:
        # Load configuration
        config = load_config()
        
        # Display start message
        console.print(Panel(
            f"[cyan]Learning from documentation source[/cyan]\n\n"
            f"[white]Source:[/white] {source_name}\n"
            f"[white]URL:[/white] {url}",
            title="Documentation Learning",
            border_style="cyan"
        ))
        
        # Initialize components
        crawler = DocumentCrawler(
            max_depth=config.KNOWLEDGE_CRAWL_MAX_DEPTH,
            max_pages=config.MAX_CRAWL_PAGES,
            requests_per_second=2.0
        )
        extractor = ContentExtractor()
        chunker = TextChunker(
            chunk_size=config.KNOWLEDGE_CHUNK_SIZE,
            chunk_overlap=config.KNOWLEDGE_CHUNK_OVERLAP
        )
        
        # Initialize embedder based on configuration
        if config.EMBEDDING_MODEL == "openai":
            if not config.OPENAI_API_KEY:
                console.print("[red]Error: OPENAI_API_KEY not configured[/red]")
                raise typer.Exit(1)
            embedder = OpenAIEmbedder(api_key=config.OPENAI_API_KEY)
            embedding_model_name = "text-embedding-3-small"
        else:
            # Default to local embedder
            embedder = LocalEmbedder(model_name=config.LOCAL_EMBEDDING_MODEL)
            embedding_model_name = config.LOCAL_EMBEDDING_MODEL
        
        # Initialize vector store and metadata store
        vector_store = ChromaDBVectorStore(config)
        await vector_store.initialize()
        
        metadata_store = MetadataStore(config)
        await metadata_store.initialize()
        
        # Create progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            # Step 1: Crawl
            crawl_task = progress.add_task("[cyan]Crawling pages...", total=None)
            logger.info("crawl_started", url=url, source_name=source_name)
            
            crawled_urls = await crawler.crawl(url)
            progress.update(crawl_task, completed=True, description=f"[green]✓ Crawled {len(crawled_urls)} pages")
            
            if not crawled_urls:
                console.print("[yellow]No pages were crawled. Check the URL and try again.[/yellow]")
                raise typer.Exit(1)
            
            # Step 2: Extract and chunk
            extract_task = progress.add_task(
                "[cyan]Extracting content and chunking...",
                total=len(crawled_urls)
            )
            
            all_chunks = []
            for page_url in crawled_urls:
                try:
                    # Fetch page again for extraction (crawler doesn't return HTML)
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(page_url) as response:
                            if response.status == 200:
                                html = await response.text()
                                
                                # Extract content
                                markdown = await extractor.extract_content(page_url, html)
                                
                                # Chunk content
                                chunks = chunker.chunk(
                                    markdown,
                                    source_url=page_url,
                                    metadata={"source": source_name}
                                )
                                all_chunks.extend(chunks)
                except Exception as e:
                    logger.warning("page_processing_failed", url=page_url, error=str(e))
                
                progress.update(extract_task, advance=1)
            
            progress.update(
                extract_task,
                description=f"[green]✓ Created {len(all_chunks)} chunks from {len(crawled_urls)} pages"
            )
            
            if not all_chunks:
                console.print("[yellow]No content chunks were created. The pages may be empty or inaccessible.[/yellow]")
                raise typer.Exit(1)
            
            # Step 3: Generate embeddings
            embed_task = progress.add_task(
                "[cyan]Generating embeddings...",
                total=len(all_chunks)
            )
            
            # Extract text from chunks
            chunk_texts = [chunk.content for chunk in all_chunks]
            
            # Generate embeddings in batches
            embeddings = await embedder.embed(chunk_texts)
            
            # Assign embeddings to chunks
            for chunk, embedding in zip(all_chunks, embeddings):
                chunk.embedding = embedding
            
            progress.update(
                embed_task,
                completed=len(all_chunks),
                description=f"[green]✓ Generated {len(embeddings)} embeddings"
            )
            
            # Step 4: Store in vector database
            store_task = progress.add_task("[cyan]Storing in vector database...", total=None)
            
            await vector_store.upsert(all_chunks)
            
            progress.update(store_task, completed=True, description="[green]✓ Stored in vector database")
            
            # Step 5: Record metadata
            metadata_task = progress.add_task("[cyan]Recording metadata...", total=None)
            
            await metadata_store.record_crawl(
                source_name=source_name,
                url=url,
                pages_crawled=len(crawled_urls),
                chunks_created=len(all_chunks),
                embedding_model=embedding_model_name
            )
            
            progress.update(metadata_task, completed=True, description="[green]✓ Metadata recorded")
        
        # Calculate statistics
        total_tokens = sum(len(chunk.content.split()) for chunk in all_chunks)
        avg_chunk_size = sum(len(chunk.content) for chunk in all_chunks) // len(all_chunks)
        
        # Display final statistics
        console.print("\n")
        console.print(Panel(
            f"[green]✓ Documentation learning completed successfully![/green]\n\n"
            f"[white]Pages crawled:[/white] {len(crawled_urls)}\n"
            f"[white]Chunks created:[/white] {len(all_chunks)}\n"
            f"[white]Average chunk size:[/white] {avg_chunk_size} characters\n"
            f"[white]Estimated tokens:[/white] ~{total_tokens:,}\n"
            f"[white]Source name:[/white] {source_name}",
            title="Learning Statistics",
            border_style="green"
        ))
        
        logger.info(
            "learn_completed",
            source_name=source_name,
            url=url,
            pages_crawled=len(crawled_urls),
            chunks_created=len(all_chunks),
            total_tokens=total_tokens
        )
        
        # Close stores
        await vector_store.close()
        await metadata_store.close()
        
    except KnowledgeEngineError as e:
        logger.error("learn_failed", url=url, source_name=source_name, error=str(e))
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.error("learn_unexpected_error", url=url, source_name=source_name, error=str(e))
        console.print(f"\n[red]Unexpected error: {str(e)}[/red]")
        console.print(f"[dim]{type(e).__name__}: {str(e)}[/dim]")
        raise typer.Exit(1)
