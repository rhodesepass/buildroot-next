################################################################################
#
# ch32-touch-firmware
#
################################################################################

CH32_TOUCH_FIRMWARE_VERSION = origin/master
CH32_TOUCH_FIRMWARE_SITE = ssh://git@github.com/rhodesepass/tp_fw.git
CH32_TOUCH_FIRMWARE_SITE_METHOD = git
CH32_TOUCH_FIRMWARE_LICENSE = WCH (SDK), Proprietary (touch library and application)
CH32_TOUCH_FIRMWARE_LICENSE_FILES = LICENSES.md
CH32_TOUCH_FIRMWARE_REDISTRIBUTE = NO
CH32_TOUCH_FIRMWARE_DEPENDENCIES = host-wch-riscv-toolchain host-python3
CH32_TOUCH_FIRMWARE_INSTALL_TARGET = NO
CH32_TOUCH_FIRMWARE_INSTALL_IMAGES = YES

define CH32_TOUCH_FIRMWARE_BUILD_CMDS
	$(HOST_DIR)/bin/python3 $(CH32_TOUCH_FIRMWARE_PKGDIR)/manifest.py check \
		--source $(@D) \
		--driver $(TOPDIR)/board/rhodesisland/epass-next/src/touch_protocol.h
	$(HOST_MAKE_ENV) $(MAKE) -C $(@D) O=$(@D)/build \
		CROSS_COMPILE=$(HOST_DIR)/opt/wch-riscv-toolchain/bin/riscv-wch-elf-
endef

define CH32_TOUCH_FIRMWARE_INSTALL_IMAGES_CMDS
	$(INSTALL) -D -m 0644 $(@D)/build/firmware.bin $(BINARIES_DIR)/ch32-touch.bin
	$(INSTALL) -D -m 0644 $(@D)/build/firmware.elf $(BINARIES_DIR)/ch32-touch.elf
	$(INSTALL) -D -m 0644 $(@D)/build/firmware.map $(BINARIES_DIR)/ch32-touch.map
	$(HOST_DIR)/bin/python3 $(CH32_TOUCH_FIRMWARE_PKGDIR)/manifest.py image \
		--source $(@D) \
		--source-revision $(CH32_TOUCH_FIRMWARE_DL_VERSION) \
		--source-url $(CH32_TOUCH_FIRMWARE_SITE) \
		--driver $(TOPDIR)/board/rhodesisland/epass-next/src/touch_protocol.h \
		--compiler $(HOST_DIR)/opt/wch-riscv-toolchain/bin/riscv-wch-elf-gcc \
		--toolchain-lock $(CH32_TOUCH_FIRMWARE_PKGDIR)/../wch-riscv-toolchain/wch-riscv-toolchain.hash \
		--image $(BINARIES_DIR)/ch32-touch.bin \
		--output $(BINARIES_DIR)/ch32-touch.json
endef

$(eval $(generic-package))
