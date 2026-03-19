# aise/core/audit.py
"""Centralized security audit logging.

All security-relevant events (command execution, config changes, auth failures,
webhook rejections, approval decisions) are written to the PostgreSQL audit_log
table via this module.

Audit log entries older than AUDIT_RETENTION_DAYS are automatically purged by
the cleanup_old_audit_logs() coroutine, which should be scheduled as a
background task.

Example usage:
    >>> from aise.core.audit import log_security_event
    >>> await log_security_event(
    ...     event_type="command_execution",
    ...     action="aws ec2 describe-instances",
    ...     component="tool_executor",
    ...     success=True,
    ...     details={"exit_code": 0, "duration_ms": 342},
    ... )
"""

from typing import Any, Dict, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

# Default retention period for audit log entries
AUDIT_RETENTION_DAYS = 90


async def log_security_event(
    event_type: str,
    action: str,
    component: str,
    success: bool,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[int]:
    """Write a security-relevant event to the audit_log table.

    Falls back to structured logging only when the database is unavailable
    so that callers are never blocked by a DB outage.

    Args:
        event_type: Category of event (e.g. "command_execution", "config_change",
                    "auth_failure", "webhook_rejected", "rate_limit_exceeded").
        action: Human-readable description of the action taken.
        component: Module/component that generated the event.
        success: Whether the action succeeded.
        user_id: Optional identity of the actor.
        resource_type: Optional type of resource affected.
        resource_id: Optional identifier of the resource affected.
        details: Optional free-form dict with additional context.
        error_message: Optional error message when success=False.

    Returns:
        Inserted row ID, or None if the DB write was skipped.
    """
    # Always emit a structured log line regardless of DB availability
    log_fn = logger.info if success else logger.warning
    log_fn(
        "security_event",
        event_type=event_type,
        action=action,
        component=component,
        success=success,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        error_message=error_message,
    )

    try:
        from aise.core.database import get_database

        db = await get_database()
        async with db.pool.acquire() as conn:
            row_id = await conn.fetchval(
                """
                INSERT INTO audit_log (
                    event_type, user_id, component, action,
                    resource_type, resource_id, details,
                    timestamp, success, error_message
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING id
                """,
                event_type,
                user_id,
                component,
                action,
                resource_type,
                resource_id,
                details,
                datetime.utcnow(),
                success,
                error_message,
            )
        return row_id
    except Exception as exc:
        # Non-fatal: log the failure but don't propagate
        logger.error(
            "audit_log_db_write_failed",
            event_type=event_type,
            error=str(exc),
        )
        return None


async def cleanup_old_audit_logs(retention_days: int = AUDIT_RETENTION_DAYS) -> int:
    """Delete audit log entries older than *retention_days*.

    Intended to be called periodically (e.g. daily) as a background task.

    Args:
        retention_days: Entries older than this many days are deleted.

    Returns:
        Number of rows deleted.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    try:
        from aise.core.database import get_database

        db = await get_database()
        async with db.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM audit_log WHERE timestamp < $1",
                cutoff,
            )
        # asyncpg returns "DELETE N" as a string
        deleted = int(result.split()[-1]) if result else 0
        logger.info(
            "audit_log_cleanup_complete",
            deleted=deleted,
            retention_days=retention_days,
            cutoff=cutoff.isoformat(),
        )
        return deleted
    except Exception as exc:
        logger.error("audit_log_cleanup_failed", error=str(exc))
        return 0
