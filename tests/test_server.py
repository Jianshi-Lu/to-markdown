"""验证 HTTP Server 入口使用集中配置。"""

import sys

import api.server as server_module
from configuration import HttpServerSettings


def test_main_uses_http_server_settings(monkeypatch) -> None:
    """入口应通过配置 getter 取得监听参数，而不是直接读取环境变量。"""

    captured: dict[str, object] = {}
    settings = HttpServerSettings(
        host="127.0.0.9",
        port=18081,
        log_level="WARNING",
    )
    monkeypatch.setattr(server_module, "get_http_server_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["server.py"])

    def run(target, **kwargs) -> None:
        captured["target"] = target
        captured.update(kwargs)

    monkeypatch.setattr(server_module.uvicorn, "run", run)

    assert server_module.main() == 0
    assert captured["target"] is server_module.app
    assert captured["host"] == "127.0.0.9"
    assert captured["port"] == 18081
    assert captured["log_level"] == "warning"
    assert captured["reload"] is False
