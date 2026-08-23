# ePass Next（Allwinner D1s）

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

