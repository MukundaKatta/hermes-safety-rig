"""SafetyRig sanity tests. Runs without any Hermes install."""

from __future__ import annotations

import pytest

from hermes_safety_rig import BudgetExceededError, DomainBlockedError, SafetyRig


def test_validates_args() -> None:
    rig = SafetyRig()

    @rig.wrap(schema={"city": "string"})
    def get(city: str) -> dict:
        return {"ok": city}

    with pytest.raises(TypeError, match="expected string"):
        get(city=123)            # type: ignore[arg-type]


def test_blocks_off_allowlist_domain() -> None:
    rig = SafetyRig(allowlist=["example.com"])

    @rig.wrap()
    def fetch(url: str) -> dict:
        return {"url": url}

    with pytest.raises(DomainBlockedError):
        fetch("https://attacker.example.org/x")


def test_allows_on_allowlist_domain() -> None:
    rig = SafetyRig(allowlist=["example.com"])

    @rig.wrap()
    def fetch(url: str) -> dict:
        return {"url": url}

    assert fetch("https://example.com/x") == {"url": "https://example.com/x"}


def test_trips_budget() -> None:
    rig = SafetyRig(daily_usd_cap=0.10, daily_token_cap=1_000)

    @rig.wrap(est_usd=0.20)
    def expensive() -> dict:
        return {"ok": True}

    with pytest.raises(BudgetExceededError):
        expensive()


def test_validates_output_shape() -> None:
    rig = SafetyRig()

    @rig.wrap(output_schema={"event_id": "string"})
    def broken() -> dict:
        return {"wrong_key": 1}

    with pytest.raises(ValueError, match="missing required field"):
        broken()
