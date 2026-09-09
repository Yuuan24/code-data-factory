"""Versioned terminal reward projections; verification evidence remains immutable."""

from __future__ import annotations

from datetime import datetime


def reward_from_verification(
    *,
    attempt_id: str,
    verification_id: str,
    verification_status: str,
    outcome: str,
    policy_version: str,
    created_at: datetime,
) -> dict[str, object]:
    if verification_status == "VERIFIED":
        if outcome not in {"PASS", "FAIL"}:
            raise ValueError("verified terminal outcome must be PASS or FAIL")
        value: float | None = 1.0 if outcome == "PASS" else 0.0
        availability = "KNOWN"
        reason = None
    else:
        value = None
        availability = "UNKNOWN"
        reason = verification_status
    return {
        "reward_record_id": f"reward-{verification_id}-{policy_version}",
        "attempt_id": attempt_id,
        "verification_id": verification_id,
        "reward_policy_version": policy_version,
        "reward_scope": "TERMINAL",
        "total_reward": value,
        "availability": availability,
        "unavailable_reason": reason,
        "created_at": created_at.isoformat(),
    }
