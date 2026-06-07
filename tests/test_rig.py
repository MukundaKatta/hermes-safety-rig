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
        get(city=123)  # type: ignore[arg-type]


def test_validates_positional_args() -> None:
    # Schema validation must work for positionally-passed args too, not only
    # kwargs — otherwise a wrapped tool called positionally raises a spurious
    # "missing required arg" instead of the real type error.
    rig = SafetyRig()

    @rig.wrap(schema={"city": "string"})
    def get(city: str) -> dict:
        return {"ok": city}

    with pytest.raises(TypeError, match="expected string"):
        get(123)  # type: ignore[arg-type]

    assert get("Paris") == {"ok": "Paris"}


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


def test_no_allowlist_permits_any_url() -> None:
    # With an empty allowlist, egress is unrestricted.
    rig = SafetyRig()

    @rig.wrap()
    def fetch(url: str) -> dict:
        return {"url": url}

    assert fetch("https://anything.example.net/x") == {
        "url": "https://anything.example.net/x"
    }


def test_budget_allows_calls_under_cap() -> None:
    rig = SafetyRig(daily_usd_cap=1.0, daily_token_cap=1_000)

    @rig.wrap(est_usd=0.30, est_tokens=100)
    def call() -> dict:
        return {"ok": True}

    # Three calls stay under the $1.00 / 1000-token caps.
    for _ in range(3):
        assert call() == {"ok": True}

    # The fourth would push spend to $1.20, over the cap.
    with pytest.raises(BudgetExceededError):
        call()


def test_blocked_domain_does_not_consume_budget() -> None:
    # A call rejected by the egress allowlist must not charge the budget,
    # so a later legitimate call still has its full budget available.
    rig = SafetyRig(
        allowlist=["example.com"], daily_usd_cap=0.10, daily_token_cap=1_000
    )

    @rig.wrap(est_usd=0.10)
    def fetch(url: str) -> dict:
        return {"url": url}

    with pytest.raises(DomainBlockedError):
        fetch("https://attacker.example.org/x")

    # Budget was not charged by the blocked call, so this allowed call fits.
    assert fetch("https://example.com/x") == {"url": "https://example.com/x"}
