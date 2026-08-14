"""Guards against a redeploy running a new page against a stale mariner_core.

Streamlit re-executes the entry script on every rerun but keeps imported
modules in sys.modules, so a redeployed app can pair a new streamlit_app.py
with the previous mariner_core.py until the process restarts. On Streamlit
Cloud the resulting TypeError is redacted, so the app must detect the mismatch
itself rather than crash.
"""

import dataclasses
import os
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import mariner_core

NEW_SETTINGS = ("anthropic_max_tokens", "anthropic_effort", "zai_max_tokens")

PreviousProviderConfig = dataclasses.make_dataclass(
    "ProviderConfig",
    [
        (field.name, field.type, dataclasses.field(default=field.default))
        for field in dataclasses.fields(mariner_core.ProviderConfig)
        if field.name not in NEW_SETTINGS
    ],
    frozen=True,
)


class DeployResilienceTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(
            os.environ, {"DEMO_MODE": "true", "PUBLIC_DEMO_ONLY": "true"}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_app(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=120).run()
        self.assertFalse(app.exception, app.exception)
        return app

    def test_current_code_reports_no_mismatch(self):
        app = self.run_app()

        self.assertEqual(app.session_state["stale_core_settings"], [])
        self.assertFalse([e for e in app.error if "older copy" in e.value])
        self.assertIn("max 32,000 out", app.sidebar.code[0].value)

    def test_stale_core_is_reported_instead_of_crashing(self):
        with patch.object(mariner_core, "ProviderConfig", PreviousProviderConfig):
            app = self.run_app()

        self.assertEqual(
            app.session_state["stale_core_settings"], sorted(NEW_SETTINGS)
        )
        notices = [e.value for e in app.error if "older copy" in e.value]
        self.assertEqual(len(notices), 1)
        # The operator needs to know the fix is inactive and how to load it.
        self.assertIn("not active", notices[0])
        self.assertIn("Reboot", notices[0])
        # Every dropped setting is named so the mismatch is identifiable.
        for setting in NEW_SETTINGS:
            self.assertIn(setting, notices[0])
        # A stale config must not take the sidebar down with it.
        self.assertIn("unknown", app.sidebar.code[0].value)


if __name__ == "__main__":
    unittest.main()
