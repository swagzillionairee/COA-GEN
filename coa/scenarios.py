"""Portable scenario JSON, strict compatibility policy, and v1.0 migration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .constants import SCHEMA_VERSION
from .models import COAConfig


class ScenarioError(ValueError):
    pass


def find_forbidden_password_path(value: Any, path: str = "$") -> str | None:
    """Find a nested password-like field without inspecting or echoing its value."""

    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            nested_path = f"{path}.{key_text}"
            normalized_key = key_text.casefold()
            if "password" in normalized_key and normalized_key != "password_source":
                return nested_path
            found = find_forbidden_password_path(nested, nested_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found = find_forbidden_password_path(nested, f"{path}[{index}]")
            if found:
                return found
    return None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioError(f"Duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def migrate_scenario(data: dict[str, Any]) -> dict[str, Any]:
    version = str(data.get("schema_version", ""))
    if version == SCHEMA_VERSION:
        return deepcopy(data)
    if version != "1.0":
        if version > SCHEMA_VERSION:
            raise ScenarioError(
                f"Scenario schema {version!r} is newer than supported schema {SCHEMA_VERSION}; "
                "upgrade the application before loading it."
            )
        raise ScenarioError(f"Unsupported scenario schema version: {version or 'missing'}")

    migrated = deepcopy(data)
    migrated["schema_version"] = "1.1"
    branding = migrated.setdefault("branding", {})
    branding.setdefault("logo", None)
    branding.setdefault("logo_use_authorized", False)
    approval = migrated.setdefault("approval", {})
    approval.setdefault("signature_image", None)
    approval.setdefault("signature_image_use_authorized", False)
    migrated.setdefault(
        "document_protection",
        {
            "watermark": {
                "enabled": False,
                "text": "CONFIDENTIAL - {client} - {report_no}",
                "font": "DejaVu Sans",
                "size": 30,
                "color": "#64748B",
                "opacity": 0.12,
                "rotation_degrees": 35,
                "placement": "center",
                "repeat": False,
            },
            "editing_restriction": {
                "enabled": False,
                "allow_document_changes": False,
                "allow_annotations": False,
                "allow_form_filling": False,
                "allow_page_assembly": False,
                "allow_printing": True,
                "allow_copying": False,
                "allow_accessibility": True,
                "password_source": "prompt_on_export",
            },
        },
    )
    migrated.setdefault("sample_image", None)
    return migrated


def load_scenario_json(content: bytes | str) -> COAConfig:
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenarioError("Scenario is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ScenarioError("Scenario JSON must contain one object")
    forbidden_path = find_forbidden_password_path(raw)
    if forbidden_path:
        raise ScenarioError(
            f"Export passwords are forbidden in scenario JSON ({forbidden_path})"
        )
    try:
        return COAConfig.model_validate(migrate_scenario(raw))
    except ValidationError as exc:
        raise ScenarioError(str(exc)) from exc


def scenario_json(config: COAConfig, *, indent: int = 2) -> bytes:
    payload = config.model_dump(mode="json", exclude_none=False)
    serialized = json.dumps(payload, indent=indent, sort_keys=True, ensure_ascii=False)
    return (serialized + "\n").encode("utf-8")


def load_default_config(template_path: Path | None = None) -> COAConfig:
    path = template_path or Path(__file__).resolve().parents[1] / "templates" / "default_coa.json"
    if path.exists():
        return load_scenario_json(path.read_bytes())
    return COAConfig()
