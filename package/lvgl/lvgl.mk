################################################################################
#
# lvgl
#
################################################################################

LVGL_VERSION = 9.5.0
LVGL_SITE = $(call github,lvgl,lvgl,v$(LVGL_VERSION))
LVGL_LICENSE = MIT
LVGL_LICENSE_FILES = LICENCE.txt
LVGL_INSTALL_STAGING = YES

# LV_USE_FREETYPE / LV_USE_LIBPNG / LV_USE_LIBJPEG_TURBO 都在本包的 lv_conf.h 里开着。
LVGL_DEPENDENCIES = freetype libpng jpeg

# lv_conf.h 是编译期配置, 决定结构体布局。共享库和所有消费者必须用同一份, 所以由本包
# 提供权威 lv_conf.h: configure 前拷进源码根, 既供编库, 又经 LV_BUILD_CONF_DIR 分支
# 被 LVGL 装到 <staging>/usr/include/lvgl/lv_conf.h 供 app 编译时取用。
define LVGL_INSTALL_CONF
	$(INSTALL) -D -m 0644 $(LVGL_PKGDIR)/lv_conf.h $(@D)/lv_conf.h
endef
LVGL_PRE_CONFIGURE_HOOKS += LVGL_INSTALL_CONF

# LVGL 的 libjpeg-turbo 后端 (lv_libjpeg_turbo.c) 要读 EXIF 方向, 用了 marker reader
# 内部 API, 需要私有头 jpegint.h —— jpeg-turbo 默认不装它。只有 lvgl 库自身编译要它
# (公共头不引用), 从 jpeg-turbo 源码补装到 staging 即可。
# 3.x 把源码挪进了 src/, 2.x 还在根目录; wildcard 在 hook 执行时才求值, 那时
# jpeg-turbo 已经解压过 (它在 LVGL_DEPENDENCIES 里)。
define LVGL_STAGE_JPEGINT
	$(INSTALL) -D -m 0644 \
		$(firstword $(wildcard $(JPEG_TURBO_DIR)/src/jpegint.h \
				       $(JPEG_TURBO_DIR)/jpegint.h)) \
		$(STAGING_DIR)/usr/include/jpegint.h
endef
LVGL_PRE_CONFIGURE_HOOKS += LVGL_STAGE_JPEGINT

LVGL_CONF_OPTS = \
	-DBUILD_SHARED_LIBS=ON \
	-DCONFIG_LV_BUILD_EXAMPLES=OFF \
	-DCONFIG_LV_BUILD_DEMOS=OFF \
	-DCONFIG_LV_USE_THORVG_INTERNAL=OFF \
	-DCONFIG_LV_USE_PRIVATE_API=ON \
	-DLV_BUILD_CONF_DIR=$(@D)

$(eval $(cmake-package))
