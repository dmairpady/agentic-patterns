"""Lesson 8: Reflection. Check an agent's draft answer, critique it, revise it.

Flow for each round:
  1. Code checks (free, certain). If they find problems -> revise.
  2. If code checks pass -> LLM critic returns a Critique. If it fails -> revise.
  3. Passed -> return the draft. After max_revisions -> safe fallback + needs_review.

Both models are injected (critic_model, reviser_model): each is a function
prompt -> text, so tests can use scripted fakes and real use can pass real_text_model.
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, ValidationError

MODEL = "claude-haiku-4-5-20251001"
SYSTEM = ("You are a support assistant for an infusion-pump manufacturer, helping hospital staff. "
          "Answer only from the facts given; never invent error codes, meanings or pump states. "
          "Never make a clinical safety decision.")

FALLBACK = ("I could not produce a verified answer to this question. "
            "Please follow your facility's procedure and contact your safety team.")


# ---------- the critic's output shape ----------

class Issue(BaseModel):
    check: Literal["no_clinical_verdict", "grounded", "escalation", "other"]
    quote: str      # the exact words in the draft that broke the rule
    fix: str        # what to change


class Critique(BaseModel):
    passed: bool
    issues: list[Issue] = []


# ---------- step 1: code checks ----------

def facts_from(steps: list[dict]) -> list[dict]:
    """Successful tool results only: the facts the answer must be based on."""
    return [s for s in steps if not s.get("is_error") and "output" in s]


def code_issues(draft: str, steps: list[dict]) -> list[str]:
    """Return problems found by code. Empty list = all code checks passed."""
    issues = []
    ok = facts_from(steps)

    # 1. Grounding: every code / serial in the draft must come from a tool result
    known_codes = {s["args"]["error_code"] for s in ok if s["tool"] == "lookup_error_code"}
    known_serials = {s["args"]["serial_number"] for s in ok if s["tool"] == "get_pump_status"}
    for code in sorted(set(re.findall(r"E-\d{2}", draft)) - known_codes):
        issues.append(f"Mentions {code}, which was not looked up. Remove it or use only looked-up codes.")
    for serial in sorted(set(re.findall(r"SN-\d{4}", draft)) - known_serials):
        issues.append(f"Mentions {serial}, which was not checked. Remove it.")

    # 2. Escalation: high-severity codes must point to the facility procedure / safety team
    high = [s for s in ok if s["tool"] == "lookup_error_code"
            and json.loads(s["output"])["severity"] == "high"]
    lowered = draft.lower()
    if high and not ("facility" in lowered or "safety team" in lowered):
        issues.append("High-severity code: tell the user to follow the facility procedure "
                      "and contact the safety team.")

    # 3. Length: at most 5 sentences
    sentences = [x for x in re.split(r"[.!?]+\s", draft.strip()) if x]
    if len(sentences) > 5:
        issues.append(f"Too long: {len(sentences)} sentences; use at most 5.")
    return issues


# ---------- step 2: LLM critic ----------

def critic_prompt(question: str, draft: str, steps: list[dict]) -> str:
    facts = [s["output"] for s in facts_from(steps)]
    return f"""You review answers from an infusion-pump support assistant.

User question: {question}
Facts from tools: {facts}
Draft answer: {draft}

Check ONLY this rule: the draft must not make a clinical decision in its own voice,
such as "do not continue infusing" or "it is safe to continue". Quoting the service
manual's action with attribution ("The service manual says ...") is allowed.

Return ONLY a JSON object, no other text:
{{"passed": true or false,
  "issues": [{{"check": "no_clinical_verdict", "quote": "exact words from the draft", "fix": "what to change"}}]}}
Use an empty issues list when passed is true."""


def run_critic(question: str, draft: str, steps: list[dict], critic_model) -> tuple[Critique | None, str | None]:
    """Returns (critique, None) if the reply is valid, else (None, error message)."""
    raw = critic_model(critic_prompt(question, draft, steps))
    try:
        start, end = raw.find("{"), raw.rfind("}")
        return Critique.model_validate_json(raw[start:end + 1]), None
    except ValidationError as e:
        return None, f"invalid critic reply: {e.errors()[0]['msg']}"


# ---------- step 3: revise ----------

def revise(question: str, draft: str, steps: list[dict], issues: list[str], reviser_model) -> str:
    facts = [s["output"] for s in facts_from(steps)]
    prompt = (f"User question: {question}\n"
              f"Facts from tools (use ONLY these): {facts}\n"
              f"Your previous draft: {draft}\n"
              f"Fix ALL of these problems: {issues}\n"
              "Return only the corrected answer.")
    return reviser_model(prompt)


# ---------- the reflection loop ----------

def reflect(question: str, draft: str, steps: list[dict], critic_model, reviser_model,
            max_revisions: int = 2) -> tuple[str, list[dict], bool]:
    """Returns (final_answer, rounds_log, needs_review)."""
    log = []
    all_issues = []                      # every issue so far, so fixes are not undone later

    for round_no in range(max_revisions + 1):
        issues = code_issues(draft, steps)
        source = "code"

        if not issues:                   # code checks passed -> ask the LLM critic
            critique, error = run_critic(question, draft, steps, critic_model)
            if critique is None:         # unreadable critic reply: never treat as passed
                log.append({"round": round_no, "source": "critic_invalid", "issues": [error]})
                return FALLBACK, log, True
            if critique.passed and not critique.issues:
                log.append({"round": round_no, "source": "passed", "issues": []})
                return draft, log, False
            issues = [f"{i.check}: '{i.quote}' -> {i.fix}" for i in critique.issues] \
                     or ["critic marked the draft as failed without details"]
            source = "critic"

        log.append({"round": round_no, "source": source, "issues": issues})
        if round_no == max_revisions:    # no revisions left
            break
        all_issues += [i for i in issues if i not in all_issues]
        draft = revise(question, draft, steps, all_issues, reviser_model)

    return FALLBACK, log, True


# ---------- the real model ----------

_client = None

def real_text_model(prompt: str) -> str:
    """Send one prompt (no tools) and return the text answer."""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    resp = _client.messages.create(model=MODEL, max_tokens=500, system=SYSTEM,
                                   messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text")


if __name__ == "__main__":
    # Example with a hand-written draft, so you can see a real critique.
    steps = [{"tool": "lookup_error_code", "args": {"error_code": "E-12"}, "is_error": False,
              "output": json.dumps({"meaning": "Downstream occlusion", "severity": "high",
                                    "action": "Check line for kinks or closed clamps"})}]
    draft = ("Do not continue infusing. E-12 means downstream occlusion. "
             "Check the line for kinks. Follow your facility procedure.")
    final, log, needs_review = reflect("Pump shows E-12. Is it safe?", draft, steps,
                                       real_text_model, real_text_model)
    for entry in log:
        print(entry)
    print("\nFINAL:", final, "\nNEEDS REVIEW:", needs_review)