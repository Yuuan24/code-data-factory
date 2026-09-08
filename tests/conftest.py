from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-real-resources", action="store_true", default=False)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-real-resources"):
        return
    skip = pytest.mark.skip(reason="requires explicit --run-real-resources and real-resource gate")
    for item in items:
        if "real_resources" in item.keywords:
            item.add_marker(skip)
