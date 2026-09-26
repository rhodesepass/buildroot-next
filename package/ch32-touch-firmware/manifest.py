#!/usr/bin/env python3
"""Validate the Linux wire contract before publishing firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol(path):
    result = {}
    for name, value in re.findall(r'^#define\s+(TOUCH_\w+)\s+(0x[0-9a-fA-F]+|[0-9]+)\s*$',
                                  path.read_text(), re.MULTILINE):
        result[name] = int(value, 0)
    if not {'TOUCH_PROTOCOL_VERSION', 'TOUCH_FRAME_SIZE', 'TOUCH_I2C_ADDRESS'} <= result.keys():
        raise ValueError(f'incomplete touch protocol: {path}')
    return result


def package_source(package):
    makefile = (package / 'ch32-touch-firmware.mk').read_text()
    revision = re.search(r'^CH32_TOUCH_FIRMWARE_VERSION = (\S+)$', makefile, re.MULTILINE)
    site = re.search(r'^CH32_TOUCH_FIRMWARE_SITE = (\S+)$', makefile, re.MULTILINE)
    if not revision or not site:
        raise ValueError('CH32 package must specify a Git repository and reference')
    return {'source_revision': revision[1], 'source_url': site[1]}


def check(source, driver):
    firmware = protocol(source / 'User/touch_protocol.h')
    if firmware != protocol(driver):
        raise ValueError('CH32 firmware and Linux driver wire definitions differ')
    return firmware


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'image'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--source-revision')
    parser.add_argument('--source-url')
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--toolchain-lock', type=Path)
    args = parser.parse_args()
    wire = check(args.source, args.driver)
    if args.action == 'check':
        print('CH32 firmware and Linux protocol: PASS')
        return
    if not args.compiler or not args.image or not args.output or not args.toolchain_lock:
        parser.error('image requires --compiler, --image, --output and --toolchain-lock')
    expected_source = package_source(Path(__file__).resolve().parent)
    if (args.source_revision != expected_source['source_revision'] or
            args.source_url != expected_source['source_url']):
        raise ValueError('image Git provenance differs from Buildroot package')
    size = args.image.stat().st_size
    if not 0 < size <= 63488 or size % 4:
        raise ValueError('touch image must be nonempty, 4-byte aligned and at most 63488 bytes')
    version = subprocess.check_output([str(args.compiler), '-dumpfullversion'], text=True).strip()
    if version != '12.2.0':
        raise ValueError(f'unexpected WCH compiler version: {version}')
    snapshot = json.loads((args.source / 'snapshot.json').read_text())
    archive = next(line.split() for line in args.toolchain_lock.read_text().splitlines()
                   if line.startswith('sha256') and '.tar.xz' in line)
    manifest = {
        'schema_version': 1, 'firmware_version': snapshot['version'],
        'chip': 'CH32V006', 'ota_target': 'touch', 'wire_target': 6,
        'file': args.image.name, 'bytes': size, 'sha256': sha256(args.image),
        'protocol_version': wire['TOUCH_PROTOCOL_VERSION'],
        'frame_size': wire['TOUCH_FRAME_SIZE'], 'i2c_address': wire['TOUCH_I2C_ADDRESS'],
        'protocol_definitions': wire,
        **expected_source,
        'compiler': 'riscv-wch-elf-gcc', 'compiler_version': version,
        'compiler_sha256': sha256(args.compiler),
        'toolchain_archive': archive[2], 'toolchain_archive_sha256': archive[1],
        'update_policy': 'explicit-touch-target',
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
