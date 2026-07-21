"""Built-in and locally saved reusable report templates."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .instrument_metadata import randomized_acquisition_time
from .models import COAConfig
from .numbering import application_data_dir
from .scenarios import load_default_config, load_scenario_json, scenario_json


BUILTIN_TEMPLATE_NAME = "Vitum Lab default"


class TemplateError(ValueError):
    pass


def template_directory() -> Path:
    return application_data_dir() / "templates"


def with_random_acquisition_time(config: COAConfig) -> COAConfig:
    updated = config.model_copy(deep=True)
    timezone_info = updated.instrument_metadata.acquired_at.tzinfo
    if timezone_info is None:
        raise TemplateError("The template acquisition timestamp must include a UTC offset")
    updated.instrument_metadata.acquired_at = randomized_acquisition_time(
        updated.analysis_date,
        timezone_info,
    )
    return updated


def list_template_names() -> list[str]:
    names = [BUILTIN_TEMPLATE_NAME]
    directory = template_directory()
    if not directory.exists():
        return names
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stem.casefold()):
        try:
            load_scenario_json(path.read_bytes())
        except (OSError, TemplateError, ValueError):
            continue
        display_name = path.stem.replace("_", " ")
        if display_name not in names:
            names.append(display_name)
    return names


def _safe_filename(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_")
    if not normalized:
        raise TemplateError("Template name must contain a letter or number")
    return normalized[:80]


def _saved_template_paths() -> dict[str, Path]:
    result: dict[str, Path] = {}
    directory = template_directory()
    if not directory.exists():
        return result
    for path in directory.glob("*.json"):
        result[path.stem.replace("_", " ")] = path
    return result


def load_template(name: str) -> COAConfig:
    if name == BUILTIN_TEMPLATE_NAME:
        return with_random_acquisition_time(load_default_config())
    path = _saved_template_paths().get(name)
    if path is None:
        raise TemplateError(f"Saved template not found: {name}")
    try:
        return with_random_acquisition_time(load_scenario_json(path.read_bytes()))
    except OSError as exc:
        raise TemplateError(f"Saved template could not be read: {name}") from exc


def save_template(name: str, config: COAConfig) -> str:
    safe_name = _safe_filename(name)
    display_name = safe_name.replace("_", " ")
    if display_name.casefold() == BUILTIN_TEMPLATE_NAME.casefold():
        raise TemplateError("Choose a different name; the built-in template cannot be overwritten")
    directory = template_directory()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{safe_name}.json"
    handle = tempfile.NamedTemporaryFile(
        "wb",
        dir=directory,
        prefix="template-",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        handle.write(scenario_json(config))
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(temporary, destination)
    finally:
        if not handle.closed:
            handle.close()
        temporary.unlink(missing_ok=True)
    return display_name
