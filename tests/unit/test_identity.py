"""
Identity Unit Tests

📚 Documentation: test_identity_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_identity_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the identity management system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import json
import uuid
from unittest.mock import patch, MagicMock
from bot.identity import load_identity, rotate_instance_id, _machine_fingerprint

class TestIdentity:
    def test_machine_fingerprint_deterministic(self):
        """Test that fingerprint is deterministic for same machine."""
        fp1 = _machine_fingerprint()
        fp2 = _machine_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256 hex length

    @patch('socket.gethostname', return_value='test-host')
    @patch('platform.platform', return_value='test-platform')
    def test_machine_fingerprint_mocked(self, mock_platform, mock_hostname):
        """Test fingerprint with mocked system info."""
        fp = _machine_fingerprint()
        assert isinstance(fp, str)
        assert len(fp) == 64

    def test_load_identity_creates_new(self, temp_state_dir, monkeypatch):
        """Test identity creation when file doesn't exist."""
        monkeypatch.setattr('pathlib.Path.home', lambda: temp_state_dir.parent)
        identity_path = temp_state_dir / "identity.json"
        
        with patch('bot.identity.IDENTITY_PATH', identity_path):
            with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
                identity = load_identity()
        
        assert identity["bot_key"] == _machine_fingerprint()
        assert identity["instance_id"] == "12345678-1234-5678-1234-567812345678"
        assert "hostname" in identity
        assert "os" in identity
        assert identity_path.exists()

    def test_load_identity_existing(self, temp_state_dir):
        """Test loading existing identity file."""
        identity_path = temp_state_dir / "identity.json"
        existing = {
            "bot_key": "existing-key",
            "instance_id": "existing-id",
            "hostname": "old-host",
            "os": "old-os"
        }
        identity_path.write_text(json.dumps(existing))
        
        with patch('bot.identity.IDENTITY_PATH', identity_path):
            loaded = load_identity()
        
        assert loaded == existing

    def test_rotate_instance_id(self, temp_state_dir):
        """Test rotating instance ID keeps bot_key."""
        identity_path = temp_state_dir / "identity.json"
        original = {
            "bot_key": "keep-this-key",
            "instance_id": "old-instance",
            "hostname": "host",
            "os": "os"
        }
        identity_path.write_text(json.dumps(original))
        
        with patch('bot.identity.IDENTITY_PATH', identity_path):
            with patch('uuid.uuid4', return_value=uuid.UUID('87654321-4321-8765-4321-876543218765')):
                rotated = rotate_instance_id()
        
        assert rotated["bot_key"] == "keep-this-key"
        assert rotated["instance_id"] == "87654321-4321-8765-4321-876543218765"
        assert rotated["hostname"] == "host"

    def test_identity_file_permissions(self, temp_state_dir):
        """Test that identity file is created with proper permissions."""
        identity_path = temp_state_dir / "identity.json"
        
        with patch('bot.identity.IDENTITY_PATH', identity_path):
            load_identity()
        
        # File should be readable/writable by owner only
        assert identity_path.exists()
        # On Windows, file permissions work differently
        # Just verify the file was created successfully
        import platform
        if platform.system() != 'Windows':
            import stat as st
            stat_info = identity_path.stat()
            mode = stat_info.st_mode
            assert not (mode & st.S_IRGRP)  # No group read
            assert not (mode & st.S_IROTH)  # No other read