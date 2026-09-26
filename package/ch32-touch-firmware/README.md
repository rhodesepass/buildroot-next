# CH32 触控固件的 Buildroot 包

`epass_next_defconfig` 默认启用 `BR2_PACKAGE_CH32_TOUCH_FIRMWARE`。固件单独使用
WCH GCC12（MounRiver 工具链包 V2.4.0 中的 GCC12 v1.4），不使用 Linux/D1s
交叉编译器，也不读取本机 MounRiver 工程或 IDE 安装目录。当前预编译工具链
支持 Linux x86_64 主机。官方包下载、固定哈希和离线缓存说明见
`../wch-riscv-toolchain/README.md`。

## 构建和产物

```sh
make ch32-touch-firmware
# 正常 make 也会构建固件，并在 post-image 阶段发布整组镜像清单。
make -j8
```

`output/images/` 包含：

- `ch32-touch.bin`：可传给 OTA `touch` 目标的 raw 固件。
- `ch32-touch.elf`、`ch32-touch.map`：调试/定位产物。
- `ch32-touch.json`：固件版本、长度、SHA256、Git 引用与仓库地址、协议及工具链哈希。
- `release-manifest.json`：本次 Linux/U-Boot/触控镜像的统一清单。

发布清单中默认 OTA 目标仍是 boot/rootfs；touch 为明确选择的可选目标。
固件不安装进 rootfs，不设置启动时自动烧录服务，USB flash.py 默认目标也不变。
从工作区根目录显式更新触控：

```sh
uv run --project epass_bmc/tools python epass_bmc/tools/bmc_ota.py \
  --uboot-fit buildroot-next/output/images/u-boot.itb \
  --image touch=buildroot-next/output/images/ch32-touch.bin --boot
```

## 源码版本与兼容性

源码独立维护于 `git@github.com:rhodesepass/tp_fw.git`；本地工作区为顶层 `tp_fw/`，
可在其中独立编译、测试和调试。Buildroot 从 Git 下载远端 `master` 分支的最新提交，
不固定提交、下载归档哈希或源码文件锁，也不直接读取本地工作区。
SSH 下载需要可访问仓库的 GitHub 凭据。

Buildroot 保留通常的下载缓存和增量构建行为，不会每次 `make` 都联网更新。
需要重新拉取时，在 Buildroot 目录清除本包的下载归档并重新构建：

```sh
rm -f dl/ch32-touch-firmware/ch32-touch-firmware-origin_master-git4.tar.gz
make ch32-touch-firmware-dirclean
make ch32-touch-firmware
```

使用自定义 `BR2_DL_DIR` 时相应调整缓存路径。源码中的 `snapshot.json` 保留固件版本；
镜像元数据中的 `source_revision: origin/master` 表示下载引用，不表示解析后的具体提交。
使用远端跟踪引用可避免 Git 下载缓存检出本地同名分支后拒绝再次更新。

构建仍会拒绝固件与 Linux 驱动触控协议定义不一致、空固件、超过 63488 字节和
非4字节对齐镜像。post-image 核对实际固件哈希、Git 引用/仓库和当前驱动协议。
工具链自身仍使用固定版本和哈希。

原 SDK 的 WCH 使用限制和无源码触摸库保留，授权来源见独立仓库 `LICENSES.md`。
包标记为不重新分发源码；不把闭源 `.a` 包装成开源实现。

## 2026-09-21 独立 Git 工程验证

`master` 已发布提交 `7fbfaa27e7752ed367a7064451663e7ac4a2b408`。
Buildroot 从远端 Git 下载并构建成功，10352 字节产物与独立工程及原基线逐字一致。
固件主机测试、7 项构建/发布保护回归、完整 Buildroot `make -j8` 和 post-image
通过；统一清单中 11 个产物的长度/哈希全部通过，触控 Git 来源及显式更新策略核验通过。
包格式检查 53 行、0 警告。
WCH GDB 可启动，OpenOCD 配置无硬件解析通过；本次未连接目标调试或刷板。

## 2026-09-20 验证

官方工具链完整目录与此前实板验证使用的 GCC12 相同；Buildroot 从自己的下载
缓存提取并安装工具链后成功编译。固件10352字节，SHA256 为
`c5d62579195d867b746fad4ebba3d17eb85da89d97f752c5435c11ae0ae5c81f`，
与此前独立实板读回的有效程序逐字一致，Flash 剩余部分全为 FF。
本次验证是构建集成和既有实板镜像一致性核查，没有重新刷板。

完整 Buildroot `make -j8`、发布清单全部镜像哈希核对、原固件主机测试、四项
构建保护回归和 check-package（0警告）通过。
