"""Small deterministic helpers used by the later formal attribution report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttributionDecision:
    status: str
    mean_difference: float
    interval_lower: float | None
    guardrail_regression: bool


def paired_group_bootstrap(
    values: dict[str, float], *, draws: int, seed: int
) -> tuple[float, float]:
    """Paired group resampling; groups, never rewritten tasks, are resampled."""
    if draws < 1 or not values:
        raise ValueError("bootstrap requires at least one group and draw")
    import random

    groups = sorted(values)
    samples: list[float] = []
    rng = random.Random(seed)
    for _ in range(draws):
        sample = [values[rng.choice(groups)] for _ in groups]
        samples.append(sum(sample) / len(sample))
    samples.sort()
    return samples[int(0.025 * (draws - 1))], samples[int(0.975 * (draws - 1))]


def decide_attribution(
    *,
    differences: dict[str, float],
    interval_lower: float | None,
    practical_threshold: float = 0.02,
    guardrail_regression: bool = False,
    completed_runs: int = 6,
) -> AttributionDecision:
    if not differences:
        raise ValueError("attribution requires paired group differences")
    mean = sum(differences.values()) / len(differences)
    if completed_runs != 6:
        return AttributionDecision("INCOMPLETE", mean, interval_lower, guardrail_regression)
    if guardrail_regression:
        return AttributionDecision(
            "IMPROVEMENT_WITH_GUARDRAIL_REGRESSION"
            if mean >= practical_threshold
            else "GUARDRAIL_REGRESSION",
            mean,
            interval_lower,
            True,
        )
    if mean < practical_threshold:
        return AttributionDecision("NO_PRACTICAL_BENEFIT", mean, interval_lower, False)
    if interval_lower is None or interval_lower <= 0:
        return AttributionDecision("UNCERTAIN", mean, interval_lower, False)
    return AttributionDecision("POSITIVE", mean, interval_lower, False)
