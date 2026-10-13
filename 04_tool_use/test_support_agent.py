import json
import pytest
import support_agent
from support_agent import run_tool


@pytest.fixture(autouse=True)          # runs automatically before every test
def reset_tickets():
    support_agent.TICKETS.clear()

def test_valid_error_code():
    output, is_error = run_tool("lookup_error_code", {"error_code": "E-47"})
    data = json.loads(output)
    assert data["meaning"] == "Air in line detected"    

def test_invalid_error_code():
    output, is_error = run_tool("lookup_error_code", {"error_code": "J-99"})
    assert is_error and "format" in output

def test_unknown_but_valid_code_is_rejected():
    output, is_error = run_tool("lookup_error_code", {"error_code": "E-99"})
    assert is_error and "not in the service manual" in output

def test_invalid_tool_name():
    output, is_error = run_tool("non_existent_tool", {"error_code": "E-47"})
    assert is_error
    assert "Unknown tool" in output

def test_invalid_serial_number():
    output, is_error = run_tool("get_pump_status", {"serial_number": "SN-9999"})
    assert is_error
    assert "error" in output

def test_duplicate_ticket_creation():
    # First, create a valid ticket
    output, is_error = run_tool("create_support_ticket", {"serial_number": "SN-4471", "error_code": "E-47", "summary": "Test issue"})
    assert not is_error
    data = json.loads(output)
    assert data["status"] == "created"

    # Now, try to create a duplicate ticket for the same error code
    output, is_error = run_tool("create_support_ticket", {"serial_number": "SN-4471", "error_code": "E-47", "summary": "Duplicate issue"})
    assert is_error
    assert "already exists" in output

