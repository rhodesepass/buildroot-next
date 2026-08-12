################################################################################
#
# epass_drm_app
#
################################################################################


EPASS_DRM_APP_VERSION = da86dacbb492e3df4c5e10d601cf140d8cf622a9
EPASS_DRM_APP_SITE = $(call github,rhodesepass,drm_app_neo,$(EPASS_DRM_APP_VERSION))
# epass-fonts: 提供 pkg-config 'epass-fonts', app 构建期据此取共享字体目录,
# 不再自带字体 (字体由 epass-fonts 包装到 /usr/share/fonts/epass)。
EPASS_DRM_APP_DEPENDENCIES = freetype libdrm libpng libevdev epass-fonts lvgl srgnvdec

# EPASS_PLATFORM 选 SoC 那套硬件粘合层: D1s 走 DE2 mixer 的 C8 palette 节点和
# stable 的 H.264 stateless uapi; 不传则是 f1c (DEBE palette + SDROT + 5.4 uapi),
# 那份在这块板子上既没有对应内核节点, 控制结构体布局也对不上。
EPASS_DRM_APP_CONF_OPTS = -DBUILD_SHARED_LIBS=OFF -DEPASS_PLATFORM=d1s --fresh

define EPASS_DRM_APP_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/app_360 $(TARGET_DIR)/root/app_360
	$(INSTALL) -D -m 0755 $(@D)/app_720 $(TARGET_DIR)/root/app_720
	cp -a $(@D)/res $(TARGET_DIR)/root/
endef


$(eval $(cmake-package))
