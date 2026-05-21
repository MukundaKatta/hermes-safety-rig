"""hermes-safety-rig: drop-in safety layer for Hermes Agent.

Wraps a tool function with four reliability primitives:
  1. agentvet     - validate arguments before the call
  2. agentguard   - block egress to off-allowlist domains
  3. AgentBudget  - cap per-run token + USD spend
  4. agentcast    - shape and validate output before returning

The rig is intentionally thin. Each primitive is a separately-published
library that owns its own logic. SafetyRig is the composition.
"""

from __future__ import annotations

from .rig import SafetyRig, BudgetExceededError, DomainBlockedError

__all__ = ["SafetyRig", "BudgetExceededError", "DomainBlockedError"]
