# Third-party notices

The application depends on the pinned packages in `requirements.lock`. Those
packages retain their own copyrights and licenses; review the installed package
metadata before redistribution. Major runtime components include:

- Streamlit — Apache License 2.0
- ReportLab — BSD-style license
- pikepdf and QPDF — Mozilla Public License 2.0 / Apache License 2.0 terms as distributed
- Matplotlib — Matplotlib license
- Pillow — HPND license
- Pydantic — MIT License
- pypdf — BSD-3-Clause License
- pypdfium2 — BSD-3-Clause or Apache License 2.0, wrapping PDFium under BSD-3-Clause
- PyInstaller — GPL 2.0 with a special exception for bundled applications

The four bundled DejaVu font files are covered by the license text stored at
`assets/fonts/DEJAVU-LICENSE.txt`.

The optional preview renderer is `pypdfium2`, used only for PNG preview and
layout verification; PDF generation itself does not require it. Its permissive
terms place no copyleft obligation on a proprietary installer or a hosted
deployment. Version 0.3.0 replaced the previous AGPL-or-commercial PyMuPDF
renderer for exactly this reason; do not reintroduce an AGPL dependency without
first re-reviewing the intended distribution model.
