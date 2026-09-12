import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydisktriage import actions
from pydisktriage.catalog import Finding
from pydisktriage.junctions import load_junctions


class TestActionsJunction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.junctions_file = self.tmp / "test_junctions.json"

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("pydisktriage.junctions.get_default_junctions_file")
    @patch("pydisktriage.actions.free_space", return_value=100 * 1024**3)
    @patch("pydisktriage.actions.Prompt.ask")
    def test_action_move_junction(self, mock_prompt, mock_free, mock_get_file):
        mock_get_file.return_value = self.junctions_file

        src = self.tmp / "test_src"
        src.mkdir()
        (src / "file.txt").write_text("hello", encoding="utf-8")
        dest = self.tmp / "test_dest"

        mock_prompt.side_effect = ["D", str(dest)]

        finding = Finding(
            ident="test-item",
            path=src,
            kind="movivel",
            size=1024,
            files=1,
            is_file=False,
        )

        ok = actions.action_move_junction(finding, default_drive="D")
        self.assertTrue(ok)
        self.assertTrue(dest.exists())
        self.assertTrue(src.exists())

        # Verify tracking record
        records = load_junctions(self.junctions_file)
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].active)
        self.assertEqual(records[0].name, "test-item")


if __name__ == "__main__":
    unittest.main()
