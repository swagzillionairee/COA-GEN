# Release verification report

Release candidate: `0.3.0`  
Verification date: `2026-07-21`

## Completed in the source build environment

- Python 3.12.13 source test suite: **69 passed**.
- Three one-page US Letter example PDFs regenerated with fixed example generation identifiers.
- PDF text, metadata, page dimensions, native-content structure, links, image placement, source-verification status, and layout limits checked automatically.
- Golden PNGs regenerated for the no-image, sample-image, single-watermark, and repeated-watermark variants.
- The revised default and sample-image PDFs were rendered at 160 DPI and visually checked for clipping, overlap, hierarchy, typography, and table density.
- AES-256 security revision 6 export reopened and verified with both pikepdf/QPDF and pypdf, including requested permissions and the absence of AcroForm and optional-content layers.
- Both desktop and hosted entry points loaded and generated a PDF through Streamlit's application test harness.
- The optional hosted password gate was exercised through successful authentication in the application test harness.
- The hosted server bound successfully, returned HTTP 200 with `ok` from `/_stcore/health`, and exited cleanly with code 0.

The previous release's PyInstaller graph and frozen-bundle smoke evidence does not automatically carry over to version 0.3.0; rebuild it before distributing a new Windows installer.

## Windows release gates still pending

- Build the versioned setup executable on Windows 10/11 with Python 3.12 x64 and Inno Setup 6.
- Run the clean-machine, no-Python, network-disabled VM matrix in `packaging/clean-machine-offline-test-record.md`.
- Record Adobe Acrobat Pro and a second compliant viewer/editor permission test.
- Code-sign the installer, record its SHA-256 checksum, and complete antivirus submission/reputation checks.

No Windows installer is represented as verified until those items are completed against the actual setup executable.
