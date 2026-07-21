"""Build a deterministic, checksummed source release ZIP."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT.parent / "COA-Generator-0.3.0-streamlit-web.zip"
ARCHIVE_ROOT = "coa-generator"
FIXED_TIMESTAMP = (2026, 7, 21, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".venv-build",
    "__pycache__",
    "build",
    "dist",
    "output",
    "release",
    "tmp",
}


def source_files(output: Path) -> list[Path]:
    files: list[Path] = []
    output = output.resolve()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"} or path.resolve() == output:
            continue
        if path.is_symlink():
            raise RuntimeError(f"Release input contains an unsupported symbolic link: {relative}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def archive_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_archive(output: Path) -> tuple[Path, str, int]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files(output)
    manifest: list[str] = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            payload = path.read_bytes()
            archive.writestr(archive_info(f"{ARCHIVE_ROOT}/{relative}"), payload)
            manifest.append(f"{hashlib.sha256(payload).hexdigest()}  {relative}")
        manifest_payload = ("\n".join(manifest) + "\n").encode("utf-8")
        archive.writestr(
            archive_info(f"{ARCHIVE_ROOT}/SOURCE_MANIFEST.sha256"),
            manifest_payload,
        )
        archive.comment = b"COA Generator 0.3.0 Streamlit web and desktop source release"

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest, len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output, digest, count = build_archive(args.output)
    print(f"archive={output}")
    print(f"files={count}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
