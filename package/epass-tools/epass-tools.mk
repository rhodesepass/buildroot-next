################################################################################
#
# epass-tools
#
################################################################################

EPASS_TOOLS_VERSION = 1.0
EPASS_TOOLS_SITE = $(TOPDIR)/board/rhodesisland/epass-next/src
EPASS_TOOLS_SITE_METHOD = local
EPASS_TOOLS_LICENSE = proprietary

EPASS_TOOLS_PROBES = cedrus-probe rot-probe vectest

define EPASS_TOOLS_BUILD_CMDS
	$(foreach probe,$(EPASS_TOOLS_PROBES), \
		$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) \
			$(@D)/$(probe).c -o $(@D)/$(probe)$(sep))
endef

define EPASS_TOOLS_INSTALL_TARGET_CMDS
	$(foreach probe,$(EPASS_TOOLS_PROBES), \
		$(INSTALL) -D -m 0755 $(@D)/$(probe) \
			$(TARGET_DIR)/usr/bin/$(probe)$(sep))
endef

$(eval $(generic-package))
