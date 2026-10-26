import importlib
from importlib.metadata import PackageNotFoundError

import pytest

import balance_the_loan_books


def test_public_api_is_exported() -> None:
    for name in balance_the_loan_books.__all__:
        assert hasattr(balance_the_loan_books, name)


def test_version_is_a_string() -> None:
    assert isinstance(balance_the_loan_books.__version__, str)


def test_version_falls_back_when_package_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", missing)
    try:
        reloaded = importlib.reload(balance_the_loan_books)
        assert reloaded.__version__ == "0.0.0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(balance_the_loan_books)
