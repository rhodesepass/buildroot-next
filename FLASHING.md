# ePass 烧录

源码和完整说明已移至 [flasher/](flasher/README.md)。

- USB 首次/完整系统烧录：`python3 flasher/flash.py`。
- BLE/Wi-Fi 升级：`python3 flasher/ota.py`。
- rootfs OTA 更新只读 lower，保留可写 overlay；目前没有独立 overlay OTA 安装路径。
