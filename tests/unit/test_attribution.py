from __future__ import annotations

from code_data_factory.evaluation.attribution import decide_attribution, paired_group_bootstrap


def test_group_bootstrap_resamples_paired_source_template_groups() -> None:
    values = {"group-a": 0.10, "group-b": -0.02}
    assert paired_group_bootstrap(values, draws=100, seed=7) == paired_group_bootstrap(
        values, draws=100, seed=7
    )


def test_attribution_keeps_no_benefit_and_guardrail_regression_distinct() -> None:
    assert (
        decide_attribution(differences={"a": 0.01, "b": 0.01}, interval_lower=0.001).status
        == "NO_PRACTICAL_BENEFIT"
    )
    assert (
        decide_attribution(
            differences={"a": 0.05, "b": 0.03}, interval_lower=0.01, guardrail_regression=True
        ).status
        == "IMPROVEMENT_WITH_GUARDRAIL_REGRESSION"
    )
