"""Shared fixtures; plain helpers and factories live in ``helpers.py``."""

from pathlib import Path

import pytest

from helpers import write_dataset


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """A minimal valid dataset (input dir) with one bank, one facility and no loans."""
    return write_dataset(tmp_path / "ds")
