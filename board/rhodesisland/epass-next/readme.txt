Audio fixes cover D1 codec routes and HPLDO/DAC/RAMP sequencing plus TinyALSA
SYNC_PTR status queries preserving the application pointer.

Linux board wiring now includes built-in BMC runtime and CH32 touch drivers.
post-image compares the touch protocol header; deploy kernel and rootfs together.

Boot integration: SPI0 BMC SPL, SPI1 NAND, PG8/PG9 UART3, external FIT OTA,
CH32 SWIO updates, and post-image SPL SRAM overlap checks.

Arknights ePass Next (Allwinner D1s)
====================================

D1s port of the T113-s3 board. Pin compatible, but NOT drop-in: the SoCs carry
different in-package DRAM, and that difference has to be handled in the SPL
before the DRAM controller is touched at all.

  T113-s3   DDR3, 1.35V
  D1s       DDR2, 1.8V    <- fed from AXP209 DCDC2

DCDC2 powers up at ~1.25V and the BROM never touches the PMIC, so a stock SPL
runs DRAM training against an undervolted DDR2 and wedges the SoC hard enough
to take the FEL loop down with it. patches/uboot/0002 raises it over TWI0
before uclass init. reg_dcdc2 in the dts must agree with that value, or the
regulator core drops the supply back the moment the AXP209 driver probes.

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

  0x0000000  boot0    256K  SPL, eGON header, read by the BROM
  0x0040000  uboot      1M  u-boot.itb (OpenSBI fw_dynamic + U-Boot proper)
  0x0140000  bootenv  128K  one erase block, so a rewrite is one erase
  0x0160000  boot      10M  dtbs.itb in a 1M slot, then kernel.itb
  0x0B60000  rootfs    28M  ubi0, one 24M read-only volume
  0x2760000  data    88.6M  ubi1, rootfs_data

The same table appears in three places and nothing checks that they agree:
the Linux board dts, the U-Boot board dts and post-image.sh.

The bus runs quad: spi0's pinctrl group covers PC6/PC7 (WP and HOLD becoming
IO2 and IO3) at 20mA, and the flash node carries spi-rx-bus-width and
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
not packaged in this tree yet; and the splash handover in S01app, since U-Boot
here does not paint one.

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
  is wired on this board. AXP209's own ADC covers the battery rails.
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
