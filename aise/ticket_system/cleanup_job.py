# aise/ticket_system/cleanup_job.py
"""
Background job for cleaning up old conversation data.

This module provides a background task that periodically deletes
old conversation data based on the configured retention policy.
"""

import asyncio
from datetime import datetime
import structlog

from aise.ticket_system.memory import ConversationMemory

logger = structlog.get_logger(__name__)


class ConversationCleanupJob:
    """Background job for cleaning up old conversations.
    
    Runs periodically to delete conversations older than the retention period.
    
    Attributes:
        memory: ConversationMemory instance
        interval_hours: Hours between cleanup runs (default: 24)
        _task: Background task handle
        _running: Flag indicating if job is running
    
    Example:
        >>> cleanup_job = ConversationCleanupJob(memory, interval_hours=24)
        >>> await cleanup_job.start()
        >>> # ... later ...
        >>> await cleanup_job.stop()
    """
    
    def __init__(
        self,
        memory: ConversationMemory,
        interval_hours: int = 24
    ):
        """Initialize cleanup job.
        
        Args:
            memory: ConversationMemory instance
            interval_hours: Hours between cleanup runs (default: 24)
        """
        self.memory = memory
        self.interval_hours = interval_hours
        self._task = None
        self._running = False
        
        logger.info(
            "cleanup_job_initialized",
            interval_hours=interval_hours,
            retention_days=memory.retention_days
        )
    
    async def start(self) -> None:
        """Start the background cleanup job.
        
        Creates an asyncio task that runs the cleanup periodically.
        """
        if self._running:
            logger.warning("cleanup_job_already_running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        
        logger.info("cleanup_job_started")
    
    async def stop(self) -> None:
        """Stop the background cleanup job.
        
        Cancels the background task and waits for it to complete.
        """
        if not self._running:
            logger.warning("cleanup_job_not_running")
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("cleanup_job_stopped")
    
    async def _run_loop(self) -> None:
        """Main loop for periodic cleanup.
        
        Runs cleanup at configured intervals until stopped.
        """
        while self._running:
            try:
                await self._run_cleanup()
                
                # Wait for next interval
                await asyncio.sleep(self.interval_hours * 3600)
            
            except asyncio.CancelledError:
                logger.info("cleanup_job_cancelled")
                break
            
            except Exception as e:
                logger.error(
                    "cleanup_job_error",
                    error=str(e),
                    message="Will retry on next interval"
                )
                # Wait before retrying
                await asyncio.sleep(300)  # 5 minutes
    
    async def _run_cleanup(self) -> None:
        """Execute cleanup operation.
        
        Deletes old conversations and logs the result.
        """
        try:
            start_time = datetime.utcnow()
            
            logger.info("cleanup_job_starting")
            
            deleted_count = await self.memory.cleanup_old_conversations()
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                "cleanup_job_completed",
                deleted_count=deleted_count,
                duration_seconds=duration
            )
        
        except Exception as e:
            logger.error(
                "cleanup_job_failed",
                error=str(e)
            )
            raise
    
    async def run_once(self) -> int:
        """Run cleanup once immediately.
        
        Useful for manual cleanup or testing.
        
        Returns:
            Number of messages deleted
        """
        logger.info("cleanup_job_manual_run")
        await self._run_cleanup()
        return await self.memory.cleanup_old_conversations()
