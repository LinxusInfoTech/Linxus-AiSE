# aise/agents/approval.py
"""Approval decision logging and management.

This module provides functionality for logging approval requests and decisions
in the AiSE system. All approval decisions are logged with timestamp and
approver identity for compliance and audit purposes.

Example usage:
    >>> from aise.agents.approval import log_approval_request, log_approval_decision
    >>> 
    >>> # Log approval request
    >>> await log_approval_request(
    ...     action="post_reply",
    ...     ticket_id="12345",
    ...     proposed_action="Post reply to ticket",
    ...     details={"message": "Your issue has been resolved..."}
    ... )
    >>> 
    >>> # Log approval decision
    >>> await log_approval_decision(
    ...     action="post_reply",
    ...     ticket_id="12345",
    ...     approved=True,
    ...     approver="user@example.com",
    ...     reason="Reply looks good"
    ... )
"""

import structlog
from typing import Optional, Dict, Any
from datetime import datetime

from aise.core.database import get_database
from aise.core.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)


async def log_approval_request(
    action: str,
    proposed_action: str,
    ticket_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> int:
    """Log an approval request to the audit log.
    
    Args:
        action: Type of action requiring approval (e.g., "post_reply", "execute_tool")
        proposed_action: Human-readable description of the proposed action
        ticket_id: Optional ticket ID associated with the action
        details: Optional additional details about the proposed action
    
    Returns:
        Audit log entry ID
    
    Example:
        >>> await log_approval_request(
        ...     action="execute_tool",
        ...     proposed_action="Execute: kubectl get pods",
        ...     details={"command": "kubectl get pods", "namespace": "default"}
        ... )
    """
    try:
        db = await get_database()
    except ConfigurationError as e:
        logger.error("approval_request_log_failed", error=str(e), reason="database_not_initialized")
        raise
    
    async with db.pool.acquire() as conn:
        record_id = await conn.fetchval(
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
            RETURNING id
            """,
            "approval_request",
            None,  # No user yet - waiting for approval
            "graph",
            action,
            "approval",
            ticket_id,
            {
                "proposed_action": proposed_action,
                "status": "pending",
                **(details or {})
            },
            datetime.utcnow(),
            True
        )
    
    logger.info(
        "approval_request_logged",
        action=action,
        proposed_action=proposed_action,
        ticket_id=ticket_id,
        audit_log_id=record_id
    )
    
    return record_id


async def log_approval_decision(
    action: str,
    approved: bool,
    approver: str,
    ticket_id: Optional[str] = None,
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> int:
    """Log an approval decision to the audit log.
    
    Args:
        action: Type of action that was approved/rejected
        approved: True if approved, False if rejected
        approver: Identity of the person who made the decision
        ticket_id: Optional ticket ID associated with the action
        reason: Optional reason for the decision
        details: Optional additional details about the decision
    
    Returns:
        Audit log entry ID
    
    Example:
        >>> await log_approval_decision(
        ...     action="post_reply",
        ...     approved=True,
        ...     approver="admin@example.com",
        ...     ticket_id="12345",
        ...     reason="Reply is appropriate"
        ... )
    """
    try:
        db = await get_database()
    except ConfigurationError as e:
        logger.error("approval_decision_log_failed", error=str(e), reason="database_not_initialized")
        raise
    
    decision = "approved" if approved else "rejected"
    
    async with db.pool.acquire() as conn:
        record_id = await conn.fetchval(
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
            RETURNING id
            """,
            "approval_decision",
            approver,
            "graph",
            action,
            "approval",
            ticket_id,
            {
                "decision": decision,
                "reason": reason,
                "approved": approved,
                **(details or {})
            },
            datetime.utcnow(),
            approved  # success=True if approved, False if rejected
        )
    
    logger.info(
        "approval_decision_logged",
        action=action,
        decision=decision,
        approver=approver,
        ticket_id=ticket_id,
        audit_log_id=record_id
    )
    
    return record_id


async def get_pending_approvals(limit: int = 10) -> list:
    """Get pending approval requests.
    
    Args:
        limit: Maximum number of pending approvals to retrieve
    
    Returns:
        List of pending approval requests
    
    Example:
        >>> pending = await get_pending_approvals()
        >>> for approval in pending:
        ...     print(f"Action: {approval['action']}")
        ...     print(f"Proposed: {approval['details']['proposed_action']}")
    """
    try:
        db = await get_database()
    except ConfigurationError as e:
        logger.error("get_pending_approvals_failed", error=str(e), reason="database_not_initialized")
        return []
    
    async with db.pool.acquire() as conn:
        records = await conn.fetch(
            """
            SELECT id, event_type, action, resource_id, details, timestamp
            FROM audit_log
            WHERE event_type = 'approval_request'
            AND details->>'status' = 'pending'
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit
        )
        
        return [dict(record) for record in records]


async def get_approval_history(
    ticket_id: Optional[str] = None,
    limit: int = 50
) -> list:
    """Get approval decision history.
    
    Args:
        ticket_id: Optional ticket ID to filter by
        limit: Maximum number of records to retrieve
    
    Returns:
        List of approval decisions
    
    Example:
        >>> history = await get_approval_history(ticket_id="12345")
        >>> for decision in history:
        ...     print(f"{decision['user_id']}: {decision['details']['decision']}")
    """
    try:
        db = await get_database()
    except ConfigurationError as e:
        logger.error("get_approval_history_failed", error=str(e), reason="database_not_initialized")
        return []
    
    async with db.pool.acquire() as conn:
        if ticket_id:
            records = await conn.fetch(
                """
                SELECT id, event_type, user_id, action, resource_id, details, timestamp, success
                FROM audit_log
                WHERE event_type IN ('approval_request', 'approval_decision')
                AND resource_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                ticket_id,
                limit
            )
        else:
            records = await conn.fetch(
                """
                SELECT id, event_type, user_id, action, resource_id, details, timestamp, success
                FROM audit_log
                WHERE event_type IN ('approval_request', 'approval_decision')
                ORDER BY timestamp DESC
                LIMIT $1
                """,
                limit
            )
        
        return [dict(record) for record in records]


async def mark_approval_processed(approval_id: int, decision: str) -> None:
    """Mark an approval request as processed.
    
    Args:
        approval_id: ID of the approval request
        decision: Decision made ("approved" or "rejected")
    
    Example:
        >>> await mark_approval_processed(123, "approved")
    """
    try:
        db = await get_database()
    except ConfigurationError as e:
        logger.error("mark_approval_processed_failed", error=str(e), reason="database_not_initialized")
        raise
    
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE audit_log
            SET details = jsonb_set(details, '{status}', $1::jsonb)
            WHERE id = $2
            """,
            f'"{decision}"',
            approval_id
        )
    
    logger.info(
        "approval_marked_processed",
        approval_id=approval_id,
        decision=decision
    )
