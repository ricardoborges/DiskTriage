import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydisktriage import cli
from pydisktriage.i18n import get_language, set_language


class TestCliLanguageSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config_file = self.tmp / "config.json"

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("pydisktriage.cli.get_configured_language")
    @patch("pydisktriage.cli.set_configured_language")
    @patch("pydisktriage.cli.select_menu", return_value="2")
    @patch("pydisktriage.cli.screen_health")
    def test_first_run_prompts_for_language(self, mock_health, mock_menu, mock_set_cfg, mock_get_cfg):
        mock_get_cfg.return_value = None  # Simulates first run (no config)

        with patch("pydisktriage.cli.Prompt.ask", return_value="0"):
            with patch("pydisktriage.cli.load_scan_cache", return_value=None):
                # When select_menu returns "2", it should select "en-US"
                # And user exits main menu with "0"
                mock_menu.side_effect = ["2", "0"]
                ret = cli.main([])

        self.assertEqual(ret, 0)
        mock_set_cfg.assert_called_with("en-US")
        self.assertEqual(get_language(), "en-US")

    @patch("pydisktriage.cli.get_configured_language")
    @patch("pydisktriage.cli.set_configured_language")
    @patch("pydisktriage.cli.screen_health")
    def test_cli_override_with_flag(self, mock_health, mock_set_cfg, mock_get_cfg):
        mock_get_cfg.return_value = "pt-BR"

        with patch("pydisktriage.cli.select_menu", return_value="0"):
            with patch("pydisktriage.cli.load_scan_cache", return_value=None):
                ret = cli.main(["--lang", "en-US"])

        self.assertEqual(ret, 0)
        self.assertEqual(get_language(), "en-US")
        mock_set_cfg.assert_called_with("en-US")


if __name__ == "__main__":
    unittest.main()
