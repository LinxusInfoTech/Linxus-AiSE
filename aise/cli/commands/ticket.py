# aise/cli/commands/ticket.py
"""aise ticket commands for ticket management.

This module provides CLI commands for viewing and managing tickets from
various ticket systems (Zendesk, Freshdesk, Email, Slack).

Example usage:
    $ aise ticket list
    $ aise ticket show 12345
"""

import typer
from typing import Optional
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from datetime import datetime
import asyncio

from aise.core.config import get_config
from aise.core.exceptions import TicketAPIError, TicketNotFoundError, ConfigurationError
from aise.ticket_system.base import TicketProvider, Ticket
from aise.ticket_system.zendesk import ZendeskProvider
from aise.ticket_system.freshdesk import FreshdeskProvider
from aise.ticket_system.email_provider import EmailProvider
from aise.ticket_system.slack_provider import SlackProvider
from aise.cli.output import console, print_error, print_warning

logger = structlog.get_logger(__name__)

# Create ticket command group
ticket_app = typer.Typer(
    name="ticket",
    help="Manage support tickets",
    no_args_is_help=True
)


def get_ticket_provider() -> TicketProvider:
    """Get configured ticket provider.
    
    Returns:
        TicketProvider instance
    
    Raises:
        ConfigurationError: If no ticket provider is configured
    """
    try:
        config = get_config()
    except RuntimeError:
        raise ConfigurationError("Configuration not initialized. Run 'aise config show' first.")
    
    # Check for Zendesk configuration
    if config.ZENDESK_SUBDOMAIN and config.ZENDESK_EMAIL and config.ZENDESK_API_TOKEN:
        logger.info("Using Zendesk provider")
        return ZendeskProvider(
            subdomain=config.ZENDESK_SUBDOMAIN,
            email=config.ZENDESK_EMAIL,
            api_token=config.ZENDESK_API_TOKEN
        )
    
    # Check for Freshdesk configuration
    if config.FRESHDESK_DOMAIN and config.FRESHDESK_API_KEY:
        logger.info("Using Freshdesk provider")
        return FreshdeskProvider(
            domain=config.FRESHDESK_DOMAIN,
            api_key=config.FRESHDESK_API_KEY
        )
    
    # Check for Email configuration
    if (config.EMAIL_IMAP_HOST and config.EMAIL_IMAP_USERNAME and 
        config.EMAIL_IMAP_PASSWORD and config.EMAIL_SMTP_HOST):
        logger.info("Using Email provider")
        return EmailProvider(
            imap_host=config.EMAIL_IMAP_HOST,
            imap_port=config.EMAIL_IMAP_PORT,
            imap_username=config.EMAIL_IMAP_USERNAME,
            imap_password=config.EMAIL_IMAP_PASSWORD,
            smtp_host=config.EMAIL_SMTP_HOST,
            smtp_port=config.EMAIL_SMTP_PORT,
            smtp_username=config.EMAIL_SMTP_USERNAME or config.EMAIL_IMAP_USERNAME,
            smtp_password=config.EMAIL_SMTP_PASSWORD or config.EMAIL_IMAP_PASSWORD
        )
    
    # Check for Slack configuration
    if config.SLACK_BOT_TOKEN:
        logger.info("Using Slack provider")
        return SlackProvider(
            bot_token=config.SLACK_BOT_TOKEN,
            signing_secret=config.SLACK_SIGNING_SECRET
        )
    
    raise ConfigurationError(
        "No ticket provider configured. Please configure one of: "
        "Zendesk, Freshdesk, Email, or Slack in your .env file or via 'aise config set'"
    )


@ticket_app.command("list")
def list_tickets(
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of tickets to display"
    )
):
    """List open tickets.
    
    Displays a table of open tickets from the configured ticket system,
    showing ticket ID, subject, customer, status, and creation date.
    
    Args:
        limit: Maximum number of tickets to display (default: 50)
    
    Examples:
        $ aise ticket list
        $ aise ticket list --limit 10
        $ aise ticket list -l 20
    """
    try:
        # Get ticket provider
        provider = get_ticket_provider()
        
        # Fetch open tickets
        console.print("[dim]Fetching open tickets...[/dim]")
        tickets = asyncio.run(provider.list_open(limit=limit))
        
        if not tickets:
            print_warning("No open tickets found")
            return
        
        # Create table
        table = Table(
            title=f"Open Tickets ({len(tickets)})",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        
        table.add_column("ID", style="yellow", no_wrap=True)
        table.add_column("Subject", style="white")
        table.add_column("Customer", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Created", style="dim")
        
        # Add rows
        for ticket in tickets:
            # Format created date
            created = ticket.created_at.strftime("%Y-%m-%d %H:%M")
            
            # Truncate subject if too long
            subject = ticket.subject
            if len(subject) > 60:
                subject = subject[:57] + "..."
            
            # Truncate customer email if too long
            customer = ticket.customer_email
            if len(customer) > 30:
                customer = customer[:27] + "..."
            
            # Format status with color
            status_colors = {
                "open": "green",
                "pending": "yellow",
                "new": "blue",
                "in_progress": "cyan",
                "on_hold": "magenta"
            }
            status_color = status_colors.get(ticket.status.value, "white")
            status_text = f"[{status_color}]{ticket.status.value}[/{status_color}]"
            
            table.add_row(
                ticket.id,
                subject,
                customer,
                status_text,
                created
            )
        
        console.print("\n")
        console.print(table)
        console.print("\n")
        console.print(f"[dim]Use 'aise ticket show <id>' to view ticket details[/dim]")
        
    except ConfigurationError as e:
        print_error(str(e), "Configure a ticket provider in your .env file")
        raise typer.Exit(1)
    except TicketAPIError as e:
        print_error(f"Ticket API error: {str(e)}", "Check your credentials and network connection")
        logger.error("ticket_list_failed", error=str(e))
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Failed to list tickets: {str(e)}")
        logger.error("ticket_list_failed", error=str(e))
        raise typer.Exit(1)


@ticket_app.command("show")
def show_ticket(
    ticket_id: str = typer.Argument(
        ...,
        help="Ticket ID to display"
    )
):
    """Show full ticket details including conversation thread.
    
    Displays complete ticket information including all messages in the
    conversation thread, formatted with rich panels for readability.
    
    Args:
        ticket_id: The ID of the ticket to display
    
    Examples:
        $ aise ticket show 12345
        $ aise ticket show TICKET-789
    """
    try:
        # Get ticket provider
        provider = get_ticket_provider()
        
        # Fetch ticket
        console.print(f"[dim]Fetching ticket {ticket_id}...[/dim]")
        ticket = asyncio.run(provider.get(ticket_id))
        
        # Display ticket header
        _display_ticket_header(ticket)
        
        # Display conversation thread
        if ticket.thread:
            _display_ticket_thread(ticket)
        else:
            console.print("\n[dim]No conversation thread available[/dim]\n")
        
    except ConfigurationError as e:
        print_error(str(e), "Configure a ticket provider in your .env file")
        raise typer.Exit(1)
    except TicketNotFoundError as e:
        print_error(f"Ticket not found: {ticket_id}", "Check the ticket ID and try again")
        raise typer.Exit(1)
    except TicketAPIError as e:
        print_error(f"Ticket API error: {str(e)}", "Check your credentials and network connection")
        logger.error("ticket_show_failed", ticket_id=ticket_id, error=str(e))
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Failed to retrieve ticket: {str(e)}")
        logger.error("ticket_show_failed", ticket_id=ticket_id, error=str(e))
        raise typer.Exit(1)


def _display_ticket_header(ticket: Ticket) -> None:
    """Display ticket header information.
    
    Args:
        ticket: Ticket object to display
    """
    # Create header table
    header_table = Table(show_header=False, box=None, padding=(0, 2))
    header_table.add_column("Label", style="cyan bold", no_wrap=True)
    header_table.add_column("Value")
    
    # Add ticket details
    header_table.add_row("ID", f"[yellow]{ticket.id}[/yellow]")
    header_table.add_row("Subject", f"[bold]{ticket.subject}[/bold]")
    header_table.add_row("Customer", ticket.customer_email)
    
    # Format status with color
    status_colors = {
        "open": "green",
        "pending": "yellow",
        "solved": "blue",
        "closed": "dim",
        "new": "cyan",
        "in_progress": "magenta",
        "on_hold": "yellow"
    }
    status_color = status_colors.get(ticket.status.value, "white")
    header_table.add_row("Status", f"[{status_color}]{ticket.status.value}[/{status_color}]")
    
    # Add timestamps
    created = ticket.created_at.strftime("%Y-%m-%d %H:%M:%S")
    updated = ticket.updated_at.strftime("%Y-%m-%d %H:%M:%S")
    header_table.add_row("Created", created)
    header_table.add_row("Updated", updated)
    
    # Add tags if present
    if ticket.tags:
        tags_str = ", ".join([f"[blue]{tag}[/blue]" for tag in ticket.tags])
        header_table.add_row("Tags", tags_str)
    
    # Display in panel
    console.print("\n")
    console.print(Panel(
        header_table,
        title="[bold cyan]Ticket Details[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    
    # Display ticket body
    if ticket.body:
        console.print("\n")
        console.print(Panel(
            ticket.body,
            title="[bold cyan]Description[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2)
        ))


def _display_ticket_thread(ticket: Ticket) -> None:
    """Display ticket conversation thread.
    
    Args:
        ticket: Ticket object with thread to display
    """
    console.print("\n")
    console.print(f"[bold cyan]Conversation Thread ({len(ticket.thread)} messages)[/bold cyan]")
    console.print()
    
    for i, message in enumerate(ticket.thread, 1):
        # Determine message style
        if message.is_customer:
            author_style = "yellow"
            border_style = "yellow"
            role = "Customer"
        else:
            author_style = "green"
            border_style = "green"
            role = "Agent"
        
        # Format timestamp
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create message header
        header = f"[{author_style}]{role}[/{author_style}] ({message.author}) • [dim]{timestamp}[/dim]"
        
        # Display message in panel
        console.print(Panel(
            message.body,
            title=header,
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 2)
        ))
        
        # Add spacing between messages (except after last)
        if i < len(ticket.thread):
            console.print()
    
    console.print()


if __name__ == "__main__":
    ticket_app()
