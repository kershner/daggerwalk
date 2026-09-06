import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from daggerwalk import paths


class LegacyPathMigrationTests(unittest.TestCase):
    def test_legacy_root_file_moves_to_new_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "state.json"
            legacy.write_text("preserved", encoding="utf-8")

            with patch.object(paths, "REPO_ROOT", root):
                result = paths._local_file(root / "runtime", "state.json")

            self.assertEqual(result.read_text(encoding="utf-8"), "preserved")
            self.assertFalse(legacy.exists())
            self.assertEqual(result, root / "runtime" / "state.json")


if __name__ == "__main__":
    unittest.main()
