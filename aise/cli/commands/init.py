# aise/cli/commands/init.py
"""aise init command for documentation indexing.

This module provides CLI commands for initializing and managing the
documentation knowledge index.

Example usage:
    $ aise init                    # Index all sources
    $ aise init --force            # Re-index everything
    $ aise init --source aws       # Index only AWS
    $ aise init --list             # Show index status
    $ aise init --clear            # Delete all indexed knowledge
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich import box
from rich.prompt import Confirm
import structlog
import asyncio

from aise.knowledge_engine.sources import REGISTERED_SOURCES, get_source
from aise.knowledge_engine.init_runner import InitRunner
from aise.knowledge_engine.vector_store import ChromaDBVectorStore
from aise.core.config import get_config
from aise.core.exceptions import KnowledgeEngineError

logger = structlog.get_logger(__name__)
console = Console()

# Create init subcommand app
init_app = typer.Typer(
    name="init",
    help="Documentation indexing commands",
    no_args_is_help=True
)


@init_app.command()
def run(
    force: bool = typer.Option(False, "--force", "-f", help="Re-index all sources regardless of age"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Index only specific source(s), comma-separated")
):
    """Initialize documentation knowledge index.
    
    Crawls, chunks, embeds, and stores documentation from configured sources.
    Skips sources already indexed within KNOWLEDGE_MIN_REINIT_HOURS unless --force is used.
    """
    asyncio.run(_run_init(force=force, source=source))


async def _run_init(force: bool = False, source: Optional[str] = None):
    """Async implementation of init run."""
    try:
        # Load config
        config = get_config()
        
        # Initialize vector store
        vector_store = ChromaDBVectorStore(config)
        await vector_store.initialize()
        
        # Create init runner
        runner = InitRunner(config, vector_store)
        
        # Determine which sources to run
        if source:
            # Parse comma-separated sources
            source_names = [s.strip() for s in source.split(",")]
            sources_to_run = []
            
            for name in source_names:
                src = get_source(name)
                if not src:
                    console.print(f"[red]Source '{name}' not found in registry[/red]")
                    console.print("Run 'aise init --list' to see available sources")
                    raise typer.Exit(1)
                sources_to_run.append(src)
        else:
            # Run all sources
            sources_to_run = REGISTERED_SOURCES
        
        console.print(f"\n[cyan]Initializing documentation index...[/cyan]")
        console.print(f"[dim]Sources: {len(sources_to_run)}[/dim]")
        console.print(f"[dim]Force re-index: {force}[/dim]\n")
        
        # Run init for each source with progress bar
        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Indexing sources...", total=len(sources_to_run))
            
            for src in sources_to_run:
                progress.update(task, description=f"Indexing {src['name']}...")
                result = await runner.run_source(src["name"], src["url"], force=force)
                results.append(result)
                progress.advance(task)
        
        # Display summary table
        _display_summary_table(results)
        
        # Close vector store
        await vector_store.close()
        
    except Exception as e:
        logger.error("init_failed", error=str(e))
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)



@init_app.command()
def list():
    """Show status of all indexed documentation sources."""
    asyncio.run(_list_sources())


async def _list_sources():
    """Async implementation of list command."""
    try:
        # Load config
        config = get_config()
        
        # Initialize vector store
        vector_store = ChromaDBVectorStore(config)
        await vector_store.initialize()
        
        # Get all sources
        indexed_sources = await vector_store.list_all_sources()
        
        # Create lookup dict
        indexed_dict = {s["source_name"]: s for s in indexed_sources}
        
        # Create table
        table = Table(
            title="Documentation Index Status",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        
        table.add_column("Source", style="green", no_wrap=True)
        table.add_column("Chunks", justify="right", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("Last Crawled", style="blue")
        
        for src in REGISTERED_SOURCES:
            name = src["name"]
            if name in indexed_dict:
                indexed = indexed_dict[name]
                crawled_at = indexed.get("crawled_at", "")
                if crawled_at:
                    # Format timestamp
                    from datetime import datetime
                    dt = datetime.fromisoformat(crawled_at)
                    crawled_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    crawled_str = "Unknown"
                
                table.add_row(
                    name,
                    str(indexed.get("chunk_count", 0)),
                    "✅ indexed",
                    crawled_str
                )
            else:
                table.add_row(
                    name,
                    "---",
                    "[dim]not indexed[/dim]",
                    "---"
                )
        
        console.print("\n")
        console.print(table)
        console.print(f"\n[dim]Total sources: {len(REGISTERED_SOURCES)}[/dim]")
        console.print(f"[dim]Indexed: {len(indexed_sources)}[/dim]\n")
        
        # Close vector store
        await vector_store.close()
        
    except Exception as e:
        logger.error("list_sources_failed", error=str(e))
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@init_app.command()
def clear():
    """Delete all indexed knowledge (requires confirmation)."""
    asyncio.run(_clear_index())


async def _clear_index():
    """Async implementation of clear command."""
    try:
        # Confirm deletion
        console.print("\n[yellow]⚠ This will delete all indexed knowledge.[/yellow]")
        confirmed = Confirm.ask("Type YES to confirm", default=False)
        
        if not confirmed:
            console.print("[dim]Cancelled[/dim]")
            return
        
        # Load config
        config = get_config()
        
        # Initialize vector store
        vector_store = ChromaDBVectorStore(config)
        await vector_store.initialize()
        
        # Get all sources
        indexed_sources = await vector_store.list_all_sources()
        
        console.print(f"\n[cyan]Deleting {len(indexed_sources)} sources...[/cyan]\n")
        
        # Delete each source
        total_chunks = 0
        for source in indexed_sources:
            source_name = source["source_name"]
            chunks_deleted = await vector_store.delete_source(source_name)
            total_chunks += chunks_deleted
            console.print(f"  [dim]Deleted {source_name}: {chunks_deleted} chunks[/dim]")
        
        console.print(f"\n[green]✓ Deleted {total_chunks} chunks from {len(indexed_sources)} sources[/green]\n")
        
        # Close vector store
        await vector_store.close()
        
    except Exception as e:
        logger.error("clear_index_failed", error=str(e))
        console.print(f"\n[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _display_summary_table(results):
    """Display summary table of init results.
    
    Args:
        results: List of InitResult objects
    """
    table = Table(
        title="Indexing Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )
    
    table.add_column("Source", style="green", no_wrap=True)
    table.add_column("Chunks", justify="right", style="yellow")
    table.add_column("Status", style="magenta")
    table.add_column("Details", style="blue")
    
    for result in results:
        if result.error:
            status = "❌ error"
            details = result.error[:50]
        elif result.skipped:
            status = "⏭ skipped"
            details = result.skip_reason or "already fresh"
        else:
            status = "✅ indexed"
            details = f"{result.duration_seconds:.1f}s"
        
        table.add_row(
            result.source_name,
            str(result.chunks_indexed) if result.chunks_indexed > 0 else "---",
            status,
            details
        )
    
    console.print("\n")
    console.print(table)
    
    # Summary stats
    successful = sum(1 for r in results if r.error is None and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if r.error is not None)
    total_chunks = sum(r.chunks_indexed for r in results)
    
    console.print(f"\n[dim]Total: {len(results)} sources | "
                 f"Indexed: {successful} | Skipped: {skipped} | Failed: {failed} | "
                 f"Chunks: {total_chunks}[/dim]\n")
