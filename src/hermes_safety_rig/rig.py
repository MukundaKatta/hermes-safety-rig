"""The SafetyRig wrapper.

Wraps any tool callable so Hermes Agent (or any agent) cannot:
  * call the tool with a malformed argument shape (agentvet),
  * fetch a URL outside the declared allowlist from inside the tool (agentguard),
  * trip past the daily token / USD cap (AgentBudget),
  * return a payload that does not parse to the declared output schema (agentcast).

Each primitive is a separate published package; the rig composes them.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlparse


class BudgetExceededError(RuntimeError):
    """Raised when the next call would push the cumulative spend past the cap."""


class DomainBlockedError(RuntimeError):
    """Raised when a tool's inner fetch hits a domain outside the allowlist."""


@dataclass
class _RunningBudget:
    """In-memory rolling budget. Replace with a persistent store for prod."""

    daily_usd_cap: float
    daily_token_cap: int
    usd_spent: float = 0.0
    tokens_spent: int = 0

    def check_and_charge(self, usd: float, tokens: int) -> None:
        if self.usd_spent + usd > self.daily_usd_cap:
            raise BudgetExceededError(
                f"USD cap {self.daily_usd_cap:.2f} would be exceeded "
                f"(current {self.usd_spent:.2f} + this {usd:.2f})"
            )
        if self.tokens_spent + tokens > self.daily_token_cap:
            raise BudgetExceededError(
                f"Token cap {self.daily_token_cap} would be exceeded"
            )
        self.usd_spent += usd
        self.tokens_spent += tokens


@dataclass
class SafetyRig:
    """One-stop safety wrapper for a Hermes Agent tool.

    Usage::

        rig = SafetyRig(allowlist=["api.x.com"], daily_usd_cap=2.5)

        @rig.wrap(schema={"city": "string"})
        def get_weather(city: str) -> dict: ...
    """

    allowlist: Iterable[str] = field(default_factory=list)
    daily_usd_cap: float = 5.0
    daily_token_cap: int = 5_000_000
    _budget: _RunningBudget = field(init=False)

    def __post_init__(self) -> None:
        self._budget = _RunningBudget(
            daily_usd_cap=self.daily_usd_cap,
            daily_token_cap=self.daily_token_cap,
        )

    def wrap(
        self,
        schema: dict[str, str] | None = None,
        output_schema: dict[str, str] | None = None,
        est_usd: float = 0.0,
        est_tokens: int = 0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator that wraps a tool function with the four checks."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            @functools.wraps(fn)
            def wrapped(*args: Any, **kwargs: Any) -> Any:
                # 1. argument validation (agentvet stand-in; in production import the real lib)
                if schema is not None:
                    _validate_args(kwargs, schema)
                # 2. budget check (charge optimistically before the call)
                self._budget.check_and_charge(est_usd, est_tokens)
                # 3. egress allowlist for any URL passed positionally or as kwargs
                _check_egress(args, kwargs, allowlist=set(self.allowlist))
                # 4. invoke real tool
                result = fn(*args, **kwargs)
                # 5. output shape validation (agentcast stand-in)
                if output_schema is not None:
                    _validate_output(result, output_schema)
                return result

            return wrapped

        return decorator


def _validate_args(kwargs: dict[str, Any], schema: dict[str, str]) -> None:
    """Reference implementation. In production this delegates to `agentvet`."""
    for key, type_hint in schema.items():
        if key not in kwargs:
            raise ValueError(f"missing required arg: {key}")
        value = kwargs[key]
        if type_hint == "string" and not isinstance(value, str):
            raise TypeError(
                f"arg {key!r}: expected string, got {type(value).__name__}. "
                f"Hermes Agent retry hint: pass {key!r} as a string."
            )
        if type_hint == "int" and not isinstance(value, int):
            raise TypeError(
                f"arg {key!r}: expected int, got {type(value).__name__}."
            )


def _check_egress(
    args: tuple, kwargs: dict, *, allowlist: set[str]
) -> None:
    """Reference implementation. In production this delegates to `agentguard`."""
    if not allowlist:
        return
    candidates: list[str] = []
    for v in list(args) + list(kwargs.values()):
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            candidates.append(v)
    for url in candidates:
        host = urlparse(url).hostname or ""
        if host not in allowlist:
            raise DomainBlockedError(
                f"egress to {host!r} blocked; allowlist={sorted(allowlist)}"
            )


def _validate_output(result: Any, output_schema: dict[str, str]) -> None:
    """Reference implementation. In production this delegates to `agentcast`."""
    if not isinstance(result, dict):
        raise TypeError(
            f"tool output: expected dict, got {type(result).__name__}"
        )
    for key, type_hint in output_schema.items():
        if key not in result:
            raise ValueError(f"output missing required field: {key}")
        value = result[key]
        if type_hint == "string" and not isinstance(value, str):
            raise TypeError(
                f"output {key!r}: expected string, got {type(value).__name__}"
            )
        if type_hint == "number" and not isinstance(value, (int, float)):
            raise TypeError(
                f"output {key!r}: expected number, got {type(value).__name__}"
            )
