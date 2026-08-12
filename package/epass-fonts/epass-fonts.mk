################################################################################
#
# epass-fonts
#
# 系统共享字体。母本 (全量思源/FontAwesome/Bebas) 来自独立仓 epass-fonts,
# 在 host 侧按 Kconfig 指定的字表子集化后装到 /usr/share/fonts/epass。
#
################################################################################

EPASS_FONTS_VERSION = 1.0

EPASS_FONTS_VERSION = 6a1555c339de0d9fdefd9325f740d47b3500b421
EPASS_FONTS_SITE = https://github.com/rhodesepass/epass-fonts.git
EPASS_FONTS_SITE_METHOD = git
EPASS_FONTS_INSTALL_STAGING = YES

# host 侧子集化用 buildroot 自己的 python3 + fonttools (见 host-python-fonttools 包)
EPASS_FONTS_DEPENDENCIES = host-python-fonttools

# 设备上的共享字体目录 (对外契约)。
# 注意: 变量名不能叫 EPASS_FONTS_DIR —— 那是 pkg 基础设施的保留名 (= 构建目录),
EPASS_FONTS_FONTSDIR = /usr/share/fonts/epass

# 子集字表 (Kconfig 配置, 类似 busybox 的 config fragment)。相对路径按 buildroot 顶层解析。
EPASS_FONTS_CHARSET_FILES = $(call qstrip,$(BR2_PACKAGE_EPASS_FONTS_CHARSET_FILES))
EPASS_FONTS_ICONS_FILE = $(call qstrip,$(BR2_PACKAGE_EPASS_FONTS_ICONS_FILE))
EPASS_FONTS_CHARSET_ABS = $(foreach f,$(EPASS_FONTS_CHARSET_FILES),\
	$(if $(filter /%,$(f)),$(f),$(TOPDIR)/$(f)))
EPASS_FONTS_ICONS_ABS = $(if $(EPASS_FONTS_ICONS_FILE),\
	$(if $(filter /%,$(EPASS_FONTS_ICONS_FILE)),$(EPASS_FONTS_ICONS_FILE),$(TOPDIR)/$(EPASS_FONTS_ICONS_FILE)))

define EPASS_FONTS_BUILD_CMDS
	$(HOST_DIR)/bin/python3 $(@D)/subset_fonts.py \
		--out $(@D)/out \
		--roles $(@D)/roles.conf \
		--charset $(EPASS_FONTS_CHARSET_ABS) \
		$(if $(EPASS_FONTS_ICONS_ABS),--icons $(EPASS_FONTS_ICONS_ABS))
endef

# staging: 生成并装 pkg-config, 供消费程序构建期取路径
define EPASS_FONTS_INSTALL_STAGING_CMDS
	$(@D)/gen_consumers.sh pc $(EPASS_FONTS_FONTSDIR) $(@D)/roles.conf > $(@D)/epass-fonts.pc
	$(INSTALL) -D -m 0644 $(@D)/epass-fonts.pc \
		$(STAGING_DIR)/usr/lib/pkgconfig/epass-fonts.pc
endef

# target: 装子集字体 + 运行期解析脚本 epass-font
define EPASS_FONTS_INSTALL_TARGET_CMDS
	$(INSTALL) -d $(TARGET_DIR)$(EPASS_FONTS_FONTSDIR)
	$(INSTALL) -m 0644 $(@D)/out/*.otf $(TARGET_DIR)$(EPASS_FONTS_FONTSDIR)/
	$(@D)/gen_consumers.sh sh $(EPASS_FONTS_FONTSDIR) $(@D)/roles.conf > $(@D)/epass-font
	$(INSTALL) -D -m 0755 $(@D)/epass-font $(TARGET_DIR)/usr/bin/epass-font
endef

$(eval $(generic-package))
