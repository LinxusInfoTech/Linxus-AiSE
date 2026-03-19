# aise/ticket_system/freshdesk.py
"""Freshdesk API ticket provider implementation."""

from datetime import datetime
from typing import List, Optional
import httpx
import structlog

from aise.ticket_system.base import TicketProvider, Ticket, Message, TicketStatus
from aise.core.exceptions import TicketAPIError, TicketNotFoundError

logger = structlog.get_logger(__name__)


class FreshdeskProvider(TicketProvider):
    """Freshdesk API v2 ticket provider.
    
    Implements the TicketProvider interface for Freshdesk Support.
    Uses the Freshdesk API v2 with API key authentication.
    
    Example:
        >>> provider = FreshdeskProvider(
        ...     domain="mycompany.freshdesk.com",
        ...     api_key="abc123..."
        ... )
        >>> tickets = await provider.list_open(limit=10)
    """
    
    def __init__(
        self,
        domain: str,
        api_key: str,
        timeout: int = 30
    ):
        """Initialize Freshdesk provider.
        
        Args:
            domain: Freshdesk domain (e.g., "mycompany.freshdesk.com")
            api_key: API key from Freshdesk profile settings
            timeout: Request timeout in seconds (default: 30)
        """
        self.domain = domain.replace("https://", "").replace("http://", "")
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = f"https://{self.domain}/api/v2"
        
        # Create HTTP client with authentication and explicit TLS verification
        # Freshdesk uses basic auth with API key as username and 'X' as password
        self.client = httpx.AsyncClient(
            auth=(api_key, "X"),
            timeout=timeout,
            verify=True,  # Enforce TLS certificate verification
            headers={"Content-Type": "application/json"}
        )
        
        logger.info("freshdesk_provider_initialized", domain=domain)
    
    async def list_open(self, limit: int = 50) -> List[Ticket]:
        """List open tickets from Freshdesk.
        
        Args:
            limit: Maximum number of tickets to return
        
        Returns:
            List of open Ticket objects
        
        Raises:
            TicketAPIError: If API request fails
        """
        try:
            logger.debug("listing_open_tickets", limit=limit)
            
            # Freshdesk API endpoint for tickets with filter
            url = f"{self.base_url}/tickets"
            params = {
                "filter": "new_and_my_open",  # Open tickets
                "per_page": min(limit, 100),  # Freshdesk max is 100
                "order_by": "updated_at",
                "order_type": "desc"
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            tickets_data = response.json()
            tickets = []
            
            for ticket_data in tickets_data:
                ticket = await self._parse_ticket(ticket_data)
                tickets.append(ticket)
            
            logger.info("open_tickets_listed", count=len(tickets))
            return tickets
            
        except httpx.HTTPStatusError as e:
            logger.error("freshdesk_api_error", status=e.response.status_code, error=str(e))
            raise TicketAPIError(
                f"Freshdesk API error: {e.response.status_code}",
                provider="freshdesk"
            )
        except Exception as e:
            logger.error("list_open_failed", error=str(e))
            raise TicketAPIError(f"Failed to list open tickets: {str(e)}", provider="freshdesk")
    
    async def get(self, ticket_id: str) -> Ticket:
        """Get ticket by ID with full thread.
        
        Args:
            ticket_id: Freshdesk ticket ID
        
        Returns:
            Ticket object with complete message thread
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketAPIError: If API request fails
        """
        try:
            logger.debug("getting_ticket", ticket_id=ticket_id)
            
            # Get ticket details
            ticket_url = f"{self.base_url}/tickets/{ticket_id}"
            ticket_response = await self.client.get(ticket_url)
            
            if ticket_response.status_code == 404:
                raise TicketNotFoundError(f"Ticket not found: {ticket_id}")
            
            ticket_response.raise_for_status()
            ticket_data = ticket_response.json()
            
            # Get ticket conversations (thread)
            conversations_url = f"{self.base_url}/tickets/{ticket_id}/conversations"
            conversations_response = await self.client.get(conversations_url)
            conversations_response.raise_for_status()
            conversations_data = conversations_response.json()
            
            # Parse ticket with thread
            ticket = await self._parse_ticket(ticket_data, conversations_data)
            
            logger.info("ticket_retrieved", ticket_id=ticket_id, messages=len(ticket.thread))
            return ticket
            
        except TicketNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("freshdesk_api_error", status=e.response.status_code, error=str(e))
            raise TicketAPIError(
                f"Freshdesk API error: {e.response.status_code}",
                provider="freshdesk"
            )
        except Exception as e:
            logger.error("get_ticket_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to get ticket: {str(e)}", provider="freshdesk")
    
    async def reply(self, ticket_id: str, message: str) -> None:
        """Post reply to ticket.
        
        Args:
            ticket_id: Freshdesk ticket ID
            message: Reply message content (HTML or plain text)
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketAPIError: If API request fails
        """
        try:
            logger.debug("posting_reply", ticket_id=ticket_id)
            
            url = f"{self.base_url}/tickets/{ticket_id}/reply"
            payload = {
                "body": message
            }
            
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 404:
                raise TicketNotFoundError(f"Ticket not found: {ticket_id}")
            
            response.raise_for_status()
            
            logger.info("reply_posted", ticket_id=ticket_id)
            
        except TicketNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("freshdesk_api_error", status=e.response.status_code, error=str(e))
            raise TicketAPIError(
                f"Freshdesk API error: {e.response.status_code}",
                provider="freshdesk"
            )
        except Exception as e:
            logger.error("reply_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to post reply: {str(e)}", provider="freshdesk")
    
    async def close(self, ticket_id: str) -> None:
        """Close ticket.
        
        Args:
            ticket_id: Freshdesk ticket ID
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketAPIError: If API request fails
        """
        try:
            logger.debug("closing_ticket", ticket_id=ticket_id)
            
            url = f"{self.base_url}/tickets/{ticket_id}"
            payload = {
                "status": 4  # Freshdesk status: 4 = Resolved
            }
            
            response = await self.client.put(url, json=payload)
            
            if response.status_code == 404:
                raise TicketNotFoundError(f"Ticket not found: {ticket_id}")
            
            response.raise_for_status()
            
            logger.info("ticket_closed", ticket_id=ticket_id)
            
        except TicketNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("freshdesk_api_error", status=e.response.status_code, error=str(e))
            raise TicketAPIError(
                f"Freshdesk API error: {e.response.status_code}",
                provider="freshdesk"
            )
        except Exception as e:
            logger.error("close_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to close ticket: {str(e)}", provider="freshdesk")
    
    async def add_tags(self, ticket_id: str, tags: List[str]) -> None:
        """Add tags to ticket.
        
        Args:
            ticket_id: Freshdesk ticket ID
            tags: List of tag names to add
        
        Raises:
            TicketNotFoundError: If ticket doesn't exist
            TicketAPIError: If API request fails
        """
        try:
            logger.debug("adding_tags", ticket_id=ticket_id, tags=tags)
            
            url = f"{self.base_url}/tickets/{ticket_id}"
            payload = {
                "tags": tags
            }
            
            response = await self.client.put(url, json=payload)
            
            if response.status_code == 404:
                raise TicketNotFoundError(f"Ticket not found: {ticket_id}")
            
            response.raise_for_status()
            
            logger.info("tags_added", ticket_id=ticket_id, tags=tags)
            
        except TicketNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            logger.error("freshdesk_api_error", status=e.response.status_code, error=str(e))
            raise TicketAPIError(
                f"Freshdesk API error: {e.response.status_code}",
                provider="freshdesk"
            )
        except Exception as e:
            logger.error("add_tags_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to add tags: {str(e)}", provider="freshdesk")
    
    async def _parse_ticket(
        self,
        ticket_data: dict,
        conversations_data: Optional[List[dict]] = None
    ) -> Ticket:
        """Parse Freshdesk API response into Ticket object.
        
        Args:
            ticket_data: Ticket data from Freshdesk API
            conversations_data: Optional conversations data for thread
        
        Returns:
            Ticket object
        """
        # Parse status
        # Freshdesk status codes: 2=Open, 3=Pending, 4=Resolved, 5=Closed
        status_map = {
            2: TicketStatus.OPEN,
            3: TicketStatus.PENDING,
            4: TicketStatus.SOLVED,
            5: TicketStatus.CLOSED
        }
        status = status_map.get(ticket_data.get("status", 2), TicketStatus.OPEN)
        
        # Parse thread
        thread = []
        if conversations_data:
            for conversation in conversations_data:
                # Skip private notes
                if conversation.get("private", False):
                    continue
                
                message = Message(
                    id=str(conversation["id"]),
                    author=str(conversation.get("user_id", "unknown")),
                    body=conversation.get("body_text", ""),
                    is_customer=conversation.get("incoming", True),
                    created_at=datetime.fromisoformat(
                        conversation["created_at"].replace("Z", "+00:00")
                    )
                )
                thread.append(message)
        
        # Create ticket
        ticket = Ticket(
            id=str(ticket_data["id"]),
            subject=ticket_data.get("subject", ""),
            body=ticket_data.get("description_text", ""),
            customer_email=ticket_data.get("email", "unknown"),
            status=status,
            tags=ticket_data.get("tags", []),
            created_at=datetime.fromisoformat(
                ticket_data["created_at"].replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                ticket_data["updated_at"].replace("Z", "+00:00")
            ),
            thread=thread
        )
        
        return ticket
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
