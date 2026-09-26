################################################################################
#
# wch-riscv-toolchain
#
################################################################################

HOST_WCH_RISCV_TOOLCHAIN_VERSION = 2.4.0
HOST_WCH_RISCV_TOOLCHAIN_SOURCE = MRS_Toolchain_Linux_X64_V240.tar.xz
HOST_WCH_RISCV_TOOLCHAIN_SITE = https://file-oss.mounriver.com/tools
HOST_WCH_RISCV_TOOLCHAIN_LICENSE = GPL-3.0+ (GCC/binutils/GDB), GPL-3.0-with-GCC-exception (runtime), BSD-like (newlib), various (bundled host libraries)
HOST_WCH_RISCV_TOOLCHAIN_LICENSE_FILES = \
	distro-info/licenses/gcc-12.2.0/COPYING3 \
	distro-info/licenses/gcc-12.2.0/COPYING.RUNTIME \
	distro-info/licenses/newlib-4.2.0.20211231/COPYING
HOST_WCH_RISCV_TOOLCHAIN_INSTALL_DIR = $(HOST_DIR)/opt/wch-riscv-toolchain

# The official CDN requires a fresh signed URL; never pin an expiring token.
define HOST_WCH_RISCV_TOOLCHAIN_FETCH_SIGNED_ARCHIVE
	$(Q)python3 $(HOST_WCH_RISCV_TOOLCHAIN_PKGDIR)/download.py \
		$(HOST_WCH_RISCV_TOOLCHAIN_DL_DIR) \
		$(HOST_WCH_RISCV_TOOLCHAIN_PKGDIR)/wch-riscv-toolchain.hash
endef
HOST_WCH_RISCV_TOOLCHAIN_PRE_DOWNLOAD_HOOKS += HOST_WCH_RISCV_TOOLCHAIN_FETCH_SIGNED_ARCHIVE

define HOST_WCH_RISCV_TOOLCHAIN_EXTRACT_CMDS
	$(XZCAT) $(HOST_WCH_RISCV_TOOLCHAIN_DL_DIR)/$(HOST_WCH_RISCV_TOOLCHAIN_SOURCE) | \
		$(TAR) --strip-components=2 -C $(@D) -xf - "Toolchain/RISC-V Embedded GCC12"
endef

define HOST_WCH_RISCV_TOOLCHAIN_INSTALL_CMDS
	test "$(HOSTARCH)" = x86_64
	mkdir -p $(HOST_WCH_RISCV_TOOLCHAIN_INSTALL_DIR)
	cp -a $(addprefix $(@D)/,bin distro-info include lib lib64 libexec \
		riscv-wch-elf share README.md version.txt) \
		$(HOST_WCH_RISCV_TOOLCHAIN_INSTALL_DIR)/
	$(HOST_WCH_RISCV_TOOLCHAIN_INSTALL_DIR)/bin/riscv-wch-elf-gcc -dumpversion | grep -qx 12.2.0
endef

$(eval $(host-generic-package))
