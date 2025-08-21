"""
API Schemas Contract Tests

📚 Documentation: test_api_schemas_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_api_schemas_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains contract tests for API schema validation.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import json
from jsonschema import validate, ValidationError

# Define JSON schemas for API contracts

REGISTER_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["bot_key", "instance_id", "version", "capabilities", "resources"],
    "properties": {
        "bot_key": {"type": "string", "minLength": 1},
        "instance_id": {"type": "string", "format": "uuid"},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "capabilities": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1
        },
        "resources": {
            "type": "object",
            "properties": {
                "cpu_cores": {"type": "integer", "minimum": 1},
                "mem_mb": {"type": "integer", "minimum": 128}
            }
        },
        "constraints": {"type": "object"},
        "meta": {"type": "object"}
    }
}

REGISTER_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["bot_id", "auth", "assignment"],
    "properties": {
        "bot_id": {"type": "string", "minLength": 1},
        "auth": {
            "type": "object",
            "required": ["access_token"],
            "properties": {
                "access_token": {"type": "string", "minLength": 1},
                "refresh_token": {"type": "string"}
            }
        },
        "assignment": {
            "type": "object",
            "required": ["operations", "max_concurrency"],
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "max_concurrency": {"type": "integer", "minimum": 1},
                "paused": {"type": "boolean"}
            }
        },
        "config": {"type": "object"}
    }
}

HEARTBEAT_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["instance_id"],
    "properties": {
        "instance_id": {"type": "string", "minLength": 1},
        "running": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["job_id", "op"],
                "properties": {
                    "job_id": {"type": "string"},
                    "op": {"type": "string"},
                    "elapsed_ms": {"type": "integer", "minimum": 0},
                    "lease_until": {"type": "string", "format": "date-time"}
                }
            }
        },
        "metrics": {
            "type": "object",
            "properties": {
                "cpu": {"type": "number", "minimum": 0, "maximum": 1},
                "mem_mb": {"type": "integer", "minimum": 0}
            }
        }
    }
}

CLAIM_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["bot_id", "operations", "limit"],
    "properties": {
        "bot_id": {"type": "string", "minLength": 1},
        "operations": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 100}
    }
}

JOB_REPORT_SCHEMA = {
    "type": "object",
    "required": ["instance_id"],
    "properties": {
        "instance_id": {"type": "string", "minLength": 1},
        "result": {"type": "object"},
        "error": {"type": "string"},
        "retry_after_ms": {"type": "integer", "minimum": 0}
    }
}


class TestApiSchemas:
    def test_register_request_valid(self):
        """Test valid register request."""
        request = {
            "bot_key": "abc123",
            "instance_id": "550e8400-e29b-41d4-a716-446655440000",
            "version": "1.0.0",
            "capabilities": ["sum", "subtract"],
            "resources": {"cpu_cores": 2, "mem_mb": 1024},
            "constraints": {},
            "meta": {"region": "us-east-1"}
        }
        validate(request, REGISTER_REQUEST_SCHEMA)

    def test_register_request_invalid_version(self):
        """Test register request with invalid version format."""
        request = {
            "bot_key": "abc123",
            "instance_id": "550e8400-e29b-41d4-a716-446655440000",
            "version": "1.0",  # Missing patch version
            "capabilities": ["sum"],
            "resources": {"cpu_cores": 2, "mem_mb": 1024}
        }
        with pytest.raises(ValidationError, match="pattern"):
            validate(request, REGISTER_REQUEST_SCHEMA)

    def test_register_response_valid(self):
        """Test valid register response."""
        response = {
            "bot_id": "bot_123",
            "auth": {"access_token": "token_xyz"},
            "assignment": {
                "operations": ["sum", "subtract"],
                "max_concurrency": 2,
                "paused": False
            }
        }
        validate(response, REGISTER_RESPONSE_SCHEMA)

    def test_heartbeat_request_valid(self):
        """Test valid heartbeat request."""
        request = {
            "instance_id": "inst_123",
            "running": [
                {
                    "job_id": "job_1",
                    "op": "sum",
                    "elapsed_ms": 1500,
                    "lease_until": "2025-01-01T00:00:00Z"
                }
            ],
            "metrics": {"cpu": 0.45, "mem_mb": 512}
        }
        validate(request, HEARTBEAT_REQUEST_SCHEMA)

    def test_heartbeat_request_minimal(self):
        """Test minimal heartbeat request."""
        request = {"instance_id": "inst_123"}
        validate(request, HEARTBEAT_REQUEST_SCHEMA)

    def test_claim_request_valid(self):
        """Test valid claim request."""
        request = {
            "bot_id": "bot_123",
            "operations": ["sum", "multiply"],
            "limit": 10
        }
        validate(request, CLAIM_REQUEST_SCHEMA)

    def test_claim_request_limit_bounds(self):
        """Test claim request limit validation."""
        # Too high
        request = {
            "bot_id": "bot_123",
            "operations": ["sum"],
            "limit": 101
        }
        with pytest.raises(ValidationError, match="maximum"):
            validate(request, CLAIM_REQUEST_SCHEMA)
        
        # Too low
        request["limit"] = 0
        with pytest.raises(ValidationError, match="minimum"):
            validate(request, CLAIM_REQUEST_SCHEMA)

    def test_job_report_complete(self):
        """Test job completion report."""
        report = {
            "instance_id": "inst_123",
            "result": {"sum": 42, "metadata": {"duration_ms": 150}}
        }
        validate(report, JOB_REPORT_SCHEMA)

    def test_job_report_failure(self):
        """Test job failure report."""
        report = {
            "instance_id": "inst_123",
            "error": "Division by zero"
        }
        validate(report, JOB_REPORT_SCHEMA)

    def test_job_report_retry(self):
        """Test job retry report."""
        report = {
            "instance_id": "inst_123",
            "error": "Temporary failure",
            "retry_after_ms": 5000
        }
        validate(report, JOB_REPORT_SCHEMA)