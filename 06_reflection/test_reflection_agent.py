import json

from reflection import FALLBACK, code_issues, reflect

# ---------- shared test data ----------

E12_STEPS = [{"tool": "lookup_error_code", "args": {"error_code": "E-12"}, "is_error": False,
              "output": json.dumps({"meaning": "Downstream occlusion", "severity": "high",
                                    "action": "Check line for kinks or closed clamps"})}]

GOOD = ("E-12 means downstream occlusion. The service manual says to check the line "
        "for kinks or closed clamps. Follow your facility procedure and contact your safety team.")
PASS = json.dumps({"passed": True, "issues": []})
FAIL_VERDICT = json.dumps({"passed": False, "issues": [
    {"check": "no_clinical_verdict", "quote": "Do not continue infusing.",
     "fix": "Remove the instruction; quote the service manual instead."}]})


def scripted_text(*replies):
    """Fake model: prompt in, next scripted text out. Records every prompt."""
    it = iter(replies)
    calls = []
    def model(prompt):
        calls.append(prompt)
        return next(it)
    model.calls = calls
    return model


# ---------- code checks (plain Python, no fake model needed) ----------

def test_code_issues_good_draft_has_none():
    assert code_issues(GOOD, E12_STEPS) == []

def test_code_issues_flags_invented_code():
    issues = code_issues(GOOD + " E-99 is also possible.", E12_STEPS)
    assert any("E-99" in i for i in issues)

def test_code_issues_flags_missing_escalation():
    issues = code_issues("E-12 means downstream occlusion.", E12_STEPS)
    assert any("facility" in i for i in issues)

def test_code_issues_flags_too_long():
    long_draft = GOOD + " One. Two. Three. Four."
    assert any("Too long" in i for i in code_issues(long_draft, E12_STEPS))


# ---------- the reflection loop ----------

def test_good_draft_passes_first_time():
    critic, reviser = scripted_text(PASS), scripted_text()
    final, log, needs_review = reflect("q", GOOD, E12_STEPS, critic, reviser)
    assert final == GOOD and not needs_review
    assert len(critic.calls) == 1 and len(reviser.calls) == 0

def test_invented_code_caught_by_code_not_critic():
    bad = GOOD + " E-99 is also possible."
    critic, reviser = scripted_text(PASS), scripted_text(GOOD)
    final, log, needs_review = reflect("q", bad, E12_STEPS, critic, reviser)
    assert final == GOOD and not needs_review
    assert log[0]["source"] == "code"            # round 0 failed on a code check
    assert len(critic.calls) == 1                 # critic only ran on the fixed draft
    assert "E-99" in reviser.calls[0]             # the reviser was told what to fix

def test_critic_flags_verdict_then_revision_passes():
    bad = "Do not continue infusing. " + GOOD
    critic, reviser = scripted_text(FAIL_VERDICT, PASS), scripted_text(GOOD)
    final, log, needs_review = reflect("q", bad, E12_STEPS, critic, reviser)
    assert final == GOOD and not needs_review
    assert [entry["source"] for entry in log] == ["critic", "passed"]
    assert "no_clinical_verdict" in reviser.calls[0]

def test_never_passes_returns_fallback_after_two_revisions():
    bad = "Do not continue infusing. " + GOOD
    critic = scripted_text(FAIL_VERDICT, FAIL_VERDICT, FAIL_VERDICT)
    reviser = scripted_text(bad, bad)
    final, log, needs_review = reflect("q", bad, E12_STEPS, critic, reviser)
    assert final == FALLBACK and needs_review
    assert len(reviser.calls) == 2 and len(log) == 3

def test_invalid_critic_reply_is_never_treated_as_passed():
    critic, reviser = scripted_text("Looks fine to me!"), scripted_text()
    final, log, needs_review = reflect("q", GOOD, E12_STEPS, critic, reviser)
    assert final == FALLBACK and needs_review
    assert log[0]["source"] == "critic_invalid"
    assert len(reviser.calls) == 0