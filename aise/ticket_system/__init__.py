# aise/ticket_system/__init__.py
"""Ticket platform integrations."""

from aise.ticket_system.base import (
    TicketProvider,
    Ticket,
    Message,
    TicketStatus
)
from aise.ticket_system.email_provider import EmailProvider
from aise.ticket_system.memory import ConversationMemory
from aise.ticket_system.cleanup_job import ConversationCleanupJob

__all__ = [
    "TicketProvider",
    "Ticket",
    "Message",
    "TicketStatus",
    "EmailProvider",
    "ConversationMemory",
    "ConversationCleanupJob"
]
