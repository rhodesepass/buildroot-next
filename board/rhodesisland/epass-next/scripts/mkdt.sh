#!/bin/sh
# Build the device tree bundle: one base tree per board revision, plus an
# overlay per screen / interface / extension, packed into a single FIT.
#
# U-Boot picks a base by the device_rev it reads out of the bootenv partition,
# applies fdt-screen-<screen> over it, then whatever the interface and ext
# lists name. Adding a variant is dropping a .dts in the right directory --
# the FIT source below is generated from what is actually there, so nothing
# else has to be edited.
#
# dtc gets -@ so the base trees carry __symbols__; without it the overlays'
# references (&panel, &backlight) have nothing to resolve against and
# "fdt apply" fails in U-Boot.
set -e

BOARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIR_IN="${BOARD_DIR}/devicetree/linux"
DIR_OUT="${BINARIES_DIR}/dt"
TEMP_DIR="${DIR_OUT}/temp"

KDIR="${BUILD_DIR}/linux-${LINUX_VERSION_PROBED:-7.1.6}"
[ -d "$KDIR" ] || KDIR=$(echo "${BUILD_DIR}"/linux-*/ | head -1)

MKIMAGE="${HOST_DIR}/bin/mkimage"
DTC="${HOST_DIR}/bin/dtc"
[ -x "$DTC" ] || DTC=dtc

rm -rf "${DIR_OUT}"
mkdir -p "${DIR_OUT}/base" "${DIR_OUT}/screen" \
	"${DIR_OUT}/interface" "${DIR_OUT}/ext" "${TEMP_DIR}"

# cpp first: the trees use dt-bindings headers and the SoC dtsi, neither of
# which dtc knows how to find.
compile() {
	src="$1"; out="$2"; ext="$3"
	name="$(basename "$src" .dts)"

	cpp -nostdinc \
		-I "${KDIR}/include" \
		-I "${KDIR}/arch/riscv/boot/dts" \
		-I "${KDIR}/arch/riscv/boot/dts/allwinner" \
		-I "${DIR_IN}/base" \
		-P -undef -x assembler-with-cpp \
		-o "${TEMP_DIR}/${name}.dts" "$src"
	"$DTC" -@ -q -I dts -O dtb -o "${out}/${name}.${ext}" "${TEMP_DIR}/${name}.dts"
	rm -f "${TEMP_DIR}/${name}.dts"
}

echo "mkdt: base trees"
for f in "${DIR_IN}"/base/devicetree-*.dts; do
	[ -e "$f" ] || continue
	echo "  $(basename "$f")"
	compile "$f" "${DIR_OUT}/base" dtb
done

for layer in screen interface ext; do
	# the directories are allowed to be empty -- a board with one panel and
	# no optional hardware still gets a valid bundle
	set -- "${DIR_IN}/${layer}"/*.dts
	[ -e "$1" ] || { echo "mkdt: no ${layer} overlays"; continue; }
	echo "mkdt: ${layer} overlays"
	for f in "$@"; do
		echo "  $(basename "$f")"
		compile "$f" "${DIR_OUT}/${layer}" dtbo
	done
done

# Generate the FIT source from what got built.
ITS="${DIR_OUT}/dtbs.its"
{
	echo '/dts-v1/;'
	echo '/ {'
	echo '    description = "ePass Next device tree bundle";'
	echo '    #address-cells = <1>;'
	echo '    images {'
	for f in "${DIR_OUT}"/base/*.dtb; do
		[ -e "$f" ] || continue
		rev="$(basename "$f" .dtb)"; rev="${rev#devicetree-}"
		printf '        fdt-base-%s {\n' "$rev"
		printf '            description = "base %s";\n' "$rev"
		printf '            data = /incbin/("./base/%s");\n' "$(basename "$f")"
		printf '            type = "flat_dt";\n            arch = "riscv";\n'
		printf '            compression = "none";\n            hash { algo = "crc32"; };\n'
		printf '        };\n'
	done
	for layer in screen interface ext; do
		case "$layer" in
			screen) prefix=fdt-screen ;;
			interface) prefix=fdt-iface ;;
			ext) prefix=fdt-ext ;;
		esac
		for f in "${DIR_OUT}/${layer}"/*.dtbo; do
			[ -e "$f" ] || continue
			name="$(basename "$f" .dtbo)"
			printf '        %s-%s {\n' "$prefix" "$name"
			printf '            description = "%s %s";\n' "$layer" "$name"
			printf '            data = /incbin/("./%s/%s");\n' "$layer" "$(basename "$f")"
			printf '            type = "flat_dt";\n            arch = "riscv";\n'
			printf '            compression = "none";\n            hash { algo = "crc32"; };\n'
			printf '        };\n'
		done
	done
	# One boot logo per screen (pre-gzipped RGB565 raw out of mklogo.py;
	# imxtract gunzips straight into the framebuffer). A screen without a
	# logo simply gets no splash -- U-Boot's imxtract fails and boot goes on.
	for f in "${BOARD_DIR}"/logo/logo-*.rgb565.gz; do
		[ -e "$f" ] || continue
		name="$(basename "$f" .rgb565.gz)"; name="${name#logo-}"
		cp "$f" "${DIR_OUT}/logo-${name}.rgb565.gz"
		printf '        logo-%s {\n' "$name"
		printf '            description = "splash logo %s (RGB565)";\n' "$name"
		printf '            data = /incbin/("./logo-%s.rgb565.gz");\n' "$name"
		printf '            type = "firmware";\n            arch = "riscv";\n'
		printf '            compression = "gzip";\n            hash { algo = "crc32"; };\n'
		printf '        };\n'
	done
	echo '    };'
	# No configurations node: nothing boots this FIT, U-Boot only imxtracts
	# individual images out of it by name.
	echo '};'
} > "$ITS"

(cd "${DIR_OUT}" && "$MKIMAGE" -f dtbs.its "${BINARIES_DIR}/dtbs.itb" > /dev/null)
rm -rf "${TEMP_DIR}"

echo "mkdt: dtbs.itb $(stat -c %s "${BINARIES_DIR}/dtbs.itb") bytes"
