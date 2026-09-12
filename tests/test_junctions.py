import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pydisktriage.fsutil import is_reparse_point
from pydisktriage.junctions import (
    create_junction_link,
    remove_junction_link,
    move_and_create_junction,
    revert_junction,
    load_junctions,
)


class TestJunctions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.junctions_file = self.tmp / "junctions.json"

    def tearDown(self):
        if self.tmp.exists():
            # If any junction remains, remove link before deleting tmp
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_remove_junction_link(self):
        real_dir = self.tmp / "real_dir"
        real_dir.mkdir()
        (real_dir / "sample.txt").write_text("hello", encoding="utf-8")
        link_dir = self.tmp / "link_dir"

        ok, msg = create_junction_link(link_dir, real_dir)
        self.assertTrue(ok, f"Failed to create junction: {msg}")
        self.assertTrue(link_dir.exists())
        self.assertTrue(is_reparse_point(link_dir))
        self.assertEqual((link_dir / "sample.txt").read_text(encoding="utf-8"), "hello")

        # Remove junction link
        ok, msg = remove_junction_link(link_dir)
        self.assertTrue(ok, f"Failed to remove junction: {msg}")
        self.assertFalse(link_dir.exists())
        self.assertTrue(real_dir.exists(), "Target directory must not be deleted when junction is removed")
        self.assertEqual((real_dir / "sample.txt").read_text(encoding="utf-8"), "hello")

    def test_move_and_create_junction_and_revert(self):
        src = self.tmp / "app_data"
        src.mkdir()
        (src / "sub").mkdir()
        (src / "sub" / "file.dat").write_text("data 123", encoding="utf-8")
        dst = self.tmp / "d_drive" / "app_data"

        ok, msg, jid = move_and_create_junction(
            src=src,
            dst=dst,
            name="test-app",
            junctions_file=self.junctions_file,
        )
        self.assertTrue(ok, f"move_and_create_junction failed: {msg}")
        self.assertTrue(src.exists())
        self.assertTrue(is_reparse_point(src))
        self.assertTrue(dst.exists())
        self.assertEqual((src / "sub" / "file.dat").read_text(encoding="utf-8"), "data 123")

        # Verify tracking record
        records = load_junctions(self.junctions_file)
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].active)
        self.assertEqual(records[0].name, "test-app")
        self.assertEqual(Path(records[0].src), src)
        self.assertEqual(Path(records[0].dst), dst)

        # Revert junction
        ok, msg = revert_junction(jid, junctions_file=self.junctions_file)
        self.assertTrue(ok, f"revert_junction failed: {msg}")
        self.assertTrue(src.exists())
        self.assertFalse(is_reparse_point(src), "After revert, src should be a real directory, not a junction")
        self.assertEqual((src / "sub" / "file.dat").read_text(encoding="utf-8"), "data 123")
        self.assertFalse(dst.exists(), "After revert, dst should be removed as data returned to src")

        records = load_junctions(self.junctions_file)
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].active)


if __name__ == "__main__":
    unittest.main()
