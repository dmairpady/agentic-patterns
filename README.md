# Agentic AI patterns from scratch
![tests](https://github.com/dmairpady/agentic-patterns/actions/workflows/tests.yml/badge.svg)

LLM workflow and agent patterns built with the raw Anthropic API, no frameworks,
each with tests that use fake LLMs so they run free in CI.

| Folder | Pattern | What it shows |
|---|---|---|
| 01_memory | Conversation memory | Statelessness; why token cost grows each turn |
| 02_chaining | Prompt chaining | Steps with a code gate and retry-with-feedback |
| 03_routing | Routing + structured output | Safety pre-filter, prompt-injection defence, Pydantic validation, safe fallbacks |
| 04_tool_use | Tool use | Tool schemas, parallel tool calls, argument validation, duplicate-safe write tool |.

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python 03_routing/routing.py   # real API
pytest -v                      # fake LLMs, free
```
## Design notes
- Code, not the LLM, makes business decisions (priority,  fallbacks).
- The LLM is injected as a function, so every failure path is testable.

## License
MIT License © 2026 Dhanya
