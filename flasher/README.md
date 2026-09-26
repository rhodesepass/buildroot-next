# ePass 烧录工具

此目录是 Buildroot 仓库中的源码，`make clean/distclean` 不会删除。
无线协议实现 `bmc_ota.py`、ESP 查询工具 `esp_ota.py`、USB ESP 辅助实现
`flash_esp.py` 和主机测试都在此目录，
不依赖外部 `epass_bmc/tools`。post-image 从这里打包副本到 `output/images/flasher/`；
output 副本可以被 clean 删除，重新打包可恢复。根目录 `flash.py` 仅兼容旧 USB 入口。

以下命令在 Buildroot 根目录执行。默认读取 `output/images`，可用 `--images PATH`
指定其他产物目录；从打包副本运行时默认读取其父 images 目录。

## USB：首次或完整系统烧录

```sh
python3 flasher/flash.py
python3 flasher/flash.py --only boot rootfs
python3 flasher/flash.py --wch --no-esp
python3 flasher/flash.py --no-system --wch --esp \
  --esp-port /dev/ttyACM0 --esp-image ../epass_bmc/build/epass_bmc.bin
```

默认经 FEL 外部加载完整 U-Boot，再通过 DFU 写入 spl/uboot/boot/rootfs，
不依赖 NAND 旧系统。`--only` 限定分区；`--wipe` 清除用户 data，
`--scrub` 强制全片擦除并重扫坏块，均需显式选择。

`--wch/--no-wch` 与 `--esp/--no-esp` 独立选择外设，默认都不更新。
`--no-system` 只更新外设。WCH 默认用 images 中的 `ch32-touch.bin`，
可用 `--wch-image PATH` 覆盖。ESP 需要 `--esp-port`，默认应用为 Buildroot
产物 `images/esp/epass_bmc.bin`，可通过 `--esp-image PATH` 覆盖；
可加 `--esp-bootloader PATH` 同时更新 bootloader。

ESP 入口仍用于已有有效分区表及 OTA 元数据的设备：读取实际活动应用槽、
验证镜像、写入并完整回读，保留 NVS、分区表、OTA 元数据、BMC SPL 和 storage。
它不负责空白 ESP 首次分区初始化或安装 BMC SPL，没有有效 OTA 选择时停止。
“首次系统烧录”指 D1s NAND，不表示已实现整板空白 ESP 初始化。

系统需要 xfel/dfu-util；外设需要已构建的 `../uopbridge/bridge.bin`，
WCH 还需带 uopbridge 后端的 minichlink（`../uopbridge/host/build.sh`）。
可用 `--bridge-bin`、`--minichlink` 指定路径。ESP 需要当前 Python 安装
`esptool>=5,<6`；桥接枚举和串口归属检查依赖 Linux sysfs。

系统 DFU 与外设桥接是两个阶段：系统完成后按提示重新进入 FEL，加载桥接，
先刷 WCH 并完整回读，再刷 ESP。只刷外设时可从 FEL 或已运行的桥接开始。
外设完成后若 D1s 仍运行桥接，正常复位启动系统。

## OTA：BLE 或 Wi-Fi

```sh
# BLE，默认只更新 boot/rootfs
python3 flasher/ota.py --address AA:BB:CC:DD:EE:FF
# Wi-Fi，经 BLE 配网，密码交互输入
python3 flasher/ota.py --transport wifi --address AA:BB:CC:DD:EE:FF --wifi-sta MY_SSID
# 复用已建立的 Wi-Fi 会话，令牌交互输入
python3 flasher/ota.py --transport wifi --url http://192.168.4.1 --only rootfs
# 只更新 WCH
python3 flasher/ota.py --address AA:BB:CC:DD:EE:FF --no-system --wch
# 显式更新 NAND U-Boot
python3 flasher/ota.py --address AA:BB:CC:DD:EE:FF --only uboot
# 仅升级 ESP，无需 U-Boot FIT
python3 flasher/ota.py --address AA:BB:CC:DD:EE:FF --no-system --esp
# 同一 Wi-Fi 事务更新系统、WCH 和 ESP
python3 flasher/ota.py --transport wifi --url http://192.168.4.1 --wch --esp
```

`--transport ble|wifi` 默认 BLE。Wi-Fi 的 `--wifi-sta`、`--wifi-ap`、`--url`
三者互斥；STA/AP 需要 BLE 地址，AP 按提示切换电脑热点。BLE/配网需要当前
Python 安装 bleak；纯 HTTP 复用会话只需标准库。

包含系统/WCH 的 OTA 先将完整 `u-boot.itb` 上传到 RAM，再更新目标，不依赖 NAND 旧
U-Boot。默认用 images 中的 FIT，可用 `--uboot-fit PATH` 指定。
默认目标是 boot/rootfs；uboot 和 WCH 都要显式选择。`--only` 不接受 SPL、
overlay 或 data；不支持 wipe/scrub、修改设备身份。
WCH 无线更新需要 BMC 和上传的 U-Boot 支持 touch target 6。

`--esp/--no-esp` 独立控制 ESP 应用更新，默认关闭。默认应用路径同 USB；
需要设备已安装支持 bmc target 7 的固件，首次启用仍需 USB。
只升级 ESP 不需要 U-Boot FIT。混合更新先用 stage 3 写入 ESP 备用槽，
再经 stage 1/2 更新所选系统/WCH；全部 END 校验成功后才执行 ota-finish
提交，最后 ota-reboot。任一步失败都停止，不自动提交剩余目标。
这不是跨芯片原子事务：D1s/WCH 是原地更新，也没有自动健康回滚。

ESP 重启后原 Wi-Fi/token 失效，重新通过 BLE 配网后，可使用
`BMC_TOKEN=... python3 flasher/esp_ota.py --url http://设备地址` 查询运行分区、
启动分区和版本。建议交互读取 BMC_TOKEN，避免写入 shell 历史。收到上传、
提交 ACK 不等于新固件已启动；重启回复丢失时工具报结果待确认，不盲目重发。

更新提交后默认启动系统；包含 ESP 时默认重启 ESP。`--no-boot` 只提交不重启。
`--att-payload` 默认 20，确认 MTU 足够后可设 244。`--timeout` 默认 120 秒。
两个入口均支持 `--dry-run`，校验本地文件并显示计划，不连接设备。

## rootfs overlay 的现状

当前 `rootfs` OTA 目标写整个 rootfs MTD 的 UBI 镜像，这是只读 lower。
独立 data 分区的 `rootfs_data` 保存 `/overlay/upper`，更新时保留。
因此 upper 中的同名旧文件或 whiteout 仍可能遮住新 rootfs；烧入新 lower
不会自动迁移、替换或删除这些覆盖内容。

目前没有独立的 overlay/data OTA 目标、overlay 更新包或安装事务。
USB 文件接口可以把文件上传到运行中合并根目录的 `/usr/...` 等路径，从而
逐文件写入 upper，但它不是 BLE/Wi-Fi OTA。BMC 的 assets HTTP 接口尚无
Linux 消费端注册，返回 `501 assets_unavailable`，不能用于 overlay 安装。

源码依据：板级 `overlay/preinit` 的 lower/upper 挂载；U-Boot
`board/sunxi/bmc_ota.c` 的 rootfs MTD 选择；BMC `main/bmc_link.c` 的 assets
分派；工作区 `usb_aio_handler/src/funcs/epass/file_ops.c` 的文件上传路径。

## 验证

```sh
python3 -m unittest discover -s flasher/tests
```

测试涵盖 USB/OTA 参数分离、镜像选择、BLE/HTTP 协议、失败中止、ESP 布局和
回读；实际构建产物已 dry-run。2026-09-21 已实板验证 ESP 单目标 USB 回读、
Wi-Fi/BLE OTA 提交、重启后的运行槽/版本及 Linux/APP READY；组合升级和断电
恢复尚未实板验证。证据见工作区 `ota/artifacts/board-test/20260921-buildroot-esp/`。
images 内提供 `flash.sh`、
`ota.sh`；`flash-all.sh` 仍开启破坏性的 USB 全片 scrub。
