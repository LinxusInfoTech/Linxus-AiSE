# aise/ticket_system/base.py
"""
Abstract base class for ticket system providers.

This module defines the interface that all ticket system integrations
must implement, along with common data models for tickets and messages.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional
import structlog

logger = structlog.get_logger(__name__)


class TicketStatus(str, Enum):
    """Ticket status enumeration."""
    OPEN = "open"
    PENDING = "pending"
    SOLVED = "solved"
    CLOSED = "closed"
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"


@dataclass
class Message:
    """Single message in a ticket thread.
    
    Attributes:
        id: Unique message identifier
        author: Name or email of message author
        body: Message content (plain text or HTML)
        is_customer: True if message is from customer, False if from agent
        created_at: Timestamp when message was created
    """
    id: str
    author: str
    body: str
    is_customer: bool
    created_at: datetime


@dataclass
class Ticket:
    """Ticket data structure.
    
    Attributes:
        id: Unique ticket identifier
        subject: Ticket subject line
        body: Initial ticket description/body
        customer_email: Email address of customer who created ticket
        status: Current ticket status
        tags: List of tags/labels applied to ticket
        created_at: Timestamp when ticket was created
        updated_at: Timestamp when ticket was last updated
        thread: List of messages in chronological order
    """
    id: str
    subject: str
    body: str
    customer_email: str
    status: TicketStatus
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    thread: List[Message]


class TicketProvider(ABC):
    """Abstract base class for ticket system providers.
    
    All ticket system integrations (Zendesk, Freshdesk, Email, Slack)
    must implement this interface to provide a consistent API for
    ticket operations.
    
    Example:
        >>> class MyTicketProvider(TicketProvider):
        ...     async def list_open(self, limit=50):
        ...         # Implementation
        ...         pass
    """
    
    @abstractmethod
    async def list_open(self, limit: int = 50) -> List[Ticket]:
        """List open tickets.
        
        Retrieves a list of open/pending tickets from the ticket system.
        
        Args:
            limit: Maximum number of tickets to return (default: 50)
        
        Returns:
            List of Ticket objects
        
        Raises:
            TicketSystemError: If API request fails
        """
        pass
    
    @abstractmethod
    async def get(self, ticket_id: str) -> Ticket:
        """Get ticket by ID.
        
        Retrieves a single ticket with its full thread of messages.
        
        Args:
            ticket_id: Unique ticket identifier
        
        Returns:
            Ticket object with complete message thread
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketSystemError: If API request fails
        """
        pass
    
    @abstractmethod
    async def reply(self, ticket_id: str, message: str) -> None:
        """Post reply to ticket.
        
        Adds a new message to the ticket thread from the agent/system.
        
        Args:
            ticket_id: Unique ticket identifier
            message: Reply message content (plain text or HTML)
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketSystemError: If API request fails
        """
        pass
    
    @abstractmethod
    async def close(self, ticket_id: str) -> None:
        """Close ticket.
        
        Marks the ticket as closed/solved in the ticket system.
        
        Args:
            ticket_id: Unique ticket identifier
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketSystemError: If API request fails
        """
        pass
    
    @abstractmethod
    async def add_tags(self, ticket_id: str, tags: List[str]) -> None:
        """Add tags to ticket.
        
        Adds one or more tags/labels to the ticket for categorization.
        
        Args:
            ticket_id: Unique ticket identifier
            tags: List of tag names to add
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketSystemError: If API request fails
        """
        pass
