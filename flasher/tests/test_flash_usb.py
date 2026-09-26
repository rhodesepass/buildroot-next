#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('epass_flash', root / 'flash.py')
flash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)


class SelectionTest(unittest.TestCase):
    def test_default_all(self):
        self.assertEqual(flash.select_stages(), flash.DFU_STAGES)
        self.assertEqual(flash.detach_command(flash.select_stages())[-3:], ['-a', 'rootfs', '-e'])

    def test_subset_fixed_order_and_dedup(self):
        stages = flash.select_stages(['uboot', 'spl', 'uboot'])
        self.assertEqual(stages, flash.DFU_STAGES[:2])
        self.assertEqual(flash.detach_command(stages)[-3:], ['-a', 'uboot', '-e'])

    def test_missing_only_selected_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            images = Path(directory)
            stages = flash.select_stages(['uboot'])
            self.assertEqual(flash.missing_images(images, stages),
                             ['sunxi-spl.bin', 'fw_dynamic.bin', 'u-boot-fel.bin', 'u-boot.dtb', 'u-boot.itb'])
            for name in flash.required_images(stages):
                (images / name).write_bytes(b'fixture')
            self.assertEqual(flash.missing_images(images, stages), [])
            self.assertFalse((images / 'rootfs.ubi').exists())

    def test_scrub_requires_all(self):
        with self.assertRaisesRegex(ValueError, '--scrub requires all'):
            flash.select_stages(['spl', 'uboot'], scrub=True)
        self.assertEqual(flash.select_stages(['rootfs', 'boot', 'uboot', 'spl'], scrub=True), flash.DFU_STAGES)
        self.assertEqual(flash.select_stages(scrub=True), flash.DFU_STAGES)

    def test_single_stage_detach(self):
        self.assertEqual(flash.detach_command(flash.select_stages(['boot']))[-3:], ['-a', 'boot', '-e'])


class UsbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.images = Path(self.tmp.name)
        for name in flash.required_images(flash.DFU_STAGES):
            (self.images / name).write_bytes(b"data")
        (self.images / "rootfs.ubi").write_bytes(bytes(128 << 10))
        (self.images / "sunxi-spl.bin").write_bytes(b"0000eGON.BT0")
        (self.images / "u-boot.dtb").write_bytes(b"\xd0\x0d\xfe\xed")
        (self.images / "u-boot-fel.bin").write_bytes(b"boot\xd0\x0d\xfe\xed")
        (self.images / "ch32-touch.bin").write_bytes(b"touch123")
        (self.images / "bridge.bin").write_bytes(b"bridge")

    def args(self, *extra):
        return flash.parser().parse_args(["--images", str(self.images), "--bridge-bin",
                                         str(self.images / "bridge.bin"), *extra])

    def test_usb_defaults_keep_peripherals(self):
        args = self.args()
        self.assertEqual(flash.prepare(args), flash.DFU_STAGES)
        self.assertFalse(args.wch or args.esp)

    def test_esp_default_image_and_required_port(self):
        (self.images / "esp").mkdir()
        firmware = self.images / "esp/epass_bmc.bin"
        firmware.write_bytes(b"fixture")
        args = self.args("--no-system", "--esp", "--esp-port", "/dev/mock")
        with patch.object(flash.importlib.util, "module_from_spec") as helper:
            with patch.object(flash.importlib.util, "spec_from_file_location"):
                self.assertEqual(flash.prepare(args), [])
            helper.return_value.validate_firmware.assert_called_once_with(firmware)
        self.assertEqual(args.esp_image, firmware)
        with self.assertRaisesRegex(ValueError, "esp-port"):
            flash.prepare(self.args("--no-system", "--esp"))

    def test_reject_invalid_combinations_before_io(self):
        cases = [
            ("--no-system",),
            ("--no-system", "--wch", "--only", "boot"),
            ("--wch-image", "not-selected.bin"),
            ("--esp",),
            ("--esp-image", "not-selected.bin"),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError), patch.object(flash, "run") as run:
                flash.prepare(self.args(*case))
                run.assert_not_called()

    def test_invalid_touch_size(self):
        (self.images / "ch32-touch.bin").write_bytes(b"abc")
        with self.assertRaisesRegex(ValueError, "WCH"):
            flash.prepare(self.args("--wch"))

    def test_missing_esp_does_not_start_system(self):
        with patch.object(flash.sys, "argv", ["flash.py", "--images", str(self.images), "--esp",
                                             "--esp-port", "/dev/mock", "--esp-image", "missing.bin"]), \
                patch.object(flash, "flash_usb") as usb, self.assertRaises(SystemExit):
            flash.main()
        usb.assert_not_called()

    def test_dry_run_never_connects_or_creates_workdir(self):
        with patch.object(flash.sys, "argv", ["flash.py", "--images", str(self.images), "--dry-run"]), \
                patch.object(flash.subprocess, "run") as run:
            flash.main()
        run.assert_not_called()
        self.assertFalse((self.images / ".flash").exists())

    def test_wch_readback_failure_prevents_esp(self):
        args = self.args("--no-system", "--wch")
        flash.prepare(args)
        args.esp = True
        args.esp_port = "/dev/mock"

        def fake_run(*cmd):
            if "-r" in cmd:
                Path(cmd[cmd.index("-r") + 1]).write_bytes(b"wrong")

        with patch.object(flash, "bridge_present", return_value=True), \
                patch.object(flash, "is_bridge_port", return_value=True), \
                patch.object(flash, "run", side_effect=fake_run) as run, \
                self.assertRaisesRegex(SystemExit, "回读不一致"):
            flash.flash_peripherals(args)
        self.assertEqual(run.call_count, 2)

    def test_wrong_esp_port_prevents_any_peripheral_write(self):
        args = self.args("--no-system", "--wch")
        args.esp = True
        args.esp_port = "/dev/not-the-bridge"
        with patch.object(flash, "bridge_present", return_value=True), \
                patch.object(flash, "is_bridge_port", return_value=False), \
                patch.object(flash.time, "monotonic", side_effect=[0, 200]), \
                patch.object(flash, "run") as run, \
                self.assertRaisesRegex(SystemExit, "不是已枚举"):
            flash.flash_peripherals(args)
        run.assert_not_called()

    def test_system_failure_stops_peripheral_stage(self):
        args = self.args("--wch")
        with patch.object(flash, "parser") as parser, \
                patch.object(flash.shutil, "which", return_value="/mock/tool"), \
                patch.object(flash, "flash_usb", side_effect=SystemExit("DFU failed")), \
                patch.object(flash, "flash_peripherals") as peripherals, \
                self.assertRaisesRegex(SystemExit, "DFU failed"):
            parser.return_value.parse_args.return_value = args
            flash.main()
        peripherals.assert_not_called()

    def test_system_completes_before_peripherals(self):
        args = self.args("--wch")
        order = []
        with patch.object(flash, "parser") as parser, \
                patch.object(flash.shutil, "which", return_value="/mock/tool"), \
                patch.object(flash, "flash_usb", side_effect=lambda *a: order.append("system")), \
                patch.object(flash, "flash_peripherals", side_effect=lambda *a: order.append("peripherals")):
            parser.return_value.parse_args.return_value = args
            flash.main()
        self.assertEqual(order, ["system", "peripherals"])


    def test_wireless_options_are_rejected(self):
        for arguments in (["--transport", "wifi"], ["--transport", "ble"],
                          ["--address", "AA"], ["--wifi-sta", "ssid"],
                          ["--wifi-ap"], ["--url", "http://example"],
                          ["--att-payload", "20"], ["--ota-tool", "ota.py"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.args(*arguments)

    def test_wch_only_needs_no_system_images(self):
        for name in flash.required_images(flash.DFU_STAGES):
            (self.images / name).unlink()
        self.assertEqual(flash.prepare(self.args("--no-system", "--wch")), [])


if __name__ == "__main__":
    unittest.main()
