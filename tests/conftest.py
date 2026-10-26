"""Shared fixtures; plain helpers and factories live in ``helpers.py``."""

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from helpers import write_dataset

# Hypothesis profiles. ``ci`` (the default) is deterministic; select another with the
# ``HYPOTHESIS_PROFILE`` environment variable, e.g. ``HYPOTHESIS_PROFILE=dev uv run pytest``.
_COMMON = settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("ci", _COMMON, max_examples=200, derandomize=True)
settings.register_profile("dev", _COMMON, max_examples=2000, derandomize=False)
# Loaded while conftest is imported, i.e. before any test module is collected.
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep tests that pin known defects (``xfail``) out of the coverage measurement.

    Lines that only an expected-to-fail test executes must not help the 100% gate: the gate
    should describe the behaviour the suite actually verifies.
    """
    cov = config.pluginmanager.get_plugin("_cov")
    if getattr(cov, "cov_controller", None) is None:
        return  # coverage is off (--no-cov): the no_cover marker would crash pytest-cov
    for item in items:
        if item.get_closest_marker("xfail") is not None:
            item.add_marker(pytest.mark.no_cover)


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """A minimal valid dataset (input dir) with one bank, one facility and no loans."""
    return write_dataset(tmp_path / "ds")
