# hermes-safety-rig

A drop-in safety layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Wraps Hermes' tool execution with four reliability primitives so a long-running personal agent can't burn money, leak data, hallucinate tool args, or emit unparseable output to downstream systems.

Built for the [Hermes Agent Challenge](https://dev.to/challenges/hermes-agent-2026-05-15).

## What it does

Hermes Agent is designed to run continuously on a $5 VPS, learn skills from experience, and persist across sessions. That long-running property is the strength — and also the failure surface. Four classes of failure get worse the longer an agent runs:

| Failure | Primitive | What it does |
|---|---|---|
| Tool arg hallucination | [`agentvet`](https://pypi.org/project/agentvet/) | Validate every tool call against a schema; throw `ToolArgError` with an LLM-friendly retry hint |
| Surprise egress (PHI/secrets to attacker.com) | [`agentguard`](https://pypi.org/project/agentguard/) | Declarative domain allowlist; raise if a tool tries to fetch off-list |
| Runaway cost | [`AgentBudget`](https://www.npmjs.com/package/@mukundakatta/agentbudget) | Per-run token + USD caps; trip when the next call would exceed |
| Unparseable output to downstream | [`agentcast`](https://pypi.org/project/agentcast/) | Structured-output validate-and-retry loop |

The rig exposes one Python class — `SafetyRig` — that wraps any Hermes tool function and runs it through this gauntlet before execution.

## Architecture

```
+--------------+
| Hermes Agent |
+------+-------+
       |
       | tool_call(name, args)
       v
+------+-----------------+
|       SafetyRig        |
|                        |
|  agentvet.validate     |  --> ToolArgError + retry hint
|  agentguard.check_url  |  --> DomainBlockedError
|  AgentBudget.check     |  --> BudgetExceededError
|        ↓               |
|   original tool fn     |  --> raw output
|        ↓               |
|  agentcast.shape       |  --> typed output | retry
+------+-----------------+
       |
       v
   Downstream system
```

## Install

```bash
pip install hermes-safety-rig
```

Or from this repo:

```bash
pip install -e .
```

## Quickstart

```python
from hermes_safety_rig import SafetyRig
from hermes_agent import register_skill          # whatever the actual Hermes import path is

rig = SafetyRig(
    allowlist=["api.openweathermap.org", "calendar.google.com"],
    daily_usd_cap=2.50,
    daily_token_cap=2_000_000,
)

@rig.wrap(schema={"city": "string", "units": "metric|imperial"})
def get_weather(city: str, units: str = "metric") -> dict:
    ...  # the actual API call

# Register the wrapped tool with Hermes
register_skill("get_weather", get_weather)
```

When the model calls `get_weather({"city": 12345})` — wrong type — `agentvet` throws before the HTTP call, and Hermes' next turn gets `expected city to be a string, got int`. The model self-corrects on the next attempt.

When the model tries to fetch `http://attacker.com/exfil` from inside a tool, `agentguard` raises.

When the cumulative cost across the day would exceed `$2.50`, `AgentBudget` trips and Hermes pauses the loop.

## Demo

`examples/persistent_inbox_triage.py` runs a Hermes Agent that triages Gmail every 10 minutes. Without the rig, three failure modes get reproduced on demand: dosage hallucination on calendar event, exfil attempt via prompt injection in an email, cost runaway during a long thread summarization loop. With the rig wired in, all three are caught and Hermes self-corrects or pauses.

```bash
python examples/persistent_inbox_triage.py --without-rig   # watch it fail
python examples/persistent_inbox_triage.py --with-rig      # watch it survive
```

## Why each primitive matters for a long-running agent

- **agentvet:** the longer a model runs, the more its tool-call shape drifts. Hard schemas catch drift on call 1, not on call 10,000.
- **agentguard:** prompt injection in an email Hermes is summarizing is a real attack surface. An allowlist is the cheapest control.
- **AgentBudget:** Hermes can chain dozens of LLM calls per task. A budget cap is the difference between a $0.50 day and a $50 day.
- **agentcast:** Hermes' output often feeds another system (a calendar API, a database write). Structured-output validation prevents silent corruption.

## Why this is novel work for the contest

Hermes Agent is the dependency; the rig is brand new. Built during the contest period. The four primitives it composes are pre-existing published packages — `agentvet`, `agentguard`, `agentcast`, `AgentBudget` — all on npm/PyPI under MIT/Apache 2.0. They are runtime dependencies, used through their public API. The novel contribution is the composition: the `SafetyRig` class, the per-failure-mode demo, the Hermes-specific glue.

## License

Apache 2.0
