# Changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.3.0 — unreleased

Version 0.3.0 has never been tagged, deployed, or distributed, so the fixes
below are folded into it rather than issued as a patch release. The Windows
release gates in `docs/VERIFICATION_REPORT.md` remain open.

### Added

- Hosted web edition: `streamlit_app.py` entry point, lean runtime
  `requirements.txt`, cloud-compatible `.streamlit/config.toml`, hosted UI mode,
  and an optional secrets-backed access password.
- `docs/STREAMLIT_DEPLOYMENT.md` covering deployment and hosted-mode privacy.
- Continuous integration (`.github/workflows/ci.yml`): the test suite on Python
  3.12, a hosted entry-point health check, and a guard that fails when the
  committed examples or golden renders drift from what the code produces.
- Hosted Windows installer build (`.github/workflows/windows-installer.yml`),
  so producing the installer no longer requires a local Windows machine. The
  artifact is unsigned and deliberately not published as a release.
- `packaging/build_windows.ps1` accepts `-PythonExe` for interpreters the `py`
  launcher does not know about, such as a CI-provisioned Python.

### Changed

- The sample-image panel is now a portrait 1:2 frame and the photo is contained
  inside it rather than cropped to fill, so a tall vial shot is shown whole
  instead of being trimmed top and bottom. The frame is 50x100 pt, which is the
  largest 1:2 panel that clears the result-note row beneath it; anything taller
  pushes the report onto a second page. The photo's own aspect is preserved, so
  it letterboxes within the frame.
- Replaced the PyMuPDF preview renderer with `pypdfium2`. PyMuPDF is
  AGPL-3.0-or-commercial, which conflicted with this project's MIT license once
  bundled into a distributed installer; `pypdfium2` is BSD-3-Clause/Apache-2.0
  and wraps BSD-3-Clause PDFium. Every bundled dependency is now permissively
  licensed, and the licensing item is removed from the release gates.
  PDF generation never used PyMuPDF, so report output is unaffected — example
  PDFs are byte-identical apart from their creation timestamps.
- Regenerated the golden renders through PDFium. The pages are visually
  unchanged; only the rasterizer and PNG encoder differ.
- `tests/test_layout.py` verifies image placement and text position through
  pypdfium2 in PDF user space (origin bottom-left) instead of PyMuPDF's
  top-left coordinates. Both assertions were mutation-checked to confirm they
  still fail on a regressed layout.

### Removed

- The "Presentational approval only - not a digital signature." caption under the
  approval block, at the maintainer's request. The approval image is still
  presentational and still not a digital signature; that is simply no longer
  printed on the page. The report-notice `SOURCE VERIFICATION REQUIRED` marker
  and the source-verification PDF metadata are unchanged.

### Fixed

- `python scripts/generate_examples.py` raised `ModuleNotFoundError: No module
  named 'coa'`. Running it as a script put `scripts/` on `sys.path` instead of
  the project root, so the command documented in the README and invoked by
  `packaging/build_windows.ps1` could never succeed.
- `pytest` was missing from `requirements.lock` even though its transitive
  dependencies were pinned there, so `packaging/build_windows.ps1` failed at its
  own test step against a freshly provisioned build environment.

### Known limitations

- `sample_image.crop_position` no longer affects the rendered report. Showing the
  whole photo and cropping it to a fill are mutually exclusive, and the panel now
  does the former. The field is retained because scenario schema `1.1` rejects
  unknown fields, so removing it would break existing saved scenarios, but the
  crop selector in the sidebar is currently inert.
- Protected (AES-256) PDF export is not supported in this build. pypdf needs a
  crypto backend to decrypt AES-256 for the independent second-parser check in
  `coa/pdf_security.py`, and no such backend is pinned, so protected export
  fails closed. The two affected tests skip rather than fail; installing
  `cryptography` enables both the feature and the tests.
