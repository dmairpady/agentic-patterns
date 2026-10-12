#Lesson 3: requirement → feature file, with gate
from anthropic import Anthropic
import os, sys, json
client = Anthropic()

REQUIREMENT = """REQ-101: When an air bubble is detected in the line, the infusion pump
shall stop infusion and raise a high-priority alarm. The user may silence the alarm
for 2 minutes. Infusion must not resume until the user clears the air bubble."""

STEP_DEFINITIONS = [
    "Given the pump is infusing",
    "When an air bubble is detected",
    "When the user silences the alarm",
    "When the user clears the air bubble",
    "Then the infusion should stop",
    "Then a high-priority alarm should sound",
    "Then the alarm should be silenced for 2 minutes",
    "Then the infusion should remain stopped",
]

SYSTEM = "You are a Software QA engineer"
MODEL = "claude-haiku-4-5-20251001"


def call_llm(prompt: str, max_tokens: int = 1000) -> str:
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens, system=SYSTEM,
                                  messages=[{"role": "user", "content": prompt}])
    if resp.stop_reason == "max_tokens":
        print("WARNING: output was truncated")
    return resp.content[0].text

def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip()

def find_invalid_lines(feature_text: str) -> list[str]:
    invalid = []
    current = None                                   # last Given/When/Then seen
    for raw in feature_text.splitlines():
        line = raw.strip()                           # 1. remove indentation
        first, _, rest = line.partition(" ")         # 2. split off first word
        if first in ("Given", "When", "Then"):
            current = first                          # 3. remember the real keyword
        elif first in ("And", "But"):
            if current is None:                      # 4a. "And" with nothing before it
                invalid.append(line)
                continue
            first = current                          # 4b. "And" means the previous keyword
        else:
            continue                                 # 5. skip Feature, Scenario, blank lines
        if f"{first} {rest}" not in STEP_DEFINITIONS:   # 6. compare the full step
            invalid.append(line)
    return invalid
# STEP 1: extract acceptance criteria as a JSON list of strings
prompt = f"""Extract the acceptance criteria from the following requirement {REQUIREMENT} and return only a JSON list of strings."""

output = call_llm(prompt)

try:
    criteria = json.loads(strip_fences(output))
except json.JSONDecodeError:
    print("ERROR: Failed to parse JSON from LLM output")
    print("LLM output was:")
    print(output)
    sys.exit(1)

if not isinstance(criteria, list) or not criteria:
    print("ERROR: LLM returned an empty list of acceptance criteria")
    sys.exit(1)


# STEP 2: generate the feature file
#   TODO: prompt includes the criteria from Step 1 AND the STEP_DEFINITIONS list,
#         and says "Use only these exact steps. Return only the feature file."
prompt = f"""Generate a Gherkin feature file for the following requirement: {REQUIREMENT}.
Use the following acceptance criteria: {criteria}
Use only the following step definitions: {STEP_DEFINITIONS}
Return only the contents of a valid .feature file no explanations or extra text."""

output = strip_fences(call_llm(prompt, max_tokens=2000))
         
print(output)
# GATE: find invalid lines
#   TODO: for each line in the output, if it starts with Given/When/Then/And,
#         check the step text against STEP_DEFINITIONS; collect invalid lines
invalid_lines = find_invalid_lines(output)
# RETRY: if invalid lines exist, call once more listing exactly which lines were
#   invalid; re-run the gate; if still invalid, print "Needs human review"
if invalid_lines:
    print("ERROR: Invalid lines found in feature file:")
    for line in invalid_lines:
        print(f"  {line}")
    prompt = f"""The following lines in the feature file are invalid: {invalid_lines}.
Generate a Gherkin feature file for the following requirement: {REQUIREMENT}.
Use the following acceptance criteria: {criteria}
Use only the following step definitions: {STEP_DEFINITIONS}
Return only the contents of a valid .feature file , no explanations or extra text."""
    output = strip_fences(call_llm(prompt, max_tokens=2000))
    invalid_lines = find_invalid_lines(output)
    if invalid_lines:
        print("ERROR: Invalid lines found in feature file after retry:")
        for line in invalid_lines:
            print(f"  {line}")
        print("Needs human review")
        sys.exit(1)
os.makedirs("features", exist_ok=True)

# Finally, your code writes the result to features/infusion_pump.feature
with open("features/infusion_pump.feature", "w") as f:
    f.write(output)


good = "  Scenario: x\n    Given the pump is infusing\n    When an air bubble is detected\n    Then the infusion should stop\n    And a high-priority alarm should sound"
bad_text = "    Given the pump is infusing\n    When the power button is pressed"
bad_keyword = "    When an air bubble is detected\n    And a high-priority alarm should sound"

assert find_invalid_lines(good) == []
assert find_invalid_lines(bad_text) == ["When the power button is pressed"]
assert find_invalid_lines(bad_keyword) == ["And a high-priority alarm should sound"]