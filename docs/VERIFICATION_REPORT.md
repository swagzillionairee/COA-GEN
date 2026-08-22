# Release verification report

Release candidate: `0.3.0`  
Verification date: `2026-08-09`

## Completed in the source build environment

- Python 3.12 source test suite: **69 passed** with a crypto backend present,
  **67 passed and 2 skipped** from `requirements.lock` alone. The two skips are
  the AES-256 protected-export cases; see the known limitation in `CHANGELOG.md`.
- The preview renderer is `pypdfium2`, which is permissively licensed. Removing
  PyMuPDF left report output unchanged: example PDFs are byte-identical apart
  from creation timestamps, and extracted page text hashes match exactly.
- Golden renders regenerated through PDFium and visually re-inspected at 1.5x
  for both layouts — no clipping, overlap, or typography regressions.
- Example generation is deterministic: repeated runs produce byte-identical
  golden PNGs and scenario JSON.
- Continuous integration runs the suite, the hosted health check, and a
  render-freshness guard on every push.
- Three one-page US Letter example PDFs regenerated with fixed example generation identifiers.
- PDF text, metadata, page dimensions, native-content structure, links, image placement, source-verification status, and layout limits checked automatically.
- Golden PNGs regenerated for the no-image, sample-image, single-watermark, and repeated-watermark variants.
- AES-256 security revision 6 export reopens and verifies through both pikepdf/QPDF and pypdf — including requested permissions and the absence of AcroForm and optional-content layers — **only when a crypto backend is installed**. It is not exercised by the pinned dependency set and is not verified for this build.
- Both desktop and hosted entry points loaded and generated a PDF through Streamlit's application test harness.
- The optional hosted password gate was exercised through successful authentication in the application test harness.
- The hosted server bound successfully, returned HTTP 200 with `ok` from `/_stcore/health`, and exited cleanly with code 0.

The previous release's PyInstaller graph and frozen-bundle smoke evidence does not automatically carry over to version 0.3.0; rebuild it before distributing a new Windows installer.

## Windows release gates still pending

- Produce the versioned setup executable. The `Windows installer` workflow builds it on a hosted Windows runner; a local Windows 10/11 host with Python 3.12 x64 and Inno Setup 6 works equally well. Neither has been run yet.
- Run the clean-machine, no-Python, network-disabled VM matrix in `packaging/clean-machine-offline-test-record.md`.
- Record Adobe Acrobat Pro and a second compliant viewer/editor permission test.
- Code-sign the installer, record its SHA-256 checksum, and complete antivirus submission/reputation checks.

No Windows installer is represented as verified until those items are completed against the actual setup executable.
