"""
Sum Plugin Unit Tests

📚 Documentation: test_sum_plugin_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_sum_plugin_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the sum operation plugin.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
from bot.state import Job
from bot.plugins.sum import handle

class TestSumPlugin:
    @pytest.mark.asyncio
    async def test_sum_basic(self):
        """Test basic sum operation."""
        job = Job(
            id="job_1",
            op="sum",
            payload={"a": 5, "b": 3}
        )
        
        result = await handle(job)
        assert result == {"result": 8}

    @pytest.mark.asyncio
    async def test_sum_negative_numbers(self):
        """Test sum with negative numbers."""
        job = Job(
            id="job_2",
            op="sum",
            payload={"a": -5, "b": 10}
        )
        
        result = await handle(job)
        assert result == {"result": 5}

    @pytest.mark.asyncio
    async def test_sum_floats(self):
        """Test sum with floating point numbers."""
        job = Job(
            id="job_3",
            op="sum",
            payload={"a": 1.5, "b": 2.5}
        )
        
        result = await handle(job)
        assert result == {"result": 4.0}

    @pytest.mark.asyncio
    async def test_sum_zero(self):
        """Test sum with zeros."""
        job = Job(
            id="job_4",
            op="sum",
            payload={"a": 0, "b": 0}
        )
        
        result = await handle(job)
        assert result == {"result": 0}

    @pytest.mark.asyncio
    async def test_sum_missing_param_a(self):
        """Test sum with missing parameter 'a'."""
        job = Job(
            id="job_5",
            op="sum",
            payload={"b": 5}
        )
        
        with pytest.raises(KeyError):
            await handle(job)

    @pytest.mark.asyncio
    async def test_sum_missing_param_b(self):
        """Test sum with missing parameter 'b'."""
        job = Job(
            id="job_6",
            op="sum",
            payload={"a": 5}
        )
        
        with pytest.raises(KeyError):
            await handle(job)

    @pytest.mark.asyncio
    async def test_sum_non_numeric(self):
        """Test sum with non-numeric values."""
        job = Job(
            id="job_7",
            op="sum",
            payload={"a": "5", "b": "3"}
        )
        
        # String concatenation will work in Python
        result = await handle(job)
        assert result == {"result": "53"}  # String concatenation