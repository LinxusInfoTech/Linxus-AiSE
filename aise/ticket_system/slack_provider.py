# aise/ticket_system/slack_provider.py
"""Slack bot ticket provider implementation."""

import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
import structlog
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from aise.ticket_system.base import TicketProvider, Ticket, Message, TicketStatus
from aise.core.exceptions import TicketAPIError, TicketNotFoundError

logger = structlog.get_logger(__name__)


class SlackProvider(TicketProvider):
    """Slack bot ticket provider.
    
    Implements the TicketProvider interface for Slack.
    Uses the Slack Web API with bot token authentication.
    Maps Slack threads to the Ticket structure where:
    - A Slack thread (message + replies) represents a ticket
    - The thread timestamp (ts) is the ticket ID
    - Thread replies are ticket messages
    
    Example:
        >>> provider = SlackProvider(
        ...     bot_token="xoxb-...",
        ...     signing_secret="abc123..."
        ... )
        >>> tickets = await provider.list_open(limit=10)
    """
    
    def __init__(
        self,
        bot_token: str,
        signing_secret: Optional[str] = None,
        channel_id: Optional[str] = None,
        timeout: int = 30
    ):
        """Initialize Slack provider.
        
        Args:
            bot_token: Slack bot token (starts with xoxb-)
            signing_secret: Slack signing secret for webhook verification
            channel_id: Default channel ID to monitor (optional)
            timeout: Request timeout in seconds (default: 30)
        """
        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.channel_id = channel_id
        self.timeout = timeout
        
        # Create Slack client
        self.client = AsyncWebClient(token=bot_token, timeout=timeout)
        
        logger.info("slack_provider_initialized", channel_id=channel_id)
    
    async def list_open(self, limit: int = 50) -> List[Ticket]:
        """List open tickets from Slack.
        
        Retrieves recent messages from the configured channel that have
        not been marked as resolved (no ✅ reaction).
        
        Args:
            limit: Maximum number of tickets to return
        
        Returns:
            List of open Ticket objects (Slack threads)
        
        Raises:
            TicketAPIError: If Slack API request fails
        """
        try:
            logger.debug("listing_open_tickets", limit=limit, channel_id=self.channel_id)
            
            if not self.channel_id:
                logger.warning("no_channel_configured")
                return []
            
            # Get recent messages from channel
            response = await self.client.conversations_history(
                channel=self.channel_id,
                limit=limit
            )
            
            if not response["ok"]:
                raise TicketAPIError(
                    f"Slack API error: {response.get('error', 'unknown')}",
                    provider="slack"
                )
            
            tickets = []
            for message in response.get("messages", []):
                # Skip bot messages and messages without text
                if message.get("bot_id") or not message.get("text"):
                    continue
                
                # Check if message is marked as resolved (has checkmark reaction)
                is_resolved = await self._is_resolved(message)
                if is_resolved:
                    continue
                
                # Parse message into ticket
                ticket = await self._parse_ticket(message)
                tickets.append(ticket)
            
            logger.info("open_tickets_listed", count=len(tickets))
            return tickets
            
        except SlackApiError as e:
            logger.error("slack_api_error", error=str(e))
            raise TicketAPIError(
                f"Slack API error: {e.response['error']}",
                provider="slack"
            )
        except Exception as e:
            logger.error("list_open_failed", error=str(e))
            raise TicketAPIError(f"Failed to list open tickets: {str(e)}", provider="slack")
    
    async def get(self, ticket_id: str) -> Ticket:
        """Get ticket by ID (Slack thread timestamp).
        
        Args:
            ticket_id: Slack message timestamp (thread_ts)
        
        Returns:
            Ticket object with complete message thread
        
        Raises:
            TicketNotFoundError: If message doesn't exist
            TicketAPIError: If Slack API request fails
        """
        try:
            logger.debug("getting_ticket", ticket_id=ticket_id)
            
            if not self.channel_id:
                raise TicketAPIError("No channel configured", provider="slack")
            
            # Parse ticket_id to extract channel and timestamp
            # Format: channel_id:timestamp or just timestamp
            if ":" in ticket_id:
                channel_id, ts = ticket_id.split(":", 1)
            else:
                channel_id = self.channel_id
                ts = ticket_id
            
            # Get the parent message
            response = await self.client.conversations_history(
                channel=channel_id,
                latest=ts,
                limit=1,
                inclusive=True
            )
            
            if not response["ok"]:
                raise TicketAPIError(
                    f"Slack API error: {response.get('error', 'unknown')}",
                    provider="slack"
                )
            
            messages = response.get("messages", [])
            if not messages:
                raise TicketNotFoundError(f"Message not found: {ticket_id}")
            
            parent_message = messages[0]
            
            # Get thread replies
            thread_response = await self.client.conversations_replies(
                channel=channel_id,
                ts=ts
            )
            
            if not thread_response["ok"]:
                raise TicketAPIError(
                    f"Slack API error: {thread_response.get('error', 'unknown')}",
                    provider="slack"
                )
            
            # Parse ticket with full thread
            ticket = await self._parse_ticket(
                parent_message,
                thread_messages=thread_response.get("messages", []),
                channel_id=channel_id
            )
            
            logger.info("ticket_retrieved", ticket_id=ticket_id, messages=len(ticket.thread))
            return ticket
            
        except TicketNotFoundError:
            raise
        except SlackApiError as e:
            logger.error("slack_api_error", error=str(e))
            raise TicketAPIError(
                f"Slack API error: {e.response['error']}",
                provider="slack"
            )
        except Exception as e:
            logger.error("get_ticket_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to get ticket: {str(e)}", provider="slack")
    
    async def reply(self, ticket_id: str, message: str) -> None:
        """Post reply to ticket (Slack thread).
        
        Args:
            ticket_id: Slack message timestamp (thread_ts)
            message: Reply message content (plain text or Slack markdown)
        
        Raises:
            TicketNotFoundError: If thread doesn't exist
            TicketAPIError: If Slack API request fails
        """
        try:
            logger.debug("posting_reply", ticket_id=ticket_id)
            
            # Parse ticket_id to extract channel and timestamp
            if ":" in ticket_id:
                channel_id, ts = ticket_id.split(":", 1)
            else:
                if not self.channel_id:
                    raise TicketAPIError("No channel configured", provider="slack")
                channel_id = self.channel_id
                ts = ticket_id
            
            # Post reply to thread
            response = await self.client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                text=message
            )
            
            if not response["ok"]:
                raise TicketAPIError(
                    f"Slack API error: {response.get('error', 'unknown')}",
                    provider="slack"
                )
            
            logger.info("reply_posted", ticket_id=ticket_id)
            
        except SlackApiError as e:
            logger.error("slack_api_error", error=str(e))
            raise TicketAPIError(
                f"Slack API error: {e.response['error']}",
                provider="slack"
            )
        except Exception as e:
            logger.error("reply_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to post reply: {str(e)}", provider="slack")
    
    async def close(self, ticket_id: str) -> None:
        """Close ticket (add checkmark reaction to mark as resolved).
        
        Args:
            ticket_id: Slack message timestamp (thread_ts)
        
        Raises:
            TicketNotFoundError: If message doesn't exist
            TicketAPIError: If Slack API request fails
        """
        try:
            logger.debug("closing_ticket", ticket_id=ticket_id)
            
            # Parse ticket_id to extract channel and timestamp
            if ":" in ticket_id:
                channel_id, ts = ticket_id.split(":", 1)
            else:
                if not self.channel_id:
                    raise TicketAPIError("No channel configured", provider="slack")
                channel_id = self.channel_id
                ts = ticket_id
            
            # Add checkmark reaction to mark as resolved
            response = await self.client.reactions_add(
                channel=channel_id,
                timestamp=ts,
                name="white_check_mark"
            )
            
            if not response["ok"]:
                # If reaction already exists, that's okay
                if response.get("error") != "already_reacted":
                    raise TicketAPIError(
                        f"Slack API error: {response.get('error', 'unknown')}",
                        provider="slack"
                    )
            
            logger.info("ticket_closed", ticket_id=ticket_id)
            
        except SlackApiError as e:
            logger.error("slack_api_error", error=str(e))
            raise TicketAPIError(
                f"Slack API error: {e.response['error']}",
                provider="slack"
            )
        except Exception as e:
            logger.error("close_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to close ticket: {str(e)}", provider="slack")
    
    async def add_tags(self, ticket_id: str, tags: List[str]) -> None:
        """Add tags to ticket (add as emoji reactions).
        
        Maps tags to emoji reactions on the message.
        
        Args:
            ticket_id: Slack message timestamp (thread_ts)
            tags: List of tag names to add as reactions
        
        Raises:
            TicketNotFoundError: If message doesn't exist
            TicketAPIError: If Slack API request fails
        """
        try:
            logger.debug("adding_tags", ticket_id=ticket_id, tags=tags)
            
            # Parse ticket_id to extract channel and timestamp
            if ":" in ticket_id:
                channel_id, ts = ticket_id.split(":", 1)
            else:
                if not self.channel_id:
                    raise TicketAPIError("No channel configured", provider="slack")
                channel_id = self.channel_id
                ts = ticket_id
            
            # Map common tags to emoji
            tag_emoji_map = {
                "urgent": "rotating_light",
                "bug": "bug",
                "feature": "sparkles",
                "question": "question",
                "aws": "cloud",
                "kubernetes": "kubernetes",
                "docker": "docker",
                "database": "database",
                "network": "globe_with_meridians"
            }
            
            # Add reactions for each tag
            for tag in tags:
                emoji = tag_emoji_map.get(tag.lower(), "label")
                try:
                    await self.client.reactions_add(
                        channel=channel_id,
                        timestamp=ts,
                        name=emoji
                    )
                except SlackApiError as e:
                    # Ignore if reaction already exists
                    if e.response.get("error") != "already_reacted":
                        logger.warning("failed_to_add_reaction", tag=tag, error=str(e))
            
            logger.info("tags_added", ticket_id=ticket_id, tags=tags)
            
        except Exception as e:
            logger.error("add_tags_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to add tags: {str(e)}", provider="slack")
    
    async def _is_resolved(self, message: Dict[str, Any]) -> bool:
        """Check if message is marked as resolved.
        
        Args:
            message: Slack message object
        
        Returns:
            True if message has checkmark reaction, False otherwise
        """
        reactions = message.get("reactions", [])
        for reaction in reactions:
            if reaction.get("name") == "white_check_mark":
                return True
        return False
    
    async def _parse_ticket(
        self,
        message: Dict[str, Any],
        thread_messages: Optional[List[Dict[str, Any]]] = None,
        channel_id: Optional[str] = None
    ) -> Ticket:
        """Parse Slack message into Ticket object.
        
        Args:
            message: Parent Slack message
            thread_messages: Optional list of thread replies
            channel_id: Channel ID for the message
        
        Returns:
            Ticket object
        """
        # Use provided channel_id or fall back to configured one
        channel = channel_id or self.channel_id or "unknown"
        
        # Extract message details
        ts = message.get("ts", "")
        text = message.get("text", "")
        user_id = message.get("user", "unknown")
        
        # Parse timestamp
        try:
            timestamp = float(ts)
            created_at = datetime.fromtimestamp(timestamp)
        except:
            created_at = datetime.now()
        
        # Get user info for email
        user_email = await self._get_user_email(user_id)
        
        # Parse thread
        thread = []
        if thread_messages:
            for msg in thread_messages:
                msg_user_id = msg.get("user", "unknown")
                msg_user_email = await self._get_user_email(msg_user_id)
                
                # Determine if message is from customer (not from bot)
                is_customer = not msg.get("bot_id")
                
                try:
                    msg_timestamp = float(msg.get("ts", "0"))
                    msg_created_at = datetime.fromtimestamp(msg_timestamp)
                except:
                    msg_created_at = datetime.now()
                
                thread_message = Message(
                    id=msg.get("ts", ""),
                    author=msg_user_email,
                    body=msg.get("text", ""),
                    is_customer=is_customer,
                    created_at=msg_created_at
                )
                thread.append(thread_message)
        else:
            # Single message thread
            thread = [
                Message(
                    id=ts,
                    author=user_email,
                    body=text,
                    is_customer=True,
                    created_at=created_at
                )
            ]
        
        # Extract tags from reactions
        tags = []
        reactions = message.get("reactions", [])
        for reaction in reactions:
            emoji = reaction.get("name", "")
            if emoji and emoji != "white_check_mark":
                tags.append(emoji)
        
        # Determine status based on reactions
        is_resolved = await self._is_resolved(message)
        status = TicketStatus.CLOSED if is_resolved else TicketStatus.OPEN
        
        # Create ticket ID with channel prefix
        ticket_id = f"{channel}:{ts}"
        
        # Extract subject from first line of text
        subject = text.split("\n")[0][:100] if text else "Slack message"
        
        # Create ticket
        ticket = Ticket(
            id=ticket_id,
            subject=subject,
            body=text,
            customer_email=user_email,
            status=status,
            tags=tags,
            created_at=created_at,
            updated_at=created_at,
            thread=thread
        )
        
        return ticket
    
    async def _get_user_email(self, user_id: str) -> str:
        """Get user email from user ID.
        
        Args:
            user_id: Slack user ID
        
        Returns:
            User email address or user ID if not found
        """
        try:
            response = await self.client.users_info(user=user_id)
            if response["ok"]:
                user = response.get("user", {})
                profile = user.get("profile", {})
                email = profile.get("email", user_id)
                return email
            return user_id
        except:
            return user_id
    
    async def close_client(self):
        """Close Slack client (cleanup)."""
        # AsyncWebClient doesn't require explicit cleanup
        pass
