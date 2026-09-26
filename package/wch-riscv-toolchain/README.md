# Pinned WCH bare-metal toolchain

This host-only package installs the GCC12 subdirectory from the official
MounRiver Studio Toolchain Linux x64 V2.4.0 archive into
`HOST_DIR/opt/wch-riscv-toolchain`. It does not use the MounRiver IDE installation
or the Linux target compiler. The prefix is `bin/riscv-wch-elf-`.

Upstream provenance, verified 2026-09-20:

- Official download page: https://www.mounriver.com/download
- Public catalog: https://api.mounriver.com/mountriver/api/version/fetchRecentOpenOcd?osType=LINUX&lang=en
- Catalog resource ID: `2030114123741700098`; release date: 2026-03-07.
- Archive: `MRS_Toolchain_Linux_X64_V240.tar.xz`, 411269512 bytes.
- Included GCC: 12.2.0, `version.txt`: `v1.4`.
- The entire GCC12 directory matched the previously validated MRS2 toolchain
  byte-for-byte in a recursive comparison.

The CDN requires a short-lived signed URL. `download.py` requests a new URL for
the fixed resource ID, restricts it to the expected official host and filename,
and verifies the pinned SHA256 before placing the archive in Buildroot's download
cache. Cached archives are checked without network access. For offline builds,
preseed `BR2_DL_DIR/wch-riscv-toolchain/` with this exact archive. The helper uses
the build machine's Python 3 standard library; no pip packages are required.

Only `Toolchain/RISC-V Embedded GCC12` is extracted. ARM, older RISC-V compilers
and OpenOCD from the archive are not installed. All included license notices
remain under `distro-info/licenses/`; the hash file additionally pins the GCC,
GCC runtime exception and newlib license texts. The host package does not add
any toolchain files to the target root filesystem.
