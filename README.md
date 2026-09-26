# ePass Next（Allwinner D1s）

## 当前构建与仓库关系

本仓库维护 D1s Linux/U-Boot 补丁、设备树、根文件系统、固件包和刷写工具。
BMC 与触控固件分别维护于 `rhodesepass/bmc_fw`、`rhodesepass/tp_fw`；三个
仓库独立提交，通过 Buildroot Git 包关联，不使用 submodule 或本地目录隐式依赖。
两个固件包均拉取 `origin/master`，不固定源码提交或源码哈希。

```sh
make epass_next_defconfig
make -j8
```

产物位于 `output/images/`；USB 使用 `flasher/flash.py`，无线升级使用
`flasher/ota.py`，先加 `--dry-run` 核对更新范围。默认不更新 WCH/ESP，需分别
指定 `--wch`、`--esp`；完整说明见 [FLASHING.md](FLASHING.md)。

发布顺序为：先提交、测试并推送 BMC/TP，再提交和推送依赖它们的 Buildroot。
推送固件后，普通 `make` 仍可能使用旧下载缓存；在本目录执行：

```sh
rm -f dl/epass-bmc-firmware/epass-bmc-firmware-origin_master-git4.tar.gz
rm -f dl/ch32-touch-firmware/ch32-touch-firmware-origin_master-git4.tar.gz
make epass-bmc-firmware-dirclean ch32-touch-firmware-dirclean
make epass-bmc-firmware ch32-touch-firmware
make -j8
```

自定义 `BR2_DL_DIR` 时调整缓存路径，清理和构建必须分步完成。
发布清单中的 `origin/master` 是下载引用，不是解析后的提交号；产物通过长度、
SHA256、工具链及协议检查核验。首次启用 BMC 深睡须一并升级配套 bootloader，
应用 OTA 无法更新 bootloader。用户应用需支持显式 READY，才能启用正常控电。

## 本次提交整理验证（2026-09-26）

- BMC ESP-IDF 构建、78 项主机测试及 bootloader 救援测试通过；拆分提交的
  中间版本另行检查充电、运行态和深睡测试。TP 独立 make 与协议/触摸测试通过。
- U-Boot 7 个、Linux 24 个补丁从下载的原始源码顺序应用通过，未使用模糊匹配。
  DT FIT 编译、SPL SRAM 布局、内核/固件触摸协议核验通过。
- Buildroot 75 项刷写和 33 项固件/清单测试通过，新增包格式检查 279 行、
  0 警告；全新输出目录的 defconfig 和包依赖解析通过。

本次未重新构建整套 Buildroot 镜像，未刷新发布镜像，也未进行新的实板刷写或
功耗/充电验收。下面历史记录的构建与板测结果只适用于对应轮次。

## 历史验证记录

以下按日期记录各轮结果；旧轮次的源码锁策略、产物大小和实板结论不代表当前版本。

2026-09-26：实际 DT FIT 的公共板级 `epass-next.dtsi` 只保留 mixer0 显示管线，
禁用未使用的 mixer1、tcon_tv0。Wi-Fi OTA 实验固件保留同一 kernel，板上启动
及播放状态正常；mixer1、bus-mixer1、bus-tcon-tv 的 enable count 为 0，硬件门控
均为关闭。相同 Spine 测试下电池侧平均功率从 1028.55 mW 降至 1003.84 mW，
约省 24.71 mW（2.4%）；面板仍用原生时序。板级源码另行 dtc 验证，不重建或覆盖
现有 images。证据见工作区 `power_measure/test-results/20260926-022314-explore/`，
实验构建见 `power_measure/experiments/display-dt/`。

2026-09-23：CH32 触摸驱动迁入内核树，使用 `CONFIG_INPUT_CH32_TOUCH_SLIDER=y`
随内核构建并直接内建。移除独立 `ch32-touch-slider` 包和 S35 模块加载脚本。
驱动源码由 Linux 补丁 0024 提供；CH32 固件协议检查使用板级协议头，
post-image 核对其与实际内核源码一致。驱动更新须同时部署新内核和 rootfs。
干净内核构建、完整 Buildroot 构建、协议测试和 40 项固件/清单测试通过；
确认驱动已链接进 vmlinux，rootfs 无旧模块和启动脚本，发布哈希一致。未刷板。

2026-09-21：CH32V006 触控固件独立维护于 `rhodesepass/tp_fw` 的 `master`，
工作区入口为 `../tp_fw/`，支持独立编译、主机测试及 WCH-LinkE/GDB 调试。
`ch32-touch-firmware` 从 Git 远端 master 构建，包内不保存重复固件源码，
不固定 commit 或源码哈希；发布清单仍检查镜像完整性及完整驱动协议。
此前固定版本的独立构建、7 项回归、完整构建及 11 个发布产物哈希核验通过。
维护方式见 [触控固件包说明](package/ch32-touch-firmware/README.md)。

2026-09-21：BMC 固件包通过 Git 获取 `rhodesepass/bmc_fw` 的 master，
不固定 commit 或源码哈希。使用原独立 IDF 工具链，版本标记为 `br-master`。
两包的普通增量构建会复用下载缓存；更新远端代码后需清除对应 origin_master 归档，
再执行包的 dirclean/build，详见各包说明。此前固定版本的 BMC 干净构建、
32 项构建/清单测试和实际产物 dry-run 通过；本次未刷板。

2026-09-21：ESP 单目标实板测试通过：USB 完整回读一致，Wi-Fi OTA 13.15 秒、
BLE OTA（ATT 244）723.02 秒，均持久化 1255424 字节。重启后版本和运行槽
核验通过，Linux/APP READY 正常、OTA pending 清零。101 项主机测试复验通过。
未实板测试三芯片组合升级或断电恢复；详见工作区
`ota/artifacts/board-test/20260921-buildroot-esp/README.md`。

2026-09-20：ESP32-C3 固件纳入 `epass-bmc-firmware`，独立固定 ESP-IDF 6.0.2、
工具链与 Python 依赖，源码快照校验后构建到 `images/esp/`，不依赖用户 IDF。
`flasher/ota.py --esp` 支持 BLE/Wi-Fi 单独或组合升级，先暂存 ESP 备用槽，
全部目标完成后统一提交并重启；默认仍不更新 ESP。详见
[BMC 构建说明](package/epass-bmc-firmware/README.md) 和 [烧录说明](flasher/README.md)。
独立 SDK 构建、完整 `make`、post-image 清单验证及 101 项主机测试通过；
ESP 应用为 1255424 字节，本次未实板刷写或验证新固件启动。

2026-09-20：烧录源码集中在 `flasher/`，不再从外部未跟踪目录打包无线客户端。
`flasher/flash.py` 用于首次/完整 USB 系统烧录，`flasher/ota.py` 用于 BLE/Wi-Fi OTA。
`--wch/--no-wch`、`--esp/--no-esp` 独立选择外设，默认都不更新；
`--no-system` 可只更新外设，`--dry-run` 检查镜像并显示计划。
WCH 支持三种通道；ESP 当前也已支持 BLE/Wi-Fi OTA。OTA 默认只更新 boot/rootfs，
保留 data 上的可写 overlay；目前没有独立 overlay OTA 安装协议。
`make clean` 只清理打包副本，保留 flasher 源码。主机测试及真实镜像 dry-run
通过，本次未执行实板刷写。完整参数、依赖与示例见 [烧录说明](flasher/README.md)。

2026-09-20：CH32 触控固件已纳入普通 Buildroot 构建。独立固定源码快照与
WCH GCC12 工具链，输出 `ch32-touch.bin/.elf/.map`、`ch32-touch.json`，
post-image 生成统一 `release-manifest.json`。构建核对源码锁、Linux协议一致性、
长度和对齐；touch 始终为显式选择的 OTA 目标，不随普通 Linux 更新自动刷写。
完整构建通过，10352字节产物与此前实板程序有效内容逐字一致。
维护及更新方式见 `package/ch32-touch-firmware/README.md`。

2026-09-20：U-Boot 增加 PG13/PG15 SWIO 的 CH32V006 触控烧录命令，
OTA 新增 `touch` 目标。完整固件先在 RAM 校验 SHA256，再逐页擦写回读；
只允许最多 62 KiB 主 Flash，保留末页范围外数据，不修改选项字节或读保护。
BMC、Python 和网页客户端同步支持触控单目标事务。补丁已同步且往返
校验通过，Buildroot 已 dirclean 后重新应用补丁并构建；Wi-Fi触控单目标
OTA 63488 字节写入、独立读回一致和重启input探测已通过。详细实板状态见
工作区 `ota/artifacts/board-test/20260920-touch/README.md`。

2026-09-19：n0.2 接入 SPI0 BMC 运行时驱动，内建电量/版本/电源状态接口。
APP 完整初始化及首帧后显式 READY 才允许 BMC 控电，正常关机通过内核
sys-off prepare 通知 BMC。APP 通信失败不使用旧电量触发关机。
BMC 另有五秒长按强关及独立 bootloader ROM 救援。内核、DT FIT、APP 交叉
构建及主机测试通过；已上板验证 READY、软关机、实体五秒强关/短按开机。
无电池时容量/电压失效，USB 状态仍有效。一轮故障注入走通 FEL/uopbridge；
最新救援手势/计数、带电池 QON 及冷启动毛刺复位仍有验证边界。本轮部署
boot 与 APP720，rootfs/data 保留。详见工作区 epass_bmc/docs/app-runtime.md。

2026-09-19：修复 D1 codec 数字路由引用不存在的 Left/Right ADC，改为模拟侧
实际注册的 ADC1/ADC2。内核已构建、仅更新 NAND boot 内核区域并 SHA256
回读一致，重启后 D1 Audio Codec 注册成功。发现 TinyALSA 2.0 在 RISC-V
SYNC_PTR 回退路径读取状态时回写旧 appl_ptr，已加入包补丁修复。
直接 PCM 写入并 drain 实测 480000 帧耗时 10.015 秒；修复库实板 A/B 使
tinyplay 同一 10 秒 WAV 从 0.31 秒恢复至 9.96 秒，修复库已安装并哈希校验。
后续示波器发现双路 HPOUT 固定高电平：对照 Tina BSP 补齐 HPLDO 供电、
30 ms 等待和左右 DAC 解除静音，用户确认双路波形出现。已持久化到 DAPM，
耳机 RAMP 按 DAC 之后上电、之前下电排序并等待 100 ms。新内核 #4 已刷写
回读校验并重启，首次播放、停止、再次播放的供电/静音寄存器切换通过。
用户已用示波器确认重启后双路波形均正常，持久修复完成实板播放闭环。
A 版芯片手动 HP2 序列不在本次验证范围内。
详细证据与测试工具见工作区 ota/artifacts/board-test/20260919-codec/。

2026-09-18：n0.2 接入 PG10 电源键为 `KEY_0`，低有效、内部上拉、20 ms 去抖。
上拉通过 GPIO descriptor 标志配置，避免静态 pinctrl 与 GPIO 申请冲突。
CH32 增加 `ABS_MISC` 状态：bit0 位置有效、bit1 多点、bit2 取消，与
`BTN_TOUCH/ABS_X` 同帧提交；通信错误立即取消手势，持续失败 100 ms 释放。
恢复后仍按住的接触保持取消直到实际松开。普通松手状态为 0，保留最后 X。
该接口用于应用区分真实滑动和异常释放；本次没有实板刷写或功能验收。

2026-09-13：BMC 无线更新统一为外部完整 U-Boot FIT → RAM → NAND，
正常启动与更新共用 `u-boot.itb`，USB FEL/DFU 也先外部加载完整 U-Boot。
BMC 仅保存两份正常 SPL；同一 SPL 根据更新请求选择外部 FIT 或正常
NAND 启动，更新不依赖 NAND 现有程序或环境。
BMC 已另行实现 BLE 引导 STA/AP 与 Wi-Fi HTTP 通道（ESP-IDF 工程，
不属于 Linux Buildroot 包）；已编译及host测试；Wi-Fi实板提速版本约40–47 KiB/s，但中断看门狗未解决，
不能作为稳定发布。板子已恢复测试前BMC，见工作区Wi-Fi板测记录。
已上板通过正常启动、外部 FIT 加载、256 KiB 校验及 NAND U-Boot 更新回读，
并重启 Linux/app_720。实板修复 SRAM 布局与 FIT 对齐读问题，Buildroot
同步重建通过。详见工作区 `ota/README.md` 和本树板级 readme。

2026-09-13：加入 `ch32-touch-slider` 内核模块包，n0.2 集成六电极滑条
`0x2a`，输出 BTN_TOUCH/ABS_X。FPC 针号直连使用 GPIO I²C：SCL=PG7、
SDA=PG6，IRQ=PG14（内部上拉、低有效）；保留 PG13/PG15 调试/复位。
驱动源码和协议头随 Buildroot 保存，不依赖 MounRiver 工程路径。
构建启用 I2C_GPIO、i2c-tools 与开机模块加载。完整镜像及上板启动通过，
GPIO I²C 总线已注册，但 CH32 0x2a 实物无 ACK，两种线序和复位均未恢复，
尚未产生 input 设备；详细验证记录见板级 readme。

2026-09-10：按主板导出网表同步 APP：背光 PWM5/PG4、屏复位 PG12、DSI 三 lane；
PG6/PG7 改 I2C2 键盘 FPC 总线，删除旧 GPIO 按键及不存在的 AXP209 节点，
关闭 SPL AXP209 初始化与未接线 USB1 host。SD、耳机、UART3、SPI1 保持网表对应连接。
当前 n0.2 名称不变，键盘 MCU 地址/协议、电源键 PG10（经 D2）/键盘 IRQ PG14（经 R25）的驱动和板级显示测试待确认。

2026-09-10：启动链改为 ESP32-C3 在 SPI0 提供 SPL，SPL 切 SPI1 从物理 NAND
0x40000 加载 U-Boot。U-Boot/Linux NAND 使用原理图 PD10–PD15（IO2=PD15、IO3=PD14），
保留原分区偏移；原 SPI0 实测结论不覆盖本次接线，SPI1 启动仍待上板验证。

2026-09-10：调试串口从 PB6/PB7 迁到 C3 对应的 PG8/PG9（UART3，115200），
覆盖 SPL early UART、U-Boot/OpenSBI 设备树和 Linux ttyS3；原控制台编号不变。
C3 提供独立 1 KiB eGON FEL 镜像，跳 ROM 0x20 前关闭 I-cache，供后续 uopbridge 下载恢复。
以上调试路径尚未验证实板。

图例：


| 状态  | 含义                     |
| --- | ---------------------- |
| 完成  | 本树有驱动，IP 已在 D1s 上跑通    |
| 部分  | 有驱动，能力不完整或只验证了子集       |
| 未启用 | 主线有驱动，本树 `.config` 没打开 |
| 未做  | 没有可用驱动                 |
| 做不成 | 试过，这颗硅上不行              |


U-Boot 列里 `—` 表示启动路径不需要这条 IP，不是缺失。

---

## 核心 / 系统


| IP             | 手册                                         | U-Boot                   | Linux                        | 用户态                 | 状态  | 说明                                                   |
| -------------- | ------------------------------------------ | ------------------------ | ---------------------------- | ------------------- | --- | ---------------------------------------------------- |
| C906           | RV64GC，32KB I/D                            | S-mode + OpenSBI generic | `THEAD_C906`，xtheadvector    | `-mtune=thead-c906` | 完成  | OPP 408/1008 MHz，电压固定 900 mV                         |
| BROM           | SD / eMMC / SPI NOR / SPI NAND 启动，USB 强制升级 | eGON SPL，FEL 回 BROM      | —                            | xfel                | 完成  |                                                      |
| DRAMC          | 封装内 64MB DDR2，最高 533 MHz                   | DDR2 几何 + 训练             | `memory@40000000`            | —                   | 完成  | 上电电压必须先到 1.8V，否则训练把核卡死                               |
| CCU            | 8 PLL，门控/复位                                | sun20i-d1                | mainline `sun20i-d1-ccu`     | —                   | 完成  |                                                      |
| PLIC           | ≤256 源，32 级优先级                             | —                        | `thead,c900-plic`            | —                   | 完成  | 外设 IRQ 填 dts 时要减 16                                  |
| CLINT          | M-mode 定时器 / IPI                           | dts 补节点给 OpenSBI         | Linux 不碰                     | —                   | 完成  | 缺了 SBI TIME=0 Hz，jiffies 冻住                          |
| DMAC           | 16 通道                                      | —                        | `sun6i-dma`                  | —                   | 完成  |                                                      |
| THS            | CPU 热传感器 ±3°C                              | —                        | `sun8i-thermal` + cpufreq 降温 | —                   | 完成  |                                                      |
| 片内 LDOA/B      | 1.8V IO / DRAM                             | 不操作                      | —                            | —                   | 未做  | 模拟电源，无独立 OS 驱动；本树用外置 PMIC 供 DRAM                     |
| RTC            | 日时分秒、定时唤醒、掉电保持寄存器                          | —                        | `rtc-sun6i`                  | —                   | 完成  |                                                      |
| Timer0/1 + AVS | 32-bit 递减；AVS 音视频同步                        | —                        | 节点强制 `disabled`              | —                   | 做不成 | rating 压过 SBI timer，但这颗芯片 PLIC 59 不响                 |
| HSTimer0/1     | 56-bit，跟 AHB 同步                            | 无                        | 未启用                          | —                   | 未做  |                                                      |
| WDT            | 系统复位                                       | —                        | `sunxi-wdt`                  | 无喂狗守护               | 完成  |                                                      |
| IOMMU          | VE / CSI / DE / G2D / DI 地址转换，可独立 bypass   | —                        | 补丁 0001/0009 有驱动，**不编译**     | —                   | 做不成 | DE 一开第二通道竖纹且无 fault；BSP 也 bypass DE。DE 走物理则 VE 也必须物理 |
| SID / eFuse    | 2 Kbit                                     | —                        | `nvmem-sunxi-sid`            | —                   | 完成  | USB PHY 用厂修 trim                                     |




## 显示 / 视频


| IP        | 手册                                                         | U-Boot                   | Linux                                       | 用户态                           | 状态  | 说明                                                            |
| --------- | ---------------------------------------------------------- | ------------------------ | ------------------------------------------- | ----------------------------- | --- | ------------------------------------------------------------- |
| DE        | 最大 2048²，主显两通道各 4 overlay，辅显一通道                            | `srgn_splash` 直接操 mixer0 | `sun4i-drm`：4 UI overlay + C8 + `drm_panic` | libdrm / LVGL                 | 完成  | UI 拆开后不能缩放；调色板是通道级共用                                          |
| TCON LCD  | RGB 1080p60 / LVDS 双链路 / i8080 / BT656                     | TCON LCD0 走 DSI          | `sun4i-tcon`                                | —                             | 部分  | DSI 出口已跑通；RGB / LVDS / i8080 同一 IP，未在 D1s 上验证                 |
| MIPI DSI  | DSI v1.01，4 lane，RGB888/666/565                            | DSI host + D-PHY + DCS   | `sun6i-mipi-dsi` + `phy-sun6i-mipi-dphy`    | —                             | 完成  |                                                               |
| TCON TV   | TV 时序                                                      | 无                        | 未启用                                         | —                             | 未做  |                                                               |
| TVE       | 1 路 CVBS OUT，NTSC/PAL                                      | 无                        | 未启用                                         | —                             | 未做  |                                                               |
| DI        | YUV420/422 去隔行，最大 2048×1280                                | 无                        | 未编                                          | —                             | 未做  |                                                               |
| G2D 旋转    | 翻转 / 0 / 90 / 180 / 270                                    | 无                        | `sun8i-rotate` @ G2D+0x28000                | `/dev/video*` m2m，`rot-probe` | 完成  | 与 A83T DE 内旋转核同一套寄存器。复位顺序反了会把 MBUS 卡死到只能断电                    |
| G2D mixer | BitBlit / StretchBlit / Porter-Duff                        | 无                        | 无驱动；TOP bit0 留在复位                           | 无                             | 未做  | 旋转核能用，mixer 核没有 mainline 驱动                                   |
| VE 解码     | H.265/H.264/H.263/MPEG-4/2/1/Xvid/Spark/VC-1/MJPEG，1080p60 | 无                        | cedrus，跳过 VE SRAM，非 tiled NV12              | srgnvdec / cedrus-probe       | 部分  | MPEG-2 / H.264 / HEVC slice 已验证。DE2 只扫 LINEAR，必须用硬件 UNTILED 口 |
| VE 编码     | JPEG/MJPEG 1080p60                                         | 无                        | cedrus 不管编码                                 | 无                             | 未做  |                                                               |
| CSI       | 8-bit RAW/YUV，BT656/BT601                                  | 无                        | 未编 `sun6i-csi`                              | —                             | 未启用 | 主线有驱动                                                         |
| TVD       | 2 路 CVBS IN，1 路解码                                          | 无                        | 无                                           | —                             | 未做  |                                                               |




## 存储


| IP             | 手册                                     | U-Boot         | Linux                 | 用户态 | 状态  | 说明                                        |
| -------------- | -------------------------------------- | -------------- | --------------------- | --- | --- | ----------------------------------------- |
| SMHC0/1/2      | SD 3.0 / SDIO 3.0 / eMMC 5.0，三套控制器同一驱动 | `sunxi-mmc`    | `sunxi-mmc`           | —   | 完成  | 三套主机控制器共用 `MMC_SUNXI`                     |
| SPI0/1（SPI 模式） | 标准/双线/四线，Mode0–3                       | `spi-sunxi`，四线 | `spi-sun6i`，单 burst 读 | —   | 完成  | 必须 `spi-rx/tx-bus-width=<4>`，否则静默掉到 1-1-1 |
| SPI1 DBI       | Type-C 3/4 线，RGB 屏                     | 无              | 未做                    | —   | 未做  | 同一控制器的 DBI 模式，没有驱动                        |




## USB / 网络


| IP        | 手册                                  | U-Boot            | Linux                      | 用户态                | 状态  | 说明                                                     |
| --------- | ----------------------------------- | ----------------- | -------------------------- | ------------------ | --- | ------------------------------------------------------ |
| USB0 DRD  | HS/FS/LS，EHCI/OHCI 主机或 11 端点 gadget | musb gadget + DFU | musb sunxi + 厂修 eFuse trim | configfs ACM / FFS | 部分  | gadget 已跑通；同一 IP 的 host 角色没开                           |
| USB1 HOST | 独立 EHCI + OHCI                      | 未用                | 主线有 EHCI/OHCI，本树没编         | 无                  | 未启用 | dts 里节点可以开，`.config` 缺 `USB_EHCI_HCD` / `USB_OHCI_HCD` |
| EMAC      | 10/100/1000，RGMII/RMII，MDIO         | 无                 | 未编 `sun8i-emac`            | 无协议栈               | 未启用 | 主线有 D1 EMAC；本树为体积砍掉整棵 TCP/IP                           |




## 音频


| IP              | 手册                               | U-Boot | Linux                                    | 用户态      | 状态  | 说明                            |
| --------------- | -------------------------------- | ------ | ---------------------------------------- | -------- | --- | ----------------------------- |
| Audio Codec DAC | 双 DAC 16/20 bit，8–192 kHz，立体声 HP | 无      | `sun4i-codec` + `sun20i-d1-codec-analog` | tinyalsa | 完成  | 模拟侧是直连 MMIO，不是老 SoC 的 ADDA-PR |
| Audio Codec ADC | 五路 ADC，MIC / LINEIN / FMIN       | 无      | 捕获路径随补丁带过来，标 incomplete                  | 未用       | 部分  | 播放已验证；录音没练完                   |
| I2S1 / I2S2     | I2S/PCM/TDM，最多 16 ch @ 48 kHz    | 无      | 未启用                                      | —        | 未启用 | 主线有 `sun4i-i2s`               |
| DMIC            | 最多 8 路 PDM，8–48 kHz              | 无      | 未启用                                      | —        | 未启用 | 主线有 `sun50i-dmic`             |
| OWA             | S/PDIF TX+RX，IEC-60958/61937     | 无      | 未启用                                      | —        | 未启用 | 主线有 `sun4i-spdif`             |




## 接口


| IP      | 手册                                      | U-Boot    | Linux                  | 用户态        | 状态  | 说明                     |
| ------- | --------------------------------------- | --------- | ---------------------- | ---------- | --- | ---------------------- |
| UART0–5 | 6 路 16550；UART1/2/3 可 4 线               | ns16550   | `8250_dw`，`NR_UARTS=6` | getty      | 完成  | 一套驱动覆盖全部 6 路           |
| TWI0–3  | 4 路 I2C，100/400 kbit/s，主从               | sunxi TWI | `i2c-mv64xxx`          | —          | 完成  |                        |
| PWM0–7  | 8 路，互补对、死区、捕获                           | 无         | 自写 `pwm-sun20i`        | —          | 完成  | 主线没有 D1 PWM，补丁 0002    |
| PIO     | PB–PG，中断、复用                             | pinctrl   | `sun20i-d1-pinctrl`    | —          | 完成  |                        |
| GPADC   | 1 通道 12-bit SAR，最高 1 MHz                | 无         | 节点保持 disabled          | —          | 未启用 | SoC dtsi 有节点；本树没开      |
| TPADC   | 4 线电阻屏 + 最多 4 路 Aux ADC                 | 无         | 未启用                    | —          | 未做  |                        |
| LEDC    | 智能灯带，最多 1024 颗                          | 无         | 未启用                    | —          | 未启用 | 主线有 `sun50i-a100-ledc` |
| CIR RX  | NEC 红外接收                                | 无         | 未启用                    | —          | 未启用 | 主线有 `sunxi-cir`        |
| CIR TX  | 任意波形 + 载波                               | 无         | 未启用                    | —          | 未做  |                        |
| CE      | AES/DES/TDES、SHA/MD5/HMAC、RSA、PRNG/TRNG | 无         | `CRYPTO_HW` 关掉         | 软件 AES/SHA | 未启用 | 主线有 `sun8i-ce`；本树用软件实现 |


手册没有、D1-H 才有的接口（HDMI 等）不列入。T113 共享 dtsi 里的 CAN 复用脚，D1s 特性清单没有 CAN，也不列入。

---



## 条数（按上表 IP 行）


| 完成  | 部分  | 未启用 | 未做  | 做不成 |
| --- | --- | --- | --- | --- |
| 21  | 5   | 9   | 8   | 2   |


**部分：** TCON LCD 非 DSI 出口、VE 解码格式子集、VE 同 IP 的编码没有、USB0 host 角色、Codec ADC。

**做不成：** sunxi Timer（中断不来）、IOMMU+DE（硅上没验证过的组合）。

---



## 移植摘要



### U-Boot（2026.07 + 7 补丁）

主线没有 D1 RISC-V sunxi。本树补了平台胶水、`dram_sun20i_d1.c` 的 DDR2 几何、musb 寄存器、时钟，以及 SPI NAND 四线。

SPL 必须在 uclass 之前用 TWI 把 DRAM 供电拉到 1.8V。FEL 返回路径要恢复 callee-saved 和 `mie/mtvec/mstatus`，并在 `_start` 起 UART——xfel 写 SRAM 当数据，不刷 icache。

显示：`srgn_splash` 起 DE2 → TCON → DSI，把 simple-framebuffer 交给内核。64MB 下 stack / `bootm` / DFU 缓冲都按容量收过。

### Linux（7.1.6 + 21 补丁）

完整自定义 config，不是 fragment。64MB 连续内存用 FLATMEM 替代 SPARSEMEM（少约 17MB 页表账面）。CMA 36MB 养 DE/cedrus。IOMMU 不用。

自带或补上的驱动：sun20i PWM、tcon_top 探时注册时钟并选 mixer 路由、UI 四 overlay、C8 索引色、drm_panic、simpledrm 放掉 firmware fb、cedrus 跳过 D1 没有的 VE SRAM、非 tiled NV12、G2D 旋转、D1 codec 模拟、USB PHY eFuse trim、musb 提前到包 flush、SPI 单 burst、C906 `-mtune`、uaccess `A` 约束。

Timer 节点必须关掉，tick 走 SBI。CLINT 节点必须在（给 OpenSBI，不是给 Linux）。

### rootfs（musl）

musl 补了 xtheadvector（RVV 0.7.1）的 memcpy/memset/strlen 一类。用户态用到的芯片能力：DRM/KMS、V4L2 m2m（cedrus / rotate）、ALSA（tinyalsa）、USB gadget configfs。

Buildroot 2026.05 上的 D1s 板级。T113-s3 板换芯，引脚兼容但不是 drop-in：封装内 DRAM 从 DDR3/1.35V 换成 DDR2/1.8V。

## 使用

```
make epass_next_defconfig
make
```

- 板级现状：[board/rhodesisland/epass-next/readme.txt](board/rhodesisland/epass-next/readme.txt)


2026-09-10 实板验证：ESP32-C3 经 BootROM SPI0 提供 SPL，后续从硬件 SPI1 NAND
启动 OpenSBI、U-Boot、Linux 7.1.6，已到达登录界面并确认 UBIFS/可写 overlay。
UART3 PG8/PG9 可通过 BMC BLE 双向使用；详见同级 `epass_bmc/README.md`。
本次 rootfs/Image 使用已核对版本的现有 7.1.6 产物，未声称重新构建整个发行版。
