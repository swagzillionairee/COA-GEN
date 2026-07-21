"""Streamlit Community Cloud entry point.

The desktop launcher continues to execute ``app.py`` directly. This entry point
only changes deployment-aware UI behavior; PDF generation remains identical.
"""

from __future__ import annotations

import os


os.environ.setdefault("COA_DEPLOYMENT_MODE", "web")

# Importing app renders the Streamlit page.
import app  # noqa: E402,F401
