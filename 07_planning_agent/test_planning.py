"""Piece 3 tests: fake models only — no API key, no cost."""
import json

from planning import make_plan, parse_plan, run_release_check

COMPONENTS = ["alarm_module", "battery_driver"]

GOOD = {"goal": "2.4 readiness", "steps": [
    {"id": 1, "tool": "find_tests", "args": {"component": "alarm_module"}, "depends_on": []},
    {"id": 2, "tool": "find_tests", "args": {"component": "battery_driver"}, "depends_on": []},
    {"id": 3, "tool": "get_open_bugs", "args": {"component": "alarm_module"}, "depends_on": []},
    {"id": 4, "tool": "get_open_bugs", "args": {"component": "battery_driver"}, "depends_on": []},
    {"id": 5, "tool": "run_tests", "args": {}, "depends_on": [1, 2]},
]}
MISSING_BATTERY_BUGS = {"goal": "2.4", "steps": [s for s in GOOD["steps"] if s["id"] != 4]}
WRONG_TOOL = {"goal": "2.4", "steps": [{"id": 1, "tool": "deploy", "args": {}, "depends_on": []}]}


def scripted(*replies):
    """A fake model that returns these replies in order and records what it was sent."""
    it = iter(replies)
    def model(system, messages):
        model.calls.append([dict(m) for m in messages])
        return next(it)
    model.calls = []
    return model


def test_parse_plan_strips_code_fences():
    plan = parse_plan("Here you go:\n```json\n" + json.dumps(GOOD) + "\n```")
    assert len(plan.steps) == 5


def test_good_plan_first_try():
    model = scripted(json.dumps(GOOD))
    plan, log = make_plan("2.4", COMPONENTS, model)
    assert plan is not None and len(log) == 1 and log[0]["problems"] == []


def test_missing_coverage_is_sent_back_and_fixed():
    model = scripted(json.dumps(MISSING_BATTERY_BUGS), json.dumps(GOOD))
    plan, log = make_plan("2.4", COMPONENTS, model)
    assert plan is not None and len(log) == 2
    feedback = model.calls[1][-1]["content"]              # what the model saw on retry
    assert "battery_driver" in feedback and "get_open_bugs" in feedback


def test_invalid_tool_name_is_caught_by_pydantic_and_retried():
    model = scripted(json.dumps(WRONG_TOOL), json.dumps(GOOD))
    plan, log = make_plan("2.4", COMPONENTS, model)
    assert plan is not None
    assert "not a valid plan" in log[0]["problems"][0]


def test_not_json_is_retried():
    model = scripted("Sure! I would check the alarm first.", json.dumps(GOOD))
    plan, _ = make_plan("2.4", COMPONENTS, model)
    assert plan is not None


def test_gives_up_after_max_attempts():
    model = scripted(*[json.dumps(MISSING_BATTERY_BUGS)] * 3)
    plan, log = make_plan("2.4", COMPONENTS, model, max_attempts=3)
    assert plan is None and len(log) == 3


def test_end_to_end_release_2_4_is_no_go():
    report = run_release_check("2.4", scripted(json.dumps(GOOD)))
    assert report["recommendation"] == "NO-GO"
    assert report["components"]["alarm_module"]["status"] == "NOT READY"
    assert report["components"]["battery_driver"]["status"] == "NOT TESTED"


def test_no_valid_plan_means_no_go_not_crash():
    report = run_release_check("2.4", scripted(*[json.dumps(WRONG_TOOL)] * 3))
    assert report["recommendation"] == "NO-GO" and "human review" in report["error"]


def test_unknown_release_does_not_call_the_model():
    model = scripted()                                    # would crash if called
    report = run_release_check("9.9", model)
    assert report["recommendation"] == "NO-GO" and model.calls == []