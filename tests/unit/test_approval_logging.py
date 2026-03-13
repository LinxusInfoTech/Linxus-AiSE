# tests/unit/test_approval_logging.py
"""Unit tests for approval logging functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from aise.agents.approval import (
    log_approval_request,
    log_approval_decision,
    get_pending_approvals,
    get_approval_history,
    mark_approval_processed
)
from aise.core.exceptions import ConfigurationError


@pytest.fixture
def mock_database():
    """Mock database manager."""
    db = Mock()
    db.pool = Mock()
    
    # Mock connection context manager
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    conn.fetch = AsyncMock(return_value=[])
    
    acquire_context = AsyncMock()
    acquire_context.__aenter__ = AsyncMock(return_value=conn)
    acquire_context.__aexit__ = AsyncMock(return_value=None)
    
    db.pool.acquire = Mock(return_value=acquire_context)
    
    return db


@pytest.mark.asyncio
class TestApprovalLogging:
    """Test approval logging functionality."""
    
    async def test_log_approval_request(self, mock_database):
        """Test logging an approval request."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            record_id = await log_approval_request(
                action="post_reply",
                proposed_action="Post reply to ticket 12345",
                ticket_id="12345",
                details={"message": "Test message"}
            )
            
            assert record_id == 1
            
            # Verify database call
            conn = await mock_database.pool.acquire().__aenter__()
            assert conn.fetchval.called
            
            # Verify correct parameters (event_type, user_id, component, action, ...)
            call_args = conn.fetchval.call_args
            assert call_args[0][1] == "approval_request"  # event_type
            assert call_args[0][3] == "graph"  # component
            assert call_args[0][4] == "post_reply"  # action
    
    async def test_log_approval_request_without_ticket(self, mock_database):
        """Test logging approval request without ticket ID."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            record_id = await log_approval_request(
                action="execute_tool",
                proposed_action="Execute kubectl command"
            )
            
            assert record_id == 1
    
    async def test_log_approval_request_database_error(self):
        """Test handling database error when logging approval request."""
        with patch("aise.agents.approval.get_database", side_effect=ConfigurationError("DB not initialized", "POSTGRES_URL")):
            with pytest.raises(ConfigurationError):
                await log_approval_request(
                    action="post_reply",
                    proposed_action="Test"
                )
    
    async def test_log_approval_decision_approved(self, mock_database):
        """Test logging an approval decision (approved)."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            record_id = await log_approval_decision(
                action="post_reply",
                approved=True,
                approver="admin@example.com",
                ticket_id="12345",
                reason="Reply looks good"
            )
            
            assert record_id == 1
            
            # Verify database call
            conn = await mock_database.pool.acquire().__aenter__()
            assert conn.fetchval.called
            
            # Verify correct parameters
            call_args = conn.fetchval.call_args
            assert call_args[0][1] == "approval_decision"  # event_type
            assert call_args[0][2] == "admin@example.com"  # user_id
            assert call_args[0][9] is True  # success=True for approved
    
    async def test_log_approval_decision_rejected(self, mock_database):
        """Test logging an approval decision (rejected)."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            record_id = await log_approval_decision(
                action="execute_tool",
                approved=False,
                approver="admin@example.com",
                reason="Command too dangerous"
            )
            
            assert record_id == 1
            
            # Verify database call
            conn = await mock_database.pool.acquire().__aenter__()
            call_args = conn.fetchval.call_args
            assert call_args[0][9] is False  # success=False for rejected
    
    async def test_log_approval_decision_with_details(self, mock_database):
        """Test logging approval decision with additional details."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            record_id = await log_approval_decision(
                action="post_reply",
                approved=True,
                approver="admin@example.com",
                ticket_id="12345",
                reason="Approved",
                details={"custom_field": "value"}
            )
            
            assert record_id == 1
    
    async def test_get_pending_approvals_empty(self, mock_database):
        """Test getting pending approvals when none exist."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            pending = await get_pending_approvals()
            
            assert pending == []
    
    async def test_get_pending_approvals_with_records(self, mock_database):
        """Test getting pending approvals with records."""
        # Mock fetch to return records
        conn = await mock_database.pool.acquire().__aenter__()
        conn.fetch.return_value = [
            {
                "id": 1,
                "event_type": "approval_request",
                "action": "post_reply",
                "resource_id": "12345",
                "details": {"proposed_action": "Post reply", "status": "pending"},
                "timestamp": datetime.utcnow()
            }
        ]
        
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            pending = await get_pending_approvals()
            
            assert len(pending) == 1
            assert pending[0]["action"] == "post_reply"
    
    async def test_get_pending_approvals_with_limit(self, mock_database):
        """Test getting pending approvals with custom limit."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            await get_pending_approvals(limit=20)
            
            # Verify limit was passed to query
            conn = await mock_database.pool.acquire().__aenter__()
            call_args = conn.fetch.call_args
            assert call_args[0][1] == 20
    
    async def test_get_pending_approvals_database_error(self):
        """Test handling database error when getting pending approvals."""
        with patch("aise.agents.approval.get_database", side_effect=ConfigurationError("DB not initialized", "POSTGRES_URL")):
            pending = await get_pending_approvals()
            
            # Should return empty list on error
            assert pending == []
    
    async def test_get_approval_history_all(self, mock_database):
        """Test getting all approval history."""
        # Mock fetch to return records
        conn = await mock_database.pool.acquire().__aenter__()
        conn.fetch.return_value = [
            {
                "id": 1,
                "event_type": "approval_decision",
                "user_id": "admin",
                "action": "post_reply",
                "resource_id": "12345",
                "details": {"decision": "approved"},
                "timestamp": datetime.utcnow(),
                "success": True
            }
        ]
        
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            history = await get_approval_history()
            
            assert len(history) == 1
            assert history[0]["action"] == "post_reply"
    
    async def test_get_approval_history_by_ticket(self, mock_database):
        """Test getting approval history for specific ticket."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            await get_approval_history(ticket_id="12345")
            
            # Verify ticket_id was used in query
            conn = await mock_database.pool.acquire().__aenter__()
            call_args = conn.fetch.call_args
            assert call_args[0][1] == "12345"
    
    async def test_get_approval_history_with_limit(self, mock_database):
        """Test getting approval history with custom limit."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            await get_approval_history(limit=100)
            
            # Verify limit was passed
            conn = await mock_database.pool.acquire().__aenter__()
            call_args = conn.fetch.call_args
            # Limit is the last parameter
            assert 100 in call_args[0]
    
    async def test_get_approval_history_database_error(self):
        """Test handling database error when getting history."""
        with patch("aise.agents.approval.get_database", side_effect=ConfigurationError("DB not initialized", "POSTGRES_URL")):
            history = await get_approval_history()
            
            # Should return empty list on error
            assert history == []
    
    async def test_mark_approval_processed(self, mock_database):
        """Test marking approval as processed."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            await mark_approval_processed(123, "approved")
            
            # Verify database call
            conn = await mock_database.pool.acquire().__aenter__()
            assert conn.execute.called
            
            # Verify correct parameters
            call_args = conn.execute.call_args
            assert call_args[0][1] == '"approved"'
            assert call_args[0][2] == 123
    
    async def test_mark_approval_processed_rejected(self, mock_database):
        """Test marking approval as rejected."""
        with patch("aise.agents.approval.get_database", return_value=mock_database):
            await mark_approval_processed(456, "rejected")
            
            conn = await mock_database.pool.acquire().__aenter__()
            call_args = conn.execute.call_args
            assert call_args[0][1] == '"rejected"'
    
    async def test_mark_approval_processed_database_error(self):
        """Test handling database error when marking processed."""
        with patch("aise.agents.approval.get_database", side_effect=ConfigurationError("DB not initialized", "POSTGRES_URL")):
            with pytest.raises(ConfigurationError):
                await mark_approval_processed(123, "approved")


class TestApprovalDataStructures:
    """Test approval data structures and validation."""
    
    def test_approval_request_structure(self):
        """Test approval request data structure."""
        approval_request = {
            "action": "post_reply",
            "proposed_action": "Post reply to ticket",
            "ticket_id": "12345",
            "details": {"message": "Test"}
        }
        
        assert "action" in approval_request
        assert "proposed_action" in approval_request
        assert approval_request["action"] == "post_reply"
    
    def test_approval_decision_structure(self):
        """Test approval decision data structure."""
        approval_decision = {
            "action": "post_reply",
            "approved": True,
            "approver": "admin@example.com",
            "reason": "Looks good"
        }
        
        assert "action" in approval_decision
        assert "approved" in approval_decision
        assert "approver" in approval_decision
        assert approval_decision["approved"] is True
    
    def test_approval_actions(self):
        """Test valid approval action types."""
        valid_actions = ["post_reply", "execute_tool", "close_ticket", "update_ticket"]
        
        for action in valid_actions:
            # All actions should be strings
            assert isinstance(action, str)
            assert len(action) > 0
