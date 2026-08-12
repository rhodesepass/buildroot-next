################################################################################
#
# srgnvdec
#
################################################################################

# 开发期靠 local.mk 的 SRGNVDEC_OVERRIDE_SRCDIR 供源码(尚未 push)。
SRGNVDEC_VERSION = 0.1.0
SRGNVDEC_SITE = https://github.com/rhodesepass/srgnvdec.git
SRGNVDEC_SITE_METHOD = git
SRGNVDEC_LICENSE = GPL-3.0+
SRGNVDEC_LICENSE_FILES = COPYING
SRGNVDEC_INSTALL_STAGING = YES

# SRGNVDEC_UAPI 选 stateless H.264 的控制结构体布局, 只能编译期定 —— 相当于用
# #ifdef 选一套寄存器布局。D1s + 7.x 是 5.11 定型的 stable uapi; F1C200s +
# 5.4.99 那份 pre-stable 内核从未导出, 包里自带头副本(prestable)。这个值会随
# 导出的 CMake target / pkg-config 传给调用方, 两边看到的必须是同一个。
#
# SRGNVDEC_WITH_PP 是旋转后处理: F1C 走 cedrus-rotate(VE SDROT, 单镜像+90/270
# 要库内拆两趟), D1s 走 sun8i-rotate(G2D, 任意组合单趟)。D1s 也开 —— 倒装补偿
# 之外还给旋转播放用。
SRGNVDEC_CONF_OPTS = \
	-DBUILD_SHARED_LIBS=OFF \
	-DSRGNVDEC_UAPI=stable \
	-DSRGNVDEC_WITH_MP4=ON \
	-DSRGNVDEC_WITH_PP=ON \
	-DSRGNVDEC_WITH_H265=ON \
	-DSRGNVDEC_BUILD_FUZZ=OFF

ifeq ($(BR2_PACKAGE_SRGNVDEC_TOOLS),y)
SRGNVDEC_CONF_OPTS += -DSRGNVDEC_BUILD_TOOLS=ON
SRGNVDEC_DEPENDENCIES += libdrm
else
SRGNVDEC_CONF_OPTS += -DSRGNVDEC_BUILD_TOOLS=OFF
endif

$(eval $(cmake-package))
