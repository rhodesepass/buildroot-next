from pathlib import Path
import subprocess
import tempfile
import unittest


class DistributionTest(unittest.TestCase):
    def test_post_image_packages_only_local_sources(self):
        flasher = Path(__file__).resolve().parents[1]
        board = flasher.parent / "board/rhodesisland/epass-next"
        post_image = (board / "post-image.sh").read_text()
        snippet = post_image.split('FLASHER_DIR=', 1)[1].split('\npython3 "${BOARD_DIR}/scripts/release-manifest.py"', 1)[0]
        script = 'set -eu\nBOARD_DIR=$1\nBINARIES_DIR=$2\nneed() { test -f "$1"; }\nFLASHER_DIR=' + snippet
        self.assertNotIn("epass_bmc", snippet)
        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory)
            for obsolete in ("flash_esp.py", "bmc_ota.py"):
                (images / obsolete).write_text("stale")
            subprocess.run(["sh", "-c", script, "package-test", str(board), directory], check=True)
            for name in ("flash.py", "flash_esp.py", "ota.py", "bmc_ota.py", "esp_ota.py", "README.md"):
                self.assertEqual((images / "flasher" / name).read_bytes(), (flasher / name).read_bytes())
            self.assertFalse((images / "bmc_ota.py").exists())
            self.assertFalse((images / "flash_esp.py").exists())
            for launcher in ("flash.sh", "flash-all.sh", "ota.sh"):
                result = subprocess.run([str(images / launcher), "--help"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            for name, data in (("u-boot.itb", b"FIT"), ("boot.itb", b"boot"),
                               ("rootfs.ubi", bytes(128 << 10))):
                (images / name).write_bytes(data)
            result = subprocess.run([str(images / "ota.sh"), "--transport", "wifi", "--url",
                                     "http://192.0.2.1", "--dry-run"], cwd="/", capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(images / "boot.itb"), result.stdout)


if __name__ == "__main__":
    unittest.main()
