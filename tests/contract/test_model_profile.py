from __future__ import annotations

from pathlib import Path

from code_data_factory.interaction.model_profile import load_model_candidates


def test_local_sampling_model_candidates_freeze_primary_fallback_and_thinking_mode() -> None:
    profile = load_model_candidates(Path("configs/experiments/model-candidates.yaml"))

    assert profile.primary.name == "qwen3-8b"
    assert profile.fallback.name == "qwen3-4b"
    assert profile.primary.revision == "b968826d9c46dd6066d109eabc6255188de91218"
    assert profile.primary.thinking_mode == "disabled"
    assert profile.fallback_on_resource_failure_only is True
