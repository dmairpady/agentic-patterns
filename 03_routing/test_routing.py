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


def test_safety_message_survives_llm_failure():
    assert route("I'm impatient, the invoice is wrong", fake_llm([]))["primary"] == "other"

def test_new_label_from_llm():
    assert route("How to get the amount back for the cancelled order?", fake_llm(["refund"]))["primary"] == "other"

def test_non_safety_message_with_no_llm_labels_routes_to_other():
    assert route("Can you add Bluetooth in the next version?", fake_llm([]))["primary"] == "other"