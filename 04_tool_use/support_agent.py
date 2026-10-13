from anthropic import Anthropic, AnthropicError, APIConnectionError
import json
import re
import traceback

ERROR_CODES = {"E-47": {"meaning": "Air in line detected", "severity": "critical",
                        "action": "Stop infusion, clamp line, follow facility air-in-line procedure"},
               "E-12": {"meaning": "Downstream occlusion", "severity": "high",
                        "action": "Check line for kinks or closed clamps"}}
PUMPS = {"SN-4471": {"state": "stopped", "alarms": ["E-47"], "battery": "62%"}}
TICKETS = []


MODEL = "claude-haiku-4-5-20251001"
TOOLS = [
    {
  "name": "lookup_error_code",
  "description": "Look up what a pump error code means: its meaning, severity (low/high/critical) and recommended action from the service manual. Use when the user mentions a code shown on a pump display, such as E-47. This does NOT check a live pump; use get_pump_status for that.",
  "input_schema": {
    "type": "object",
    "properties": {
      "error_code": {
        "type": "string",
        "pattern": "^E-\\d{2}$",
        "description": "Error code exactly as shown on the display, e.g. E-47"
      }
    },
    "required": ["error_code"]
  }
},

    {
  "name": "get_pump_status",
  "description": "Get the current status of a pump, including its state (infusing/stopped), any active alarms, and battery level. Use when the user mentions a specific pump by serial number.",
  "input_schema": {
    "type": "object",
    "properties": {
      "serial_number": {
        "type": "string",
        "pattern": "^SN-\\d{4}$",
        "description": "Serial number of the pump, e.g. SN-4471"
      }
    },
    "required": ["serial_number"]
  }
},
{
    "name": "create_support_ticket",
    "description": "Create a support ticket for the issue described by the user. Use when the user reports a problem that requires follow-up by the support team.",
    "input_schema": {
      "type": "object", 
      "properties": {
        "description": {
          "type": "string",
          "description": "Description of the issue reported by the user"
        }
      },
      "required": ["description"]
    }
  }     
]

SYSTEM = ("You are a support assistant for an infusion-pump manufacturer, helping hospital staff. "
          "Answer only from tool results; never invent error codes, meanings or pump states. "
          "Never make a clinical safety decision, such as whether it is safe to keep infusing: "
          "state what the service manual says and tell the user to follow their facility's safety "
          "procedure and contact the safety team. Create a support ticket only for real device problems.")


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Run one tool. Returns (json_string, is_error). Never raises."""
    try:
        if name == "lookup_error_code":
            code = args.get("error_code", "")
            if not re.fullmatch(r"E-\d{2}", code):
                return json.dumps({"error": f"Invalid code format {code!r}; expected like E-47"}), True
            if code not in ERROR_CODES:
                return json.dumps({"error": f"{code} is not in the service manual"}), True
            if  ERROR_CODES[code]['severity'] == 'critical':
                return json.dumps({"error": f"{code} is a critical error code; {ERROR_CODES[code]['action']}"}), True
            return json.dumps(ERROR_CODES[code]), False
        if name == "get_pump_status":
            code = args.get("serial_number", "")
            if not re.fullmatch(r"SN-\d{4}", code):
                return json.dumps({"error": f"Invalid serial number format {code!r}; expected like SN-4471"}), True
            if code not in PUMPS:
                return json.dumps({"error": f"{code} is not a known pump"}), True
            return json.dumps(PUMPS[code]), False
        if name == "create_support_ticket":
            code = args.get("serial_number", "")
            error_code = args.get("error_code", "")
            summary = args.get("summary", "")
            if not re.fullmatch(r"SN-\d{4}", code):
                return json.dumps({"error": f"Invalid serial number format {code!r}; expected like SN-4471"}), True
            if not re.fullmatch(r"E-\d{2}", error_code):
                return json.dumps({"error": f"Invalid error code format {error_code!r}; expected like E-47"}), True
            if code not in PUMPS:
                return json.dumps({"error": f"{code} is not a known pump"}), True
            if error_code not in ERROR_CODES:
                return json.dumps({"error": f"{error_code} is not in the service manual"}), True
            if error_code in [ticket["error_code"] for ticket in TICKETS]:
                return json.dumps({"error": f"Ticket for {error_code} already exists"}), True
            ticket = {"serial_number": code, "error_code": error_code, "summary": summary}
            TICKETS.append(ticket)
            return json.dumps({"ticket_id": len(TICKETS), "status": "created", "ticket": ticket}), False
        return json.dumps({"error": f"Unknown tool: {name}"}), True
    except Exception as e:
        return json.dumps({"error": f"Tool failed: {e}"}), True


def answer(message: str) -> str:
    client = Anthropic()
    messages = [{"role": "user", "content": message}]
    try:
        resp = client.messages.create(model=MODEL, max_tokens=1000, system=SYSTEM,
                                    tools=TOOLS, messages=messages)
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})   # the model's request
            results = []
            for block in resp.content:                                        # EVERY tool call
                if block.type == "tool_use":
                    print(f"Tool call: {block.name}({json.dumps(block.input)})")
                    output, is_error = run_tool(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": output, "is_error": is_error})
            messages.append({"role": "user", "content": results})             # results, matched by ID
            resp = client.messages.create(model=MODEL, max_tokens=1000, system=SYSTEM,
                                        tools=TOOLS, messages=messages)
            if resp.stop_reason == "tool_use":
                print("NOTE: the model wanted another tool call; handling that is Lesson 7")
    except APIConnectionError as exc:
        if exc.__cause__:
            traceback.print_exception(exc.__cause__)
        print("Underlying cause:", repr(exc.__cause__))
        raise            
    return "".join(b.text for b in resp.content if b.type == "text")


if __name__ == "__main__":
    print(answer("Pump SN-4471 is showing E-47. Is it safe to keep infusing?"))

