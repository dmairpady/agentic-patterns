import json

from routing import route


def fake_llm(labels):
    """Build a fake LLM that always returns these labels."""
    return lambda message: json.dumps({"labels": labels, "reason": "test"})


def timeout_llm(message):
    raise TimeoutError("API timed out")


def test_billing_message_routes_to_billing():
    assert route("Invoice charged twice", fake_llm(["billing"]))["primary"] == "billing"


def test_safety_message_survives_timeout():
    assert route("Pump stopped, patient connected", timeout_llm)["primary"] == "safety_incident"