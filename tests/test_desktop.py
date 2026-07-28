from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
    app.state.model_executor.shutdown(wait=True)
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


def test_server_shutdown_escalates_when_graceful_stop_times_out() -> None:
    server = SimpleNamespace(should_exit=False, force_exit=False)
    server_thread = Mock()
    server_thread.is_alive.side_effect = [True, False]

    run_desktop._stop_server(server, server_thread)

    assert server.should_exit is True
    assert server.force_exit is True
    assert server_thread.join.call_args_list[0].kwargs == {"timeout": 10}
    assert server_thread.join.call_args_list[1].kwargs == {"timeout": 3}


def test_desktop_hard_exits_when_background_worker_does_not_stop(monkeypatch) -> None:
    server = SimpleNamespace(should_exit=False, force_exit=False)
    server_thread = Mock()
    server_thread.is_alive.return_value = False
    worker = SimpleNamespace(name="lead-worker_0")
    monkeypatch.setattr(run_desktop, "_active_worker_threads", Mock(return_value=[worker]))
    hard_exit = Mock()
    monkeypatch.setattr(run_desktop, "_hard_exit", hard_exit)

    run_desktop._stop_server(server, server_thread, worker_timeout=0)

    hard_exit.assert_called_once_with(0)


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ValueError("workspace database is invalid"), id="invalid-database"),
        pytest.param(PermissionError("workspace drive is unavailable"), id="unavailable-drive"),
        pytest.param(FileExistsError("migration destination changed"), id="migration-conflict"),
        pytest.param(RuntimeError("migration marker does not match"), id="migration-marker"),
        pytest.param(OSError("exports folder is read-only"), id="exports-folder"),
    ],
)
def test_storage_error_is_shown_and_instance_lock_is_released(
    monkeypatch, tmp_path, error
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("LEAD_SCRAPER_NO_BROWSER", "1")
    monkeypatch.setattr(run_desktop, "_prepare_storage", Mock(side_effect=error))
    show_error = Mock()
    monkeypatch.setattr(run_desktop, "_show_startup_error", show_error)

    run_desktop.main()

    show_error.assert_called_once()
    assert str(error) in show_error.call_args.args[1]
    assert not run_desktop._INSTANCE_HANDLES
