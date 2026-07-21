# Specification implementation checklist

| Area | Implementation | Verification |
| --- | --- | --- |
| Source verification | Compact fixed status in the report-notice header plus Subject and Keywords metadata | `test_pdf_content.py` |
| Reusable templates | Built-in Vitum Lab defaults, local save/apply workflow, and randomized acquisition time | `test_templates.py`, instrument tests |
| Sidebar contrast | Explicit high-contrast selectors for buttons, selects, inputs, labels, hover and disabled states | Streamlit smoke test plus source review |
| Shared analytical model | `coa/calculations.py` derives all areas, purity, table values and chart inputs | calculation/chromatogram tests |
| Exact displayed 100% | Stable largest-remainder allocation | boundary and rounding tests |
| One-page Letter layout | Absolute fixed regions with overflow exceptions and peak/length preflight | layout and PDF tests |
| Chromatogram | Seeded baseline, drift, disturbance, Gaussian/tailing peaks and matched labels | deterministic chart tests |
| Instrument panel | Canonical identifiers without DEV/BETA prefixes, analysis-date timestamp, 1-5 PM window, and acquisition SW row | instrument tests |
| Portable images | Decode/orient/strip/resize/hash/base64 with authorization gates | image/branding/approval tests |
| Watermark | Validated literal variables, print content layer, single/repeated modes | PDF text and validation tests |
| Editing restrictions | AES-256 R6, explicit permissions, no forms/OCGs, pikepdf+pypdf verification | security tests |
| Scenarios | Strict 1.1, explicit 1.0 migration, future/unknown rejection, no password fields | scenario/security tests |
| Numbering | Atomic durable local state, padding, start, rollover, batch reservation | numbering tests |
| Batch | CSV/JSON/portable ZIP, relative images, all-row preflight, collision checks, manifest | batch tests |
| Offline launcher | Loopback binding, health wait, port fallback, instance reuse, clean exit | source smoke test; Windows record pending |
| Hosted Streamlit | Cloud entry point, runtime dependencies, optional secrets-backed password gate, hosted UI mode | hosted app harness and HTTP health smoke test |
| Windows distribution | PyInstaller one-folder and per-user Inno Setup source | clean Windows build/test pending |

## Release gates not fabricatable in this environment

- Build and code-sign the versioned Windows setup executable on Windows.
- Execute the offline clean-VM matrix and attach evidence to the test record.
- Verify behavior in Adobe Acrobat Pro and a second independent compliant editor.
- Review PyMuPDF licensing or replace the optional preview renderer for the intended distribution model.
