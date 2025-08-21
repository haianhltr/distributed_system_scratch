"""
Settings Unit Tests

📚 Documentation: test_settings_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_settings_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the configuration management system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import os
from unittest.mock import patch
from bot.settings import Settings, _int, _str

class TestSettings:
    def test_default_settings(self):
        """Test that default settings are correctly loaded."""
        settings = Settings()
        assert settings.server_base == "http://localhost:8000/v1"
        assert settings.heartbeat_interval == 30
        assert settings.bot_lease_ttl == 120
        assert settings.job_lease_ttl == 180
        assert settings.claim_batch_size == 5
        assert settings.max_concurrency == 2
        assert settings.version == "1.0.0"

    def test_env_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {
            "SERVER_BASE": "https://prod.example.com/api",
            "HEARTBEAT_INTERVAL_SEC": "60",
            "MAX_CONCURRENCY": "10"
        }):
            # Re-import to get new environment values
            from bot.settings import Settings
            settings = Settings()
            assert settings.server_base == "https://prod.example.com/api"
            assert settings.heartbeat_interval == 60
            assert settings.max_concurrency == 10

    def test_frozen_dataclass(self):
        """Test that settings are immutable."""
        settings = Settings()
        with pytest.raises(AttributeError):
            settings.heartbeat_interval = 999

    def test_helper_functions(self):
        """Test _int and _str helper functions."""
        with patch.dict(os.environ, {"TEST_INT": "42", "TEST_STR": "hello"}):
            assert _int("TEST_INT", 10) == 42
            assert _int("MISSING_INT", 10) == 10
            assert _str("TEST_STR", "default") == "hello"
            assert _str("MISSING_STR", "default") == "default"

    @patch.dict(os.environ, {"INVALID_INT": "not_a_number"})
    def test_invalid_int_env(self):
        """Test that invalid integer env vars raise ValueError."""
        with pytest.raises(ValueError):
            _int("INVALID_INT", 10)