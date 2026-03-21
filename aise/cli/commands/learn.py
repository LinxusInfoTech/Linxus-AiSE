# aise/cli/commands/learn.py
"""aise learn command for documentation learning.

Example usage:
    $ aise learn list
    $ aise learn enable aws
    $ aise learn url --url https://docs.example.com --source-name example
"""

import typer
import asyncio
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich import box
import structlog

from aise.knowledge_engine.sources import get_registry
from aise.knowledge_engine.crawler import DocumentCrawler
from aise.knowledge_engine.extractor import ContentExtractor
from aise.knowledge_engine.chunker import TextChunker
from aise.knowledge_engine.embedder import OpenAIEmbedder, LocalEmbedder
from aise.knowledge_engine.vector_store import ChromaDBVectorStore
from aise.knowledge_engine.metadata_store import MetadataStore
from aise.knowledge_engine.init_runner import InitRunner
from aise.core.config import load_config
from aise.core.exceptions import KnowledgeEngineError

logger = structlog.get_logger(__name__)
console = Console()

learn_app = typer.Typer(
    name="learn",
    help="Documentation learning commands",
    no_args_is_help=True
)


def _build_runner(config) -> InitRunner:
    """Build a fully wired InitRunner from config."""
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

    if config.EMBEDDING_MODEL == "openai":
        if not config.OPENAI_API_KEY:
            console.print("[red]Error: OPENAI_API_KEY not configured[/red]")
            raise typer.Exit(1)
        embedder = OpenAIEmbedder(api_key=config.OPENAI_API_KEY)
    else:
        embedder = LocalEmbedder(model_name=config.LOCAL_EMBEDDING_MODEL)

    vector_store = ChromaDBVectorStore(config)
    return InitRunner(config, vector_store, crawler, extractor, chunker, embedder), vector_store


@learn_app.command()
def list():
    """List available pre-configured documentation sources."""
    asyncio.run(_list_async())


async def _list_async():
    try:
        registry = get_registry()
        sources = registry.list_sources()

        config = load_config()
        metadata_store = MetadataStore(config)
        await metadata_store.initialize()
        learned = {s["source_name"] for s in await metadata_store.list_all_sources()}
        await metadata_store.close()

        table = Table(
            title="Available Documentation Sources",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Name", style="green", no_wrap=True)
        table.add_column("Display Name", style="white")
        table.add_column("Category", style="blue")
        table.add_column("Est. Size (MB)", justify="right", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("Recommended", justify="center")

        for source in sources:
            status = "[green]Learned[/green]" if source.name in learned else "[dim]Not Learned[/dim]"
            table.add_row(
                source.name,
                source.display_name,
                source.category.value,
                str(source.estimated_size_mb),
                status,
                "✓" if source.recommended else ""
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(sources)} | Learned: {len(learned)}[/dim]")
        console.print("\n[cyan]To enable a source:[/cyan] aise learn enable <name>")

    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@learn_app.command()
def enable(source_name: str):
    """Enable and learn from a pre-configured documentation source."""
    asyncio.run(_enable_async(source_name))


async def _enable_async(source_name: str):
    registry = get_registry()
    source = registry.get_source(source_name)

    if not source:
        console.print(f"[red]Source '{source_name}' not found. Run 'aise learn list' to see available sources.[/red]")
        raise typer.Exit(1)

    console.print(f"\n[cyan]Enabling:[/cyan] {source.display_name}")
    console.print(f"[dim]URL:[/dim] {source.url}")
    await _run_pipeline(source.url, source.name)


@learn_app.command(name="url")
def learn_url(
    url: str = typer.Option(..., "--url", help="URL to crawl and learn from"),
    source_name: str = typer.Option(..., "--source-name", help="Name for this documentation source")
):
    """Learn from a custom documentation URL."""
    asyncio.run(_run_pipeline(url, source_name))


async def _run_pipeline(url: str, source_name: str):
    """Run the full crawl → extract → chunk → embed → store pipeline."""
    try:
        config = load_config()
        runner, vector_store = _build_runner(config)

        console.print(Panel(
            f"[white]Source:[/white] {source_name}\n[white]URL:[/white] {url}",
            title="Documentation Learning",
            border_style="cyan"
        ))

        await vector_store.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Learning {source_name}...", total=None)
            result = await runner.run_source(source_name, url)
            progress.update(task, completed=True)

        if result.error:
            console.print(f"\n[red]Error: {result.error}[/red]")
            raise typer.Exit(1)

        if result.skipped:
            console.print(f"\n[yellow]Skipped:[/yellow] {result.skip_reason}")
            return

        console.print(Panel(
            f"[green]✓ Completed[/green]\n\n"
            f"[white]Chunks indexed:[/white] {result.chunks_indexed}\n"
            f"[white]Duration:[/white] {result.duration_seconds:.1f}s",
            title="Learning Statistics",
            border_style="green"
        ))

        await vector_store.close()

    except KnowledgeEngineError as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {type(e).__name__}: {str(e)}[/red]")
        raise typer.Exit(1)
