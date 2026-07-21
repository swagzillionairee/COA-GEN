from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "streamlit is not installed")
class StreamlitSmokeTests(unittest.TestCase):
    def test_app_loads_and_generates_current_preview(self) -> None:
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as temporary:
            previous = os.environ.get("COA_DATA_DIR")
            os.environ["COA_DATA_DIR"] = temporary
            try:
                app_path = Path(__file__).resolve().parents[1] / "app.py"
                app = AppTest.from_file(str(app_path), default_timeout=45).run()
                self.assertEqual(len(app.exception), 0)
                next(button for button in app.button if button.label == "Generate preview").click()
                app.run(timeout=45)
                self.assertEqual(len(app.exception), 0)
                self.assertGreaterEqual(len(app.get("download_button")), 2)
            finally:
                if previous is None:
                    os.environ.pop("COA_DATA_DIR", None)
                else:
                    os.environ["COA_DATA_DIR"] = previous

    def test_hosted_entry_point_loads_without_desktop_exit_control(self) -> None:
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as temporary:
            previous_data = os.environ.get("COA_DATA_DIR")
            previous_mode = os.environ.get("COA_DEPLOYMENT_MODE")
            os.environ["COA_DATA_DIR"] = temporary
            os.environ.pop("COA_DEPLOYMENT_MODE", None)
            try:
                app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
                app = AppTest.from_file(str(app_path), default_timeout=45).run()
                self.assertEqual(len(app.exception), 0)
                self.assertIn("Hosted web edition", [caption.value for caption in app.caption])
                self.assertNotIn("Exit application", [button.label for button in app.button])
                next(button for button in app.button if button.label == "Generate preview").click()
                app.run(timeout=45)
                self.assertEqual(len(app.exception), 0)
            finally:
                if previous_data is None:
                    os.environ.pop("COA_DATA_DIR", None)
                else:
                    os.environ["COA_DATA_DIR"] = previous_data
                if previous_mode is None:
                    os.environ.pop("COA_DEPLOYMENT_MODE", None)
                else:
                    os.environ["COA_DEPLOYMENT_MODE"] = previous_mode

    def test_optional_hosted_password_gate(self) -> None:
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as temporary:
            previous_data = os.environ.get("COA_DATA_DIR")
            previous_mode = os.environ.get("COA_DEPLOYMENT_MODE")
            previous_password = os.environ.get("COA_APP_PASSWORD")
            os.environ["COA_DATA_DIR"] = temporary
            os.environ["COA_DEPLOYMENT_MODE"] = "web"
            os.environ["COA_APP_PASSWORD"] = "test-only-password"
            try:
                app_path = Path(__file__).resolve().parents[1] / "app.py"
                app = AppTest.from_file(str(app_path), default_timeout=45).run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual([item.label for item in app.text_input], ["Access password"])
                next(item for item in app.text_input if item.label == "Access password").set_value(
                    "test-only-password"
                )
                next(button for button in app.button if button.label == "Open generator").click()
                app.run(timeout=45)
                self.assertEqual(len(app.exception), 0)
                self.assertIn(
                    "Certificate of Analysis Generator",
                    [title.value for title in app.title],
                )
            finally:
                for name, value in (
                    ("COA_DATA_DIR", previous_data),
                    ("COA_DEPLOYMENT_MODE", previous_mode),
                    ("COA_APP_PASSWORD", previous_password),
                ):
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
