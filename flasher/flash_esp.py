#!/usr/bin/env python3
"""Update the active ESP32-C3 application without replacing its data partitions."""

import argparse
import hashlib
from pathlib import Path
import struct
import zlib


TABLE_ADDRESS = 0x8000
SECTOR_SIZE = 0x1000


def validate_firmware(path):
    data = Path(path).read_bytes()
    if len(data) < 24 or data[0] != 0xE9:
        raise ValueError(f"{path}: missing or truncated ESP image header")
    if struct.unpack_from("<H", data, 12)[0] != 5:
        raise ValueError(f"{path}: firmware is not for ESP32-C3 (chip ID 5)")
    count = data[1]
    if not 1 <= count <= 16 or data[23] not in (0, 1):
        raise ValueError(f"{path}: invalid ESP image segment count or hash flag")
    position = 24
    checksum = 0xEF
    for _ in range(count):
        if position + 8 > len(data):
            raise ValueError(f"{path}: truncated ESP segment header")
        _, length = struct.unpack_from("<II", data, position)
        position += 8
        if length % 4 or position + length > len(data):
            raise ValueError(f"{path}: invalid or truncated ESP segment data")
        for value in data[position:position + length]:
            checksum ^= value
        position += length
    checksum_position = position + (15 - position % 16)
    if checksum_position >= len(data):
        raise ValueError(f"{path}: missing ESP image checksum")
    if data[checksum_position] != checksum:
        raise ValueError(f"{path}: ESP image checksum mismatch")
    if data[23]:
        hash_start = checksum_position + 1
        if len(data) < hash_start + 32:
            raise ValueError(f"{path}: truncated ESP image SHA256")
        if hashlib.sha256(data[:hash_start]).digest() != data[hash_start:hash_start + 32]:
            raise ValueError(f"{path}: ESP image SHA256 mismatch")
    return data


def parse_layout(table):
    if len(table) != SECTOR_SIZE:
        raise ValueError("Incomplete ESP partition table")
    partitions = []
    slots = {}
    ota = None
    for pos in range(0, len(table), 32):
        record = table[pos:pos + 32]
        if record == b"\xff" * 32:
            break
        magic = struct.unpack_from("<H", record)[0]
        if magic == 0xEBEB:
            if record[16:] != hashlib.md5(table[:pos]).digest():
                raise ValueError("ESP partition table MD5 mismatch")
            if table[pos + 32:] != b"\xff" * (len(table) - pos - 32):
                raise ValueError("Unexpected records after partition table checksum")
            break
        if magic != 0x50AA:
            raise ValueError("Invalid ESP partition table entry")
        _, kind, subtype, address, size = struct.unpack_from("<HBBII", record)
        if not size or address < TABLE_ADDRESS + SECTOR_SIZE or address % SECTOR_SIZE or size % SECTOR_SIZE:
            raise ValueError("Invalid ESP partition alignment or size")
        if address + size > 0x100000000:
            raise ValueError("ESP partition address overflow")
        for start, length in partitions:
            if address < start + length and start < address + size:
                raise ValueError("Overlapping ESP partitions")
        partitions.append((address, size))
        if kind == 0:
            if subtype not in (0x10, 0x11) or subtype - 0x10 in slots or address % 0x10000:
                raise ValueError("Expected exactly two aligned ESP OTA app partitions")
            slots[subtype - 0x10] = (address, size)
        elif kind == 1 and subtype == 0:
            if ota is not None or size != 2 * SECTOR_SIZE:
                raise ValueError("Expected one 8192-byte otadata partition")
            ota = (address, size)
    if set(slots) != {0, 1} or ota is None:
        raise ValueError("Missing ESP OTA app partitions or otadata")
    return slots, ota


def active_slot(metadata):
    if len(metadata) != 2 * SECTOR_SIZE:
        raise ValueError("Incomplete ESP OTA metadata")
    sequences = []
    for pos in (0, SECTOR_SIZE):
        sequence = struct.unpack_from("<I", metadata, pos)[0]
        state, crc = struct.unpack_from("<II", metadata, pos + 24)
        if (sequence not in (0, 0xFFFFFFFF) and state in (0, 1, 2, 0xFFFFFFFF)
                and crc == zlib.crc32(metadata[pos:pos + 4], 0xFFFFFFFF)):
            sequences.append(sequence)
    if not sequences:
        raise ValueError("No valid OTA selection; refusing to guess active slot")
    return (max(sequences) - 1) % 2


def prepare_images(slots, slot, app, bootloader=None, validated=None):
    address, capacity = slots[slot]
    data = validated[0] if validated is not None else validate_firmware(app)
    if not 0 < len(data) <= capacity:
        raise ValueError("ESP application is empty or exceeds active partition capacity")
    images = [(address, Path(app), data)]
    if bootloader is not None:
        data = validated[1] if validated is not None else validate_firmware(bootloader)
        if not 0 < len(data) <= TABLE_ADDRESS:
            raise ValueError("ESP bootloader is empty or would overwrite the partition table")
        images.insert(0, (0, Path(bootloader), data))
    return images


def verify_image(esp, read_flash, address, expected):
    for start in range(0, len(expected), 65536):
        chunk = expected[start:start + 65536]
        actual = read_flash(esp, address + start, len(chunk), no_progress=True)
        if actual != chunk:
            raise ValueError(f"ESP readback mismatch at {address + start:#x}")


def flash(args):
    validated = (validate_firmware(args.app),
                 validate_firmware(args.bootloader) if args.bootloader is not None else None)
    if validated[1] is not None and len(validated[1]) > TABLE_ADDRESS:
        raise ValueError("ESP bootloader would overwrite the partition table")
    from esptool import attach_flash, read_flash, write_flash
    from esptool.targets.esp32c3 import ESP32C3ROM

    esp = ESP32C3ROM(args.port, 115200)
    try:
        esp.connect(mode=args.connect_mode)
        esp = esp.run_stub()
        attach_flash(esp)
        if args.baud != 115200:
            esp.change_baud(args.baud)
        table = read_flash(esp, TABLE_ADDRESS, SECTOR_SIZE, no_progress=True)
        slots, (ota_address, ota_size) = parse_layout(table)
        metadata = read_flash(esp, ota_address, ota_size, no_progress=True)
        slot = active_slot(metadata)
        images = prepare_images(slots, slot, args.app, args.bootloader, validated)
        print(f"ESP active ota_{slot} @ {slots[slot][0]:#x}; preserving data and OTA selection", flush=True)
        # Pass the captured bytes so verification cannot race a rebuilt image file.
        write_flash(esp, [(address, data) for address, _, data in images],
                    flash_mode="keep", flash_freq="keep", flash_size="keep", compress=True)
        for address, path, expected in images:
            verify_image(esp, read_flash, address, expected)
            print(f"READBACK_OK {address:#x} {path.name} {len(expected)} SHA256={hashlib.sha256(expected).hexdigest()}", flush=True)
        if read_flash(esp, ota_address, ota_size, no_progress=True) != metadata:
            raise ValueError("ESP OTA metadata changed during flashing")
        if read_flash(esp, TABLE_ADDRESS, SECTOR_SIZE, no_progress=True) != table:
            raise ValueError("ESP partition table changed during flashing")
        if args.after == "hard-reset":
            esp.hard_reset()
        print(f"ESP VERIFIED; after={args.after}", flush=True)
    finally:
        esp._port.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--bootloader", type=Path)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--connect-mode", choices=("default-reset", "no-reset"), default="no-reset")
    parser.add_argument("--after", choices=("hard-reset", "no-reset"), default="hard-reset")
    args = parser.parse_args()
    if args.baud <= 0:
        parser.error("--baud must be positive")
    try:
        flash(args)
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"ESP flashing failed: {error}\n")


if __name__ == "__main__":
    main()
