"""Tests for backend settings (BE-05)."""

import pytest

from app.config import get_settings


def test_cors_origins_default_to_vite_dev_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert get_settings().cors_origins == ("http://localhost:5173", "http://127.0.0.1:5173")


def test_cors_origins_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://a.test , http://b.test ")
    # Spaces around each origin are trimmed.
    assert get_settings().cors_origins == ("http://a.test", "http://b.test")


def test_empty_cors_origins_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " , ")
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        get_settings()


@pytest.mark.parametrize(
    "origin",
    [
        "localhost:5173",
        "http://",
        "ftp://a.test",
        "http://localhost:5173/",
        "http://a.test/path",
        "http://a.test?key=value",
        "http://a.test#fragment",
        "http://a.test?",
        "http://a.test#",
        "http://user:password@a.test",
        "http://@a.test",
        "http://a.test:",
        "http://a.test:bad",
        "http://a.test:65536",
        "http://a.test:0",
        "http://[bad-ip]",
        "http://a. test",
        "http://a.\ttest",
        "http://a\\b.test",
        "http://a..test",
        "http://-bad-.test",
        "http://localhost.:5173",
        "*",
        "http://*.test",
        "null",
    ],
)
def test_malformed_cors_origin_raises(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", origin)
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        get_settings()


@pytest.mark.parametrize(
    "origin",
    ["https://a.test", "http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173"],
)
def test_explicit_cors_origin_is_accepted(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    monkeypatch.setenv("CORS_ORIGINS", origin)
    assert get_settings().cors_origins == (origin,)


def test_error_names_the_bad_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://ok.test,http://localhost:5173/")
    with pytest.raises(ValueError, match="'http://localhost:5173/'"):
        get_settings()


def test_one_malformed_origin_rejects_entire_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,not-an-origin")
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        get_settings()


@pytest.mark.parametrize(
    "configured,expected",
    [
        ("HTTP://LOCALHOST:80", "http://localhost"),
        ("https://A.TEST:443", "https://a.test"),
        ("http://[0:0:0:0:0:0:0:1]:5173", "http://[::1]:5173"),
        ("https://bücher.test", "https://xn--bcher-kva.test"),
    ],
)
def test_origins_match_browser_serialization(
    monkeypatch: pytest.MonkeyPatch, configured: str, expected: str
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", configured)
    assert get_settings().cors_origins == (expected,)


def test_mock_mode_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOCK_MODE", raising=False)
    assert get_settings().mock_mode is True


@pytest.mark.parametrize("raw,expected", [("1", True), ("0", False), (" 1 ", True), (" 0 ", False)])
def test_mock_mode_reads_flag(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("MOCK_MODE", raw)
    assert get_settings().mock_mode is expected


@pytest.mark.parametrize("raw", ["", "true", "false", "yes", "2", "-1"])
def test_invalid_mock_mode_raises(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("MOCK_MODE", raw)
    with pytest.raises(ValueError, match="MOCK_MODE"):
        get_settings()


def test_openai_key_is_read_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", " sk-test-not-real ")
    assert get_settings().openai_api_key == "sk-test-not-real"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_or_blank_openai_key_is_none(monkeypatch: pytest.MonkeyPatch, raw) -> None:
    if raw is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", raw)
    assert get_settings().openai_api_key is None


def test_openai_key_never_appears_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert "sk-test-not-real" not in repr(get_settings())


def test_openai_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert get_settings().openai_model == "gpt-4o-mini"


def test_openai_model_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    assert get_settings().openai_model == "gpt-test"
