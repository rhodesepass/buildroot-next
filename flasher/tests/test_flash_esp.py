import importlib.util
import hashlib
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib


SPEC = importlib.util.spec_from_file_location("flash_esp", Path(__file__).resolve().parents[1] / "flash_esp.py")
flash_esp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flash_esp)


def partition(kind, subtype, address, size):
    return struct.pack("<HBBII16sI", 0x50AA, kind, subtype, address, size, b"test", 0)


def table(*entries):
    return b"".join(entries).ljust(4096, b"\xff")


def metadata(first, second, corrupt=False):
    data = bytearray(b"\xff" * 8192)
    for pos, sequence in ((0, first), (4096, second)):
        if sequence is not None:
            encoded = struct.pack("<I", sequence)
            data[pos:pos + 4] = encoded
            struct.pack_into("<II", data, pos + 24, 2, zlib.crc32(encoded, 0xFFFFFFFF) ^ int(corrupt))
    return bytes(data)


def firmware():
    header = bytearray(24)
    header[0:2] = bytes((0xE9, 1))
    struct.pack_into("<H", header, 12, 5)
    header[23] = 1
    image = header + struct.pack("<II", 0x3C000000, 4) + b"\x01\x02\x03\x04"
    image += b"\x00" * (15 - len(image) % 16) + bytes((0xEF ^ 1 ^ 2 ^ 3 ^ 4,))
    return bytes(image) + hashlib.sha256(image).digest()


class FlashEspTests(unittest.TestCase):
    def setUp(self):
        self.entries = [partition(1, 0, 0xF000, 8192),
                        partition(0, 0x10, 0x20000, 0x180000),
                        partition(0, 0x11, 0x1A0000, 0x180000)]

    def test_dynamic_layout_and_newest_sequence(self):
        slots, ota = flash_esp.parse_layout(table(*self.entries))
        self.assertEqual(ota, (0xF000, 8192))
        self.assertEqual(slots[flash_esp.active_slot(metadata(3, 4))][0], 0x1A0000)
        self.assertEqual(flash_esp.active_slot(metadata(5, 4)), 0)

    def test_invalid_crc_and_erased_metadata_rejected(self):
        for data in (metadata(1, 2, corrupt=True), metadata(None, None), metadata(0, None)):
            with self.assertRaises(ValueError):
                flash_esp.active_slot(data)

    def test_one_invalid_record_uses_other(self):
        self.assertEqual(flash_esp.active_slot(metadata(None, 6)), 1)

    def test_overlap_and_missing_slot_rejected(self):
        with self.assertRaises(ValueError):
            flash_esp.parse_layout(table(*self.entries, partition(1, 2, 0x20000, 4096)))
        with self.assertRaises(ValueError):
            flash_esp.parse_layout(table(*self.entries[:2]))

    def test_capacity_and_bootloader_limit(self):
        slots = {0: (0x20000, 4096)}
        with patch.object(flash_esp, "validate_firmware", return_value=b"A" * 4097):
            with self.assertRaises(ValueError):
                flash_esp.prepare_images(slots, 0, "app.bin")
        with patch.object(flash_esp, "validate_firmware", side_effect=[b"APP", b"B" * 32769]):
            with self.assertRaises(ValueError):
                flash_esp.prepare_images(slots, 0, "app.bin", "bootloader.bin")
        with patch.object(flash_esp, "validate_firmware", side_effect=[b"APP", b"BOOT"]):
            images = flash_esp.prepare_images(slots, 0, "app.bin", "bootloader.bin")
        self.assertEqual([(address, data) for address, _, data in images], [(0, b"BOOT"), (0x20000, b"APP")])

    def test_chunked_readback_and_failure(self):
        read = Mock(side_effect=[b"A" * 65536, b"B"])
        flash_esp.verify_image(None, read, 0x20000, b"A" * 65536 + b"B")
        self.assertEqual(read.call_args.args[1:3], (0x30000, 1))
        with self.assertRaisesRegex(ValueError, "readback mismatch"):
            flash_esp.verify_image(None, Mock(return_value=b"X"), 0x20000, b"A")

    def test_flash_preserves_metadata_and_checks_it_before_reset(self):
        original_table = table(*self.entries)
        original_metadata = metadata(3, 4)
        for changed in (False, True):
            with self.subTest(changed=changed):
                esp = Mock()
                esp.run_stub.return_value = esp
                api = ModuleType("esptool")
                api.attach_flash = Mock()
                api.write_flash = Mock()
                api.read_flash = Mock(side_effect=[original_table, original_metadata, b"APP",
                                                  b"corrupted" if changed else original_metadata,
                                                  original_table])
                target = ModuleType("esptool.targets.esp32c3")
                target.ESP32C3ROM = Mock(return_value=esp)
                modules = {"esptool": api, "esptool.targets": ModuleType("esptool.targets"),
                           "esptool.targets.esp32c3": target}
                args = SimpleNamespace(port="test", baud=115200, connect_mode="no-reset",
                                       app="app.bin", bootloader=None, after="hard-reset")
                with patch.dict(sys.modules, modules), patch.object(flash_esp, "validate_firmware", return_value=b"APP"):
                    if changed:
                        with self.assertRaisesRegex(ValueError, "metadata changed"):
                            flash_esp.flash(args)
                        esp.hard_reset.assert_not_called()
                    else:
                        flash_esp.flash(args)
                        esp.hard_reset.assert_called_once()
                self.assertEqual(api.write_flash.call_args.args[1], [(0x1A0000, b"APP")])
                esp._port.close.assert_called_once()

    def test_valid_c3_firmware(self):
        image = firmware()
        with patch.object(Path, "read_bytes", return_value=image):
            self.assertEqual(flash_esp.validate_firmware("app.bin"), image)

    def test_invalid_firmware_rejected(self):
        image = firmware()
        wrong_chip = bytearray(image)
        wrong_chip[12] = 0
        bad_checksum = bytearray(image)
        bad_checksum[47] ^= 1
        bad_hash = bytearray(image)
        bad_hash[-1] ^= 1
        overflow = bytearray(image)
        struct.pack_into("<I", overflow, 28, 0xFFFFFFFC)
        for data in (b"not an ESP firmware", image[:23], image[:28], image[:35],
                     image[:40], image[:-1], wrong_chip, bad_checksum, bad_hash, overflow):
            with self.subTest(length=len(data)), patch.object(Path, "read_bytes", return_value=data):
                with self.assertRaises(ValueError):
                    flash_esp.validate_firmware("bad.bin")


if __name__ == "__main__":
    unittest.main()
