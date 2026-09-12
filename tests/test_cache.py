import tempfile
import unittest
from pathlib import Path

from pydisktriage.catalog import Finding
from pydisktriage.cache import load_scan_cache, save_scan_cache, clear_scan_cache


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache_file = self.tmp / "test_cache.json"

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_cache(self):
        findings = [
            Finding(
                ident="pyenv",
                path=Path(r"C:\Users\test\.pyenv"),
                kind="movivel",
                size=1024 * 1024 * 500,
                files=1200,
                is_file=False,
                env_var="PYENV_ROOT",
                clean_cmd="pyenv versions",
                note="Versões do Python",
                discovered=False,
            ),
            Finding(
                ident="extra_cache",
                path=Path(r"C:\Users\test\AppData\Local\extra"),
                kind="descartavel",
                size=1024 * 1024 * 100,
                files=50,
                is_file=False,
                discovered=True,
            ),
        ]
        large_files = [(Path(r"C:\Users\test\big.iso"), 1024 * 1024 * 1024)]

        save_scan_cache(
            findings=findings,
            large_files=large_files,
            home=Path(r"C:\Users\test"),
            min_gb=1.0,
            discovery=True,
            cache_file=self.cache_file,
        )

        self.assertTrue(self.cache_file.exists())

        loaded = load_scan_cache(cache_file=self.cache_file)
        self.assertIsNotNone(loaded)
        assert loaded is not None

        self.assertEqual(len(loaded.findings), 2)
        self.assertEqual(loaded.findings[0].ident, "pyenv")
        self.assertEqual(loaded.findings[0].path, Path(r"C:\Users\test\.pyenv"))
        self.assertEqual(loaded.findings[0].kind, "movivel")
        self.assertEqual(loaded.findings[0].size, 1024 * 1024 * 500)
        self.assertEqual(loaded.findings[0].files, 1200)
        self.assertFalse(loaded.findings[0].is_file)
        self.assertEqual(loaded.findings[0].env_var, "PYENV_ROOT")
        self.assertEqual(loaded.findings[0].clean_cmd, "pyenv versions")
        self.assertEqual(loaded.findings[0].note, "Versões do Python")
        self.assertFalse(loaded.findings[0].discovered)

        self.assertEqual(loaded.findings[1].ident, "extra_cache")
        self.assertTrue(loaded.findings[1].discovered)

        self.assertEqual(len(loaded.large_files), 1)
        self.assertEqual(loaded.large_files[0], (Path(r"C:\Users\test\big.iso"), 1024 * 1024 * 1024))
        self.assertTrue(loaded.discovery)
        self.assertIsNotNone(loaded.timestamp)

    def test_load_nonexistent_cache(self):
        loaded = load_scan_cache(cache_file=self.tmp / "nonexistent.json")
        self.assertIsNone(loaded)

    def test_load_corrupt_cache(self):
        self.cache_file.write_text("{ corrupt json ", encoding="utf-8")
        loaded = load_scan_cache(cache_file=self.cache_file)
        self.assertIsNone(loaded)

    def test_clear_cache(self):
        self.cache_file.write_text("{}", encoding="utf-8")
        self.assertTrue(self.cache_file.exists())
        clear_scan_cache(cache_file=self.cache_file)
        self.assertFalse(self.cache_file.exists())


if __name__ == "__main__":
    unittest.main()
