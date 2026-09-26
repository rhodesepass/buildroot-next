################################################################################
#
# esp-idf
#
################################################################################

HOST_ESP_IDF_VERSION = 6.0.2
HOST_ESP_IDF_SOURCE = esp-idf-v$(HOST_ESP_IDF_VERSION).zip
HOST_ESP_IDF_SITE = https://dl.espressif.com/github_assets/espressif/esp-idf/releases/download/v$(HOST_ESP_IDF_VERSION)
HOST_ESP_IDF_LICENSE = Apache-2.0, various (SDK components and host tools)
HOST_ESP_IDF_LICENSE_FILES = esp-idf-v$(HOST_ESP_IDF_VERSION)/LICENSE
HOST_ESP_IDF_DEPENDENCIES = $(BR2_CMAKE_HOST_DEPENDENCY) host-ninja host-python3 host-python-pip
HOST_ESP_IDF_ROOT = $(HOST_DIR)/opt/esp-idf
HOST_ESP_IDF_TOOLCHAIN_ARCHIVE = riscv32-esp-elf-15.2.0_20251204-x86_64-linux-gnu.tar.xz

include $(TOPDIR)/package/esp-idf/python-downloads.mk
HOST_ESP_IDF_EXTRA_DOWNLOADS = \
	https://github.com/espressif/crosstool-NG/releases/download/esp-15.2.0_20251204/$(HOST_ESP_IDF_TOOLCHAIN_ARCHIVE) \
	$(HOST_ESP_IDF_PYTHON_DOWNLOADS)

# Constraints are replaced by the checked-in, fully hashed dependency lock.
HOST_ESP_IDF_ENV = env -u PYTHONHOME -u PYTHONPATH \
	PYTHONNOUSERSITE=1 PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 \
	IDF_PATH=$(HOST_ESP_IDF_ROOT)/sdk \
	IDF_TOOLS_PATH=$(HOST_ESP_IDF_ROOT)/tools \
	IDF_PYTHON_ENV_PATH=$(HOST_ESP_IDF_ROOT)/venv \
	IDF_PYTHON_CHECK_CONSTRAINTS=no IDF_COMPONENT_MANAGER=0 \
	PATH=$(HOST_ESP_IDF_ROOT)/venv/bin:$(HOST_ESP_IDF_ROOT)/toolchain/bin:$(BR_PATH)

define HOST_ESP_IDF_EXTRACT_CMDS
	$(UNZIP) -q $(HOST_ESP_IDF_DL_DIR)/$(HOST_ESP_IDF_SOURCE) -d $(@D)
endef

define HOST_ESP_IDF_INSTALL_CMDS
	test "$(HOSTARCH)" = x86_64
	test "$$(uname -s)" = Linux
	rm -rf $(HOST_ESP_IDF_ROOT)
	mkdir -p $(HOST_ESP_IDF_ROOT)/sdk $(HOST_ESP_IDF_ROOT)/toolchain $(HOST_ESP_IDF_ROOT)/tools
	cp -a $(@D)/esp-idf-v$(HOST_ESP_IDF_VERSION)/. $(HOST_ESP_IDF_ROOT)/sdk/
	$(XZCAT) $(HOST_ESP_IDF_DL_DIR)/$(HOST_ESP_IDF_TOOLCHAIN_ARCHIVE) | \
		$(TAR) --strip-components=1 -C $(HOST_ESP_IDF_ROOT)/toolchain -xf -
	$(HOST_ESP_IDF_ROOT)/toolchain/bin/riscv32-esp-elf-gcc -dumpversion | grep -qx 15.2.0
	$(HOST_MAKE_ENV) env -u PYTHONHOME -u PYTHONPATH PYTHONNOUSERSITE=1 \
		$(HOST_DIR)/bin/python3 -m venv --without-pip $(HOST_ESP_IDF_ROOT)/venv
	$(HOST_MAKE_ENV) $(HOST_ESP_IDF_ENV) $(HOST_DIR)/bin/python3 -m pip \
		--isolated --no-cache-dir --python $(HOST_ESP_IDF_ROOT)/venv/bin/python install \
		--no-index --find-links $(HOST_ESP_IDF_DL_DIR) --no-deps --require-hashes \
		-r $(HOST_ESP_IDF_PKGDIR)/bootstrap.lock
	$(HOST_MAKE_ENV) $(HOST_ESP_IDF_ENV) $(HOST_ESP_IDF_ROOT)/venv/bin/python -m pip \
		--isolated --no-cache-dir install --no-index --find-links $(HOST_ESP_IDF_DL_DIR) \
		--no-build-isolation --no-deps --require-hashes \
		-r $(HOST_ESP_IDF_PKGDIR)/requirements.lock
	$(HOST_MAKE_ENV) $(HOST_ESP_IDF_ENV) $(HOST_ESP_IDF_ROOT)/venv/bin/python -m pip check
	$(HOST_MAKE_ENV) $(HOST_ESP_IDF_ENV) $(HOST_ESP_IDF_ROOT)/venv/bin/python \
		$(HOST_ESP_IDF_ROOT)/sdk/tools/idf_tools.py check-python-dependencies --no-constraints
	$(INSTALL) -m 0644 $(HOST_ESP_IDF_PKGDIR)/requirements.lock $(HOST_ESP_IDF_ROOT)/requirements.lock
	$(INSTALL) -m 0644 $(HOST_ESP_IDF_PKGDIR)/python-sources.json $(HOST_ESP_IDF_ROOT)/python-sources.json
endef

$(eval $(host-generic-package))
