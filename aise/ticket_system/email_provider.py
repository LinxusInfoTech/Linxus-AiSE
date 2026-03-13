# aise/ticket_system/email_provider.py
"""Email (IMAP/SMTP) ticket provider implementation."""

import asyncio
import email
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import structlog
from aioimaplib import aioimaplib
import aiosmtplib

from aise.ticket_system.base import TicketProvider, Ticket, Message, TicketStatus
from aise.core.exceptions import TicketAPIError, TicketNotFoundError

logger = structlog.get_logger(__name__)


class EmailProvider(TicketProvider):
    """Email IMAP/SMTP ticket provider.
    
    Implements the TicketProvider interface for email-based ticketing.
    Uses IMAP for receiving tickets and SMTP for sending replies.
    
    Example:
        >>> provider = EmailProvider(
        ...     imap_host="imap.gmail.com",
        ...     imap_port=993,
        ...     smtp_host="smtp.gmail.com",
        ...     smtp_port=587,
        ...     username="support@mycompany.com",
        ...     password="secret"
        ... )
        >>> tickets = await provider.list_open(limit=10)
    """
    
    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        timeout: int = 30
    ):
        """Initialize Email provider.
        
        Args:
            imap_host: IMAP server hostname
            imap_port: IMAP server port (typically 993 for SSL)
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port (typically 587 for TLS)
            username: Email account username
            password: Email account password
            timeout: Request timeout in seconds (default: 30)
        """
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.timeout = timeout
        
        logger.info("email_provider_initialized", imap_host=imap_host, smtp_host=smtp_host)
    
    async def _connect_imap(self) -> aioimaplib.IMAP4_SSL:
        """Connect to IMAP server.
        
        Returns:
            Connected IMAP client
        
        Raises:
            TicketAPIError: If connection fails
        """
        try:
            client = aioimaplib.IMAP4_SSL(host=self.imap_host, port=self.imap_port, timeout=self.timeout)
            await client.wait_hello_from_server()
            await client.login(self.username, self.password)
            await client.select("INBOX")
            return client
        except Exception as e:
            logger.error("imap_connection_failed", error=str(e))
            raise TicketAPIError(f"Failed to connect to IMAP: {str(e)}", provider="email")
    
    async def list_open(self, limit: int = 50) -> List[Ticket]:
        """List open tickets from email inbox.
        
        Args:
            limit: Maximum number of tickets to return
        
        Returns:
            List of open Ticket objects (unseen emails)
        
        Raises:
            TicketAPIError: If IMAP request fails
        """
        client = None
        try:
            logger.debug("listing_open_tickets", limit=limit)
            
            client = await self._connect_imap()
            
            # Search for unseen emails
            status, data = await client.search("UNSEEN")
            
            if status != "OK":
                raise TicketAPIError(f"IMAP search failed: {status}", provider="email")
            
            # Parse message IDs
            message_ids = data[0].decode().split()
            message_ids = message_ids[:limit]  # Limit results
            
            tickets = []
            for msg_id in message_ids:
                try:
                    ticket = await self._fetch_ticket(client, msg_id)
                    tickets.append(ticket)
                except Exception as e:
                    logger.warning("failed_to_parse_email", msg_id=msg_id, error=str(e))
            
            logger.info("open_tickets_listed", count=len(tickets))
            return tickets
            
        except Exception as e:
            logger.error("list_open_failed", error=str(e))
            raise TicketAPIError(f"Failed to list open tickets: {str(e)}", provider="email")
        finally:
            if client:
                try:
                    await client.logout()
                except:
                    pass
    
    async def get(self, ticket_id: str) -> Ticket:
        """Get ticket by ID (email message ID).
        
        Args:
            ticket_id: Email message ID
        
        Returns:
            Ticket object with complete message thread
        
        Raises:
            TicketNotFoundError: If email doesn't exist
            TicketAPIError: If IMAP request fails
        """
        client = None
        try:
            logger.debug("getting_ticket", ticket_id=ticket_id)
            
            client = await self._connect_imap()
            ticket = await self._fetch_ticket(client, ticket_id)
            
            logger.info("ticket_retrieved", ticket_id=ticket_id)
            return ticket
            
        except TicketNotFoundError:
            raise
        except Exception as e:
            logger.error("get_ticket_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to get ticket: {str(e)}", provider="email")
        finally:
            if client:
                try:
                    await client.logout()
                except:
                    pass
    
    async def reply(self, ticket_id: str, message: str) -> None:
        """Post reply to ticket via email.
        
        Args:
            ticket_id: Email message ID (used to get original email for reply)
            message: Reply message content (plain text)
        
        Raises:
            TicketNotFoundError: If original email doesn't exist
            TicketAPIError: If SMTP send fails
        """
        client = None
        try:
            logger.debug("posting_reply", ticket_id=ticket_id)
            
            # Get original email to extract reply-to address and subject
            client = await self._connect_imap()
            original_ticket = await self._fetch_ticket(client, ticket_id)
            
            # Create reply email
            msg = MIMEMultipart()
            msg["From"] = self.username
            msg["To"] = original_ticket.customer_email
            msg["Subject"] = f"Re: {original_ticket.subject}"
            msg.attach(MIMEText(message, "plain"))
            
            # Send via SMTP
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                start_tls=True,
                timeout=self.timeout
            )
            
            logger.info("reply_posted", ticket_id=ticket_id)
            
        except TicketNotFoundError:
            raise
        except Exception as e:
            logger.error("reply_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to post reply: {str(e)}", provider="email")
        finally:
            if client:
                try:
                    await client.logout()
                except:
                    pass
    
    async def close(self, ticket_id: str) -> None:
        """Close ticket (mark email as seen).
        
        Args:
            ticket_id: Email message ID
        
        Raises:
            TicketNotFoundError: If email doesn't exist
            TicketAPIError: If IMAP request fails
        """
        client = None
        try:
            logger.debug("closing_ticket", ticket_id=ticket_id)
            
            client = await self._connect_imap()
            
            # Mark as seen (closed)
            status, data = await client.store(ticket_id, "+FLAGS", "\\Seen")
            
            if status != "OK":
                raise TicketAPIError(f"Failed to mark email as seen: {status}", provider="email")
            
            logger.info("ticket_closed", ticket_id=ticket_id)
            
        except Exception as e:
            logger.error("close_failed", ticket_id=ticket_id, error=str(e))
            raise TicketAPIError(f"Failed to close ticket: {str(e)}", provider="email")
        finally:
            if client:
                try:
                    await client.logout()
                except:
                    pass
    
    async def add_tags(self, ticket_id: str, tags: List[str]) -> None:
        """Add tags to ticket (not supported for email).
        
        Email doesn't natively support tags, so this is a no-op.
        
        Args:
            ticket_id: Email message ID
            tags: List of tag names (ignored)
        """
        logger.debug("add_tags_not_supported", ticket_id=ticket_id, tags=tags)
        # Email doesn't support tags natively, so this is a no-op
        pass
    
    async def _fetch_ticket(self, client: aioimaplib.IMAP4_SSL, msg_id: str) -> Ticket:
        """Fetch and parse email into Ticket object.
        
        Args:
            client: Connected IMAP client
            msg_id: Email message ID
        
        Returns:
            Ticket object
        
        Raises:
            TicketNotFoundError: If email doesn't exist
        """
        try:
            # Fetch email
            status, data = await client.fetch(msg_id, "(RFC822)")
            
            if status != "OK":
                raise TicketNotFoundError(f"Email not found: {msg_id}")
            
            # Parse email
            raw_email = data[1]
            email_message = email.message_from_bytes(raw_email)
            
            # Extract fields
            subject = email_message.get("Subject", "No Subject")
            from_addr = email.utils.parseaddr(email_message.get("From", ""))[1]
            date_str = email_message.get("Date", "")
            
            # Parse date
            try:
                date_tuple = email.utils.parsedate_to_datetime(date_str)
                created_at = date_tuple
            except:
                created_at = datetime.now()
            
            # Extract body
            body = ""
            if email_message.is_multipart():
                for part in email_message.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = email_message.get_payload(decode=True).decode("utf-8", errors="ignore")
            
            # Create single message for thread (email doesn't have threads in IMAP)
            thread = [
                Message(
                    id=msg_id,
                    author=from_addr,
                    body=body,
                    is_customer=True,
                    created_at=created_at
                )
            ]
            
            # Create ticket
            ticket = Ticket(
                id=msg_id,
                subject=subject,
                body=body,
                customer_email=from_addr,
                status=TicketStatus.OPEN,
                tags=[],
                created_at=created_at,
                updated_at=created_at,
                thread=thread
            )
            
            return ticket
            
        except TicketNotFoundError:
            raise
        except Exception as e:
            logger.error("failed_to_parse_email", msg_id=msg_id, error=str(e))
            raise TicketAPIError(f"Failed to parse email: {str(e)}", provider="email")
