import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PACKAGE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("epass_bmc_build", PACKAGE / "build.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def firmware():
    header = bytearray(24)
    header[:2] = b"\xe9\x01"
    struct.pack_into("<H", header, 12, 5)
    return header + struct.pack("<II", 0x3C000000, 256) + bytes(271) + b"\xef"


def partition(kind, subtype, offset, size, name):
    return struct.pack("<HBBII16sI", 0x50AA, kind, subtype, offset, size, name.encode(), 0)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.images = self.root / "images"
        self.images.mkdir()
        self.sdk = self.root / "host/opt/esp-idf"
        self.sdk_lock = self.root / "sdk.hash"
        self.sdk_lock.write_text("locked SDK fixture\n")
        self.source_lock = self.root / "SOURCES.sha256"
        self.revision = "2651d5f4e3ef6c5a280bd61aef080b58c0e4d1b8"
        self.source_url = "git@github.com:rhodesepass/bmc_fw.git"
        for name, data in {
            "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\n",
            "sdkconfig": "CONFIG_IDF_TARGET=\"esp32c3\"\n",
            "sdkconfig.defaults": "CONFIG_IDF_TARGET=\"esp32c3\"\n",
            "main/CMakeLists.txt": "idf_component_register(SRCS main.c)\n",
            "main/main.c": "void app_main(void) {}\n",
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        (self.source / "tools").mkdir()
        (self.source / "tools/pack_spl.py").write_text(
            "def pack_spls(images):\n"
            "    data = images[0]\n"
            "    if data[4:12] != b'eGON.BT0':\n"
            "        raise ValueError('invalid SPL fixture')\n"
            "    return data.ljust(0x20000, b'\\xff') * 2 + b'\\xff' * 0x40000\n"
        )
        (self.source / "partitions.csv").write_text("d1s_spl,data,0x40,0x320000,0x80000,\n")
        self.lock_source()
        self.work = self.source / "build"
        (self.work / "bootloader").mkdir(parents=True)
        (self.work / "partition_table").mkdir()
        (self.work / "epass_bmc.bin").write_bytes(firmware())
        (self.work / "bootloader/bootloader.bin").write_bytes(firmware())
        table = b"".join([
            partition(1, 2, 0x9000, 0x6000, "nvs"),
            partition(1, 0, 0xF000, 0x2000, "otadata"),
            partition(1, 1, 0x11000, 0x1000, "phy_init"),
            partition(0, 0x10, 0x20000, 0x180000, "ota_0"),
            partition(0, 0x11, 0x1A0000, 0x180000, "ota_1"),
            partition(1, 0x40, 0x320000, 0x80000, "d1s_spl"),
            partition(1, 0x82, 0x3A0000, 0x60000, "storage"),
        ]).ljust(3072, b"\xff")
        (self.work / "partition_table/partition-table.bin").write_bytes(table)
        (self.work / "ota_data_initial.bin").write_bytes(b"\xff" * 8192)
        shutil.copyfile(self.source / "sdkconfig", self.work / "sdkconfig")
        self.layout = {
            "flash_files": {"0x0": "bootloader/bootloader.bin", "0x8000": "partition_table/partition-table.bin",
                            "0xf000": "ota_data_initial.bin", "0x20000": "epass_bmc.bin"},
            "write_flash_args": ["--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "4MB"],
        }
        self.write_layout()
        spl = bytearray(1024)
        spl[4:12] = b"eGON.BT0"
        struct.pack_into("<II", spl, 12, 0x5F0A6C39, len(spl))
        checksum = sum(struct.unpack("<256I", spl)) & 0xFFFFFFFF
        struct.pack_into("<I", spl, 12, checksum)
        (self.images / "sunxi-spl.bin").write_bytes(spl)
        self.args = SimpleNamespace(source=self.source, images=self.images, sdk=self.sdk,
                                    sdk_lock=self.sdk_lock, cmake="/private/bin/cmake",
                                    ninja="/private/bin/ninja", jobs=3,
                                    source_lock=self.source_lock, revision=self.revision,
                                    source_url=self.source_url)

    def lock_source(self):
        entries = []
        for path in sorted(self.source.rglob("*")):
            if path.is_file() and "build" not in path.relative_to(self.source).parts:
                entries.append(f"{sha(path.read_bytes())}  {path.relative_to(self.source)}\n")
        self.source_lock.write_text("".join(entries))

    def write_layout(self):
        (self.work / "flasher_args.json").write_text(json.dumps(self.layout))

    def test_source_lock_valid_and_build_outputs_excluded(self):
        self.assertEqual(builder.check_source(self.source, self.source_lock), sha(self.source_lock.read_bytes()))

    def test_git_tree_assets_are_locked_and_generated_metadata_excluded(self):
        for name in ("README.md", "docs/interfaces.md", "tests/test_client.py", "main/fel_spl.bin",
                     "web/vendor/LICENSE-xterm", "web/vendor/xterm.js", ".gitignore"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"locked source asset\x00\n")
        self.lock_source()
        for name in (".git/HEAD", ".applied_patches_list", ".stamp_patched",
                     ".files-list.before", "tools/__pycache__/pack_spl.pyc"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"generated metadata")
        self.assertEqual(builder.check_source(self.source, self.source_lock), sha(self.source_lock.read_bytes()))
        (self.source / "web/vendor/xterm.js").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            builder.check_source(self.source, self.source_lock)

    def test_old_embedded_source_lock_is_not_implicitly_trusted(self):
        (self.source / "SOURCES.sha256").write_text("obsolete embedded lock\n")
        with self.assertRaisesRegex(ValueError, "Unlisted"):
            builder.check_source(self.source, self.source_lock)

    def test_locked_symlink_cannot_reference_external_files(self):
        external = self.root / "external.c"
        external.write_text("external source\n")
        (self.source / "main/external.c").symlink_to(external)
        self.lock_source()
        with self.assertRaisesRegex(ValueError, "leaves the source tree"):
            builder.check_source(self.source, self.source_lock)

    def test_revision_requires_full_git_commit_before_build_or_install(self):
        for revision in ("main", "2651d5f4e3ef", "g" * 40, "a" * 41):
            self.args.revision = revision
            with self.subTest(revision=revision), patch.object(builder.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "40-character"):
                    builder.build(self.args)
                with self.assertRaisesRegex(ValueError, "40-character"):
                    builder.install(self.args)
                run.assert_not_called()
                self.assertFalse((self.images / "esp/manifest.json").exists())

    def test_cli_passes_external_source_identity_to_both_actions(self):
        for action, extra in (("build", ["--sdk", str(self.sdk), "--cmake", "cmake", "--ninja", "ninja"]),
                              ("install", ["--images", str(self.images), "--sdk-lock", str(self.sdk_lock)])):
            argv = ["build.py", action, "--source", str(self.source),
                    "--source-lock", str(self.source_lock), "--revision", self.revision.upper(),
                    "--source-url", self.source_url, *extra]
            with self.subTest(action=action), patch("sys.argv", argv), patch.object(builder, action) as call:
                builder.main()
            args = call.call_args.args[0]
            self.assertEqual(args.source_lock, self.source_lock)
            self.assertEqual(args.revision, self.revision)
            self.assertEqual(args.source_url, self.source_url)

    def test_changed_source_rejected_before_compiler(self):
        (self.source / "main/main.c").write_text("void changed(void) {}\n")
        with patch.object(builder.subprocess, "run") as run, self.assertRaises(ValueError):
            builder.build(self.args)
        run.assert_not_called()

    def test_branch_build_and_install_accept_unlocked_source_changes(self):
        self.args.revision = "origin/master"
        self.args.source_lock = None
        (self.source / "main/main.c").write_text("void changed(void) {}\n")
        with patch.object(builder.subprocess, "run") as run:
            builder.build(self.args)
        self.assertIn("-DPROJECT_VER=br-master", run.call_args_list[0].args[0])
        builder.install(self.args)
        manifest = json.loads((self.images / "esp/manifest.json").read_text())
        self.assertEqual(manifest["source_revision"], "origin/master")
        self.assertIsNone(manifest["source_lock_sha256"])

    def test_unlisted_build_inputs_are_rejected(self):
        for name in ("main/new.c", "main/new.S", "main/extra.cmake", "main/Kconfig.projbuild", "extra.cmake"):
            with self.subTest(name=name):
                path = self.source / name
                path.write_text("unlisted build input\n")
                try:
                    with self.assertRaisesRegex(ValueError, "Unlisted"):
                        builder.check_source(self.source, self.source_lock)
                finally:
                    path.unlink()

    def test_invalid_lock_paths_and_duplicates_rejected(self):
        lock = self.source_lock
        original = lock.read_text()
        digest = sha((self.source / "main/main.c").read_bytes())
        for extra in (f"{digest}  ../outside.c\n", f"{digest}  /tmp/outside.c\n", original.splitlines()[0] + "\n"):
            with self.subTest(extra=extra):
                lock.write_text(original + extra)
                with self.assertRaises(ValueError):
                    builder.check_source(self.source, self.source_lock)
        lock.write_text("")
        with self.assertRaisesRegex(ValueError, "Empty"):
            builder.check_source(self.source, self.source_lock)

    def test_environment_uses_private_sdk_and_removes_host_overrides(self):
        keys = ("IDF_PATH", "IDF_TOOLS_PATH", "IDF_PYTHON_ENV_PATH", "ESP_IDF_VERSION", "PYTHONPATH",
                "PYTHONHOME", "PIP_INDEX_URL", "VIRTUAL_ENV", "CC", "CXX", "CPP", "AR", "AS", "LD",
                "CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS", "CROSS_COMPILE", "CMAKE_TOOLCHAIN_FILE",
                "CMAKE_PREFIX_PATH", "CMAKE_MODULE_PATH", "CMAKE_GENERATOR", "PKG_CONFIG_PATH",
                "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "COMPILER_PATH",
                "GCC_EXEC_PREFIX", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR")
        contaminated = {key: "/user/custom" for key in keys}
        contaminated.update(PATH="/user/idf/bin:/user/venv/bin", HOME="/user/home", SOURCE_DATE_EPOCH="1")
        with patch.dict(os.environ, contaminated, clear=True):
            env = builder.build_environment(self.sdk)
        self.assertEqual(env["IDF_PATH"], str(self.sdk / "sdk"))
        self.assertEqual(env["IDF_TOOLS_PATH"], str(self.sdk / "tools"))
        self.assertEqual(env["IDF_PYTHON_ENV_PATH"], str(self.sdk / "venv"))
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["IDF_COMPONENT_MANAGER"], "0")
        self.assertEqual(env["IDF_TARGET"], "esp32c3")
        self.assertNotEqual(env["SOURCE_DATE_EPOCH"], "1")
        self.assertNotIn("/user", env["PATH"])
        self.assertEqual(env["PATH"].split(os.pathsep)[:3], [str(self.sdk / "venv/bin"), str(self.sdk / "toolchain/bin"), str(self.sdk.parents[1] / "bin")])
        for key in keys:
            if key not in ("IDF_PATH", "IDF_TOOLS_PATH", "IDF_PYTHON_ENV_PATH"):
                self.assertNotIn(key, env)

    def test_build_invokes_only_private_sdk_and_preserves_source_config(self):
        original = (self.source / "sdkconfig").read_bytes()
        with patch.dict(os.environ, {"IDF_PATH": "/user/idf", "PATH": "/user/bin"}), \
                patch.object(builder.subprocess, "run") as run:
            builder.build(self.args)
        self.assertEqual(run.call_count, 2)
        configure, compile = run.call_args_list
        command = configure.args[0]
        self.assertEqual(command[0], self.args.cmake)
        self.assertIn(f"-DPYTHON={self.sdk / 'venv/bin/python'}", command)
        self.assertIn(f"-DCMAKE_MAKE_PROGRAM={self.args.ninja}", command)
        self.assertIn(f"-DSDKCONFIG={self.work / 'sdkconfig'}", command)
        self.assertIn("-DIDF_TARGET=esp32c3", command)
        self.assertIn("-DPROJECT_VER=br-" + self.revision[:12], command)
        self.assertEqual(compile.args[0], [self.args.cmake, "--build", str(self.work), "--parallel", "3"])
        for call in run.call_args_list:
            self.assertTrue(call.kwargs["check"])
            self.assertEqual(call.kwargs["env"]["IDF_PATH"], str(self.sdk / "sdk"))
            self.assertNotIn("/user", call.kwargs["env"]["PATH"])
        self.assertEqual((self.source / "sdkconfig").read_bytes(), original)

    def test_failed_configure_does_not_build(self):
        with patch.object(builder.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "cmake")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                builder.build(self.args)
        self.assertEqual(run.call_count, 1)

    def test_install_manifest_hashes_and_initial_flash_layout(self):
        builder.install(self.args)
        output = self.images / "esp"
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["chip"], "esp32c3")
        self.assertEqual(manifest["source_lock_sha256"], sha(self.source_lock.read_bytes()))
        self.assertEqual(manifest["source_revision"], self.revision)
        self.assertEqual(manifest["source_url"], self.source_url)
        self.assertEqual(manifest["sdk_lock_sha256"], sha(self.sdk_lock.read_bytes()))
        self.assertEqual(manifest["sdkconfig_sha256"], sha((self.work / "sdkconfig").read_bytes()))
        self.assertEqual(manifest["version"], "br-" + self.revision[:12])
        self.assertEqual((manifest["ota_target"], manifest["wire_target"], manifest["ota_file"]), ("bmc", 7, "epass_bmc.bin"))
        self.assertTrue(manifest["requires_explicit_selection"])
        expected = {"epass_bmc.bin", "bootloader.bin", "partition-table.bin", "ota_data_initial.bin", "d1s_spl.bin", "flash_args.json"}
        self.assertEqual(set(manifest["artifacts"]), expected)
        for name, entry in manifest["artifacts"].items():
            data = (output / name).read_bytes()
            self.assertEqual(entry, {"bytes": len(data), "sha256": sha(data)})
        layout = json.loads((output / "flash_args.json").read_text())
        self.assertTrue(layout["initial_install_only"])
        self.assertEqual(layout["chip"], "esp32c3")
        self.assertEqual({int(address, 0): name for address, name in layout["flash_files"].items()},
                         {0: "bootloader.bin", 0x8000: "partition-table.bin", 0xF000: "ota_data_initial.bin",
                          0x20000: "epass_bmc.bin", 0x320000: "d1s_spl.bin"})
        self.assertEqual(layout["write_flash_args"], self.layout["write_flash_args"])
        spl = (self.images / "sunxi-spl.bin").read_bytes()
        packed = (output / "d1s_spl.bin").read_bytes()
        self.assertEqual(len(packed), 0x80000)
        self.assertEqual(packed[:len(spl)], spl)
        self.assertEqual(packed[0x20000:0x20000 + len(spl)], spl)
        self.assertEqual(packed[0x40000:], b"\xff" * 0x40000)

    def test_invalid_app_and_bootloader_rejected(self):
        for name in ("epass_bmc.bin", "bootloader/bootloader.bin"):
            path = self.work / name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(b"not an ESP firmware")
                with self.assertRaises(ValueError):
                    builder.install(self.args)
                self.assertFalse((self.images / "esp/manifest.json").exists())
                path.write_bytes(original)

    def test_oversized_bootloader_rejected(self):
        (self.work / "bootloader/bootloader.bin").write_bytes(firmware().ljust(0x8001, b"\xff"))
        with self.assertRaises(ValueError):
            builder.install(self.args)

    def test_app_larger_than_ota_slot_rejected(self):
        (self.work / "epass_bmc.bin").write_bytes(firmware().ljust(0x180001, b"\xff"))
        with self.assertRaisesRegex(ValueError, "OTA slot"):
            builder.install(self.args)

    def test_initial_metadata_size_checked(self):
        (self.work / "ota_data_initial.bin").write_bytes(b"\xff" * 4096)
        with self.assertRaisesRegex(ValueError, "metadata"):
            builder.install(self.args)

    def test_wrong_flash_addresses_or_missing_targets_rejected(self):
        original = dict(self.layout["flash_files"])
        for address, replacement in (("0x20000", "0x9000"), ("0x0", "0x1000"), ("0xf000", None)):
            with self.subTest(address=address, replacement=replacement):
                mapping = dict(original)
                name = mapping.pop(address)
                if replacement:
                    mapping[replacement] = name
                self.layout["flash_files"] = mapping
                self.write_layout()
                with self.assertRaises(ValueError):
                    builder.install(self.args)

    def test_invalid_spl_rejected(self):
        (self.images / "sunxi-spl.bin").write_bytes(b"not a sunxi SPL")
        with self.assertRaises(ValueError):
            builder.install(self.args)

    def test_binary_spl_partition_must_match_exported_address(self):
        path = self.work / "partition_table/partition-table.bin"
        table = bytearray(path.read_bytes())
        struct.pack_into("<II", table, 5 * 32 + 4, 0x330000, 0x70000)
        path.write_bytes(table)
        with self.assertRaisesRegex(ValueError, "SPL|spl"):
            builder.install(self.args)

    def test_missing_build_product_does_not_publish(self):
        (self.work / "bootloader/bootloader.bin").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            builder.install(self.args)
        self.assertFalse((self.images / "esp/manifest.json").exists())

    def test_failed_install_keeps_previously_published_artifacts(self):
        builder.install(self.args)
        output = self.images / "esp"
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        (self.work / "epass_bmc.bin").write_bytes(b"invalid replacement")
        with self.assertRaises(ValueError):
            builder.install(self.args)
        self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, original)


if __name__ == "__main__":
    unittest.main()
