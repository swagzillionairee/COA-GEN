"""Atomic local report-number sequence with batch reservation."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator


class NumberingError(RuntimeError):
    pass


@dataclass(frozen=True)
class NumberingPolicy:
    prefix: str = ""
    separator: str = "-"
    padding: int = 6
    sequence_start: int = 1
    rollover_annually: bool = True

    def format(self, year: int, sequence: int) -> str:
        prefix = f"{self.prefix}{self.separator}" if self.prefix else ""
        return f"{prefix}{year}{self.separator}{sequence:0{self.padding}d}"


def application_data_dir() -> Path:
    override = os.environ.get("COA_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "COAGenerator"


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
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


def _load_state(path: Path, policy: NumberingPolicy, year: int) -> dict[str, int]:
    if not path.exists():
        return {"year": year, "next_sequence": policy.sequence_start}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        stored_year = int(state["year"])
        next_sequence = int(state["next_sequence"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise NumberingError("Local numbering state is corrupt; it was not reset automatically") from exc
    if next_sequence < policy.sequence_start:
        raise NumberingError("Local numbering sequence is below its configured start")
    if policy.rollover_annually and stored_year != year:
        return {"year": year, "next_sequence": policy.sequence_start}
    return {"year": stored_year, "next_sequence": next_sequence}


def _atomic_write(path: Path, state: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix="numbering-", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    try:
        json.dump(state, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary, path)
    finally:
        if not handle.closed:
            handle.close()
        temporary.unlink(missing_ok=True)


def reserve_report_numbers(
    count: int,
    *,
    policy: NumberingPolicy = NumberingPolicy(),
    existing_numbers: set[str] | None = None,
    state_directory: Path | None = None,
    today: date | None = None,
) -> list[str]:
    if count < 1 or count > 100:
        raise NumberingError("Reservation count must be between 1 and 100")
    directory = state_directory or application_data_dir()
    state_path = directory / "numbering.json"
    lock_path = directory / "numbering.lock"
    year = (today or date.today()).year
    existing = existing_numbers or set()
    with _exclusive_lock(lock_path):
        state = _load_state(state_path, policy, year)
        reserved: list[str] = []
        sequence = state["next_sequence"]
        while len(reserved) < count:
            candidate = policy.format(state["year"], sequence)
            sequence += 1
            if candidate in existing or candidate in reserved:
                continue
            reserved.append(candidate)
        state["next_sequence"] = sequence
        _atomic_write(state_path, state)
    return reserved


def manual_number_warning(report_no: str, existing_numbers: set[str]) -> str | None:
    if report_no in existing_numbers:
        return f"Report number {report_no!r} already exists or is reserved in this batch."
    return None
