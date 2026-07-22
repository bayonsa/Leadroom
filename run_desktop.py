from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

# Windowed PyInstaller apps have no standard streams, while Uvicorn configures stream logging.
_DEVNULL_HANDLES = []
_INSTANCE_HANDLES = []
for stream_name in ("stdout", "stderr"):
    if getattr(sys, stream_name) is None:
        handle = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        setattr(sys, stream_name, handle)
        _DEVNULL_HANDLES.append(handle)


def _instance_url(port: int, token: str) -> str:
    return f"http://127.0.0.1:{port}/?launch_token={token}"


def _write_instance_state(path: Path, port: int, token: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"pid": os.getpid(), "port": port, "token": token}),
        encoding="utf-8",
    )
    temporary.replace(path)


def _focus_window(title: str) -> bool:
    if os.name != "nt":
        return False
    import ctypes

    handle = ctypes.windll.user32.FindWindowW(None, title)
    if not handle:
        return False
    ctypes.windll.user32.ShowWindow(handle, 9)  # SW_RESTORE
    ctypes.windll.user32.SetForegroundWindow(handle)
    return True


def _activate_existing_instance(path: Path, timeout: float = 10) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            port = int(state["port"])
            token = str(state["token"])
            if not 1 <= port <= 65535 or len(token) < 20:
                raise ValueError("invalid instance state")
            with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1):
                pass
            if os.getenv("LEAD_SCRAPER_NO_BROWSER") == "1" or _focus_window("Leadroom"):
                return True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, URLError):
            pass
        time.sleep(0.2)
    return False


def _run_native_window(app, port: int, launch_token: str, icon_path: Path) -> None:
    import webview

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        reload=False,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server_thread = threading.Thread(target=server.run, name="leadroom-api", daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1):
                break
        except (OSError, URLError):
            time.sleep(0.2)
    else:
        server.should_exit = True
        server_thread.join(timeout=5)
        raise RuntimeError("Leadroom API did not become ready")

    window = webview.create_window(
        "Leadroom",
        _instance_url(port, launch_token),
        width=1420,
        height=900,
        min_size=(960, 640),
        background_color="#f8f7f3",
    )

    def choose_directory(initial_path: str = "") -> str:
        result = window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=initial_path or "",
        )
        return str(result[0]) if result else ""

    app.state.choose_directory = choose_directory
    window.events.closed += lambda *_args: setattr(server, "should_exit", True)
    try:
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            icon=str(icon_path),
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)


def main() -> None:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    bootstrap_root = Path(
        os.getenv("LEADROOM_BOOTSTRAP_ROOT")
        or (Path(os.getenv("LOCALAPPDATA", Path.home())) / "Leadroom")
    )
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    instance_state = bootstrap_root / "leadroom.instance.json"
    instance_handle = (bootstrap_root / "leadroom.instance.lock").open("a+b")
    instance_handle.seek(0, 2)
    if instance_handle.tell() == 0:
        instance_handle.write(b"0")
        instance_handle.flush()
    instance_handle.seek(0)
    try:
        import msvcrt
        msvcrt.locking(instance_handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        instance_handle.close()
        _activate_existing_instance(instance_state)
        return
    _INSTANCE_HANDLES.append(instance_handle)
    (bootstrap_root / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[RotatingFileHandler(
            bootstrap_root / "logs" / "leadroom.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )],
    )
    from app.storage import apply_pending_storage

    storage_config_path = bootstrap_root / "storage.json"
    storage = apply_pending_storage(storage_config_path, bootstrap_root)
    data_root = Path(storage["data_root"])
    for child in ("exports",):
        (data_root / child).mkdir(parents=True, exist_ok=True)
    os.environ["LEADROOM_BOOTSTRAP_ROOT"] = str(bootstrap_root)
    os.environ["LEADROOM_STORAGE_CONFIG"] = str(storage_config_path)
    os.environ["LEADROOM_DATA_ROOT"] = str(data_root)
    os.environ["LEADROOM_CACHE_DIR"] = storage["cache_dir"]
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = storage["browser_dir"]
    os.environ["OLLAMA_MODELS"] = storage["ollama_dir"]
    os.environ.setdefault("LEAD_SCRAPER_FRONTEND_DIR", str(bundle_root / "frontend" / "dist"))
    os.environ["LEAD_SCRAPER_DATABASE"] = str(data_root / "lead_scraper.db")
    previous_launch_token = os.environ.get("LEADROOM_LAUNCH_TOKEN")
    launch_token = secrets.token_urlsafe(32)
    os.environ["LEADROOM_LAUNCH_TOKEN"] = launch_token
    configured_port = int(os.getenv("LEADROOM_PORT", "0"))
    if configured_port:
        port = configured_port
    else:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
    _write_instance_state(instance_state, port, launch_token)
    from app.api import create_app

    try:
        app = create_app()
        if os.getenv("LEAD_SCRAPER_NO_BROWSER") == "1":
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=port,
                reload=False,
                log_config=None,
                access_log=False,
            )
        else:
            _run_native_window(
                app,
                port,
                launch_token,
                bundle_root / "assets" / "leadroom-icon.ico",
            )
    finally:
        try:
            state = json.loads(instance_state.read_text(encoding="utf-8"))
            if state.get("token") == launch_token:
                instance_state.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass
        try:
            import msvcrt
            instance_handle.seek(0)
            msvcrt.locking(instance_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        instance_handle.close()
        if instance_handle in _INSTANCE_HANDLES:
            _INSTANCE_HANDLES.remove(instance_handle)
        if previous_launch_token is None:
            os.environ.pop("LEADROOM_LAUNCH_TOKEN", None)
        else:
            os.environ["LEADROOM_LAUNCH_TOKEN"] = previous_launch_token


if __name__ == "__main__":
    main()
