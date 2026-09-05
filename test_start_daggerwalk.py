import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import start_daggerwalk


class SoftwareCursorTests(unittest.TestCase):
    def test_installs_cursor_in_streaming_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exe = root / "DaggerfallUnity.exe"
            source = root / "source" / "Cursor.png"
            source.parent.mkdir()
            source.write_bytes(b"software cursor")

            with (
                patch.object(start_daggerwalk, "DAGGERFALL_EXE", str(exe)),
                patch.object(start_daggerwalk, "SOFTWARE_CURSOR", source),
            ):
                result = start_daggerwalk.install_software_cursor()

            target = (
                root / "DaggerfallUnity_Data" / "StreamingAssets" /
                "Textures" / "Cursor.png"
            )
            self.assertTrue(result)
            self.assertEqual(target.read_bytes(), b"software cursor")


if __name__ == "__main__":
    unittest.main()
