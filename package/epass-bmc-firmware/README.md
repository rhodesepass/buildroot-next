# ESP32-C3 BMC 固件

`BR2_PACKAGE_EPASS_BMC_FIRMWARE=y` 将 BMC 纳入普通 Buildroot 构建，
ePass 默认配置已启用。包只安装到 `output/images/esp/`，不进入 Linux rootfs。

```sh
make epass-bmc-firmware
make epass-bmc-firmware-dirclean
make epass-bmc-firmware
```

`host-esp-idf` 自动下载固定 ESP-IDF 6.0.2、配套 RISC-V 工具链和锁定的
Python 依赖，全部进入 Buildroot 下载缓存。运行环境位于
`output/host/opt/esp-idf/`，不使用用户的 IDF_PATH、venv 或 ~/.espressif。
支持 Linux x86_64 构建主机。固件包依赖正常 U-Boot，以同次构建的
`sunxi-spl.bin` 生成 ESP 的两份正常 SPL 分区镜像。

## 源码与维护

源码通过 Buildroot 的 Git 下载机制获取，不再保留 `src/` 副本，也不读取
工作区 `epass_bmc/` 的未提交改动。

- 仓库：`ssh://git@github.com/rhodesepass/bmc_fw.git`。
- 拉取远端 `master`（`origin/master`），不固定 commit、下载归档哈希或源码文件哈希。

首次下载需要主机具备访问该仓库的 SSH 权限；认证由主机 SSH 配置处理，
不将私钥或令牌写进包。缓存保存于 `dl/epass-bmc-firmware/`，普通 clean
不会删除下载缓存，可用 `make epass-bmc-firmware-source` 预下载。
源配置保留不动，CMake 在 build 子目录使用 sdkconfig 工作副本。
固件版本为 `br-master`；清单的 `source_revision=origin/master` 表示下载引用，不代表实际 commit。

更新固件时先推送 BMC 仓库，删除下载缓存中的
`epass-bmc-firmware-origin_master-git4.tar.gz`，再执行
`make epass-bmc-firmware-dirclean`，完成后再执行 `make epass-bmc-firmware`。
不要并行执行清理与构建。普通增量构建会复用缓存，
不会每次联网刷新。原工作区工程仍可单独使用 ESP-IDF 开发。
无线客户端源码维护于
`flasher/bmc_ota.py`，升级协议时需同步客户端和固件，并运行双方测试。

本地工程未提供整体开源许可；本包按 Proprietary 处理，禁止 legal-info
自动重新分发。ESP-IDF 和工具链保留上游许可，不把上游许可扩展到本地代码。

## 产物和烧录

- `epass_bmc.bin`：ESP 应用，唯一的 ESP OTA 输入，wire target 7。
- `bootloader.bin`、`partition-table.bin`、`ota_data_initial.bin`：初始安装产物。
- `d1s_spl.bin`：同次构建的正常 SPL 双槽分区镜像。
- `flash_args.json`：完整初始布局与地址，明确标记 initial_install_only。
- `manifest.json`：各文件长度/哈希、Git 仓库与下载引用、SDK 锁哈希和配置哈希。

主发布清单 `release-manifest.json` 核验 ESP 产物，并把 bmc 标为显式可选目标。
完整初始布局会写分区表和 OTA 元数据，不可当普通应用更新包使用。
现有 USB `flasher/flash.py --esp` 仍只更新已安装设备的活动应用槽，
默认读取本包 `esp/epass_bmc.bin`，可显式另选 bootloader。

首次启用 APP 关机深睡时，必须部署同次构建的 bootloader 和应用。
仅应用 OTA 会保留旧 bootloader，固件此时报告 `sleep=bootloader_required`。
不要用完整初始布局覆盖现有设备；USB 更新可通过 `--esp-bootloader` 显式选择
配套 bootloader，并保留现有分区表、OTA 元数据与 SPL。

```sh
# 仅升级 ESP，BLE
python3 flasher/ota.py --address AA:BB:CC:DD:EE:FF --no-system --esp
# 同一 Wi-Fi 会话升级系统、WCH 和 ESP
python3 flasher/ota.py --transport wifi --url http://192.168.4.1 --wch --esp
```

ESP 自身 OTA 需要设备已安装支持 bmc target 7 的版本；首次启用仍需 USB。
组合升级先暂存 ESP 备用槽，再更新系统/WCH，全部成功才提交并重启 ESP。
这不是三芯片原子更新：D1s/WCH 是原地写入，需要保持跨版本兼容。
ESP 重启后重新 BLE 配网获取新 token，再查询运行分区和版本验证启动结果。

## 历史固定 Git 版本验证（2026-09-21）

远程 HEAD 与固定 commit 一致；SSH/Git 下载、归档及 100 个文件哈希检查、
dirclean 后完整 BMC 编译、32 项构建/清单测试、USB/OTA dry-run 均通过。
新应用 1255424 字节，版本 `br-2651d5f4e3ef`，SHA256 为
`538025a01ae0460c84249afbce7c685a937912e7a547bb5388563fa912e80a71`。
ESP 单独发布元数据核验通过。本次未刷板；整树 make 尝试被另一个 CH32 包的
全零 Git 版本占位值阻断，未宣称整树构建或总发布清单更新通过。

## 历史快照验证记录（2026-09-20）

以下记录对应切换 Git 方式之前的快照镜像，不能代替当前 Git 镜像的实板验证。

独立下载并校验 SDK/工具链；从锁定缓存建立全新 Python venv，pip check 和
IDF 官方依赖检查通过。`make epass-bmc-firmware`、普通完整 `make` 及
post-image 发布清单核验均通过。应用 1255424 字节，两个应用槽均有约 20% 余量；
版本 `br-29587271d96f`，SHA256
`115d51a7f3caf7777ad54e9eae619afd9c3190fc94ced009c8045abcbdf7f7e0`。
75 项 flasher 测试、26 项构建/发布清单测试通过；打包后的 ESP-only BLE、
系统/WCH/ESP Wi-Fi 组合及 USB 默认镜像 dry-run 通过。未执行本次实板刷写，
未验证新镜像启动，也未执行断电测试。

2026-09-21 补充实板验证：打包后的 USB 入口安装本镜像并完整回读一致；
Wi-Fi OTA（13.15 秒）和 BLE OTA（ATT 244，723.02 秒）均完成 1255424 字节
durable END、显式提交和重启。实际运行槽依次 ota_0 → ota_1 → ota_0，版本
`br-29587271d96f` 正确，Linux/APP READY 正常、pending 清零。
未执行系统/WCH/ESP 组合实板升级或断电测试；工作区证据见
`ota/artifacts/board-test/20260921-buildroot-esp/README.md`。
