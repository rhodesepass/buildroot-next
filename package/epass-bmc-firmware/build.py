#!/usr/bin/env python3
"""Build and describe BMC Git sources using the private SDK."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_source(source, lock_path):
    listed = set()
    for line in lock_path.read_text().splitlines():
        expected, name = line.split("  ", 1)
        path = source / name
        if (Path(name).is_absolute() or ".." in Path(name).parts or name in listed
                or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise ValueError(f"Invalid source lock entry: {name}")
        if not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Source lock path leaves the source tree: {name}")
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"BMC source changed without updating its lock: {name}")
        listed.add(name)
    if not listed:
        raise ValueError("Empty source lock")
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if (relative.parts[0] in ("build", ".git") or "__pycache__" in relative.parts or
                path.name.startswith((".stamp_", ".files-list")) or
                str(relative) == ".applied_patches_list"):
            continue
        if path.is_file() and str(relative) not in listed:
            raise ValueError(f"Unlisted BMC source: {path}")
    return digest(lock_path)


def validate_revision(value):
    if value == "origin/master":
        return value
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise ValueError("BMC revision must be a complete 40-character hexadecimal Git commit")
    return value.lower()


def project_version(revision):
    return "br-" + revision.removeprefix("origin/")[:12]


def build_environment(sdk):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("IDF_", "ESP_", "PYTHON", "PIP_")) or key in (
                "CC", "CXX", "CPP", "AR", "AS", "LD", "CFLAGS", "CPPFLAGS", "CXXFLAGS",
                "LDFLAGS", "CROSS_COMPILE", "CMAKE_TOOLCHAIN_FILE", "VIRTUAL_ENV",
                "CMAKE_PREFIX_PATH", "CMAKE_MODULE_PATH", "CMAKE_GENERATOR",
                "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR",
                "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH",
                "COMPILER_PATH", "GCC_EXEC_PREFIX"):
            env.pop(key, None)
    env.update(IDF_PATH=str(sdk / "sdk"), IDF_TOOLS_PATH=str(sdk / "tools"),
               IDF_PYTHON_ENV_PATH=str(sdk / "venv"), IDF_COMPONENT_MANAGER="0",
               IDF_PYTHON_CHECK_CONSTRAINTS="no",
               IDF_TARGET="esp32c3", PYTHONNOUSERSITE="1", SOURCE_DATE_EPOCH="1789862400")
    env["PATH"] = os.pathsep.join([str(sdk / "venv/bin"), str(sdk / "toolchain/bin"),
                                  str(sdk.parents[1] / "bin"), os.defpath])
    return env


def build(args):
    source = args.source.resolve()
    revision = validate_revision(args.revision)
    if args.source_lock is not None:
        check_source(source, args.source_lock)
    work = source / "build"
    work.mkdir(exist_ok=True)
    shutil.copyfile(source / "sdkconfig", work / "sdkconfig")
    sdk = args.sdk.resolve()
    env = build_environment(sdk)
    python = sdk / "venv/bin/python"
    subprocess.run([args.cmake, "-S", str(source), "-B", str(work), "-G", "Ninja",
                    f"-DCMAKE_MAKE_PROGRAM={args.ninja}", f"-DPYTHON={python}",
                    "-DIDF_TARGET=esp32c3", f"-DSDKCONFIG={work / 'sdkconfig'}",
                    f"-DSDKCONFIG_DEFAULTS={source / 'sdkconfig.defaults'}",
                    f"-DPROJECT_VER={project_version(revision)}", "-DPYTHON_DEPS_CHECKED=1"],
                   env=env, check=True)
    subprocess.run([args.cmake, "--build", str(work), "--parallel", str(args.jobs)], env=env, check=True)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_install(args, output):
    source = args.source.resolve()
    revision = validate_revision(args.revision)
    source_hash = check_source(source, args.source_lock) if args.source_lock is not None else None
    build_dir = source / "build"
    images = args.images.resolve()
    files = {"epass_bmc.bin": "epass_bmc.bin", "bootloader.bin": "bootloader/bootloader.bin",
             "partition-table.bin": "partition_table/partition-table.bin",
             "ota_data_initial.bin": "ota_data_initial.bin"}
    for name, built in files.items():
        path = build_dir / built
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing BMC build product: {path}")
        shutil.copyfile(path, output / name)
    helper = load_module("esp_image_check", Path(__file__).resolve().parents[2] / "flasher/flash_esp.py")
    helper.validate_firmware(output / "epass_bmc.bin")
    helper.validate_firmware(output / "bootloader.bin")
    if (output / "bootloader.bin").stat().st_size > 0x8000:
        raise ValueError("ESP bootloader overlaps partition table")
    table = (output / "partition-table.bin").read_bytes().ljust(4096, b"\xff")
    slots, (ota_offset, ota_size) = helper.parse_layout(table)
    spl_partitions = []
    for position in range(0, len(table), 32):
        magic, kind, subtype, offset, size = struct.unpack_from("<HBBII", table, position)
        if magic != 0x50AA:
            break
        if kind == 1 and subtype == 0x40:
            spl_partitions.append((offset, size))
    if spl_partitions != [(0x320000, 0x80000)]:
        raise ValueError("BMC SPL binary partition layout changed")
    if (output / "epass_bmc.bin").stat().st_size > min(size for _, size in slots.values()):
        raise ValueError("BMC application exceeds an OTA slot")
    if (output / "ota_data_initial.bin").stat().st_size != ota_size:
        raise ValueError("Initial OTA metadata has unexpected size")
    packer = load_module("bmc_pack_spl", source / "tools/pack_spl.py")
    packed_spl = packer.pack_spls([(images / "sunxi-spl.bin").read_bytes()])
    (output / "d1s_spl.bin").write_bytes(packed_spl)
    layout = json.loads((build_dir / "flasher_args.json").read_text())
    built_files = {built: name for name, built in files.items()}
    flash_files = {address: built_files[path] for address, path in layout["flash_files"].items()}
    expected_layout = {0: "bootloader.bin", 0x8000: "partition-table.bin",
                       ota_offset: "ota_data_initial.bin", slots[0][0]: "epass_bmc.bin"}
    if {int(address, 0): name for address, name in flash_files.items()} != expected_layout:
        raise ValueError("ESP flasher_args.json does not match partition layout")
    # This partition is part of the board contract; reject layout drift before publishing it.
    partition_lines = (source / "partitions.csv").read_text().splitlines()
    spl = next([field.strip() for field in line.split(",")] for line in partition_lines
               if line.strip().startswith("d1s_spl,"))
    if int(spl[3], 0) != 0x320000 or int(spl[4], 0) != len(packed_spl):
        raise ValueError("BMC SPL partition layout changed")
    flash_files["0x320000"] = "d1s_spl.bin"
    initial = {"chip": "esp32c3", "initial_install_only": True,
               "flash_files": flash_files, "write_flash_args": layout["write_flash_args"]}
    (output / "flash_args.json").write_text(json.dumps(initial, indent=2) + "\n")
    artifacts = {}
    for name in [*files, "d1s_spl.bin", "flash_args.json"]:
        path = output / name
        artifacts[name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    manifest = {"schema_version": 1, "chip": "esp32c3", "idf_version": "6.0.2",
                "version": project_version(revision), "source_lock_sha256": source_hash,
                "source_revision": revision, "source_url": args.source_url,
                "sdk_lock_sha256": digest(args.sdk_lock),
                "sdkconfig_sha256": digest(build_dir / "sdkconfig"),
                "ota_target": "bmc", "wire_target": 7, "ota_file": "epass_bmc.bin",
                "requires_explicit_selection": True, "artifacts": artifacts}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"BMC images: {output}, app {artifacts['epass_bmc.bin']['bytes']} bytes")


def install(args):
    images = args.images.resolve()
    images.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".esp-stage-", dir=images) as directory:
        staging = Path(directory)
        prepare_install(args, staging)
        output = images / "esp"
        output.mkdir(exist_ok=True)
        # Publish metadata last so interrupted copies cannot validate as a complete new release.
        for path in sorted(staging.iterdir(), key=lambda path: path.name == "manifest.json"):
            path.replace(output / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile = commands.add_parser("build")
    compile.add_argument("--source", type=Path, required=True)
    compile.add_argument("--sdk", type=Path, required=True)
    compile.add_argument("--cmake", required=True)
    compile.add_argument("--ninja", required=True)
    compile.add_argument("--jobs", type=int, default=1)
    output = commands.add_parser("install")
    output.add_argument("--source", type=Path, required=True)
    output.add_argument("--images", type=Path, required=True)
    output.add_argument("--sdk-lock", type=Path, required=True)
    for command in (compile, output):
        command.add_argument("--source-lock", type=Path)
        command.add_argument("--revision", type=validate_revision, required=True)
        command.add_argument("--source-url", required=True)
    args = parser.parse_args()
    (build if args.command == "build" else install)(args)


if __name__ == "__main__":
    main()
