from planning import Plan, Step, build_report, NOTE

STEPS = [
    Step(id=1, tool="find_tests", args={"component": "alarm_module"}),
    Step(id=2, tool="find_tests", args={"component": "battery_driver"}),
    Step(id=3, tool="get_open_bugs", args={"component": "alarm_module"}),
    Step(id=4, tool="get_open_bugs", args={"component": "battery_driver"}),
    Step(id=5, tool="run_tests", depends_on=[1, 2]),
]
PLAN = Plan(goal="2.4 readiness", steps=STEPS)
COMPONENTS = ["alarm_module", "battery_driver"]


def results(**overrides):
    """Release 2.4 results (what execute_plan returns), with optional overrides."""
    base = {
        1: ["T-101", "T-102"],
        2: [],
        3: [{"id": "BUG-7", "severity": "high"}],
        4: [],
        5: {"T-101": "pass", "T-102": "fail"},
    }
    base.update({int(k[1:]): v for k, v in overrides.items()})   # s3=... -> step 3
    return base


def test_release_2_4_report():
    report = build_report(COMPONENTS, PLAN, results())
    alarm = report["components"]["alarm_module"]
    assert alarm["status"] == "NOT READY"
    assert any("T-102" in r for r in alarm["reasons"])
    assert any("BUG-7" in r for r in alarm["reasons"])
    assert report["components"]["battery_driver"]["status"] == "NOT TESTED"
    assert report["recommendation"] == "NO-GO"


def test_all_green_is_ready_and_go():
    r = results(s2=["T-201"], s5={"T-101": "pass", "T-102": "pass", "T-201": "pass"},
                s3=[])
    report = build_report(COMPONENTS, PLAN, r)
    assert report["components"]["alarm_module"] == {"status": "READY", "reasons": []}
    assert report["components"]["battery_driver"]["status"] == "READY"
    assert report["recommendation"] == "GO"


def test_low_severity_bug_does_not_block():
    r = results(s2=["T-201"], s5={"T-101": "pass", "T-102": "pass", "T-201": "pass"},
                s3=[{"id": "BUG-9", "severity": "low"}])
    assert build_report(COMPONENTS, PLAN, r)["components"]["alarm_module"]["status"] == "READY"


def test_tool_error_means_unknown():
    r = results(s2={"error": "test server down"})
    battery = build_report(COMPONENTS, PLAN, r)["components"]["battery_driver"]
    assert battery["status"] == "UNKNOWN"
    assert any("test server down" in reason for reason in battery["reasons"])


def test_test_with_no_outcome_is_unknown():
    r = results(s3=[], s5={"T-101": "pass"})          # T-102 never got a result
    alarm = build_report(COMPONENTS, PLAN, r)["components"]["alarm_module"]
    assert alarm["status"] == "UNKNOWN"
    assert any("T-102" in reason for reason in alarm["reasons"])


def test_not_ready_beats_unknown():
    r = results(s1={"error": "test server down"}, s5={})   # tests unknown, BUG-7 still open
    alarm = build_report(COMPONENTS, PLAN, r)["components"]["alarm_module"]
    assert alarm["status"] == "NOT READY"


def test_report_always_says_a_human_decides():
    assert build_report(COMPONENTS, PLAN, results())["note"] == NOTE