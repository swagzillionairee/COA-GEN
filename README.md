# Certificate of Analysis Generator 0.3.0

A Streamlit application that creates polished one-page sample Certificates of
Analysis from user-entered data and authorized branding. It can run as a local
Windows application or as a hosted website.

Every PDF carries one compact source-verification status in the report-notice
header and records the fuller status in metadata:

> Software-generated COA - verify results against original instrument source data.

This application does not currently connect to laboratory instruments, make
accreditation claims, or turn an approval image into an electronic or digital
signature. Before a report is issued, its values must be checked against the
original source data.

## What is included

- A reusable Vitum Lab default template plus locally saved custom templates
- Two one-page US Letter layouts: `Reference COA` and `Reference COA with Sample Image`
- Native/selectable report text and vector layout, with a generated raster chromatogram
- One shared analytical-result model for purity, areas, percent areas, labels, and chart peaks
- Deterministic largest-remainder display correction to exactly `100.00%`
- Safe PNG/JPEG/WebP processing, orientation correction, metadata stripping, size limits, hashes, and portable base64 scenarios
- Authorization gates for uploaded logos and PNG signature images
- Literal custom watermarks with four validated template variables
- Optional AES-256 revision-6 editing restrictions, applied after content finalization and verified with both pikepdf/QPDF and pypdf
- Strict schema `1.1`, documented `1.0 → 1.1` migration, and reject-unknown-field compatibility policy
- Atomic local numbering and batch CSV/JSON/ZIP generation with preflight validation and a machine-readable ZIP manifest
- Managed localhost-only launcher, Windows installer source, and Streamlit Community Cloud entry point
- Fictional examples and an automated test suite

## Quick start from source

Python 3.12 x64 is the tested source runtime.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
python launcher.py
```

The launcher selects `127.0.0.1:8501` when available, otherwise selects a free
loopback port, waits for health, and opens the browser. A second launch reuses
the healthy running instance. Use **Exit application** in the sidebar or run
`python launcher.py --stop` to terminate it cleanly.

For developer mode without the managed launcher:

```powershell
streamlit run app.py --server.address 127.0.0.1
```

No CDN, telemetry, cloud synchronization, or external analytics are required.

## Host it as a website

The cloud entry point is `streamlit_app.py`. The repository includes a lean
runtime `requirements.txt` and a cloud-compatible `.streamlit/config.toml`.

1. Put the complete `coa-generator` folder in a GitHub repository.
2. In Streamlit Community Cloud, create an app from that repository.
3. Set the entrypoint to `streamlit_app.py` and choose Python 3.12 in Advanced settings.
4. Recommended: add this secret in Advanced settings, using your own strong password:

   ```toml
   APP_PASSWORD = "replace-this-with-a-long-unique-password"
   ```

5. Deploy and open the generated `streamlit.app` URL.

See `docs/STREAMLIT_DEPLOYMENT.md` for the full GitHub and deployment walkthrough.

The password gate is optional and is separate from Streamlit Community Cloud's
own public/private sharing controls. Do not commit `.streamlit/secrets.toml`.

## Typical workflow

1. Apply a reusable template, choose a PDF layout, and edit report-specific details.
2. Upload only branding or approval assets that you own or are authorized to use.
3. Generate the live preview. Export always regenerates from the current validated model; a stale preview is never reused.
4. Download the portable source JSON with the report.
5. For an editing-restricted PDF, enter the owner password twice immediately before export. The password is never placed in a scenario, manifest, metadata field, filename, log, or persisted setting.

The protected-export notice is literal: permission flags deter routine changes in
compliant PDF software, but cannot prevent screenshots, photography, decryption,
or modification by sufficiently capable tools. Use certificate-based digital
signing as a separate future feature if change detection or signer identity is required.

## Batch inputs

The maximum is 100 reports. All rows are validated before output unless
partial-success mode is explicitly selected. Report numbers and sanitized output
filenames must be unique.

- Direct upload: `.csv` or `.json`
- Image references: upload a `.zip` containing exactly one CSV/JSON input and the relative image files
- Dates: ISO `YYYY-MM-DD`
- CSV peak arrays: semicolon-separated, such as `0.741;3.188`
- Relative path fields: `sample_image_path`, `logo_path`, `signature_image_path`
- Authorization booleans: `logo_use_authorized`, `signature_image_use_authorized`
- Password fields are rejected in every batch format

See `examples/batch-example.csv`, `examples/batch-example.json`, and
`examples/batch-schema.json`.

## Validation and deterministic behavior

Date order is fixed as `receipt <= analysis <= report <= document issue`. Areas
must be finite and nonnegative, the included total must be positive, retention
times must be unique and in range, and exactly one peak is designated as the
purity peak. Manual areas must agree with requested purity within `0.000001`.

The same scenario, calculation-model version, template version, and random seed
reproduce analytical values and chart geometry. Byte-identical PDFs additionally
require fixed metadata timestamps, identifiers, fonts, and dependency versions.

Strict identifier mode rejects differences from the canonical sample/lot/test/date
helpers. Normal mode preserves those differences as scenario warnings.

## Local data and privacy

The installed application treats its program directory as read-only and uses:

```text
%LOCALAPPDATA%\COAGenerator\
|-- numbering.json       durable sequence; not reset with defaults
|-- logs\                rotating diagnostics without report contents or images
|-- cache\               disposable preview/cache data
|-- recent-files.json    removable recent-file history
`-- temp\                disposable local working files
```

The in-app clear action removes only caches and recent history. It does not delete
the numbering sequence, PDFs, scenarios, or any user-selected output. The
installer and uninstaller intentionally preserve `%LOCALAPPDATA%\COAGenerator`.

On hosted Streamlit, uploaded assets and generated PDFs are handled in the running
session and are not intentionally written as report files. Custom templates,
recent report-number history, and numbering state use the host's local filesystem,
which is temporary on Community Cloud and can be reset by a reboot or redeploy.
Download source JSON files for anything you need to preserve. A public deployment
also shares one server process, so use private sharing or the optional password gate.

## Tests

```powershell
python -m pytest
python scripts\generate_examples.py
```

The suite covers calculations, chromatogram determinism, image handling,
authorization gates, identifiers, scenario migrations, batching, numbering,
one-page layout, text/metadata extraction, and AES-256 permission verification.
The current release evidence and remaining platform gates are recorded in
`docs/VERIFICATION_REPORT.md`.

Build the checksummed source archive with:

```powershell
python scripts\build_source_archive.py
```

## Windows packaging

The primary target is a per-user PyInstaller one-folder installation on 64-bit:

- Windows 10 22H2
- Windows 11 23H2 and 24H2

Run on a Windows build host with Python 3.12 x64 and Inno Setup 6:

```powershell
.\packaging\build_windows.ps1
```

The script creates the isolated environment, installs the lock, runs tests,
regenerates examples, builds the no-console one-folder application, invokes the
Inno Setup installer, and writes a SHA-256 checksum. Set `INNO_SETUP_COMPILER`
if `ISCC.exe` is not in its default location.

The build script checks the system-wide and per-user Inno Setup locations,
including `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

The source archive does **not** claim that a Windows installer or clean-machine
offline verification has passed merely because packaging scripts exist. Before
release, build the setup executable on Windows and complete every item in
`packaging/clean-machine-offline-test-record.md`. Code-signing and antivirus
submission are release operations, not simulated by this repository.

## Scenario compatibility

Schema `1.1` rejects unknown fields rather than silently discarding them. The
explicit `1.0 → 1.1` migration adds disabled watermark/editing-restriction
defaults and empty optional logo/signature fields. Unsupported future versions
are rejected with an upgrade message.

## License and dependency review

Application source is MIT-licensed. See `THIRD_PARTY_LICENSES.md`, especially the
PyMuPDF preview-renderer licensing note, before redistributing a proprietary build.
