################################################################################
#
# epass-bmc-firmware
#
################################################################################

EPASS_BMC_FIRMWARE_VERSION = origin/master
EPASS_BMC_FIRMWARE_SITE = ssh://git@github.com/rhodesepass/bmc_fw.git
EPASS_BMC_FIRMWARE_SITE_METHOD = git
EPASS_BMC_FIRMWARE_LICENSE = Proprietary
EPASS_BMC_FIRMWARE_REDISTRIBUTE = NO
EPASS_BMC_FIRMWARE_DEPENDENCIES = host-esp-idf uboot
EPASS_BMC_FIRMWARE_INSTALL_TARGET = NO
EPASS_BMC_FIRMWARE_INSTALL_IMAGES = YES

define EPASS_BMC_FIRMWARE_BUILD_CMDS
	$(HOST_DIR)/bin/python3 $(EPASS_BMC_FIRMWARE_PKGDIR)/build.py build \
		--source $(@D) --sdk $(HOST_DIR)/opt/esp-idf \
		--revision $(EPASS_BMC_FIRMWARE_DL_VERSION) --source-url $(EPASS_BMC_FIRMWARE_SITE) \
		--cmake $(BR2_CMAKE) --ninja $(HOST_DIR)/bin/ninja \
		--jobs $(PARALLEL_JOBS)
endef

define EPASS_BMC_FIRMWARE_INSTALL_IMAGES_CMDS
	$(HOST_DIR)/bin/python3 $(EPASS_BMC_FIRMWARE_PKGDIR)/build.py install \
		--source $(@D) --images $(BINARIES_DIR) \
		--revision $(EPASS_BMC_FIRMWARE_DL_VERSION) --source-url $(EPASS_BMC_FIRMWARE_SITE) \
		--sdk-lock $(EPASS_BMC_FIRMWARE_PKGDIR)/../esp-idf/esp-idf.hash
endef

$(eval $(generic-package))
