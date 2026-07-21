"""Validated CSV/JSON batch generation with deterministic names and manifest."""

from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .constants import APP_VERSION, MAX_BATCH_SIZE
from .image_processing import process_image_upload
from .models import COAConfig
from .pdf_generator import generate_pdf
from .scenarios import find_forbidden_password_path, scenario_json
from .validation import validate_for_export


@dataclass(frozen=True)
class BatchRowError:
    row: int
    field: str
    message: str


@dataclass
class BatchValidationResult:
    configs: list[COAConfig] = field(default_factory=list)
    errors: list[BatchRowError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def sanitized_output_stem(report_no: str, sample_name: str) -> str:
    raw = f"{report_no}_{sample_name}"
    cleaned = re.sub(r"[^A-Za-z0-9._+-]+", "_", raw).strip("._")
    return (cleaned or "coa-report")[:120]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return False
    raise ValueError(f"Expected a boolean, received {value!r}")


def _merge(target: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


def _csv_row_update(row: dict[str, str]) -> dict[str, Any]:
    scalar_fields = {
        "report_no",
        "client",
        "sample_name",
        "strength_or_presentation",
        "batch_no",
        "receipt_date",
        "analysis_date",
        "report_date",
        "document_issue_date",
        "test",
        "matrix",
        "notes",
        "purity_qualifier",
        "result_note",
        "result_note_marker",
    }
    update: dict[str, Any] = {key: value for key, value in row.items() if key in scalar_fields and value != ""}
    if row.get("number_of_samples"):
        update["number_of_samples"] = int(row["number_of_samples"])
    analytical: dict[str, Any] = {}
    for field_name, converter in {
        "purity_percent": float,
        "purity_display_decimals": int,
        "main_peak_time": float,
        "random_seed": int,
        "absolute_area_scale": float,
    }.items():
        if row.get(field_name):
            analytical[field_name] = converter(row[field_name])
    if row.get("secondary_peak_times"):
        analytical["secondary_peak_times"] = [
            float(value) for value in row["secondary_peak_times"].split(";") if value.strip()
        ]
    if row.get("secondary_peak_percent_areas"):
        analytical["secondary_peak_percent_areas"] = [
            float(value) for value in row["secondary_peak_percent_areas"].split(";") if value.strip()
        ]
    if analytical:
        update["analytical"] = analytical
    if row.get("watermark_text") or row.get("watermark_enabled"):
        update["document_protection"] = {
            "watermark": {
                "enabled": _as_bool(row.get("watermark_enabled", "false")),
                **({"text": row["watermark_text"]} if row.get("watermark_text") else {}),
            }
        }
    if row.get("editing_restriction_enabled"):
        update.setdefault("document_protection", {})["editing_restriction"] = {
            "enabled": _as_bool(row["editing_restriction_enabled"])
        }
    return update


def _load_rows(content: bytes, filename: str) -> list[dict[str, Any]]:
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig")
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]
    if filename.lower().endswith(".json"):
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict) and "reports" in data:
            data = data["reports"]
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError("Batch JSON must be an array of report objects or an object with a reports array")
        return data
    raise ValueError("Batch input must be CSV or JSON")


def _apply_image_paths(
    update: dict[str, Any],
    row: dict[str, Any],
    base_directory: Path | None,
) -> None:
    path_fields = (
        ("sample_image_path", "sample", None),
        ("logo_path", "logo", "branding"),
        ("signature_image_path", "signature", "approval"),
    )
    for field_name, purpose, container in path_fields:
        path_value = row.get(field_name)
        if not path_value:
            continue
        candidate = Path(str(path_value))
        if candidate.is_absolute():
            raise ValueError(f"{field_name} must be relative to the batch input directory")
        if base_directory is None:
            raise ValueError(f"{field_name} cannot be resolved without a batch source directory")
        resolved = (base_directory / candidate).resolve()
        if base_directory.resolve() not in resolved.parents and resolved != base_directory.resolve():
            raise ValueError(f"{field_name} escapes the batch input directory")
        if not resolved.is_file():
            raise ValueError(f"{field_name} does not exist: {candidate}")
        image = process_image_upload(resolved.read_bytes(), resolved.name, purpose)  # type: ignore[arg-type]
        image_data = image.model_dump(mode="json")
        if container is None:
            update["sample_image"] = image_data
            update.setdefault("template", {})["preset"] = "Reference COA with Sample Image"
        elif container == "branding":
            update.setdefault("branding", {})["logo"] = image_data
            update["branding"]["logo_use_authorized"] = _as_bool(row.get("logo_use_authorized", False))
        else:
            update.setdefault("approval", {})["signature_image"] = image_data
            update["approval"]["signature_image_use_authorized"] = _as_bool(
                row.get("signature_image_use_authorized", False)
            )


def validate_batch(
    content: bytes,
    filename: str,
    base_config: COAConfig,
    *,
    source_directory: Path | None = None,
    partial_success: bool = False,
) -> BatchValidationResult:
    result = BatchValidationResult()
    try:
        rows = _load_rows(content, filename)
    except Exception as exc:
        result.errors.append(BatchRowError(0, "file", str(exc)))
        return result
    if not rows:
        result.errors.append(BatchRowError(0, "file", "Batch contains no data rows"))
        return result
    if len(rows) > MAX_BATCH_SIZE:
        result.errors.append(
            BatchRowError(0, "file", f"Batch contains {len(rows)} rows; maximum is {MAX_BATCH_SIZE}")
        )
        return result

    report_numbers: set[str] = set()
    stems: set[str] = set()
    for index, row in enumerate(rows, start=2 if filename.lower().endswith(".csv") else 1):
        forbidden_path = find_forbidden_password_path(row)
        if forbidden_path:
            result.errors.append(
                BatchRowError(
                    index,
                    forbidden_path,
                    "Passwords are forbidden in CSV and JSON batch input",
                )
            )
            continue
        try:
            update = _csv_row_update(row) if filename.lower().endswith(".csv") else dict(row)
            _apply_image_paths(update, row, source_directory)
            for helper_field in (
                "sample_image_path",
                "logo_path",
                "logo_use_authorized",
                "signature_image_path",
                "signature_image_use_authorized",
            ):
                update.pop(helper_field, None)
            data = _merge(base_config.model_dump(mode="json"), update)
            config = COAConfig.model_validate(data)
            export_validation = validate_for_export(config)
            if export_validation.errors:
                for issue in export_validation.errors:
                    result.errors.append(BatchRowError(index, issue.field, issue.message))
                continue
            if config.report_no in report_numbers:
                raise ValueError(f"Duplicate report number {config.report_no!r}")
            stem = sanitized_output_stem(config.report_no, config.sample_name)
            if stem.casefold() in stems:
                raise ValueError(f"Output filename collision for {stem!r}")
            report_numbers.add(config.report_no)
            stems.add(stem.casefold())
            result.configs.append(config)
        except (ValueError, ValidationError) as exc:
            result.errors.append(BatchRowError(index, "row", str(exc)))

    if result.errors and not partial_success:
        result.configs.clear()
    return result


def validate_batch_upload(
    content: bytes,
    filename: str,
    base_config: COAConfig,
    *,
    partial_success: bool = False,
) -> BatchValidationResult:
    """Validate CSV/JSON or a portable ZIP containing input plus relative images."""

    if not filename.lower().endswith(".zip"):
        return validate_batch(
            content,
            filename,
            base_config,
            partial_success=partial_success,
        )
    if len(content) > 100 * 1024 * 1024:
        return BatchValidationResult(
            errors=[BatchRowError(0, "file", "Batch ZIP exceeds the 100 MB limit")]
        )
    try:
        with tempfile.TemporaryDirectory(prefix="coa-batch-") as temporary:
            root = Path(temporary).resolve()
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                total_uncompressed = sum(info.file_size for info in archive.infolist())
                if total_uncompressed > 250 * 1024 * 1024:
                    raise ValueError("Batch ZIP exceeds the 250 MB expanded-size limit")
                for info in archive.infolist():
                    destination = (root / info.filename).resolve()
                    if root not in destination.parents and destination != root:
                        raise ValueError("Batch ZIP contains an unsafe traversal path")
                archive.extractall(root)
            inputs = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".csv", ".json"}
            ]
            if len(inputs) != 1:
                raise ValueError("Batch ZIP must contain exactly one CSV or JSON input file")
            batch_input = inputs[0]
            return validate_batch(
                batch_input.read_bytes(),
                batch_input.name,
                base_config,
                source_directory=batch_input.parent,
                partial_success=partial_success,
            )
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        return BatchValidationResult(errors=[BatchRowError(0, "file", str(exc))])


def generate_batch_archive(
    configs: list[COAConfig],
    *,
    owner_password: str | None = None,
    owner_password_confirm: str | None = None,
    open_password: str | None = None,
) -> bytes:
    if not configs:
        raise ValueError("No validated reports are available for generation")
    output = io.BytesIO()
    manifest: dict[str, Any] = {
        "manifest_version": "1.0",
        "application_version": APP_VERSION,
        "report_count": len(configs),
        "reports": [],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for config in configs:
            stem = sanitized_output_stem(config.report_no, config.sample_name)
            generated = generate_pdf(
                config,
                owner_password=owner_password,
                owner_password_confirm=owner_password_confirm,
                open_password=open_password,
            )
            archive.writestr(f"pdf/{stem}.pdf", generated.pdf_bytes)
            archive.writestr(f"scenarios/{stem}.json", scenario_json(generated.config))
            manifest["reports"].append(
                {
                    "report_no": generated.config.report_no,
                    "sample_name": generated.config.sample_name,
                    "pdf": f"pdf/{stem}.pdf",
                    "scenario": f"scenarios/{stem}.json",
                    "generation_identifier": generated.config.audit.generation_identifier,
                    "editing_restricted": generated.protection is not None,
                }
            )
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return output.getvalue()
