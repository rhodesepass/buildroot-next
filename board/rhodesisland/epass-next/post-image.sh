#!/bin/sh
# Assemble the flashable pieces for the Arknights ePass Next (D1s).
#
# Layout must match the partition tables in BOTH sun20i-d1s-epass-next.dts
# files (Linux and U-Boot); nothing checks that they agree.
#
#   0x0000000  boot0    256K  SPL (eGON header, loaded by the BROM)
#   0x0040000  uboot      1M  u-boot.itb (OpenSBI fw_dynamic + U-Boot proper)
#   0x0140000  bootenv  128K  one erase block, env.txt
#   0x0160000  boot      10M  dtbs.itb in a 1M slot, then kernel.itb
#   0x0B60000  rootfs    28M  ubi0, one 24M read-only volume (overlay lower)
#   0x2760000  data    88.6M  ubi1, rootfs_data (overlay upper + work)
#
# data is left erased on purpose: preinit builds its UBI device and volume on
# first boot, which is what lets a full reflash keep the user's data.
set -e

BOARD_DIR="$(dirname "$0")"
BINARIES_DIR="${BINARIES_DIR:-$1}"

cmp "${BUILD_DIR}/linux-7.1.6/drivers/input/misc/ch32_touch_protocol.h" \
	"${BOARD_DIR}/src/touch_protocol.h"

SPL_OFF=$((0x0))
UBOOT_OFF=$((0x40000))
BOOTENV_OFF=$((0x140000))
BOOT_OFF=$((0x160000))
# dtbs.itb sits at the front of the boot partition in a slot of its own, and
# kernel.itb follows it. Same arrangement as the prev-generation boards, which
# is what the flasher already knows how to produce.
DTBS_SLOT=$((0x100000))
ROOTFS_OFF=$((0xb60000))
DATA_OFF=$((0x2760000))
FLASH_SIZE=$((128 * 1024 * 1024))

need() {
	if [ ! -f "$1" ]; then
		echo "post-image: missing $1" >&2
		exit 1
	fi
}

need "${BINARIES_DIR}/sunxi-spl.bin"
need "${BINARIES_DIR}/u-boot.itb"
need "${BINARIES_DIR}/Image"

DTB="${BINARIES_DIR}/sun20i-d1s-epass-next.dtb"
need "$DTB"

# Nothing may run over into the next partition. Checking here turns a layout
# mistake into a build failure instead of a device that boots halfway.
fits() {
	sz=$(stat -c %s "$1")
	if [ "$sz" -gt "$3" ]; then
		echo "post-image: $2 is ${sz} bytes but only $3 fit" >&2
		exit 1
	fi
}

# The kernel goes into flash as a FIT holding a gzipped Image. RISC-V has no
# self-decompressing image and booti will not take a compressed one, so the
# container has to do it -- bootm inflates on the way in. Worth roughly 44% of
# the slot. The raw Image stays in images/ because the FEL path pushes it
# straight to DRAM.
MKIMAGE="${HOST_DIR}/bin/mkimage"
[ -x "$MKIMAGE" ] || MKIMAGE=mkimage
gzip -9 -c "${BINARIES_DIR}/Image" > "${BINARIES_DIR}/Image.gz"
# dtc resolves /incbin/ against the directory holding the .its, so the .its
# has to sit next to its payloads. mkimage shells out to dtc by name, hence
# the PATH.
cp "${BOARD_DIR}/kernel.its" "${BINARIES_DIR}/kernel.its"
(cd "$BINARIES_DIR" && PATH="${HOST_DIR}/bin:$PATH" \
	"$MKIMAGE" -f kernel.its kernel.itb > /dev/null)
rm -f "${BINARIES_DIR}/Image.gz" "${BINARIES_DIR}/kernel.its"
echo "post-image: kernel.itb $(stat -c %s "${BINARIES_DIR}/kernel.itb") bytes (Image was $(stat -c %s "${BINARIES_DIR}/Image"))"

# The device tree bundle: one base per revision, overlays per screen and
# option. Built here rather than by the kernel because dtc needs -@ for the
# overlays to resolve, and because it tracks the board directory, not the
# kernel tree.
BINARIES_DIR="$BINARIES_DIR" BUILD_DIR="$BUILD_DIR" HOST_DIR="$HOST_DIR" \
	sh "${BOARD_DIR}/scripts/mkdt.sh"

need "${BINARIES_DIR}/dtbs.itb"
fits "${BINARIES_DIR}/dtbs.itb" "dtbs slot" "$DTBS_SLOT"

# boot.itb is what the flasher writes: the dtbs bundle padded out to its slot,
# then the kernel. One partition, one image, one DFU alt setting.
BOOTIMG="${BINARIES_DIR}/boot.itb"
rm -f "$BOOTIMG"
tr '\0' '\377' < /dev/zero 2>/dev/null | dd of="$BOOTIMG" bs=1024 \
	count=$((DTBS_SLOT / 1024)) iflag=fullblock status=none
dd if="${BINARIES_DIR}/dtbs.itb" of="$BOOTIMG" conv=notrunc status=none
cat "${BINARIES_DIR}/kernel.itb" >> "$BOOTIMG"
echo "post-image: boot.itb $(stat -c %s "$BOOTIMG") bytes"

fits "${BINARIES_DIR}/sunxi-spl.bin" boot0 $((UBOOT_OFF - SPL_OFF))
fits "${BINARIES_DIR}/u-boot.itb"    uboot $((BOOTENV_OFF - UBOOT_OFF))
fits "$BOOTIMG"                      boot  $((ROOTFS_OFF - BOOT_OFF))

# The identity blob, copied out so flash.py and flash.sh can write it.
ENVTXT="${BINARIES_DIR}/env.txt"
cp "${BOARD_DIR}/env.txt" "$ENVTXT"
fits "$ENVTXT" bootenv $((BOOT_OFF - BOOTENV_OFF))

if [ -f "${BINARIES_DIR}/rootfs.ubi" ]; then
	fits "${BINARIES_DIR}/rootfs.ubi" rootfs $((DATA_OFF - ROOTFS_OFF))
else
	echo "post-image: no rootfs.ubi built" >&2
fi

# What flash.py needs to run U-Boot out of DRAM over FEL. u-boot.itb is the
# form the SPL loads; FEL has no SPL to do that, so the pieces go in
# separately. U-Boot with CONFIG_OF_SEPARATE finds its dtb appended to its own
# image, hence the concatenation -- but OpenSBI is handed the tree by address,
# so it needs a copy of its own as well.
UBDIR=$(echo "${BUILD_DIR}"/uboot-*/ | head -1)
python3 "${BOARD_DIR}/scripts/check-spl-layout.py" "$UBDIR"
if [ -f "${UBDIR}/u-boot-nodtb.bin" ] && [ -f "${UBDIR}/u-boot.dtb" ]; then
	cat "${UBDIR}/u-boot-nodtb.bin" "${UBDIR}/u-boot.dtb" \
		> "${BINARIES_DIR}/u-boot-fel.bin"
	cp "${UBDIR}/u-boot.dtb" "${BINARIES_DIR}/u-boot.dtb"
	echo "post-image: u-boot-fel.bin $(stat -c %s "${BINARIES_DIR}/u-boot-fel.bin") bytes"
else
	echo "post-image: no u-boot-nodtb.bin, FEL flashing will not work" >&2
fi

# xfel's direct NAND commands address SPI0, while the physical NAND is on
# SPI1. Use the board's FEL-to-U-Boot/DFU path for both normal and full erase.
FLASHER_DIR="${BOARD_DIR}/../../../flasher"
mkdir -p "${BINARIES_DIR}/flasher"
for file in flash.py flash_esp.py ota.py bmc_ota.py esp_ota.py README.md; do
	need "${FLASHER_DIR}/${file}"
	cp "${FLASHER_DIR}/${file}" "${BINARIES_DIR}/flasher/${file}"
done
cp "${BOARD_DIR}/../../../flash.py" "${BINARIES_DIR}/flash.py"
# Remove obsolete generated copies so old entry points cannot diverge.
rm -f "${BINARIES_DIR}/flash_esp.py" "${BINARIES_DIR}/bmc_ota.py"
cat > "${BINARIES_DIR}/flash.sh" <<'EOF'
#!/bin/sh
set -eu
IMAGES_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "${IMAGES_DIR}/flasher/flash.py" --images "$IMAGES_DIR" "$@"
EOF
chmod +x "${BINARIES_DIR}/flash.sh"

cat > "${BINARIES_DIR}/flash-all.sh" <<'EOF'
#!/bin/sh
# Full-chip force erase and bad block rescan; destroys user data.
set -eu
IMAGES_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "${IMAGES_DIR}/flasher/flash.py" --images "$IMAGES_DIR" --scrub "$@"
EOF
chmod +x "${BINARIES_DIR}/flash-all.sh"

cat > "${BINARIES_DIR}/ota.sh" <<'EOF'
#!/bin/sh
set -eu
IMAGES_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "${IMAGES_DIR}/flasher/ota.py" --images "$IMAGES_DIR" "$@"
EOF
chmod +x "${BINARIES_DIR}/ota.sh"
