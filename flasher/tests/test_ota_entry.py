import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("ota_entry", Path(__file__).resolve().parents[1] / "ota.py")
ota = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ota)


class OtaEntryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.images = Path(self.directory.name)
        for name, data in (("u-boot.itb", b"FIT"), ("boot.itb", b"boot"),
                           ("rootfs.ubi", bytes(128 << 10)), ("ch32-touch.bin", b"WCH!")):
            (self.images / name).write_bytes(data)
        (self.images / "esp").mkdir()
        header = bytearray(24)
        header[0:2] = b"\xe9\x01"
        struct.pack_into("<H", header, 12, 5)
        firmware = header + struct.pack("<II", 0x3C000000, 256) + bytes(271) + b"\xef"
        (self.images / "esp/epass_bmc.bin").write_bytes(firmware)

    def args(self, *extra):
        return ota.parser().parse_args(["--images", str(self.images), *extra])

    def test_default_ota_preserves_uboot_and_peripherals(self):
        args = ota.prepare(self.args("--address", "AA:BB"))
        self.assertEqual([item.split("=")[0] for item in args.extra_images], ["boot", "rootfs"])
        self.assertTrue(args.boot)
        self.assertFalse(args.esp)

    def test_http_needs_no_ble_address(self):
        args = ota.prepare(self.args("--transport", "wifi", "--url", "http://192.0.2.1", "--only", "boot"))
        self.assertIsNone(args.address)
        self.assertEqual(len(args.extra_images), 1)

    def test_touch_only(self):
        (self.images / "rootfs.ubi").unlink()
        (self.images / "boot.itb").unlink()
        args = ota.prepare(self.args("--address", "AA", "--no-system", "--wch"))
        self.assertEqual(args.extra_images, [f"touch={self.images / 'ch32-touch.bin'}"])

    def test_explicit_uboot_fixed_order_dedup(self):
        args = ota.prepare(self.args("--address", "AA", "--only", "boot", "uboot", "uboot"))
        self.assertEqual([item.split("=")[0] for item in args.extra_images], ["uboot", "boot"])

    def test_reject_usb_spl_and_overlay_targets(self):
        for options in [("--transport", "usb"), ("--only", "spl"),
                        ("--only", "overlay"), ("--wipe",), ("--scrub",)]:
            with self.subTest(options=options), self.assertRaises(SystemExit):
                self.args(*options)

    def test_invalid_options(self):
        for options in [(), ("--transport", "wifi"), ("--wifi-ap", "--address", "AA"),
                        ("--address", "AA", "--no-system"),
                        ("--address", "AA", "--no-system", "--wch", "--only", "boot"),
                        ("--address", "AA", "--wch-image", "missing"),
                        ("--address", "AA", "--esp-image", "missing"),
                        ("--address", "AA", "--att-payload", "300")]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                ota.prepare(self.args(*options))

    def test_esp_only_ble_and_wifi_need_no_fit(self):
        (self.images / "u-boot.itb").unlink()
        (self.images / "boot.itb").unlink()
        (self.images / "rootfs.ubi").unlink()
        for route in (("--address", "AA"), ("--transport", "wifi", "--url", "http://192.0.2.1")):
            with self.subTest(route=route):
                args = ota.prepare(self.args(*route, "--no-system", "--esp", "--no-boot"))
                self.assertEqual(args.extra_images, [f"bmc={self.images / 'esp/epass_bmc.bin'}"])
                self.assertIsNone(args.uboot_fit)
                self.assertFalse(args.boot)

    def test_esp_mixed_targets_stage_esp_first(self):
        args = ota.prepare(self.args("--address", "AA", "--esp", "--wch"))
        self.assertEqual([item.split("=")[0] for item in args.extra_images], ["bmc", "boot", "rootfs", "touch"])
        self.assertEqual(args.esp_image, self.images / "esp/epass_bmc.bin")

    def test_explicit_esp_path_and_no_esp(self):
        source = self.images / "esp/epass_bmc.bin"
        custom = self.images / "custom.bin"
        source.rename(custom)
        args = ota.prepare(self.args("--address", "AA", "--esp", "--esp-image", str(custom)))
        self.assertEqual(args.esp_image, custom)
        args = ota.prepare(self.args("--address", "AA", "--no-esp"))
        self.assertFalse(any(item.startswith("bmc=") for item in args.extra_images))

    def test_invalid_esp_prevents_connection(self):
        (self.images / "esp/epass_bmc.bin").write_bytes(b"bad firmware")
        with patch("sys.argv", ["ota.py", "--images", str(self.images), "--address", "AA", "--esp"]), \
                patch.object(ota.asyncio, "run") as connect, self.assertRaises(SystemExit):
            ota.main()
        connect.assert_not_called()

    def test_rootfs_alignment_checked_before_connection(self):
        (self.images / "rootfs.ubi").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            ota.prepare(self.args("--address", "AA"))

    def test_missing_fit_rejected_for_touch_only(self):
        (self.images / "u-boot.itb").unlink()
        with self.assertRaisesRegex(ValueError, "FIT"):
            ota.prepare(self.args("--address", "AA", "--no-system", "--wch"))

    def test_dryrun_never_prompts_or_connects(self):
        with patch("sys.argv", ["ota.py", "--images", str(self.images), "--transport", "wifi",
                                "--wifi-sta", "test", "--address", "AA", "--dry-run"]), \
                patch.object(ota.getpass, "getpass") as password, \
                patch.object(ota.asyncio, "run") as connect:
            ota.main()
        password.assert_not_called()
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
