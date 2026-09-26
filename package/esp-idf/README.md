# ESP-IDF host package

This package installs an independent ESP32-C3 build environment under
`output/host/opt/esp-idf`. It never sources a user's `export.sh`, copies a user's
SDK installation, or runs a networked pip resolver during build/install.

- `sdk/`: official ESP-IDF 6.0.2 release archive, including submodules.
  Upstream tag commit: `7101770dc6db2667b3c477cc31365dd1acd6db4e`.
- `toolchain/`: official `riscv32-esp-elf`, GCC 15.2.0,
  `esp-15.2.0_20251204`; archive checksum comes from that SDK's `tools/tools.json`.
- `venv/`: Buildroot host CPython 3.14, without system site packages.
  The package selects its SSL module because `idf_tools.py` imports SSL even
  when its dependency check runs offline.
- `requirements.lock` and `python-sources.json`: installed copies of the
  complete Python dependency lock and release-file provenance.

The supported host is Linux x86_64 with glibc 2.34 or newer, as required by the
selected cryptography wheel. The binary Python wheels require CPython 3.14.
Changing Buildroot's Python minor version requires regenerating the wheel lock.

`make host-esp-idf-source` downloads the SDK, compiler and all 63 Python
distributions through Buildroot's normal download/hash/cache machinery.
After the package and its Buildroot dependencies are cached, install/build
requires no network. Downloaded files live in `dl/esp-idf`; normal `make clean`
removes the installed environment but preserves this download cache.

Python versions were taken from the working IDF 6.0.2 environment, with pip
26.1 and wheel 0.46.3 explicitly added for isolated bootstrapping. Every file URL
and SHA256 was retrieved from its version-specific PyPI JSON response, then
independently downloaded and checked. `esptool` 5.3.1 is distributed as an sdist;
the package builds it offline using the already installed, locked setuptools
81.0.0 and wheel. All remaining inputs are wheels. `--require-hashes`,
`--no-index`, `--no-deps` and `--no-build-isolation` prevent an implicit resolver
or build-backend download; `pip check` validates the installed dependency closure.

Consumers should depend on `host-esp-idf` and select
`BR2_PACKAGE_HOST_ESP_IDF`. Use `HOST_ESP_IDF_ROOT` for paths and
`HOST_ESP_IDF_ENV` for the environment. CMake may be the suitable host system
version selected by Buildroot's `BR2_CMAKE`; Ninja and Python come from the
Buildroot host tree. Managed component downloading is disabled because the BMC
uses only the pinned IDF components and its own sources.

To update the lock, select compatible release files from each package's PyPI
metadata and update `python-sources.json`, `python-downloads.mk`,
`requirements.lock`, `bootstrap.lock`, and `esp-idf.hash` together. Verify a
fresh private environment with no network and `pip check` before changing the
SDK or Python versions. The official IDF constraints use version ranges and are
not a reproducibility lock; this package does not download or resolve them.

An existing Buildroot host Python built without SSL must be rebuilt once after
enabling this package (`make host-python3-dirclean`, then the normal build).
The normal fresh-build dependency graph includes SSL automatically.
