from types import SimpleNamespace as NS
from agent import run_agent


# --- helpers: build fake API replies ---
def tool_call(name, args, id="t1"):
    return NS(type="tool_use", name=name, input=args, id=id)

def text(t):
    return NS(type="text", text=t)

def reply(*blocks, stop="end_turn"):
    return NS(stop_reason=stop, content=list(blocks))

def scripted(*replies):
    it = iter(replies)
    calls = []
    def model(messages):
        calls.append(messages)
        return next(it)
    model.calls = calls
    return model


# --- test 1 ---
def test_two_parallel_tools_then_answer():
    # 1. ARRANGE: write the script — what the "model" will say, in order
    model = scripted(
        reply(tool_call("get_pump_status", {"serial_number": "SN-4471"}, id="a"),
              tool_call("lookup_error_code", {"error_code": "E-12"}, id="b"),
              stop="tool_use"),
        reply(text("Pump is stopped; E-12 means downstream occlusion.")),
    )

    # 2. ACT: run your real agent loop with the fake model
    answer, steps = run_agent("Check SN-4471, it shows E-12", model)

    # 3. ASSERT: check the answer, which tools ran, and how many model calls
    assert answer == "Pump is stopped; E-12 means downstream occlusion."
    assert [s["tool"] for s in steps] == ["get_pump_status", "lookup_error_code"]
    assert len(model.calls) == 2

#----test 2: same tool called three times ----
def test_same_tool_thrice():
    model = scripted(
        reply(tool_call("lookup_error_code", {"error_code": "E-12"}, id="a"),
              stop="tool_use"),
        reply(tool_call("lookup_error_code", {"error_code": "E-12"}, id="a"),
              stop="tool_use"),
        reply(tool_call("lookup_error_code", {"error_code": "E-12"}, id="a"),
              stop="tool_use"),
        reply(text("E-12 means downstream occlusion; Error E-47 (critical): Air in line detected. Service manual action: Stop infusion, clamp line, follow facility air-in-line procedure. Follow your facility's safety procedure and contact your safety team;Stopped: the agent repeated the same tool call. Needs human review",)),
    )

    answer, steps = run_agent("Check SN-4471, it shows E-12 ", model)
    assert 'repeated' in answer
    assert [s["tool"] for s in steps] == ["lookup_error_code", "lookup_error_code"]
    assert len(model.calls) == 2

#----test 3: tool keep failing ---
def test_failing_tool():
        model = scripted(
        reply(tool_call("lookup_error_code", {"error_code": "E-98"}, id="a"),
              stop="tool_use"),
        reply(tool_call("lookup_error_code", {"error_code": "E-88"}, id="a"),
              stop="tool_use"),
        reply(tool_call("lookup_error_code", {"error_code": "E-190"}, id="a"),
              stop="tool_use"),
        reply(text("error code doesnt exist")),
    )
        answer, steps = run_agent("Check SN-4471, it shows E-98, E-88,E-190 ", model,2)
        assert all(s["is_error"] for s in steps) 
        assert len(model.calls) == 2

#----test 3: tool hits step limit---
def test_limit_hitting():
        model = scripted(
        reply(tool_call("lookup_error_code", {"error_code": "E-12"}, id="a"),
              stop="tool_use"),
        reply(tool_call("lookup_error_code", {"error_code": "E-11"}, id="a"),
              stop="tool_use"),
        reply(text("E-12 means downstream occlusion; E-11 means upstream occlusion")),
    )
        answer, steps = run_agent("Check SN-4471, it shows E-98, E-88,E-190 ", model,2)
        assert 'reached' in answer
        assert len(model.calls) == 2

def test_critical_code_message():
        model = scripted(
             reply(tool_call("lookup_error_code",{"error_code":"E-12"}, id="a"),stop= "tool_use"),
             reply(tool_call("lookup_error_code",{"error_code":"E-47"},id ="a"),stop='tool_use'),
             reply(text("E-12 means downstream occlusion;Error E-47 (critical): Air in line detected. Service manual action: Stop infusion, clamp line, follow facility air-in-line procedure. Follow your facility's safety procedure and contact your safety team"))
        )
        answer, steps = run_agent("Check SN-4471, it shows E-12, E-47 ", model)
        assert 'critical' in answer
        assert [s["tool"] for s in steps] == ["lookup_error_code", "lookup_error_code"]

def test_model_call_count():
        model = scripted(
             reply(tool_call("lookup_error_code",{"error_code":"E-12"}, id="a"),stop= "tool_use"),
             reply(tool_call("lookup_error_code",{"error_code":"E-47"},id ="a"),stop='tool_use'),
             reply(text("E-12 means downstream occlusion;Error E-47 (critical): Air in line detected. Service manual action: Stop infusion, clamp line, follow facility air-in-line procedure. Follow your facility's safety procedure and contact your safety team"))
        )
        answer, steps = run_agent("Check SN-4471, it shows E-12, E-47 ", model)
        assert len(model.calls) == 2