# aise/cli/output.py
"""Rich output formatting utilities for CLI.

This module provides helper functions for formatting CLI output using Rich,
including panels, tables, progress bars, and streaming text display.

Example usage:
    >>> from aise.cli.output import print_panel, print_diagnosis
    >>> 
    >>> print_panel("Success!", "Operation completed", style="green")
    >>> print_diagnosis("EC2 instance is unreachable due to security group rules...")
"""

from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import box
import structlog

logger = structlog.get_logger(__name__)

# Global console instance
console = Console()


def print_panel(
    title: str,
    content: str,
    style: str = "cyan",
    border_style: str = "cyan"
):
    """Print content in a Rich panel.
    
    Args:
        title: Panel title
        content: Panel content
        style: Content style color
        border_style: Border style color
    """
    panel = Panel(
        content,
        title=title,
        style=style,
        border_style=border_style,
        box=box.ROUNDED
    )
    console.print(panel)


def print_diagnosis(diagnosis: str):
    """Print diagnosis with markdown formatting.
    
    Args:
        diagnosis: Diagnosis text (supports markdown)
    """
    console.print("\n")
    console.print(Panel(
        Markdown(diagnosis),
        title="[bold cyan]Diagnosis[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2)
    ))
    console.print("\n")


def print_error(message: str, details: Optional[str] = None):
    """Print error message in red panel.
    
    Args:
        message: Error message
        details: Optional error details
    """
    content = f"[bold red]Error:[/bold red] {message}"
    if details:
        content += f"\n\n[dim]{details}[/dim]"
    
    console.print("\n")
    console.print(Panel(
        content,
        border_style="red",
        box=box.ROUNDED
    ))
    console.print("\n")


def print_success(message: str):
    """Print success message in green panel.
    
    Args:
        message: Success message
    """
    console.print("\n")
    console.print(Panel(
        f"[bold green]✓[/bold green] {message}",
        border_style="green",
        box=box.ROUNDED
    ))
    console.print("\n")


def print_warning(message: str):
    """Print warning message in yellow panel.
    
    Args:
        message: Warning message
    """
    console.print("\n")
    console.print(Panel(
        f"[bold yellow]⚠[/bold yellow] {message}",
        border_style="yellow",
        box=box.ROUNDED
    ))
    console.print("\n")


def print_info(message: str):
    """Print info message in blue panel.
    
    Args:
        message: Info message
    """
    console.print("\n")
    console.print(Panel(
        f"[bold blue]ℹ[/bold blue] {message}",
        border_style="blue",
        box=box.ROUNDED
    ))
    console.print("\n")


def print_table(
    title: str,
    columns: List[str],
    rows: List[List[str]],
    show_header: bool = True
):
    """Print data in a Rich table.
    
    Args:
        title: Table title
        columns: Column headers
        rows: Table rows
        show_header: Whether to show header row
    """
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=show_header,
        header_style="bold cyan"
    )
    
    # Add columns
    for col in columns:
        table.add_column(col)
    
    # Add rows
    for row in rows:
        table.add_row(*row)
    
    console.print("\n")
    console.print(table)
    console.print("\n")


def print_code(code: str, language: str = "bash"):
    """Print code with syntax highlighting.
    
    Args:
        code: Code to display
        language: Programming language for syntax highlighting
    """
    syntax = Syntax(code, language, theme="monokai", line_numbers=False)
    console.print("\n")
    console.print(syntax)
    console.print("\n")


def stream_text(text_generator):
    """Stream text output token by token.
    
    Args:
        text_generator: Generator yielding text tokens
    """
    for token in text_generator:
        console.print(token, end="")
    console.print()  # Final newline


async def stream_text_async(text_generator):
    """Stream text output token by token (async).
    
    Args:
        text_generator: Async generator yielding text tokens
    """
    async for token in text_generator:
        console.print(token, end="", flush=True)
    console.print()  # Final newline


def print_key_value(data: Dict[str, Any], title: Optional[str] = None):
    """Print key-value pairs in a formatted table.
    
    Args:
        data: Dictionary of key-value pairs
        title: Optional table title
    """
    table = Table(
        title=title,
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 2)
    )
    
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    for key, value in data.items():
        table.add_row(key, str(value))
    
    console.print("\n")
    console.print(table)
    console.print("\n")


def print_list(items: List[str], title: Optional[str] = None, style: str = "cyan"):
    """Print a bulleted list.
    
    Args:
        items: List items
        title: Optional title
        style: Style color
    """
    if title:
        console.print(f"\n[bold {style}]{title}[/bold {style}]")
    
    for item in items:
        console.print(f"  • {item}")
    
    console.print()


def create_progress() -> Progress:
    """Create a Rich progress bar.
    
    Returns:
        Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    )


def print_separator(char: str = "─", length: int = 80):
    """Print a separator line.
    
    Args:
        char: Character to use for separator
        length: Length of separator
    """
    console.print(f"[dim]{char * length}[/dim]")
