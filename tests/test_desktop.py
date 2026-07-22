from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import run_desktop


def test_desktop_server_does_not_configure_console_logging(monkeypatch, tmp_path) -> None:
    run = Mock()
    monkeypatch.setattr(run_desktop.uvicorn, "run", run)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("LEAD_SCRAPER_NO_BROWSER", "1")

    run_desktop.main()

    app = run.call_args.args[0]
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert 0 < run.call_args.kwargs["port"] < 65536
    assert run.call_args.kwargs["reload"] is False
    assert run.call_args.kwargs["log_config"] is None
    assert run.call_args.kwargs["access_log"] is False
    assert Path(run_desktop.os.environ["PLAYWRIGHT_BROWSERS_PATH"]) == tmp_path / "ms-playwright"
    app.state.executor.shutdown(wait=True)


def test_package_includes_runtime_data_files() -> None:
    package_script = Path(__file__).parents[1] / "scripts" / "package.ps1"
    contents = package_script.read_text(encoding="utf-8")

    assert "--collect-data tldextract" in contents
    assert "--collect-data undetected_playwright" in contents
    assert "--collect-all tiktoken" in contents
    assert "--collect-all webview" in contents
    assert "--hidden-import webview.platforms.edgechromium" in contents
    assert "--hidden-import tiktoken_ext.openai_public" in contents


def test_second_launch_opens_the_running_instance(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "leadroom.instance.json"
    state_path.write_text(
        json.dumps(
            {
                "pid": 1234,
                "port": 8765,
                "token": "a-valid-launch-token-with-enough-length",
            }
        ),
        encoding="utf-8",
    )
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.delenv("LEAD_SCRAPER_NO_BROWSER", raising=False)
    monkeypatch.setattr(run_desktop, "urlopen", Mock(return_value=response))
    focused = Mock(return_value=True)
    monkeypatch.setattr(run_desktop, "_focus_window", focused)

    assert run_desktop._activate_existing_instance(state_path, timeout=0.1)
    focused.assert_called_once_with("Leadroom")


def test_closing_native_window_stops_the_local_server(monkeypatch) -> None:
    class EventHook:
        def __iadd__(self, handler):
            closed_handlers.append(handler)
            return self

    closed_handlers = []
    window = SimpleNamespace(events=SimpleNamespace(closed=EventHook()))
    server = SimpleNamespace(should_exit=False, run=Mock(), install_signal_handlers=None)
    webview = SimpleNamespace(
        create_window=Mock(return_value=window),
        start=Mock(side_effect=lambda **_kwargs: closed_handlers[0]()),
    )
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(run_desktop.uvicorn, "Server", Mock(return_value=server))
    monkeypatch.setattr(run_desktop, "urlopen", Mock(return_value=response))

    icon_path = Path("assets/leadroom-icon.ico")
    run_desktop._run_native_window(Mock(), 8765, "a-valid-launch-token", icon_path)

    assert server.should_exit is True
    webview.create_window.assert_called_once()
    webview.start.assert_called_once_with(
        gui="edgechromium",
        debug=False,
        private_mode=False,
        icon=str(icon_path),
    )
