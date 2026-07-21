"""Managed localhost-only launcher used by source and packaged Windows builds."""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator

from coa.lifecycle import (
    clear_disposable_temporary_files,
    exit_request_path,
    request_application_exit,
)
from coa.numbering import application_data_dir


PREFERRED_PORT = 8501


def _resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root else Path(__file__).resolve().parent


def _configure_logging() -> logging.Logger:
    log_dir = application_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("coa-launcher")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            log_dir / "launcher.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


@contextmanager
def _launch_lock() -> Iterator[None]:
    path = application_data_dir() / "launcher.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _state_path() -> Path:
    return application_data_dir() / "running-instance.json"


def _read_state() -> dict[str, object] | None:
    try:
        state = json.loads(_state_path().read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(port: int, child_pid: int) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"port": port, "child_pid": child_pid, "launcher_pid": os.getpid()}),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _health(port: int, timeout: float = 0.6) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/_stcore/health", timeout=timeout
        ) as response:
            return response.status == 200
    except Exception:
        return False


def _available_port() -> int:
    for requested in (PREFERRED_PORT, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", requested))
                return int(probe.getsockname()[1])
        except OSError:
            continue
    raise RuntimeError("No local port is available")


def _streamlit_child(app_path: str, port: str) -> int:
    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
        "--client.showErrorDetails=false",
    ]
    return int(streamlit_cli.main() or 0)


def _start_child(port: int, logger: logging.Logger) -> subprocess.Popen[bytes]:
    app_path = _resource_root() / "app.py"
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--streamlit-child", str(app_path), str(port)]
    else:
        command = [sys.executable, str(Path(__file__).resolve()), "--streamlit-child", str(app_path), str(port)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    log_path = application_data_dir() / "logs" / "streamlit.log"
    log_handle = log_path.open("ab")
    logger.info("Starting managed local server on 127.0.0.1:%s", port)
    return subprocess.Popen(
        command,
        cwd=str(_resource_root()),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        env={**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"},
    )


def _wait_ready(child: subprocess.Popen[bytes], port: int, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Local server stopped before becoming ready")
        if _health(port):
            return
        time.sleep(0.2)
    child.terminate()
    raise RuntimeError("Local server did not become ready within 45 seconds")


def launch() -> int:
    logger = _configure_logging()
    exit_request_path().unlink(missing_ok=True)
    with _launch_lock():
        state = _read_state()
        if state is not None:
            try:
                existing_port = int(state["port"])
            except (KeyError, TypeError, ValueError):
                existing_port = 0
            if existing_port and _health(existing_port):
                webbrowser.open(f"http://127.0.0.1:{existing_port}")
                logger.info("Reused existing local server on port %s", existing_port)
                return 0
            _state_path().unlink(missing_ok=True)

        port = _available_port()
        child = _start_child(port, logger)
        _write_state(port, child.pid)

    def stop_child(*_args) -> None:
        if child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    try:
        _wait_ready(child, port)
        webbrowser.open(f"http://127.0.0.1:{port}")
        while child.poll() is None:
            if exit_request_path().exists():
                logger.info("Received clean-exit request")
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                break
            time.sleep(0.5)
        return int(child.returncode or 0)
    finally:
        _state_path().unlink(missing_ok=True)
        exit_request_path().unlink(missing_ok=True)
        clear_disposable_temporary_files()


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "--streamlit-child":
        return _streamlit_child(sys.argv[2], sys.argv[3])
    if "--stop" in sys.argv:
        request_application_exit()
        return 0
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
