import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pydisktriage.fsutil import delete_tree, move_tree


class TestFsUtil(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_move_tree_directory(self):
        src = self.tmp / "src"
        dst = self.tmp / "dst"
        (src / "sub1" / "sub2").mkdir(parents=True)
        (src / "file1.txt").write_text("hello 1", encoding="utf-8")
        (src / "sub1" / "file 2.txt").write_text("hello 2 with spaces", encoding="utf-8")
        (src / "sub1" / "sub2" / "file3.bin").write_bytes(b"x" * 1024)

        bytes_reported = []
        res = move_tree(src, dst, progress=lambda n: bytes_reported.append(n))

        self.assertTrue(res.ok, f"move_tree failed with errors: {res.errors}")
        self.assertFalse(src.exists(), "Source directory should have been removed")
        self.assertTrue(dst.exists(), "Destination directory should exist")
        self.assertEqual((dst / "file1.txt").read_text(encoding="utf-8"), "hello 1")
        self.assertEqual((dst / "sub1" / "file 2.txt").read_text(encoding="utf-8"), "hello 2 with spaces")
        self.assertEqual(len((dst / "sub1" / "sub2" / "file3.bin").read_bytes()), 1024)
        self.assertGreater(sum(bytes_reported), 0)
        self.assertEqual(res.files_done, 3)

    def test_move_tree_single_file(self):
        src_file = self.tmp / "single.txt"
        src_file.write_text("single content", encoding="utf-8")
        dst = self.tmp / "dst"

        res = move_tree(src_file, dst)
        self.assertTrue(res.ok)
        self.assertFalse(src_file.exists())
        self.assertEqual((dst / "single.txt").read_text(encoding="utf-8"), "single content")

    def test_move_tree_merge_existing(self):
        src = self.tmp / "src"
        dst = self.tmp / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "f1.txt").write_text("from src", encoding="utf-8")
        (dst / "f1.txt").write_text("old dst", encoding="utf-8")
        (src / "f2.txt").write_text("new f2", encoding="utf-8")

        res = move_tree(src, dst)
        self.assertTrue(res.ok)
        self.assertFalse(src.exists())
        self.assertEqual((dst / "f1.txt").read_text(encoding="utf-8"), "from src")
        self.assertEqual((dst / "f2.txt").read_text(encoding="utf-8"), "new f2")

    def test_move_tree_merge_identical_files(self):
        src = self.tmp / "src_identical"
        dst = self.tmp / "dst_identical"
        src.mkdir()
        dst.mkdir()
        (src / "same.txt").write_text("identical", encoding="utf-8")
        shutil.copy2(src / "same.txt", dst / "same.txt")
        (src / "new.txt").write_text("new content", encoding="utf-8")

        res = move_tree(src, dst)
        self.assertTrue(res.ok, f"Failed: {res.errors}")
        self.assertFalse(src.exists())
        self.assertEqual((dst / "same.txt").read_text(encoding="utf-8"), "identical")
        self.assertEqual((dst / "new.txt").read_text(encoding="utf-8"), "new content")

    def test_delete_tree(self):
        folder = self.tmp / "to_delete"
        (folder / "sub").mkdir(parents=True)
        (folder / "f1.txt").write_text("a", encoding="utf-8")
        (folder / "sub" / "f2.txt").write_text("b", encoding="utf-8")

        res = delete_tree(folder, keep_root=False)
        self.assertTrue(res.ok)
        self.assertFalse(folder.exists())

    def test_move_tree_python_fallback(self):
        from pydisktriage.fsutil import _move_tree_python
        src = self.tmp / "fallback_src"
        dst = self.tmp / "fallback_dst"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "file.txt").write_text("fallback test", encoding="utf-8")

        res = _move_tree_python(src, dst)
        self.assertTrue(res.ok)
        self.assertFalse(src.exists())
        self.assertEqual((dst / "sub" / "file.txt").read_text(encoding="utf-8"), "fallback test")


if __name__ == "__main__":
    unittest.main()
