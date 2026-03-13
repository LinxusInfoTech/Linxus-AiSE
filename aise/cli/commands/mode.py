# aise/cli/commands/mode.py
"""aise mode command for operational mode management.

This module provides CLI commands for viewing and changing the operational mode
of the AiSE system. The system supports three modes:
- interactive: Respond to direct CLI commands only
- approval: Pause before executing tools or posting replies
- autonomous: Execute all operations without human intervention

Example usage:
    $ aise mode
    Current mode: approval
    
    $ aise mode set autonomous
    Mode changed to: autonomous
    
    $ aise mode set approval
    Mode changed to: approval
"""

import typer
from typing import Optional, Literal
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from datetime import datetime
import asyncio

from aise.core.config import get_config, load_config
from aise.core.database import get_database, initialize_database
from aise.core.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)
console = Console()

# Create mode command group
mode_app = typer.Typer(
    name="mode",
    help="View and change operational mode",
    no_args_is_help=False
)


@mode_app.callback(invoke_without_command=True)
def mode_callback(ctx: typer.Context):
    """Show current operational mode."""
    if ctx.invoked_subcommand is None:
        # No subcommand, show current mode
        show_current_mode()


def show_current_mode():
    """Display the current operational mode."""
    try:
        config = get_config()
        current_mode = config.AISE_MODE
        
        # Create mode description table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="cyan bold")
        table.add_column("Value")
        
        table.add_row("Current Mode", f"[bold green]{current_mode}[/bold green]")
        
        # Add mode descriptions
        mode_descriptions = {
            "interactive": "Respond to direct CLI commands only",
            "approval": "Pause before executing tools or posting replies",
            "autonomous": "Execute all operations without human intervention"
        }
        
        table.add_row("Description", mode_descriptions.get(current_mode, "Unknown mode"))
        
        console.print(Panel(table, title="Operational Mode", border_style="blue"))
        
        # Show available modes
        console.print("\n[bold]Available Modes:[/bold]")
        for mode, description in mode_descriptions.items():
            indicator = "→" if mode == current_mode else " "
            console.print(f"  {indicator} [cyan]{mode}[/cyan]: {description}")
        
        console.print("\n[dim]Use 'aise mode set <mode>' to change mode[/dim]")
        
    except RuntimeError as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Hint: Configuration not initialized. Run 'aise config show' first.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@mode_app.command("set")
def set_mode(
    mode: str = typer.Argument(
        ...,
        help="Mode to set: interactive, approval, or autonomous"
    )
):
    """Change the operational mode.
    
    Args:
        mode: The mode to set (interactive, approval, or autonomous)
    
    Examples:
        $ aise mode set approval
        $ aise mode set autonomous
        $ aise mode set interactive
    """
    # Validate mode
    valid_modes = ["interactive", "approval", "autonomous"]
    if mode not in valid_modes:
        console.print(f"[red]Error: Invalid mode '{mode}'[/red]")
        console.print(f"[yellow]Valid modes: {', '.join(valid_modes)}[/yellow]")
        raise typer.Exit(1)
    
    try:
        # Load config
        config = get_config()
        old_mode = config.AISE_MODE
        
        if old_mode == mode:
            console.print(f"[yellow]Mode is already set to: {mode}[/yellow]")
            return
        
        # Update mode in database
        asyncio.run(_update_mode_in_database(mode, old_mode))
        
        # Update config in memory
        config.AISE_MODE = mode
        
        console.print(f"[green]✓[/green] Mode changed from [cyan]{old_mode}[/cyan] to [bold green]{mode}[/bold green]")
        console.print("[dim]Changes applied immediately without restart[/dim]")
        
    except RuntimeError as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Hint: Configuration not initialized. Run 'aise config show' first.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error updating mode: {str(e)}[/red]")
        logger.error("mode_update_failed", error=str(e))
        raise typer.Exit(1)


async def _update_mode_in_database(new_mode: str, old_mode: str) -> None:
    """Update mode in database and log the change.
    
    Args:
        new_mode: The new mode to set
        old_mode: The previous mode
    """
    try:
        # Get database connection
        db = await get_database()
    except ConfigurationError:
        # Database not initialized, try to initialize it
        config = get_config()
        db = await initialize_database(config)
    
    async with db.pool.acquire() as conn:
        # Update configuration table
        await conn.execute(
            """
            INSERT INTO configuration (key, value, value_type, description, is_sensitive, updated_by)
            VALUES ($1, $2, 'string', 'Operational mode: interactive, approval, or autonomous', FALSE, 'cli')
            ON CONFLICT (key) DO UPDATE
            SET value = $2, updated_at = NOW(), updated_by = 'cli'
            """,
            "AISE_MODE",
            new_mode
        )
        
        # Log mode change in audit log
        await conn.execute(
            """
            INSERT INTO audit_log (
                event_type,
                user_id,
                component,
                action,
                resource_type,
                resource_id,
                details,
                timestamp,
                success
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            "mode_change",
            "cli_user",  # TODO: Get actual user from system
            "cli",
            "set_mode",
            "configuration",
            "AISE_MODE",
            {
                "old_mode": old_mode,
                "new_mode": new_mode,
                "changed_via": "cli"
            },
            datetime.utcnow(),
            True
        )
    
    logger.info(
        "mode_changed",
        old_mode=old_mode,
        new_mode=new_mode,
        changed_via="cli"
    )


@mode_app.command("history")
def mode_history(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Number of recent mode changes to show"
    )
):
    """Show mode change history.
    
    Args:
        limit: Number of recent changes to display (default: 10)
    
    Examples:
        $ aise mode history
        $ aise mode history --limit 20
        $ aise mode history -n 20
    """
    try:
        # Get mode change history from database
        history = asyncio.run(_get_mode_history(limit))
        
        if not history:
            console.print("[yellow]No mode changes recorded[/yellow]")
            return
        
        # Create history table
        table = Table(title="Mode Change History", show_header=True, header_style="bold cyan")
        table.add_column("Timestamp", style="dim")
        table.add_column("Old Mode", style="cyan")
        table.add_column("New Mode", style="green")
        table.add_column("Changed By", style="yellow")
        
        for record in history:
            timestamp = record["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            details = record["details"]
            old_mode = details.get("old_mode", "unknown")
            new_mode = details.get("new_mode", "unknown")
            changed_by = record.get("user_id", "unknown")
            
            table.add_row(timestamp, old_mode, new_mode, changed_by)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error retrieving mode history: {str(e)}[/red]")
        logger.error("mode_history_failed", error=str(e))
        raise typer.Exit(1)


async def _get_mode_history(limit: int) -> list:
    """Retrieve mode change history from database.
    
    Args:
        limit: Maximum number of records to retrieve
    
    Returns:
        List of mode change records
    """
    try:
        db = await get_database()
    except ConfigurationError:
        config = get_config()
        db = await initialize_database(config)
    
    async with db.pool.acquire() as conn:
        records = await conn.fetch(
            """
            SELECT event_type, user_id, component, action, details, timestamp
            FROM audit_log
            WHERE event_type = 'mode_change'
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit
        )
        
        return [dict(record) for record in records]


if __name__ == "__main__":
    mode_app()
