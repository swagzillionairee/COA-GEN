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
- PyMuPDF — GNU Affero General Public License 3.0 or a commercial license
- PyInstaller — GPL 2.0 with a special exception for bundled applications

The four bundled DejaVu font files are covered by the license text stored at
`assets/fonts/DEJAVU-LICENSE.txt`.

Important: PyMuPDF's licensing may not suit every proprietary distribution.
Obtain an appropriate commercial license or replace the optional preview
renderer before distributing a closed-source installer. The PDF-generation
library itself does not require PyMuPDF; it is used only for PNG preview and
layout verification.
