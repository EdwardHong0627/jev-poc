import pytest

from jev_bot.config import DEFAULT_ENDPOINT, load_config


def test_load_config_rejects_missing_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JEV_API_TOKEN", raising=False)

    with pytest.raises(EnvironmentError, match="JEV_API_TOKEN"):
        load_config()


def test_load_config_rejects_blank_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "   ")

    with pytest.raises(EnvironmentError, match="JEV_API_TOKEN"):
        load_config()


def test_load_config_uses_default_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.delenv("JEV_ENDPOINT", raising=False)

    config = load_config()

    assert config.token == "test-token"
    assert config.endpoint == DEFAULT_ENDPOINT


def test_load_config_uses_endpoint_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "https://openrouter.ai/api/alpha/decisions?v=2")

    assert load_config().endpoint == "https://openrouter.ai/api/alpha/decisions?v=2"


def test_load_config_uses_default_for_blank_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "   ")

    assert load_config().endpoint == DEFAULT_ENDPOINT


def test_load_config_rejects_http_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "http://openrouter.ai/api/alpha/decisions")

    with pytest.raises(ValueError, match="JEV_ENDPOINT"):
        load_config()


def test_load_config_rejects_userinfo_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv(
        "JEV_ENDPOINT", "https://user:pass@openrouter.ai/api/alpha/decisions"
    )

    with pytest.raises(ValueError, match="JEV_ENDPOINT"):
        load_config()


def test_load_config_rejects_non_openrouter_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "https://example.test/decisions")

    with pytest.raises(ValueError, match="JEV_ENDPOINT"):
        load_config()


def test_load_config_rejects_malformed_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")
    monkeypatch.setenv("JEV_ENDPOINT", "not-a-url")

    with pytest.raises(ValueError, match="JEV_ENDPOINT"):
        load_config()


def test_config_repr_redacts_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "test-token")

    assert "test-token" not in repr(load_config())


def test_load_config_reads_dotenv_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("JEV_API_TOKEN", raising=False)
    monkeypatch.delenv("JEV_ENDPOINT", raising=False)
    (tmp_path / ".env").write_text(
        "JEV_API_TOKEN=dotenv-token\n"
        "JEV_ENDPOINT=https://openrouter.ai/api/alpha/decisions?v=dotenv\n"
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.token == "dotenv-token"
    assert config.endpoint == "https://openrouter.ai/api/alpha/decisions?v=dotenv"
    assert "dotenv-token" not in capsys.readouterr().out


def test_load_config_prefers_environ_over_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("JEV_API_TOKEN", "env-token")
    (tmp_path / ".env").write_text("JEV_API_TOKEN=dotenv-token\n")
    monkeypatch.chdir(tmp_path)

    assert load_config().token == "env-token"
