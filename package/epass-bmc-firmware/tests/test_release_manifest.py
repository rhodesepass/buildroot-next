import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PACKAGE = Path(__file__).resolve().parents[1]
BUILDROOT = PACKAGE.parents[1]
SCRIPT = BUILDROOT / "board/rhodesisland/epass-next/scripts/release-manifest.py"
SPEC = importlib.util.spec_from_file_location("epass_release_manifest", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
ENABLED = "BR2_PACKAGE_EPASS_BMC_FIRMWARE=y\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.images = Path(self.temporary.name)
        self.esp = self.images / "esp"
        self.esp.mkdir()
        for name in ("sunxi-spl.bin", "u-boot.itb", "boot.itb", "rootfs.ubi"):
            (self.images / name).write_bytes(name.encode())
        artifacts = {}
        for name in ("epass_bmc.bin", "bootloader.bin", "partition-table.bin", "ota_data_initial.bin",
                     "d1s_spl.bin", "flash_args.json"):
            data = ("fixture " + name).encode()
            (self.esp / name).write_bytes(data)
            artifacts[name] = {"bytes": len(data), "sha256": digest(data)}
        self.manifest = {
            "schema_version": 1, "chip": "esp32c3", "idf_version": "6.0.2",
            "source_lock_sha256": None,
            "sdk_lock_sha256": digest((PACKAGE.parent / "esp-idf/esp-idf.hash").read_bytes()),
            "ota_target": "bmc", "wire_target": 7, "ota_file": "epass_bmc.bin",
            "requires_explicit_selection": True, "artifacts": artifacts,
            **release.bmc_source(PACKAGE),
        }
        self.write_manifest()

    def write_manifest(self):
        (self.esp / "manifest.json").write_text(json.dumps(self.manifest))

    def test_disabled_ignores_even_stale_esp_artifacts(self):
        (self.esp / "manifest.json").write_text("invalid stale manifest")
        for config in ("", "# BR2_PACKAGE_EPASS_BMC_FIRMWARE is not set\n",
                       "BR2_PACKAGE_EPASS_BMC_FIRMWARE=n\n"):
            with self.subTest(config=config):
                result = release.generate(self.images, config)
                self.assertNotIn("esp_firmware", result)
                self.assertNotIn("bmc", result["optional_ota_targets"])
                self.assertFalse(any(name.startswith("esp/") for name in result["artifacts"]))
                self.assertEqual(result["default_ota_targets"], ["boot", "rootfs"])

    def test_enabled_includes_verified_esp_as_optional_only(self):
        result = release.generate(self.images, ENABLED)
        self.assertEqual(result["default_ota_targets"], ["boot", "rootfs"])
        self.assertEqual(result["optional_ota_targets"], ["uboot", "bmc"])
        self.assertEqual(result["esp_firmware"], self.manifest)
        for name, artifact in self.manifest["artifacts"].items():
            expected = dict(artifact, requires_explicit_selection=True,
                            ota_target="bmc" if name == "epass_bmc.bin" else None)
            self.assertEqual(result["artifacts"]["esp/" + name], expected)
        self.assertNotIn("bmc", result["default_ota_targets"])
        self.assertEqual(result["artifacts"]["boot.itb"]["ota_target"], "boot")

    def test_same_size_corruption_rejected_for_each_esp_artifact(self):
        for name in self.manifest["artifacts"]:
            with self.subTest(name=name):
                path = self.esp / name
                original = path.read_bytes()
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                try:
                    with self.assertRaisesRegex(ValueError, "stale ESP artifact"):
                        release.generate(self.images, ENABLED)
                finally:
                    path.write_bytes(original)

    def test_changed_size_rejected(self):
        with (self.esp / "epass_bmc.bin").open("ab") as stream:
            stream.write(b"extra")
        with self.assertRaisesRegex(ValueError, "stale ESP artifact"):
            release.generate(self.images, ENABLED)

    def test_stale_sdk_lock_rejected(self):
        for key in ("sdk_lock_sha256",):
            original = self.manifest[key]
            with self.subTest(key=key):
                self.manifest[key] = "0" * 64
                self.write_manifest()
                try:
                    with self.assertRaisesRegex(ValueError, "stale or incompatible ESP"):
                        release.generate(self.images, ENABLED)
                finally:
                    self.manifest[key] = original
                    self.write_manifest()

    def test_stale_git_provenance_rejected(self):
        for key, value in (("source_revision", "0" * 40), ("source_url", "ssh://wrong/repo.git"),
                           ("version", "br-stale")):
            original = self.manifest[key]
            with self.subTest(key=key):
                self.manifest[key] = value
                self.write_manifest()
                with self.assertRaisesRegex(ValueError, "ESP Git provenance"):
                    release.generate(self.images, ENABLED)
                self.manifest[key] = original
                self.write_manifest()

    def test_wrong_ota_identity_rejected(self):
        for key, value in (("ota_target", "touch"), ("wire_target", 6), ("ota_file", "bootloader.bin")):
            original = self.manifest[key]
            with self.subTest(key=key):
                self.manifest[key] = value
                self.write_manifest()
                try:
                    with self.assertRaisesRegex(ValueError, "stale or incompatible ESP"):
                        release.generate(self.images, ENABLED)
                finally:
                    self.manifest[key] = original
                    self.write_manifest()

    def test_escaping_artifact_path_rejected(self):
        self.manifest["artifacts"]["../outside.bin"] = {"bytes": 1, "sha256": "0" * 64}
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "artifact"):
            release.generate(self.images, ENABLED)

    def test_missing_artifact_file_rejected(self):
        (self.esp / "epass_bmc.bin").unlink()
        with self.assertRaises((ValueError, OSError)):
            release.generate(self.images, ENABLED)

    def test_missing_app_entry_rejected(self):
        del self.manifest["artifacts"]["epass_bmc.bin"]
        self.write_manifest()
        with self.assertRaises(ValueError):
            release.generate(self.images, ENABLED)


if __name__ == "__main__":
    unittest.main()
