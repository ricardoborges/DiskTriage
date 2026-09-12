import tempfile
import unittest
from pathlib import Path
from pydisktriage.config import (
    get_configured_language,
    load_config,
    save_config,
    set_configured_language,
)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp_dir.name) / "config.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_non_existent_config(self):
        cfg = load_config(self.config_path)
        self.assertEqual(cfg, {})
        self.assertIsNone(get_configured_language(self.config_path))

    def test_save_and_load_config(self):
        success = save_config({"language": "en-US"}, self.config_path)
        self.assertTrue(success)
        cfg = load_config(self.config_path)
        self.assertEqual(cfg.get("language"), "en-US")

    def test_set_and_get_configured_language(self):
        set_configured_language("pt-br", self.config_path)
        self.assertEqual(get_configured_language(self.config_path), "pt-BR")

        set_configured_language("en", self.config_path)
        self.assertEqual(get_configured_language(self.config_path), "en-US")


if __name__ == "__main__":
    unittest.main()
