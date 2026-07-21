"""Local application directories, cache controls, and launcher signaling."""

from __future__ import annotations

import os
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .numbering import application_data_dir


def cache_directory() -> Path:
    return application_data_dir() / "cache"


def recent_history_path() -> Path:
    return application_data_dir() / "recent-files.json"


def recent_report_numbers() -> set[str]:
    try:
        data = json.loads(recent_history_path().read_text(encoding="utf-8"))
        return {
            str(item["report_no"])
            for item in data.get("exports", [])
            if isinstance(item, dict) and item.get("report_no")
        }
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def record_recent_export(
    report_no: str,
    generation_identifier: str | None,
    *,
    protected: bool,
) -> None:
    """Record only collision-relevant metadata, never report bodies or secrets."""

    path = recent_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        exports = data.get("exports", []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        exports = []
    entry = {
        "report_no": report_no,
        "generation_identifier": generation_identifier,
        "protected": protected,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    exports = [
        item
        for item in exports
        if not (
            isinstance(item, dict)
            and item.get("report_no") == report_no
            and item.get("generation_identifier") == generation_identifier
        )
    ]
    exports.append(entry)
    payload = json.dumps({"exports": exports[-200:]}, indent=2, sort_keys=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix="recent-", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    try:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary, path)
    finally:
        if not handle.closed:
            handle.close()
        temporary.unlink(missing_ok=True)


def exit_request_path() -> Path:
    return application_data_dir() / "exit.request"


def clear_cache_and_history() -> None:
    """Clear disposable state without touching numbering or user-selected files."""

    cache = cache_directory()
    if cache.exists():
        shutil.rmtree(cache)
    recent_history_path().unlink(missing_ok=True)


def request_application_exit() -> None:
    path = exit_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("exit\n", encoding="ascii")


def clear_disposable_temporary_files() -> None:
    temporary = application_data_dir() / "temp"
    if temporary.exists():
        shutil.rmtree(temporary, ignore_errors=True)
