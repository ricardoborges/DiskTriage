import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydisktriage import cli
from pydisktriage.catalog import Finding
from pydisktriage.cache import get_default_cache_path, save_scan_cache, clear_scan_cache


class TestCliCacheIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache_file = self.tmp / "test_cli_cache.json"

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("pydisktriage.cache.get_default_cache_path")
    def test_cli_loads_cache_on_start(self, mock_get_cache):
        mock_get_cache.return_value = self.cache_file

        findings = [
            Finding(
                ident="test_item",
                path=Path.home() / "test",
                kind="descartavel",
                size=1024 * 1024 * 100,
                files=10,
                is_file=False,
            )
        ]
        save_scan_cache(
            findings=findings,
            large_files=[],
            home=Path.home(),
            min_gb=1.0,
            discovery=False,
            cache_file=self.cache_file,
        )

        session = cli.Session(home=Path.home(), min_gb=1.0)
        # Mocking user quitting immediately
        with patch("pydisktriage.cli.Prompt.ask", side_effect=["0"]):
            with patch("pydisktriage.cli.screen_health"):
                ret = cli.main([])

        self.assertEqual(ret, 0)
        clear_scan_cache(cache_file=self.cache_file)


if __name__ == "__main__":
    unittest.main()
