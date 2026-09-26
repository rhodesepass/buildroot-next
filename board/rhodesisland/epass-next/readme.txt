Repository dependencies and release order (2026-09-26)
----------------------------------------------------
BMC (rhodesepass/bmc_fw), TP (rhodesepass/tp_fw), and Buildroot are independent
repositories, not submodules. Both peripheral packages fetch origin/master;
local uncommitted or unpushed changes are not included. Commit/test/push firmware
first, then publish the matching Buildroot integration. Keep floating source
references; retain toolchain hashes, image integrity and wire-protocol checks.
Remove each package's origin_master-git4 download archive before refreshing it,
then complete package dirclean before starting its build. Adjust paths for
BR2_DL_DIR. Source revision fields name the reference, not the resolved commit.
Initial BMC deep-sleep deployment requires the matching bootloader as well as
the application; OTA updates only the application. APP must explicitly send READY.
The dated records below describe earlier validation, not a fresh board acceptance.

Commit preparation validation (2026-09-26)
----------------------------------------
BMC IDF build, 78 host tests and bootloader rescue tests passed; intermediate
BMC commits also ran their available charging/runtime/sleep tests. TP make and
touch/protocol tests passed. All 7 U-Boot and 24 Linux patches applied in order
to pristine downloaded sources with zero fuzz. DT FIT compilation, SPL SRAM
layout and kernel/firmware touch protocol checks passed. Buildroot flasher tests
(75), firmware/manifest tests (33), new package format checks (279 lines, zero
warnings), and a fresh-output defconfig/dependency parse passed.
This preparation did not rebuild the complete Buildroot image set, refresh
release images, flash hardware, or repeat power/charging acceptance tests.

Single display pipeline power test (2026-09-26)
---------------------------------------------
The DT FIT source, devicetree/linux/base/epass-next.dtsi, now selects only
mixer0 and disables mixer1 and tcon_tv0. Wi-Fi OTA of the isolated DT change
with the same kernel booted and retained normal playback state. Board clock
readback showed mixer1, bus-mixer1 and bus-tcon-tv at enable_count=0 with
hardware gates off. The matched Spine battery-side samples averaged
1028.55 mW with both pipelines and 1003.84 mW with one, a 24.71 mW (2.4%)
reduction. The panel keeps its native timing. The source DT is compiled
separately for validation; existing images are not rebuilt or overwritten.
Evidence: workspace power_measure/test-results/20260926-022314-explore/;
isolated construction: power_measure/experiments/display-dt/.

CH32 built-in input driver (2026-09-23)
------------------------------------
Linux patch 0024 integrates the driver into drivers/input/misc with
CONFIG_INPUT_CH32_TOUCH_SLIDER=y. It probes from device tree during boot;
the standalone Buildroot package and S35touch-slider are removed.
The firmware manifest uses src/touch_protocol.h; post-image compares that
header with the actual kernel driver header before assembling images.
After source edits, update patch 0024, run make linux-dirclean, then make.
Deploy kernel and rootfs together to remove the old module/startup script.
Existing deployed overlays containing those files must also be cleaned.
Validation: clean Linux extraction/patch/build and full Buildroot make passed.
vmlinux contains the driver init/probe, modules.builtin records it, and
rootfs.tar contains neither the old .ko nor S35touch-slider. Boot/rootfs
hashes match release-manifest.json. In-tree snapshot and firmware encoder
tests plus 40 firmware/manifest Python tests passed. No board flash/test.

BMC Git source integration (2026-09-21)
-------------------------------------
epass-bmc-firmware now fetches ssh://git@github.com/rhodesepass/bmc_fw.git
at origin/master through Buildroot's Git downloader, without fixed source hashes.
The embedded source copy is removed. The ESP manifest records the repository,
origin/master reference and br-master version; image integrity checks remain enabled.
Both peripheral packages reuse cached origin_master archives. Remove the relevant
origin_master archive and run package dirclean/build to fetch new upstream code.
The private IDF toolchain and images/esp layout remain unchanged. Initial fetch
uses host SSH credentials; no credentials are stored in the package.
Before unpinning, Git download/hash checks, clean BMC compilation, 32 build/manifest tests and
USB/OTA dry-runs passed. The full-tree make attempt was blocked by a separate
CH32 package's zero Git revision placeholder; no new board flash was performed.

ESP single-target board validation (2026-09-21)
---------------------------------------------
Packaged USB flasher wrote/read back all 1255424 app bytes on the real board.
Wi-Fi OTA committed ota_0 -> ota_1 in 13.15 s; BLE with ATT payload 244 committed
ota_1 -> ota_0 in 723.02 s. Both ENDs reported consumed=durable=1255424, error=0.
After each explicit reboot, running/boot partitions matched, the version was
br-29587271d96f, staged/committed were cleared, Linux sync worked, APP armed=1,
and pending=0. Host regressions: 101 passed. No NAND/WCH update, three-chip
mixed board test or power-cut test. Evidence: workspace
ota/artifacts/board-test/20260921-buildroot-esp/README.md.

ESP BMC build and OTA integration (2026-09-20)
--------------------------------------------
epass-bmc-firmware builds a source-hashed snapshot with a separately downloaded
ESP-IDF 6.0.2, compiler and locked private Python environment. Firmware is
installed only to images/esp; its application, initial layout, normal SPL pair
and hashes join the release manifest. No user IDF environment is required.
flasher/ota.py --esp uses bmc target 7 over BLE or Wi-Fi: stage ESP in the
inactive slot, update requested D1s/CH32 images, then commit and optionally
reboot. ESP-only OTA needs no FIT. It is opt-in and not a cross-chip atomic
update. After ESP reboot, reprovision Wi-Fi and query the running version.
See package/epass-bmc-firmware/README.md and flasher/README.md.
Validation: independent SDK install and offline Python dependency checks,
ESP firmware build, full Buildroot make/post-image and 101 host tests passed.
Application size is 1255424 bytes; packaged ESP-only BLE, mixed Wi-Fi and USB
dry-runs passed. No board flashing or new-firmware boot validation in this run.

Unified host flasher (2026-09-20)
--------------------------------
Sources live in flasher/, outside make clean output paths. flasher/flash.py
provides initial/full USB FEL/DFU flashing; flasher/ota.py provides BLE/Wi-Fi
OTA using the local bmc_ota.py client, without external source dependencies.
WCH and ESP updates are
independently opt-in (--wch/--esp, explicit --no-wch/--no-esp). --no-system
allows peripheral-only updates; --dry-run validates inputs without hardware.
USB defaults to four NAND stages; wireless defaults to boot/rootfs,
rejecting SPL, wipe/scrub and identity changes. WCH wireless uses target 6.
USB ESP update reads the partition table and valid OTA selection,
update the active app and optional bootloader, verify readback, and preserve
NVS/otadata/partition table/SPL/storage. Blank provisioning is out of scope.
After system DFU, re-enter FEL for uopbridge. Write/read back WCH before ESP;
the specified ESP port must belong to uopbridge. post-image packages the local
flasher/ directory and USB/OTA shell launchers. See flasher/README.md.
Rootfs OTA replaces the rootfs MTD lower image and preserves the data-backed
overlay upper. There is no separate overlay OTA target or package installer.
USB file uploads can write individual merged-root paths; the BLE/Wi-Fi assets
endpoint has no registered Linux consumer and returns assets_unavailable.
Host regression tests and real-image dry-runs passed; no new board flashing.

CH32 firmware build integration (2026-09-20)
-------------------------------------------
epass_next_defconfig enables ch32-touch-firmware. As of 2026-09-21, sources
are maintained in rhodesepass/tp_fw (master), with a standalone workspace
at ../tp_fw supporting make, host tests and WCH-LinkE/GDB debugging.
The package fetches Git origin/master and uses separately downloaded/
hashed WCH GCC12 without MounRiver paths or a duplicate package/src tree.
Images include ch32-touch.bin/.elf/.map and ch32-touch.json; post-image emits
release-manifest.json with touch explicitly optional. Linux wire-protocol
mismatches fail the build; post-image checks image integrity, the source
reference, repository URL and protocol definitions. Firmware is not installed in rootfs
and normal Linux/USB updates do not implicitly flash it. Before unpinning, full make passed;
10352-byte firmware matches the previously verified real-board program.
The 2026-09-21 Git migration passed standalone and full Buildroot builds,
seven regression tests, check-package (zero warnings), and all 11 release
artifact hashes. No board flashing or target debug attachment was performed.
See package/ch32-touch-firmware/README.md for rebuild and license details.

CH32 touch controller OTA (2026-09-20)
-------------------------------------
U-Boot adds CONFIG_CH32_SWIO/CONFIG_CMD_CH32 with PG13 SWIO and PG15 reset.
The touch target (wire target 6) buffers at most 63488 bytes, checks whole-image
SHA256 before mutation, then erases/programs/verifies 256-byte pages. The final
partial page preserves bytes outside the image. No option-byte or protection
changes are exposed. BMC and both BLE/HTTP clients support touch-only finish.
Patch round-trip and clean Buildroot U-Boot build passed. Real-board HTTP
touch-only END reported 63488 durable bytes; independent minichlink readback
matched and Linux registered the CH32 input device after reboot. See workspace
ota/artifacts/board-test/20260920-touch/README.md for current board evidence.

BMC APP runtime and power control (2026-09-19)
--------------------------------------------
n0.2 enables a 2 MHz SPI0 epass,bmc device. CONFIG_BATTERY_EPASS_BMC=y
provides /sys/class/power_supply/epass-bmc battery data and bmc_version,
boot_epoch, power_state, boot_ready. Only explicit userspace READY after
successful APP initialization and first LVGL frame unlocks power cuts.
The sys-off prepare handler sends POWEROFF after device_shutdown; a failed
request keeps power. Communication loss invalidates battery data.
BMC firmware adds the five-second button force-off and a separate early
bootloader rescue hook, independent of BLE and normal BMC application.
Kernel/DT FIT and APP cross-builds plus host tests passed. Board tests passed
READY, soft poweroff, physical five-second force-off and short-press startup.
USB-only operation returns ENODATA for battery capacity/voltage while status
remains available. One fault-injection run recovered through FEL/uopbridge;
latest rescue timing, battery-only QON interaction and intermittent C3 clock
glitch resets remain outside the passed boundary. Boot and APP720 were
deployed while preserving rootfs/data. See workspace
epass_bmc/docs/app-runtime.md. Initial deployment requires both C3 bootloader
and application updates with identical RTC retention configuration.

BMC update bootstrap (2026-09-13)
--------------------------------
Every wireless update receives the complete u-boot.itb (including OpenSBI)
from the external client through BMC/SPI into RAM before any NAND image.
BMC holds exactly two normal SPL copies (128 KiB each); no dedicated rescue
SPL or cached U-Boot FIT. The normal SPL checks BMC update state before NAND:
normal boot loads NAND, update boot waits for the external FIT. Failed updates
must stop rather than fall back to NAND. ota-rescue remains a command alias.
The physical 512 KiB SPL partition is unchanged, with its unused half erased.
USB flash.py loads complete U-Boot from the host through FEL before DFU;
u-boot-fel.bin is only a packaging variant. FEL mailbox takes priority over
BMC state and old NAND environment. There is one U-Boot configuration/FIT.
BMC firmware and clients stay in workspace epass_bmc (ESP-IDF), not Linux
rootfs. BMC now implements BLE-guided STA/AP and authenticated HTTP channels;
Wi-Fi build/host tests pass and STA/AP were board-tested. Fast experimental
variants reach about 40-47 KiB/s but still exhibit unresolved IWDT resets.
The BMC/ESP partition table has been rolled back to the pre-test backup.
The assets channel still needs a Linux SPI consumer.
See workspace ota/README.md for installation, protocol and test boundaries.
Validation: patches round-trip; clean Buildroot U-Boot build and post-image
passed. Board testing found/fixed SRAM overlap (8 KiB early stack/heap) and
FIT four-byte tail reads. SPI1 selection is explicit in the Buildroot config.
post-image checks ROM-loaded SPL versus GD/heap/stack reservations.
Board tests passed normal NAND boot, external FIT to RAM U-Boot, 256 KiB
verify-only, and NAND U-Boot write/readback (882809 durable bytes), then Linux
login and app_720 startup. Only uboot was updated in NAND; no boot/rootfs/data
reflash or power-cut test. Tested workspace artifacts have their own SHA256
in ota/artifacts/board-test/20260913-single-spl/tested-artifacts.json; do not
substitute independently rebuilt image hashes for the tested ones.

Power key and touch status (2026-09-18)
--------------------------------------
n0.2 gpio-keys reports KEY_0 on PG10, active-low, internally pulled up, with
20 ms debounce. GPIO_PULL_UP lets gpiod own the bias and mux without a
competing static pinctrl claim. CONFIG_KEYBOARD_GPIO and INPUT_EVDEV are on.
CH32 ABS_MISC is a bitmask: 1=position valid, 2=multi-touch, 4=cancelled.
It is submitted with BTN_TOUCH/ABS_X in one SYN_REPORT. Normal release has
BTN_TOUCH=0, ABS_MISC=0 and retains the last X. Applications must handle a
normal release before checking the current position-valid bit.
The first communication error cancels the gesture immediately; 100 ms of
failure additionally releases keys. Synthetic releases (restart, contact
boundary, suspend, stop, failure) carry CANCEL, as do subsequent frames
until real idle. That idle frame remains cancelled; the next frame clears
the latch. Firmware wire protocol and optional key mappings are unchanged.
Driver and MounRiver linux source copies are kept identical. No board
flashing or real power-key/touch functionality was tested in this change.
Validation: ch32-touch-slider-rebuild passed against Linux 7.1.6/RISC-V;
mkdt.sh and boe_035 overlay merge passed. fdtget confirms PG10 flags 0x11,
KEY_0 (0x0b), and debounce 20. MounRiver linux make test passed both snapshot
and actual firmware encoder/decoder tests. Package rebuild still reports
missing .files-list*.before bookkeeping files after successful module
installation; it exits zero. No full rootfs/boot image repack was performed.

CH32 touch slider integration (2026-09-13)
------------------------------------------
Linux patch 0024 contains the driver and v1 protocol headers; clean builds
do not require the MounRiver firmware directory.
The n0.2 base includes ch32-touch-slider.dtsi: 7-bit address 0x2a,
GPIO I2C SDA=PG6/SCL=PG7, IRQ=PG14 active-low with internal pull-up.
This matches fpc_keys pin numbering, which swaps the hardware I2C2 order.
I2C2 is disabled on n0.2; PG13/SWIO and PG15/RST remain unclaimed.
Kernel CONFIG_I2C_GPIO=y supports the slave's clock stretching. The driver
is built in with CONFIG_INPUT_CH32_TOUCH_SLIDER=y.
The driver provides BTN_TOUCH and ABS_X (0..1023); swipe-keycodes remains
optional. Raw 64-byte reads must be one combined I2C transfer, not two
SMBus block reads. i2c-tools and evtest are available for board validation.

Build: make epass_next_defconfig; make
Incremental driver after refreshing the patched source: make linux-rebuild
Diagnostics: i2cdetect -l; cat /proc/bus/input/devices; evtest /dev/input/eventN
The slave holds IRQ low until its current sequence is acknowledged. Unbind
the input driver before manually reading/acknowledging the same address.

Board test result (2026-09-13)
------------------------------
Full Buildroot build passed; rootfs.tar contains the driver, S35touch-slider,
i2ctransfer and evtest. The final n0.2 DTB overlays with boe_035 successfully.
Boot/rootfs were flashed with --only; user data, SPL and U-Boot partitions
were not selected. BMC was returned from FEL to normal boot mode.
The first GPIO-I2C probe failed because its own static GPIO pinctrl state
conflicted with gpiod's claim. Removing that state fixed adapter registration;
GPIO direction is now owned by i2c-gpio, while PG14 keeps its IRQ pull-up.
The real board registers i2c-0, but CH32 0x2a returns ENXIO/no ACK. Both wire
orders and a 50 ms reset pulse were tested; neither order found an address.
SWIO/PG13=1, IRQ/PG14=0, RST/PG15=1. These logic reads do not prove target
supply voltage or signal integrity. No CH32 evdev node is registered yet.
Temporary alternate-bus tests were removed by the final reboot.
The app package had a stale override-source snapshot hardcoded to DRM card0;
rebuilding epass_drm_app incorporated the already-present native-DRM selection
fix. The final flashed system runs the updated app on card1, DSI reports
connected, and USB epass mode works. Board-side app/module SHA256 values
match the final Buildroot target files. CH32 still returns no ACK.
Logs and image hashes: output/ch32-validation/ (not source-controlled).
Next hardware step: inspect CH32 I2C registers and SCL/SDA at the MCU pins;
do not infer input or gesture success from successful image flashing.

APP schematic alignment (2026-09-10)
-----------------------------------
Export evidence: epass_bmc/build/pin-audit/mainboard.xml (kicad-cli netlist).
Current n0.2 wiring: LCD PWM5/PG4, reset PG12; three DSI data lanes on
PD0..PD7 including the clock pair. BOE overlay already selects three lanes.
U-Boot splash pinmux follows these pins as well. SD remains MMC0/PF0..PF5;
USB0 remains peripheral, USB1 host controllers are disabled (pins NC).
Headphone codec routing remains valid. The CH32 key FPC is now described
by the 2026-09-13 GPIO-I2C/IRQ integration above. CH32 SWIO PG13 and reset
PG15, and PG10 (PWRBTN via D2) remain unclaimed.
No separate display touch controller is wired to APP; the CH32 key FPC
is the input interface described above. BMC GPIO defines
remain authoritative for the present board; schematic ESP pins are next rev.
No board has been flashed for this alignment; DTB/U-Boot build validation
is separate from functional tests on the current assembled board.

Current boot wiring (2026-09-10)
--------------------------------
The BROM reads eGON SPL from the ESP32-C3 SPI NAND emulator on SPI0.
SPL then selects SPI1 (0x04026000, CCU 0x944, PD10..PD13 function 4)
and reads u-boot.itb from physical NAND offset 0x40000. U-Boot and Linux
use SPI1 quad mode on PD10..PD15, matching the mainboard schematic.
UART3 on PG8/PG9 connects to the ESP32-C3 console bridge. The old n0.2
switch-3/switch-4 GPIO key nodes are removed because they claim these pins.
PG6/PG7 belong to the key FPC bus (now GPIO I2C); all old discrete GPIO keys are removed.
The NAND partition offsets are preserved; its boot0 copy is no longer the
BROM boot source. Program sunxi-spl.bin into the selected BMC raw SPL slot.
Validation: U-Boot including SPL/FIT builds; Linux DTB and layered dtbs.itb
build; both patch series round-trip to the working trees. The production SPL
reader passes a host ASan/UBSan test for byte/page/block offsets, bad blocks
and partition bounds (tests/test_spl_spinand_read.py in the eprv workspace).
SPL is 90112 bytes; u-boot.itb is 877289 bytes.
This wiring migration requires real-board boot validation; the previous
SPI0 hardware results do not validate this SPI1 route.

Arknights ePass Next (Allwinner D1s)
====================================

D1s port of the T113-s3 board. Pin compatible, but NOT drop-in: the SoCs carry
different in-package DRAM, and that difference has to be handled in the SPL
before the DRAM controller is touched at all.

  T113-s3   DDR3, 1.35V
  D1s       DDR2, 1.8V    <- mainboard EA3036 fixed rail

The current mainboard has no AXP209; PB2/PB3/PB4 are unconnected.
SPL must leave CONFIG_SUNXI_DRAM_VCC_AXP209_DCDC2 disabled. The Linux
PMIC node was removed so it cannot probe a device absent from the board.
The VCCDRAM selection resistors (R48/R49) must match the fitted D1s DDR2.

Building
--------
  make epass_next_defconfig
  make

Mainline U-Boot has no D1/RISC-V sunxi support at all (nothing under
arch/riscv, no D1 defconfigs -- only the ARM T113/R528 side reuses
dram_sun20i_d1.c), so this pulls smaeul's d1-wip, same as buildroot's own
nezha_defconfig does.

Console
-------
Kernel log goes to both the panel (console=tty0) and the serial port
(console=ttyS3), with ttyS3 as /dev/console so the getty stays on serial.
tty0 needs CONFIG_VT plus fbdev emulation -- with VT off nothing ever drives
a modeset and the panel stays dark even though every driver probed fine.

Flash layout
------------
128MB SPI NAND, 2K page, 128K erase block; every boundary is a whole number
of erase blocks.

  0x0000000  boot0    256K  reserved legacy SPL copy (BROM now reads BMC)
  0x0040000  uboot      1M  u-boot.itb (OpenSBI fw_dynamic + U-Boot proper)
  0x0140000  bootenv  128K  one erase block, so a rewrite is one erase
  0x0160000  boot      10M  dtbs.itb in a 1M slot, then kernel.itb
  0x0B60000  rootfs    28M  ubi0, one 24M read-only volume
  0x2760000  data    88.6M  ubi1, rootfs_data

The same table appears in three places and nothing checks that they agree:
the Linux board dts, the U-Boot board dts and post-image.sh.

The bus runs quad: SPI1 uses PD10 CS, PD11 CLK, PD12 IO0, PD13 IO1,
PD15 IO2 and PD14 IO3. Its pinctrl group drives all six pads at 20mA, and the flash node carries spi-rx-bus-width and
spi-tx-bus-width. Both halves are needed. Without the widths spinand never
gets SPI_RX_QUAD in spi->mode, spi_mem_supports_op rejects every x4 entry in
the chip's variant table, and it settles on the 1S-1S-1S read without saying
so.

The boot partition holds two FITs rather than one, in the arrangement the
F1C generation used and the flasher already knows how to produce: the device
tree bundle at the front in a slot of its own, the kernel right after it.
They are separate because which tree to use is not known until U-Boot has
read the board's identity, while the kernel is the same for every board.

rootfs and data are separate MTD partitions rather than two volumes of one
UBI device, and that separation is the whole point: flashing rewrites rootfs
and leaves data untouched, so an upgrade keeps the user's data. flash.sh
does exactly that; flash-all.sh erases data as well, after which preinit
rebuilds it empty.

The system volume is a fixed 24MiB rather than autoresize, so a firmware
that outgrows its partition fails the build instead of being discovered on a
device. post-image.sh checks every payload against its partition for the
same reason -- it caught a bad dtb offset the first time it ran.

The kernel goes in as a FIT with the Image gzipped: RISC-V has no
self-decompressing image and booti will not take a compressed one, so the
container has to do it and bootm inflates on the way in. That is 6.8M of
Image in 3.5M of flash. The raw Image stays in images/ because the FEL path
pushes it straight to DRAM.

rootfs layering
---------------
The root is an overlay assembled by /preinit (init=/preinit), ported from
the F1C board minus its SD path:

  lower    the read-only UBIFS the kernel mounted from ubi0
  upper    on ubi1:rootfs_data, the separate data partition
  work     likewise

So the running system is writable while nothing ever writes to the system
volume. preinit rebuilds the data partition in place if it will not mount --
first flash, migration leftovers, damaged media -- which factory-resets the
data and leaves the system alone; only a second failure is fatal. It also
honours a .factory_reset flag in the upper, which has to be handled here
because once the overlay is up the running root *is* that overlay.

The kernel does not carry an initramfs. It did during bring-up, when the
NAND was not fitted and UBI was unreachable, but an embedded initramfs *is*
the root filesystem as far as the kernel is concerned: root= is never
consulted, so preinit never runs and the overlay is never assembled. It cost
1.5M of the boot partition on top of that.

Userspace startup
-----------------
Everything under overlay/ is copied over the target as the rootfs overlay, so
it lands after the packages and wins any conflict -- that is how /etc/mdev.conf
replaces the one busybox installs. Sysvinit-style scripts, run by busybox init
through rcS in name order:

  S00zram     16M of compressed swap
  S00sdsetup  first-boot growth of an SD-booted rootfs, and the share partition
  S01app      the app supervisor: picks app_720 or app_360 by the panel's
              compatible, mounts the card, restarts the app forever and acts
              on the exit code it asked to be restarted with
  S02sdwatch  the pulled-card daemon, for when the root filesystem is the card
  S99usbaio   usb_aio_handler, held back until the app is up so the gadget
              enumeration does not race it for display and storage

They come from the F1C board and three of them are inert here for now. The two
SD ones exit on the first line, because root= is ubi and both test for it, and
sdwatch's binary has not been ported either; they are in place for the SD boot
path that is planned rather than because anything runs them today. Card
*hotplug* does work -- mmc0 is enabled, so a card shows up as mmcblk0p1, mdev
calls /usr/sbin/sd-hotplug and /sd is mounted through /usr/sbin/sdmount, the
single entry point that both the hotplug hook and S01app go through under an
flock.

Nothing starts an MTP daemon, but the overlay still carries umtprd config:
usb_aio_handler has umtp-responder built into its mtp function, and that
function copies /etc/umtprd/umtprd_{sd,nosd}.conf over umtprd.conf before it
loads, picking by whether /sd is actually mounted. The two differ only in
whether the card's directories are exported. Both cut the transfer buffers
from the stock 64K/64K/1M to 16K/16K/64K, which is what 64MB of DRAM affords.

The storage entries those configs export -- /app, /assets, /dispimg -- are
directories in the overlay for the same reason: they belong to the read-only
lower, and a host writing into them over MTP copies them up into the data
partition like any other write.

What did not come over: S00dramqos, which programs the F1C's DRAM controller
port arbiter and means nothing on this SoC; S15battery_hwcd, whose binary is
not packaged in this tree yet. U-Boot paints a splash; see the DSI handover
section below for the current ownership boundary.

Output
------
  flash.py                     the flasher; run it from the buildroot root
  output/images/sunxi-spl.bin  boot0
  output/images/u-boot.itb     OpenSBI fw_dynamic + U-Boot proper
  output/images/boot.itb       dtbs.itb padded to 1M, then kernel.itb
  output/images/rootfs.ubi     ubi0
  output/images/u-boot-fel.bin U-Boot with its dtb appended, for the FEL run
  output/images/flash.sh       raw xfel writes, for brick recovery

Flashing
--------
  ./flash.py                       keep user data
  ./flash.py --wipe                factory reset as well
  ./flash.py --scrub               and wipe the factory bad block markers
  ./flash.py --rev n0.2 --screen boe_035

This is the normal path and it needs nothing but xfel and dfu-util. See "The
Mostima flashing mailbox" below for what it actually does.

If U-Boot itself is too broken to come up and serve DFU, fall back to writing
the chip directly from FEL:

  cd output/images && ./flash.sh       # keeps the data partition
  cd output/images && ./flash-all.sh   # erases it first

That is much slower and cannot set the board's identity, so a board flashed
this way falls back to the defaults compiled into the environment.

FEL bring-up (no boot media needed)
-----------------------------------
With the SPI NAND depopulated the SPL detects a FEL boot and hands control
back to the BROM once DRAM is up, so the host can push OpenSBI + kernel
straight into DRAM over USB:

  xfel write 0x20000 sunxi-spl.bin && xfel exec 0x20000   # DRAM up, back in FEL
  xfel write 0x40000000 fw_jump.bin
  xfel write 0x43000000 sun20i-d1s-epass-next.dtb
  xfel write 0x40200000 Image
  xfel exec  0x40000000

Two things make that work, both in patches/uboot/0003: the SPL must restore
the full callee-saved register set *and* mie/mtvec/mstatus before returning
(the FEL loop is interrupt driven, and the SPL masks all interrupts), and
uart3 is brought up in _start because xfel writes SRAM as data without ever
invalidating the icache -- running a helper payload first leaves stale
instructions cached at 0x20000.

Memory budget
-------------
64MB total, and the single biggest win here has nothing to do with what is
built in: the riscv defconfig picks SPARSEMEM, whose section bookkeeping is
sized against the whole physical address space. On one contiguous 64MB bank
that costs about 17MB. FLATMEM sizes the memmap against the RAM that exists:

                    SPARSEMEM/CMA 16M    FLATMEM/CMA 32M
  kernel-managed           39.3 MB            56.7 MB
  MemAvailable             14.4 MB            31.8 MB
  boot to login              35 s               22 s

It surfaced as a panic ("memblocks_present: Failed to allocate 0x1000000")
when CMA went to 32M, which looks like CMA being too big and is not. If this
board ever seems short of memory again, check the memory model before
cutting CMA.

The kernel config is a full one rather than arch-default-plus-fragment,
because a fragment can only add. What the riscv defconfig switches on by
default was the bulk of the image: a complete TCP/IP stack with netfilter,
IPVS, bridging and VLAN on a board with no networking hardware at all, and
the DVB stack with some fifty satellite tuner drivers behind the media menu.
Removing both took .text from 6.5MB to 4.9MB.

The second pass was the other RISC-V platforms, which the defconfig also
turns on and which are easy to miss because none of them is a subsystem:
StarFive JH7100/JH7110, SiFive, Sophgo CV1800/SG2042, TH1520, Canaan,
PolarFire, plus virtio, SDHCI+Cadence, SERIO/ATKBD and DW-HDMI. Switching
off the ARCH_* symbols takes their drivers with them. That is 344K off
Image *after* adding the audio codec, and most of it is .data -- match
tables and driver structures rather than code:

                     before      after
  .text            5394796    5346042
  .data            2132520    1828848
  Image            7532032    7179776

RISCV_APLIC and RISCV_IMSIC survive that pass: arch/riscv/Kconfig selects
them unconditionally, so the D1 carries two interrupt controllers it does
not have.

CMA is 32MB -- what the F1C platform needed to keep cedrus fed under load --
and backs every DRM and cedrus buffer, because the IOMMU cannot be used
(below). CMA pages remain available to movable allocations while the decoder
is idle, so this is not 32MB spent.

The IOMMU dead end
------------------
The D1 has an IOMMU and patch 0001 carries a working driver port for it, but
DE behind it is broken on this silicon: one translated scanout channel works,
and the moment a second mixer channel starts fetching the whole screen
collapses into white with fine vertical stripes -- no IOMMU fault, page
tables verified correct, full TLB flush no help, and none of the prefetch /
out-of-order / write-buffer / auto-gating knobs (poked live over devmem)
change anything. The tell is in the vendor kernels: both the D1 and T113 BSP
dts pin DE to bypass (iommus flag 0) while translating VE/G2D/DI/CSI, so DE
behind the IOMMU is a configuration Allwinner never validated. Mainline H6
does run DE translated -- different IOMMU generation, no help here.

With DE stuck on physical addresses, VE has to stay on them too: decoded
frames are scanned out directly, and a translated VE would hand DRM
non-contiguous dmabufs the bypassed DE cannot import. So the IOMMU buys
nothing on this board; the driver is compiled out and the dts carries no
iommu node.

Display
-------
mixer0 -> tcon_top -> tcon_lcd0 -> DSI, 720x1280. Patch 0008 splits the UI
channel into its four hardware overlays, so the CRTC exposes five planes:
primary on the VI channel plus four UI overlays. Overlay z-order is fixed by
the hardware (immutable zpos) and the UI planes cannot scale -- the channel
has a single scaler, which the split forces off.

Indexed colour (patch 0010)
---------------------------
UI planes also take DRM_FORMAT_C8: 8-bit indices into a 256-entry ARGB8888
palette, a quarter the buffer and the scanout bandwidth of ARGB8888, with
per-index alpha. The palette belongs to the channel, not to a plane -- all
four UI overlays index the same table -- so it is uploaded as 1024 bytes of
little-endian ARGB8888 to

  /sys/devices/platform/soc/5100000.mixer/palette

Upload order does not matter: the RAM refuses writes while the layer is
down, so the driver keeps a shadow and replays it once a layer appears.
Reads return that shadow, since the RAM itself always reads back zero.

None of these registers are documented -- see the patch for what was
established on hardware, and note in particular that the vendor driver's
two-dbuff upload dance is not required.

Video decode
------------
cedrus drives the VE; /dev/video0 with MPEG-2, H.264 and HEVC slice input.
`cedrus-probe` on the target dumps the queues and the layouts it settles on.

Take the *untiled* NV12 capture format, not SUNXI_TILED_NV12/NV12_32L32.
The tiled one is the VE's native output and what the F1C build uses, but
DRM_FORMAT_MOD_ALLWINNER_TILED only exists in the old sun4i backend path --
the DE2 mixer advertises LINEAR alone, so AddFB2 on a tiled buffer fails and
the frame cannot be scanned out. Untiled costs nothing: it is a hardware
output mode (VE_PRIMARY_OUT_FMT), not a driver-side detile, and D1's variant
carries CEDRUS_CAPABILITY_UNTILED.

Untiled NV12 is bytesperline = ALIGN(width, 16), height = ALIGN(height, 16),
chroma straight after luma -- so at 720x1280 nothing is padded at all, and
the buffer imports as plain DRM_FORMAT_NV12 onto a VI plane. Verified: the
VE offers it, and the mixer scans NV12 out.

The tick trap
-------------
Two dts nodes exist only to keep the kernel's tick running, and both are
needed. Miss either one and jiffies freeze about a second into boot:

  - clint@14000000. M-mode only, so Linux never touches it and the SoC dtsi
    does not describe it -- but OpenSBI needs it to provide SBI TIME. Check
    the banner: "Platform Timer Device: aclint-mtimer @ 24000000Hz" is right,
    "--- @ 0Hz" means SBI_SET_TIMER is a no-op.
  - timer@2050000 disabled. Its clockevent rating (350) beats the riscv/SBI
    one (100) so it wins the tick device, but it sits on PLIC irq 59, which
    never fires here.

The failure does not look like a timer problem. Nothing oopses, no hung task
is reported, mdelay() still works (it spins on a CSR) and printk timestamps
keep advancing (sched_clock reads the same CSR) -- but every msleep() blocks
forever. It surfaces as the DSI panel hanging in st7703_enable(), fbcon never
starting, and getty never printing a prompt.

Debugging it needs a print that survives console_lock: register_framebuffer()
takes over the console, so anything printk emits under it only reaches the
ring buffer and is lost when the CPU stops. sbi_debug_console_write() goes
straight out over SBI DBCN and is what actually located the hang.

Audio
-----
The codec is one IP in two halves: the digital DAC/ADC and its FIFOs at
0x02030000, driven by sun4i-codec, and the analog side -- PGA, headphone
amp, mic bias -- at 0x02030300, driven by sun20i-d1-codec-analog. The dts
carries both as separate nodes tied by allwinner,codec-analog-controls,
because they are two drivers.

Neither the nodes nor the D1 support in sun4i-codec are upstream; both come
from the T113 tree (../linux-next) and land here as patch 0013. Two things
about that port are worth knowing:

- The analog half is plain MMIO on this SoC, not the ADDA-PR indirect
  register bus the older parts use. sun8i-codec-analog also carries a
  sun20i-d1-codec-analog match in the T113 tree, left over from an earlier
  attempt; it is dropped here, because two drivers claiming one compatible
  bind by link order and the ADDA-PR one cannot work.
- Only playback is exercised. The capture path came over with the rest and
  the T113 tree's own commit calls it incomplete.

Card slot
---------
mmc0 is enabled with broken-cd -- the detect pin is not wired to the SoC, so
the core polls for a card. Nothing in the boot path uses it; the root
filesystem still comes from UBI on the SPI NAND.

Thermal and cpufreq
-------------------
The SoC dtsi already describes both: an OPP table with 408MHz and 1008MHz,
and a cpu-thermal zone that passively caps the CPU at 85C and shuts down at
100C. cpufreq-dt picks the board up because cpu0 carries operating-points-v2
-- the machine is not in cpufreq-dt-platdev's allowlist, and does not need to
be.

What was missing until now is the sensor. THS is described and enabled in the
dtsi, but CONFIG_SUN8I_THERMAL was off, so the thermal framework was built in
with nothing to measure and the zone above never did anything. It is on now.

Voltage does not scale with the frequency: both OPPs ask for 900mV and
vcc-core is a fixed rail, not a PMIC output. Switching to 408MHz saves what
the lower clock saves and nothing more.

Known gaps
----------
- The GPADC and the LEDC (the WS2812 controller) are left disabled -- neither
  is wired on this board. Battery management belongs to the BMC; no APP PMIC ADC is described.
- RISCV_APLIC and RISCV_IMSIC are compiled in although the D1 has only a
  PLIC: arch/riscv/Kconfig selects both unconditionally, so they cannot be
  switched off without patching it.
- The IOMMU driver (patch 0001) is carried but not built -- see "The IOMMU
  dead end" above.


Board identity: revisions, screens, and the bootenv partition
-------------------------------------------------------------
One firmware image runs on every ePass Next. What differs between two boards
is recorded on the board itself, in the bootenv partition: a plain text
env.txt that U-Boot imports before it decides anything.

  device_rev=n0.2
  screen=boe_035

device_rev names a hardware revision. "n" is Next, as against "p" for the
prev-generation F1C boards, whose revisions run p0.1 upward -- the two
generations share a flasher and a device manager, so the letter is what keeps
their revision numbers from colliding. screen names the panel; boe_035 is the
same 3.5" BOE part the F1C boards use.

bootenv is not U-Boot's environment. The environment itself is
CONFIG_ENV_IS_NOWHERE: compiled in, never written back, identical on every
board. That is deliberate. If the environment were writable, a board's
identity and its boot logic would live in the same place, one "saveenv" could
destroy either, and recovering a board would mean knowing what its
environment used to say. Keeping them apart means the boot logic is a
property of the firmware and the identity is a property of the board, and
reflashing can rewrite one without touching the other.


Device trees: four layers
-------------------------
The tree the kernel gets is assembled at boot from up to four pieces, matching
the F1C boards:

  base       devicetree/linux/base/devicetree-<rev>.dts   one per revision
  screen     devicetree/linux/screen/<panel>.dts          the panel
  interface  devicetree/linux/interface/<name>.dts        optional
  ext        devicetree/linux/ext/<name>.dts              optional

The base is a full tree; the other three are overlays. mkdt.sh compiles them
all into dtbs.itb, and generates the FIT source from whatever is actually
present -- adding a panel is dropping a .dts in screen/ and rebuilding,
nothing else. dtc gets -@ so the base carries __symbols__; without it the
overlays' &panel and &backlight references have nothing to resolve against
and "fdt apply" fails.

The layering happens in U-Boot, not in the kernel and not at build time:

  imxtract dtbs.itb fdt-base-n0.2     -> dtbaddr
  fdt apply fdt-screen-boe_035
  fdt apply fdt-iface-<each>          from ${interface}, if set
  fdt apply fdt-ext-<each>            from ${ext}, if set

It has to be U-Boot because the revision is only known once bootenv has been
read, and it has to be at boot rather than at flash time because the same
image is written to every board.

The base layer holds everything true of the revision regardless of what is
plugged into it: memory, regulators, the PMIC, pinctrl, the SPI NAND and its
partitions, the display engine and DSI host, the video engine, the backlight
PWM, the key GPIOs, and the panel node stripped down to reset-gpios and its
supplies. The screen overlay fills in the rest of the panel -- compatible,
backlight, rotation. So a panel swap is one file and never touches the base.

U-Boot has its own, separate tree: devicetree/uboot/sun20i-d1s-epass-next.dts,
minimal by design -- console UART, SPI NAND with the partition table DFU
derives its alt settings from, USB for the flashing mailbox, and the CLINT
node OpenSBI needs for its timer. It is not carried as a patch: buildroot
copies it into arch/riscv/dts/ at build time
(BR2_TARGET_UBOOT_CUSTOM_DTS_PATH), so a dts edit takes effect with plain
"make uboot-rebuild", no dirclean. sync-patches.sh keeps it in step with the
u-boot working tree the same way it regenerates the patches.


The boot state machine
----------------------
bootcmd in uboot.env, in order:

  mtdinit      force the SPI NAND to probe. Driver model probes on demand and
               nothing has asked for it yet, so without this the partitions do
               not exist and "mtd read boot" fails with -ENODEV.
  load1env     read the Mostima mailbox; flash the board if that is why we are
               here; then import bootenv, defaulting rev and screen if it is
               blank so that a freshly flashed board still reaches a prompt
  loaddtbs     read dtbs.itb, extract the base tree for this revision
  applyscreen  layer the panel overlay; a missing one is not fatal, the board
               just comes up headless
  applyiface   ) space separated lists from bootenv, normally empty
  applyext     )
  loadkernel   read kernel.itb over the dtbs bundle at the same address --
               which is why loaddtbs must finish extracting first
  setbootargs  build the command line
  bootm        inflate and go

Anything that cannot be recovered from runs failsafe, which stops at the
prompt rather than resetting: a board that reboot-loops is harder to rescue
than one sitting still, and this one has a FEL button.

All offsets into the boot partition are relative to the partition, so the MTD
layer's bad-block skipping keeps them true. The F1C boards address the raw
device instead and have to scan for the kernel FIT header.


The Mostima flashing mailbox
----------------------------
flash.py does not write the SPI NAND from the host. It runs U-Boot on the
board and lets U-Boot do it, which is both much faster over USB and the only
way the board can be told who it is.

  1. Load the SPL over FEL with its eGON magic altered from BT0 to FEL, so it
     brings up DRAM and returns to the BROM instead of chaining onward. xfel
     has no built-in DDR init for the D1s; this is that step.
  2. Write the mailbox to DRAM, then OpenSBI, U-Boot, the U-Boot dtb and a
     fw_dynamic_info saying "next stage is U-Boot, S-mode".
  3. Jump via a seven-instruction shim. flash.py assembles it itself, so
     flashing needs no cross toolchain -- only xfel and dfu-util.

     The tree handed to OpenSBI must be the one appended to the U-Boot image,
     not a copy of it. OpenSBI stamps its own PMP memory reservations into
     whatever tree it is given, and U-Boot later copies them out of *its own*
     fdt into the kernel's -- riscv_fdt_copy_resv_mem_node(gd->fdt_blob,
     blob). Point OpenSBI at a separate copy and the reservations are silently
     lost: the kernel then sees one unbroken 64M instead of two ranges either
     side of a 384K hole, and faults as soon as it allocates inside OpenSBI's
     region, which PMP denies S-mode entirely. Booting from flash never hits
     this, because there the SPL hands OpenSBI the tree that came with U-Boot
     in the first place.
  4. That U-Boot's bootcmd runs mstmchk, finds the mailbox, writes the
     identity to bootenv, honours the wipe flags, and serves DFU.
  5. Four images go down in one DFU session. DFU_DETACH at the end makes
     U-Boot leave DFU, and bootcmd resets the board.

     Resetting rather than booting on is deliberate. The U-Boot doing the
     flashing arrived over FEL, and that leaves the SoC in a state a cold boot
     does not: with identical CCU registers a 300M memcpy measures 0.75s
     against 0.29s after a reset, which is what DRAM running uncached looks
     like. The return-to-FEL path restores mstatus and the callee-saved
     registers, and the C906's cache and memory-attribute CSRs are not
     ordinary architectural state that anything puts back. Booting on would
     hand the user a system at a third of its speed until the first power
     cycle, so the two seconds a reset costs are worth it.

Mailbox layout, byte for byte the same as the F1C generation so that one
host-side flasher drives both:

  0x00  8  magic "Mostima_"
  0x08  1  boot type: 1 = NAND flow, 2 = SD flow
  0x09  1  flags
  0x0a  2  padding
  0x0c  4  u32 LE length of the env payload, including its NUL
  0x10  n  env text for "env import -t", e.g. device_rev= / screen=

Boot type 2 is reserved and unimplemented here: this board has no card slot
fitted. The number is kept anyway so the two generations do not disagree
about what 2 means when the slot arrives.

Flags, handled by mstm_prep:

  0x01  wipe user data. Flashing normally leaves the data partition alone,
        which is what makes a full reflash a data-preserving upgrade.
  0x02  full-chip force erase and bad block rescan. Wipes factory bad block
        markers along with everything else and lets them be rediscovered from
        the erase results. Implies 0x01. This also erases boot0, uboot and
        bootenv -- U-Boot is running from DRAM at that point and the DFU run
        rewrites them, but an interruption in between means FEL recovery.
        Unlike the F1C generation this needs no U-Boot patch: 2026.07's
        nanddev_erase() already drops the BBT entry and erases anyway, and a
        block whose erase fails keeps its on-chip marker, so the table rebuilds
        itself correctly on the next attach.

U-Boot zeroes the magic once it has consumed the mailbox, so a plain reboot
does not walk back into the flashing path.

Where the mailbox goes is not arbitrary. It has to survive from the FEL write
until bootcmd reads it, which rules out most of DRAM:

  0x40000000  OpenSBI, up to _fw_end at 0x40045000, PMP-protected
  0x40100000  the mailbox. This hole is structural -- OpenSBI cannot grow into
              it and the kernel's load address is above it
  0x40200000  the kernel
  0x41000000  the FIT/dtb/env scratch addresses from uboot.env
  0x42e00000  U-Boot proper, 0x43e00000 its pre-relocation stack
  0x44000000  top of DRAM. U-Boot relocates itself to just below here, which
              is why the mailbox cannot simply live at the end

CONFIG_MSTMCHK_ADDR in the U-Boot defconfig and mstmaddr in uboot.env both
carry this address and have to agree.

DFU offers four alt settings: spl, uboot, boot, rootfs. bootenv is not one of
them -- it comes from the mailbox, so the flasher cannot contradict the
identity it just declared. data is not one either: it belongs to the user, and
mstm_prep is the only thing allowed to touch it.


Keeping the patches in step
---------------------------
2026-09-19 audio: D1 card routes now reference ADC1/ADC2, matching the
analog widgets. The six missing-route errors prevented the entire sound
card from registering, including playback. Updated kernel was written at
boot partition offset 0x100000 and SHA256 readback matched; DT, rootfs,
bootloader and user data were retained. The rebooted kernel registers
D1 Audio Codec successfully.

TinyALSA 2.0 also needs the package patch preserving appl_ptr when reading
state through SYNC_PTR on RISC-V. Direct WRITEI_FRAMES plus DRAIN played
480000 stereo frames at 48 kHz in 10.015 seconds. Test signal is left 1 kHz,
right 2 kHz, amplitude 8191/32768, DAC volume 63, front volume 160/160,
headphone volume 4 (-18 dB). Electrical output awaits oscilloscope evidence.
Patched TinyALSA was tested on the same board: the same 10-second WAV now
takes 9.96 seconds in tinyplay, versus 0.31 seconds with the old library.
The fixed library was atomically installed in the board overlay and its
SHA256 matched the host build. A fresh 600-second stereo tone was started.
Further scope testing found DC-only HPOUT on both channels. Comparing the
local Tina sun20iw1-codec BSP identified missing HPLDO power and DAC unmute.
Enabling those bits with the BSP's 30 ms delay produced waveforms on both
channels, confirmed by the user. The driver now implements this in DAPM;
headphone ramp is an output driver, ordered after DAC power-up and before
DAC power-down, with 100 ms settling delays. Kernel #4 was flashed and
readback-verified. After reboot, first play, idle and second play correctly
toggle power/unmute/ramp without manual register writes. The user confirmed
both waveforms remain normal on the scope after reboot, completing playback
validation of the persistent fix. The board revision bits are 3 (automatic ramp);
the A-silicon manual HP2 sequence is outside this validation.
See workspace ota/artifacts/board-test/20260919-codec/ for test sources.

The kernel and U-Boot are worked on as ordinary git checkouts next to this
tree (../linux-7.1.6, ../u-boot-2026.07) and reach the build as the patch
series in patches/. Those are two separate steps, and forgetting the second
is silent: buildroot keeps using the tree it unpacked and patched the first
time, and "make linux-rebuild" only recompiles. That has cost a flash-and-test
cycle three times.

  ../sync-patches.sh

regenerates both series from the working trees, applies each to a pristine
checkout and compares it against the tree it came from, then dirclean's both
so the next build re-unpacks. Run it after touching either tree.

2026-09-10 BMC debug route
--------------------------
UART3 now uses PG8 TX -> C3 GPIO20 RX and PG9 RX <- C3 GPIO21 TX at
115200 baud. SPL selects CONFIG_SUNXI_SPL_UART3_PG; the default early-UART
route remains PB6/PB7 for other boards. U-Boot, OpenSBI stdout-path and Linux
keep serial3/ttyS3 and select the same PG pins. U-Boot pinctrl handles UART3
function 5 on PG8/PG9 while retaining function 7 on PB6/PB7.

The C3 recovery image is generated by epass_bmc/tools/make_fel_spl.py: an
eGON.BT0 image with a 1024-byte checked length. It disables the ROM-enabled
I-cache, fences instructions and jumps to the locally disassembled ROM
FEL vector 0x20. It needs no DRAM or saved FEL caller frame. After USB FEL
enumerates, load uopbridge as usual; do not reuse fel-boot/spl-fel.bin as a
cold boot image because that image expects an existing FEL return frame.
Build validation does not establish BLE capture, FEL USB enumeration or
uopbridge flashing on hardware.

2026-09-10 board validation: ESP32-C3 provides the 90112-byte SPL on BootROM
SPI0; SPL reads W25N01GV on hardware SPI1 (0x04026000). OpenSBI 1.9,
U-Boot 2026.07, Linux 7.1.6 and the UBIFS/overlay root reached login.
UART3 PG8/PG9 was captured and used for a shell through BMC BLE. Linux's
logical spi0.0 resolves to /soc/4026000.spi; it is the hardware SPI1 bus.
Independent U-Boot builds must also apply the default environment setting
normally added by Buildroot's Kconfig fixup, so Mostima/DFU is present.

DSI handover (2026-09-10)
-------------------------
LCD reset is PG12, active low, in both the Linux panel DT and U-Boot's
merged-DT-driven splash. Intermittent Linux DCS B9 -110 was reproduced with
the running U-Boot splash. Skipping splash passed 3/3 boots; clearing the
DSI instruction start bit and pulsing CCU MIPI reset passed another 3/3.
These are small diagnostic samples, not a long-run reliability result.

srgn_splash now owns a board_quiesce_devices() hook: at bootm handover it
stops the DSI instruction engine, TCON requests and mixer DMA, powers down
D-PHY, and leaves shared MIPI reset asserted for Linux probe to deassert.
Bus gates and shared PLL_VIDEO0/PERIPH clocks are retained. Failed panel or
FDT setup is cleaned up too; the hook is a no-op without hardware ownership.
The U-Boot logo remains visible until handover, but continuous scanout during
Linux boot is no longer guaranteed. Framebuffer reservation/free-on-takeover
metadata is retained. The fixed build still requires board verification.
See epass_bmc/docs/dsi-handoff.md in the workspace for evidence and limits.

2026-09-11: The srgn_splash OS-handoff cleanup was flashed with --only uboot.
Five consecutive normal boots reached login without the intermittent DCS -110.
PG12 reset wiring was retained. Detailed A/B evidence: epass_bmc/docs/dsi-handoff.md.
