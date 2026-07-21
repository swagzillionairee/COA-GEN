# COA Generator - Claude handoff guideline

Use this document as the working specification and project handoff for the COA
Generator. Preserve validated behavior unless a requested change explicitly
supersedes it, and update tests and release documentation with every change.

## Project goal

Maintain a dual-mode Streamlit application—an offline-first Windows edition and
a hosted web edition—that creates polished, single-page US Letter Certificate
of Analysis PDFs from operator-entered data.
The current application generates deterministic analytical values and
chromatograms; it does not ingest or authenticate laboratory instrument output.
Before a report is issued, an operator must verify the values against the
original instrument source data.

Current release: `0.3.0`  
Python target: 3.12 x64  
UI: Streamlit  
PDF engine: ReportLab  
Windows bundle: PyInstaller one-folder plus Inno Setup 6 installer
Web entry point: `streamlit_app.py` for Streamlit Community Cloud

## Current user experience

- The app opens locally through `launcher.py` and binds only to loopback.
- The hosted edition opens through `streamlit_app.py`, hides desktop-only exit
  controls, and supports an optional secrets-backed access password.
- The sidebar uses explicit high-contrast styling so buttons, select boxes,
  inputs, labels, hover states, and disabled states remain readable.
- A template picker is shown prominently in the sidebar.
- `Vitum Lab default` is built in and applied on first launch/reset.
- Operators can save the current form as a reusable local template and apply it
  later without re-entering repeated information.
- Reports can be previewed, exported as PDF, saved as portable JSON scenarios,
  and generated in batches from CSV/JSON or portable ZIP inputs.
- Passwords for editing-restricted exports are requested transiently and are
  never serialized, logged, placed in metadata, or saved in a batch file.

## Vitum Lab default template

The built-in template in `templates/default_coa.json` contains:

- Client: Vitum Lab
- Receipt date: June 4, 2026
- Analysis date: June 4, 2026
- Report date: June 4, 2026
- Document issue date: June 4, 2026
- Matrix: Lyophilized Powder
- Number of samples: 1
- Test: Purity
- Instrument: Instrument 2
- Acquisition SW Version: 6400 Series Triple B.09.00
- Acquired date: always synchronized to the analysis date
- Acquired time: randomized between 1:00 PM and 5:00 PM whenever the template is
  applied

Generated identifiers and instrument rows do not display DEV or BETA prefixes.
The generic Software row was replaced by Acquisition SW Version.

## PDF requirements already implemented

- Exactly one US Letter page with selectable native text.
- Two layouts: `Reference COA` and `Reference COA with Sample Image`.
- The sample-image layout places the image and its label/caption in a bounded
  column without overlap.
- Typography is consistent across body, metadata, table, and footer regions;
  headers may use larger or bold type.
- The peak-list grid is compact and has a fixed maximum row count.
- The displayed purity, raw peak areas, percent areas, peak list, and
  chromatogram all come from one validated analytical result model.
- Displayed percent areas use deterministic largest-remainder correction and
  total exactly 100.00%.
- The PDF has fixed regions and fails with a layout overflow error instead of
  silently clipping content.
- The old red development banner, visible generation ID, app/template version
  line, development-simulation statement, and the old bottom sentence
  `Generated report - analytical results have not been independently verified.`
  are absent.
- A compact fixed `SOURCE VERIFICATION REQUIRED` status appears in the report
  notice header. PDF Subject/Keywords contain the fuller source-verification
  status. Do not remove this last marker while the app still creates
  deterministic analytical results instead of importing and validating real
  instrument output.
- Approval images are presentational only and are explicitly not digital
  signatures.

## Branding and media

- Editable organization name, address, website, phone, email, colors, fonts,
  footer disclaimer, and optional quality statement.
- Optional logo and approval/signature images accept PNG, JPEG, or WebP.
- Image handling corrects orientation, strips metadata, resizes safely, imposes
  byte/pixel limits, and stores a SHA-256 hash in portable scenarios.
- The operator must confirm that uploaded branding and approval assets are owned
  or authorized before they are rendered.

## Analytical model

- Supports automatic peak generation and explicit manual peaks.
- Validates finite nonnegative areas, unique retention times, one main peak,
  in-range peaks, positive included total, and consistency between requested
  purity and component areas.
- Chromatograms are deterministic from the scenario, model versions, and random
  seed.
- The default template uses area-percent purity and a seeded generated trace.
- Do not describe the current output as instrument-authenticated or accredited.
  A real production-lab workflow requires source-file ingestion, method and
  calibration traceability, reviewer access controls, audit logging, and a
  documented validation process.

## Document protection

- Optional AES-256 revision-6 editing restrictions are applied only after the
  PDF is finalized.
- Permissions cover changes, annotations, forms, page assembly, printing,
  copying, and accessibility.
- Protection is verified by reopening through pikepdf/QPDF and pypdf.
- Permission flags deter casual edits but do not replace certificate-based
  digital signatures and cannot prevent screenshots or determined modification.

## Scenarios, templates, numbering, and batches

- Scenario schema version is `1.1`; unknown fields and unsupported future
  versions are rejected.
- A documented migration upgrades schema `1.0` to `1.1`.
- Locally saved templates live under the per-user application data directory.
- Report numbering uses atomic durable local state and checks for collisions.
- Batch limit is 100 reports with preflight validation, unique report numbers,
  unique sanitized filenames, and a machine-readable output manifest.
- Nested or top-level password fields are rejected from scenarios and batches.

## Local storage and privacy

The installed application treats its program directory as read-only and uses
`%LOCALAPPDATA%\COAGenerator\` for numbering state, logs, cache, recent-file
history, temporary files, and saved templates. Clearing cache/history must not
delete numbering state, exported reports, scenarios, or user-selected files.
The app requires no CDN, telemetry, cloud synchronization, or external analytics.

## Important files

- `app.py`: Streamlit UI and state management
- `streamlit_app.py`: hosted deployment entry point
- `launcher.py`: managed local server lifecycle
- `coa/models.py`: strict validated data models
- `coa/pdf_generator.py`: one-page PDF renderer
- `coa/calculations.py`: analytical result calculations
- `coa/chromatogram.py`: deterministic chromatogram renderer
- `coa/instrument_metadata.py`: instrument display rows and identifiers
- `coa/templates.py`: built-in/custom template workflow
- `coa/scenarios.py`: schema serialization and migration
- `coa/batch.py`: batch parsing, preflight, generation, and manifests
- `coa/pdf_security.py`: AES-256 protection and verification
- `templates/default_coa.json`: Vitum Lab default
- `tests/`: regression suite
- `packaging/build_windows.ps1`: complete Windows release build
- `docs/STREAMLIT_DEPLOYMENT.md`: hosted deployment and privacy guidance

## Development and verification commands

From the `coa-generator` directory on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\generate_examples.py
.\.venv\Scripts\python.exe launcher.py
```

For every PDF layout change:

1. Run the full test suite.
2. Regenerate examples.
3. Render both PDF layouts to images.
4. Visually inspect for clipping, overlap, inconsistent fonts, unreadable small
   text, chart/table collisions, and misplaced footer content.
5. Reopen the PDFs and verify they remain exactly one 612 x 792 point page.
6. Confirm expected text and metadata, and confirm removed legacy strings stay
   absent.

## Windows installer build

Install Python 3.12 x64 and Inno Setup 6, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build_windows.ps1
```

The script automatically checks the usual system paths and the per-user path:
`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

Expected installer:

```text
packaging\release\COA-Generator-Setup-0.3.0.exe
```

## Release gates

Do not represent an installer as production-verified until all of these are
complete against the actual Windows build:

- Build the installer on Windows 10/11 with Python 3.12 x64 and Inno Setup 6.
- Run the clean-machine, no-Python, network-disabled test matrix.
- Verify protected PDFs in Adobe Acrobat Pro and a second compliant editor.
- Code-sign the installer and record its SHA-256 checksum.
- Complete antivirus/reputation submission as applicable.
- Review PyMuPDF licensing for the intended distribution model.
- Deploy the hosted build privately, configure its secret outside source, and
  confirm the production URL is healthy before sharing it.
- If reports will be issued as real laboratory results, replace or augment the
  generated data path with validated instrument-source ingestion, traceability,
  reviewer controls, audit history, and applicable quality/regulatory review.

## Change discipline for future Claude work

- Preserve strict Pydantic validation and reject unknown input fields.
- Keep report calculations and rendering derived from the same result object.
- Never persist passwords or include them in errors, logs, scenarios, metadata,
  filenames, or manifests.
- Keep `launcher.py` loopback-only and preserve offline operation; do not apply
  that binding to the hosted `streamlit_app.py` entry point.
- Never commit `.streamlit/secrets.toml` or a real `APP_PASSWORD` value.
- Preserve user files and durable numbering during cache clearing, upgrades, and
  uninstall.
- Add regression tests for every bug fix and behavioral change.
- Bump `VERSION`, package metadata, installer metadata, constants, and release
  docs together.
- Regenerate examples and rebuild the deterministic checksummed source ZIP only
  after the final test pass.
