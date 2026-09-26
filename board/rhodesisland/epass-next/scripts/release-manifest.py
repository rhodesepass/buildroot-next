#!/usr/bin/env python3
"""Describe built images without implicitly selecting peripheral updates."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def bmc_source(package):
    makefile = (package / 'epass-bmc-firmware.mk').read_text()
    revision = re.search(r'^EPASS_BMC_FIRMWARE_VERSION = (origin/master|[0-9a-f]{40})$', makefile, re.MULTILINE)
    site = re.search(r'^EPASS_BMC_FIRMWARE_SITE = (\S+)$', makefile, re.MULTILINE)
    if not revision or not site:
        raise ValueError('BMC package must specify a Git repository and source revision')
    version = 'br-' + revision[1].removeprefix('origin/')[:12]
    return {'source_revision': revision[1], 'source_url': site[1], 'version': version}


def generate(images, config):
    enabled = 'BR2_PACKAGE_CH32_TOUCH_FIRMWARE=y' in config.splitlines()
    result = {'schema_version': 1, 'board': 'epass-next', 'artifacts': {},
              'default_ota_targets': ['boot', 'rootfs'], 'optional_ota_targets': ['uboot']}
    for name, target in (('sunxi-spl.bin', None), ('u-boot.itb', 'uboot'),
                         ('boot.itb', 'boot'), ('rootfs.ubi', 'rootfs')):
        path = images / name
        if path.is_file():
            result['artifacts'][name] = {'bytes': path.stat().st_size,
                                          'sha256': digest(path), 'ota_target': target}
    if enabled:
        package = Path(__file__).resolve().parents[4] / 'package/ch32-touch-firmware'
        spec = importlib.util.spec_from_file_location('touch_manifest', package / 'manifest.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        wire = checker.protocol(Path(__file__).resolve().parents[1] / 'src/touch_protocol.h')
        touch = json.loads((images / 'ch32-touch.json').read_text())
        if any(touch.get(key) != value for key, value in checker.package_source(package).items()):
            raise ValueError('stale or incompatible touch Git provenance; rebuild ch32-touch-firmware')
        binary = images / 'ch32-touch.bin'
        if (touch['file'] != binary.name or touch['bytes'] != binary.stat().st_size or
                touch['sha256'] != digest(binary) or touch['ota_target'] != 'touch' or
                touch['wire_target'] != 6 or touch['protocol_version'] != wire['TOUCH_PROTOCOL_VERSION'] or
                touch.get('frame_size') != wire['TOUCH_FRAME_SIZE'] or
                touch.get('i2c_address') != wire['TOUCH_I2C_ADDRESS'] or
                touch.get('protocol_definitions') != wire or
                not 0 < touch['bytes'] <= 63488 or touch['bytes'] % 4):
            raise ValueError('stale or incompatible touch image; rebuild ch32-touch-firmware')
        touch['requires_explicit_selection'] = True
        result['artifacts'][binary.name] = touch
        result['optional_ota_targets'].append('touch')
    if 'BR2_PACKAGE_EPASS_BMC_FIRMWARE=y' in config.splitlines():
        package = Path(__file__).resolve().parents[4] / 'package/epass-bmc-firmware'
        esp = json.loads((images / 'esp/manifest.json').read_text())
        if any(esp.get(key) != value for key, value in bmc_source(package).items()):
            raise ValueError('stale or incompatible ESP Git provenance; rebuild epass-bmc-firmware')
        required_esp = {'epass_bmc.bin', 'bootloader.bin', 'partition-table.bin',
                        'ota_data_initial.bin', 'd1s_spl.bin', 'flash_args.json'}
        if set(esp['artifacts']) != required_esp:
            raise ValueError('incomplete ESP artifact manifest')
        if (esp['ota_target'] != 'bmc' or esp['wire_target'] != 7 or
                esp['ota_file'] != 'epass_bmc.bin' or
                esp['sdk_lock_sha256'] != digest(package.parent / 'esp-idf/esp-idf.hash')):
            raise ValueError('stale or incompatible ESP firmware; rebuild epass-bmc-firmware')
        for name, artifact in esp['artifacts'].items():
            if Path(name).name != name:
                raise ValueError('invalid ESP artifact path')
            path = images / 'esp' / name
            if artifact['bytes'] != path.stat().st_size or artifact['sha256'] != digest(path):
                raise ValueError(f'stale ESP artifact: {name}')
            result['artifacts'][f'esp/{name}'] = dict(artifact, requires_explicit_selection=True,
                                                    ota_target='bmc' if name == esp['ota_file'] else None)
        result['esp_firmware'] = esp
        result['optional_ota_targets'].append('bmc')
    for name, key in (('linux_version', 'BR2_LINUX_KERNEL_CUSTOM_VERSION_VALUE'),
                      ('uboot_version', 'BR2_TARGET_UBOOT_CUSTOM_VERSION_VALUE')):
        match = re.search(rf'^{key}="([^"]+)"$', config, re.MULTILINE)
        if match:
            result[name] = match[1]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    manifest = generate(args.images, args.config.read_text())
    (args.images / 'release-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
