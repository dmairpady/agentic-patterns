"""Lesson 9: Plan-and-execute — release-readiness agent.

    release ──► list_changes (code) ──► make_plan (LLM) ──► validate_plan (code)
                                             ▲                     │
                                             └── retry w/ problems ┘
            ──► execute_plan (code) ──► build_report (code) ──► human decides

The LLM decides WHAT to check. Code guarantees it is safe, complete, and run correctly.
"""
import json
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError

MODEL = "claude-haiku-4-5-20251001"

# ---------- fake data (no real systems) ----------

CHANGES = {"2.4": ["alarm_module", "battery_driver"]}
TESTS = {"alarm_module": ["T-101", "T-102"], "battery_driver": []}      # battery has NO tests
RESULTS = {"T-101": "pass", "T-102": "fail"}
BUGS = {"alarm_module": [{"id": "BUG-7", "severity": "high"}], "battery_driver": []}


# ---------- tools (read / run only) ----------

def list_changes(release: str) -> list[str]:
    return CHANGES.get(release, [])

def find_tests(component: str) -> list[str]:
    return TESTS.get(component, [])

def run_tests(test_ids: list[str]) -> dict[str, str]:
    return {t: RESULTS.get(t, "not_found") for t in test_ids}

def get_open_bugs(component: str) -> list[dict]:
    return BUGS.get(component, [])


# ---------- the plan's shape ----------

ToolName = Literal["find_tests", "run_tests", "get_open_bugs"]


class Step(BaseModel):
    id: int
    tool: ToolName                 # Pydantic rejects any other tool name
    args: dict = {}
    depends_on: list[int] = []


class Plan(BaseModel):
    goal: str
    steps: list[Step] = Field(min_length=1, max_length=8)   # Pydantic enforces the step limit


# ---------- Piece 1: validate_plan ----------

def validate_plan(plan: Plan, components: list[str]) -> list[str]:
    """Return a list of problems; [] means the plan is safe to run."""
    problems = []
    steps = plan.model_dump()["steps"]
    seen_ids = set()
    find_test_ids = {s["id"] for s in steps if s["tool"] == "find_tests"}

    for step in steps:
        sid = step["id"]
        # 1. unique ids
        if sid in seen_ids:
            problems.append(f"Step {sid} has a duplicate step id.")
        # 2. depends_on only points backwards
        for dep in step["depends_on"]:
            if dep not in seen_ids:
                problems.append(f"Step {sid} depends on step {dep}, which does not come before it.")
        seen_ids.add(sid)
        # 3. known components only
        if step["tool"] in ("find_tests", "get_open_bugs"):
            comp = step["args"].get("component")
            if comp not in components:
                problems.append(f"Step {sid} uses unknown component {comp}; allowed: {components}.")
        # 5. run_tests needs a find_tests to feed it
        if step["tool"] == "run_tests":
            if not any(dep in find_test_ids for dep in step["depends_on"]):
                problems.append(f"Step {sid} is run_tests but does not depend on any find_tests step.")

    # 4. coverage: what is MISSING
    for comp in components:
        if not any(s["tool"] == "find_tests" and s["args"].get("component") == comp for s in steps):
            problems.append(f"Component {comp} has no find_tests step.")
        if not any(s["tool"] == "get_open_bugs" and s["args"].get("component") == comp for s in steps):
            problems.append(f"Component {comp} has no get_open_bugs step.")
    return problems


# ---------- Piece 2a: execute_plan ----------

TOOLS = {"find_tests": find_tests, "run_tests": run_tests, "get_open_bugs": get_open_bugs}


def execute_plan(plan: Plan) -> dict[int, object]:
    """Run a VALIDATED plan. Return {step_id: result}. One failing tool never stops the run."""
    results = {}
    for step in plan.steps:
        try:
            if step.tool == "run_tests":
                test_ids = []
                for dep in step.depends_on:
                    if isinstance(results.get(dep), list):      # skip error dicts
                        test_ids.extend(results[dep])
                results[step.id] = TOOLS["run_tests"](test_ids) if test_ids else {}
            else:
                results[step.id] = TOOLS[step.tool](**step.args)
        except Exception as e:
            results[step.id] = {"error": str(e)}
    return results


# ---------- Piece 2b: build_report ----------

BLOCKING_SEVERITIES = {"high", "critical"}
NOTE = "Recommendation only. A human makes the release decision."


def build_report(components: list[str], plan: Plan, results: dict[int, object]) -> dict:
    """Per-component status (NOT READY > UNKNOWN > NOT TESTED > READY) + GO / NO-GO."""

    def result_for(tool, comp):
        for s in plan.steps:
            if s.tool == tool and s.args.get("component") == comp:
                return results.get(s.id)
        return None

    outcomes = {}                                   # {test_id: "pass"/"fail"/...}
    for s in plan.steps:
        r = results.get(s.id)
        if s.tool == "run_tests" and isinstance(r, dict) and "error" not in r:
            outcomes.update(r)

    report = {}
    for comp in components:
        tests, bugs = result_for("find_tests", comp), result_for("get_open_bugs", comp)
        bad, unknown = [], []

        for name, r in (("find_tests", tests), ("get_open_bugs", bugs)):
            if isinstance(r, dict) and "error" in r:
                unknown.append(f"{name} failed: {r['error']}")
        if isinstance(tests, list):
            for t in tests:
                outcome = outcomes.get(t)
                if outcome is None:
                    unknown.append(f"{t} has no result")
                elif outcome != "pass":
                    bad.append(f"{t} {'failed' if outcome == 'fail' else outcome}")
        if isinstance(bugs, list):
            for b in bugs:
                if b["severity"] in BLOCKING_SEVERITIES:
                    bad.append(f"{b['id']} ({b['severity']}) is open")

        if bad:
            report[comp] = {"status": "NOT READY", "reasons": bad}
        elif unknown:
            report[comp] = {"status": "UNKNOWN", "reasons": unknown}
        elif tests == []:
            report[comp] = {"status": "NOT TESTED", "reasons": ["no tests found"]}
        else:
            report[comp] = {"status": "READY", "reasons": []}

    all_ready = all(v["status"] == "READY" for v in report.values())
    return {"components": report, "recommendation": "GO" if all_ready else "NO-GO", "note": NOTE}


# ---------- Piece 3: the LLM planner ----------

PLANNER_SYSTEM = """You are a release-readiness planner. You do NOT run anything.
You write a plan that other code will check and run.

Tools a plan may use:
- find_tests(component)     -> list of test ids for that component
- get_open_bugs(component)  -> open bugs for that component
- run_tests()               -> runs the test ids found by the find_tests steps it depends_on.
                               Give it NO args; list those find_tests step ids in depends_on.

Rules:
1. Step ids are unique integers starting at 1.
2. depends_on may only list EARLIER step ids.
3. Use only the components you are given.
4. Every component needs a find_tests step AND a get_open_bugs step.
5. Every run_tests step depends on at least one find_tests step.
6. At most 8 steps.

Reply with ONLY a JSON object, no prose, in this shape:
{"goal": "...", "steps": [
  {"id": 1, "tool": "find_tests", "args": {"component": "x"}, "depends_on": []},
  {"id": 2, "tool": "run_tests", "args": {}, "depends_on": [1]}
]}"""


def planner_message(release: str, components: list[str]) -> str:
    return (f"Release: {release}\n"
            f"Changed components: {json.dumps(components)}\n"
            f"Write the plan to check if this release is ready.")


def parse_plan(text: str) -> Plan:
    """Model text -> Plan. Tolerates ```json fences / stray prose around the object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in the reply.")
    return Plan.model_validate_json(text[start:end + 1])


def make_plan(release: str, components: list[str],
              call_model: Callable[[str, list[dict]], str],
              max_attempts: int = 3) -> tuple[Plan | None, list[dict]]:
    """Ask the LLM for a plan; check it; on failure send the problems back and retry.

    Returns (plan, log). plan is None if every attempt failed -> a human must look.
    """
    messages = [{"role": "user", "content": planner_message(release, components)}]
    log = []

    for attempt in range(1, max_attempts + 1):
        reply = call_model(PLANNER_SYSTEM, messages)
        try:
            plan = parse_plan(reply)
            problems = validate_plan(plan, components)       # OUR rules, in code
        except (ValidationError, ValueError) as e:
            plan, problems = None, [f"Your reply was not a valid plan: {e}"]

        log.append({"attempt": attempt, "problems": problems})
        if not problems:
            return plan, log

        # retry with feedback: keep the history, tell the model exactly what was wrong
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content":
                         "That plan has problems:\n- " + "\n- ".join(problems) +
                         "\nReply with a corrected plan as JSON only."})
    return None, log


def run_release_check(release: str, call_model) -> dict:
    """The whole agent: plan -> validate -> execute -> report."""
    components = list_changes(release)
    if not components:
        return {"recommendation": "NO-GO", "error": f"No changes found for release {release}.",
                "note": NOTE}

    plan, log = make_plan(release, components, call_model)
    if plan is None:
        return {"recommendation": "NO-GO", "error": "Could not get a valid plan; needs human review.",
                "planning_log": log, "note": NOTE}

    results = execute_plan(plan)
    report = build_report(components, plan, results)
    report["plan"] = plan.model_dump()
    report["planning_log"] = log
    return report


# ---------- real model (only used when you run this file) ----------

def real_model(system: str, messages: list[dict]) -> str:
    import anthropic
    client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY
    resp = client.messages.create(model=MODEL, max_tokens=1024, system=system, messages=messages)
    return resp.content[0].text


if __name__ == "__main__":
    print(json.dumps(run_release_check("2.4", real_model), indent=2))