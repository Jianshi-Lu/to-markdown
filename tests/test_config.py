from configuration.config import (
    Settings,
    get_conversion_settings,
    get_http_server_settings,
)


def _settings(**overrides) -> Settings:
    values = {
        "omlx_base_url": "http://127.0.0.1:8000/v1",
        "omlx_api_key": "sensitive-test-value",
        "omlx_model": "ocr-model",
        "omlx_ocr_prompt": "document parsing.",
        "omlx_ocr_max_tokens": 1024,
        "omlx_ocr_temperature": 0.0,
        "omlx_ocr_repetition_penalty": 1.1,
        "max_upload_mb": 100,
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_repr_hides_api_key() -> None:
    settings = _settings()

    assert "sensitive-test-value" not in repr(settings)


def test_conversion_settings_read_environment(monkeypatch) -> None:
    get_conversion_settings.cache_clear()
    monkeypatch.setenv("OMLX_BASE_URL", "http://omlx.test/v1")
    monkeypatch.setenv("OMLX_API_KEY", "sensitive-test-value")
    monkeypatch.setenv("OMLX_MODEL", "ocr-test-model")
    try:
        settings = get_conversion_settings()

        assert settings.omlx_base_url == "http://omlx.test/v1"
        assert settings.omlx_api_key == "sensitive-test-value"
        assert settings.omlx_model == "ocr-test-model"
        assert "sensitive-test-value" not in repr(settings)
    finally:
        get_conversion_settings.cache_clear()


def test_http_server_settings_read_environment(monkeypatch) -> None:
    get_http_server_settings.cache_clear()
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("SERVER_PORT", "18081")
    monkeypatch.setenv("SERVER_LOG_LEVEL", "warning")
    try:
        settings = get_http_server_settings()

        assert settings.host == "0.0.0.0"
        assert settings.port == 18081
        assert settings.log_level == "WARNING"
    finally:
        get_http_server_settings.cache_clear()
