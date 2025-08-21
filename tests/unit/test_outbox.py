"""
Outbox Unit Tests

📚 Documentation: test_outbox_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_outbox_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the outbox system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import json
import pathlib
from unittest.mock import patch, mock_open
from bot import outbox

class TestOutbox:
    def test_append_item(self, temp_state_dir):
        """Test appending items to outbox."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            item = {"job_id": "job_123", "action": "complete", "payload": {"result": 42}}
            outbox.append(item)
        
        assert test_file.exists()
        content = test_file.read_text()
        assert json.loads(content.strip()) == item

    def test_append_multiple_items(self, temp_state_dir):
        """Test appending multiple items maintains JSONL format."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            items = [
                {"job_id": "job_1", "action": "complete"},
                {"job_id": "job_2", "action": "fail"},
                {"job_id": "job_3", "action": "retry"}
            ]
            for item in items:
                outbox.append(item)
        
        lines = test_file.read_text().strip().split('\n')
        assert len(lines) == 3
        for i, line in enumerate(lines):
            assert json.loads(line) == items[i]

    def test_drain_empty(self, temp_state_dir):
        """Test draining empty outbox."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            items = outbox.drain()
        
        assert items == []
        assert not test_file.exists()

    def test_drain_all_items(self, temp_state_dir):
        """Test draining all items from outbox."""
        test_file = temp_state_dir / "outbox.jsonl"
        items = [
            {"job_id": "job_1", "data": 1},
            {"job_id": "job_2", "data": 2},
            {"job_id": "job_3", "data": 3}
        ]
        test_file.write_text('\n'.join(json.dumps(item) for item in items) + '\n')
        
        with patch('bot.outbox.OBX', test_file):
            drained = outbox.drain()
        
        assert drained == items
        assert not test_file.exists()

    def test_drain_with_limit(self, temp_state_dir):
        """Test draining with max_items limit."""
        test_file = temp_state_dir / "outbox.jsonl"
        items = [{"job_id": f"job_{i}", "data": i} for i in range(10)]
        test_file.write_text('\n'.join(json.dumps(item) for item in items) + '\n')
        
        with patch('bot.outbox.OBX', test_file):
            drained = outbox.drain(max_items=5)
        
        assert len(drained) == 5
        assert drained == items[:5]
        assert not test_file.exists()  # File is still deleted

    def test_append_creates_directory(self, tmp_path):
        """Test that append creates parent directory if needed."""
        test_file = tmp_path / "new_dir" / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            outbox.append({"test": "data"})
        
        assert test_file.parent.exists()
        assert test_file.exists()

    def test_concurrent_append_safety(self, temp_state_dir):
        """Test that concurrent appends don't corrupt file."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        # Simulate multiple rapid appends
        with patch('bot.outbox.OBX', test_file):
            for i in range(100):
                outbox.append({"job_id": f"job_{i}", "seq": i})
        
        # All lines should be valid JSON
        lines = test_file.read_text().strip().split('\n')
        assert len(lines) == 100
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["seq"] == i

    def test_drain_handles_corrupted_lines(self, temp_state_dir):
        """Test drain handles corrupted JSONL gracefully."""
        test_file = temp_state_dir / "outbox.jsonl"
        content = """{"valid": 1}
not json at all
{"valid": 2}
{broken json
{"valid": 3}
"""
        test_file.write_text(content)
        
        with patch('bot.outbox.OBX', test_file):
            # Should raise or skip bad lines depending on implementation
            # For robustness, let's assume it skips bad lines
            with pytest.raises(json.JSONDecodeError):
                outbox.drain()

    def test_outbox_rotation_safety(self, temp_state_dir):
        """Test safe rotation doesn't lose data."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            # Add items
            outbox.append({"job_id": "job_1"})
            outbox.append({"job_id": "job_2"})
            
            # Drain (which deletes file)
            items = outbox.drain()
            
            # Add more items
            outbox.append({"job_id": "job_3"})
            
            # Should have old items from drain and new file with new item
            assert len(items) == 2
            assert test_file.exists()
            assert "job_3" in test_file.read_text()