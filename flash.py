#!/usr/bin/env python3
"""Flash an Arknights ePass Next (D1s) over FEL + DFU.

Counterpart of ../f1c_epass/buildroot/flash.py, which does the same job for
the previous generation. The mailbox format and the boot type numbers are
deliberately identical so that one host-side flasher can drive both.

The flow:

  1. FEL: load the SPL with its eGON magic altered so it initialises DRAM and
     returns to the BROM instead of chaining onward. This is the "ddrbin" step
     -- xfel has no built-in DDR init for the D1s.
  2. Drop the Mostima mailbox in DRAM: who this board is, and what to wipe.
  3. Load OpenSBI, U-Boot, the U-Boot dtb and a fw_dynamic_info describing
     where to go, then jump via a short shim, assembled below.
  4. That U-Boot reads the mailbox, writes the identity to the bootenv
     partition, honours the wipe flags and serves DFU. Four images go down in
     one session; DFU_DETACH at the end makes it leave DFU and reset, so the
     board comes up through the normal SPL chain rather than carrying on from
     the state a FEL load leaves the SoC in.

Only xfel and dfu-util are needed on the host -- the shim is assembled here.

Usage:  ./flash.py [--rev n0.2] [--screen boe_035] [--wipe] [--scrub]
"""

import argparse
import struct
import subprocess
import sys
import time
from pathlib import Path

IMAGES = Path(__file__).resolve().parent / "output" / "images"

# 信箱 header 的 flags 字节 (offset 0x09), U-Boot 侧由 mstmchk 导出成
# ${mstm_flags}, 由 mstm_prep 处理。不带任何位就是保数据升级。
FLAG_WIPE_USERDATA = 0x01
FLAG_NAND_SCRUB = 0x02  # 全片不跳坏块强制擦除后重扫坏块; 隐含 WIPE_USERDATA

BOOT_TYPE_NAND = 0x01
BOOT_TYPE_SD = 0x02  # 本板没有卡座, 号段保留给和 F1C 共用的 flasher

# DRAM map for the FEL run. Reasoned about in the board's uboot defconfig,
# next to CONFIG_MSTMCHK_ADDR; keep the two in step.
SPL_ADDR = 0x00020000  # SRAM A1, where the BROM loads boot0 from too
SBI_ADDR = 0x40000000
MSTM_ADDR = 0x40100000  # == CONFIG_MSTMCHK_ADDR
SHIM_ADDR = 0x42000000
UBOOT_ADDR = 0x42E00000  # == CONFIG_TEXT_BASE
INFO_ADDR = 0x43100000
# The device tree handed to OpenSBI is not a copy -- it is the one appended to
# the U-Boot image, whose address main() works out. It has to be that exact
# tree, because OpenSBI stamps its own memory reservations into whatever it is
# given, and U-Boot later copies them from *its* fdt into the kernel's.
# Pointing OpenSBI at a separate copy silently loses them: the kernel then
# believes OpenSBI's 384K is free memory, and faults the moment it allocates
# there, since PMP denies S-mode any access to it.

DFU_VIDPID = "1f3a:1010"
# Order matters only in that rootfs is last: the detach that follows it is what
# makes U-Boot leave DFU and reset.
DFU_STAGES = [
    ("spl", "sunxi-spl.bin"),
    ("uboot", "u-boot.itb"),
    ("boot", "boot.itb"),
    ("rootfs", "rootfs.ubi"),
]


def run(*cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(cmd)}")
    return r


def make_mailbox(rev, screen, boot_type, flags, out):
    env = f"device_rev={rev}\nscreen={screen}\n".encode() + b"\0"
    out.write_bytes(
        b"Mostima_"
        + bytes([boot_type, flags, 0, 0])
        + struct.pack("<I", len(env))
        + env
    )


def li(rd, value):
    """RV64 li for a positive 32-bit constant: lui, then addi for the rest."""
    assert 0 < value < 0x80000000, f"{value:#x} would sign-extend on RV64"
    # addi's immediate is signed, so borrow from the upper part when the low
    # 12 bits would come out negative.
    hi = (value + 0x800) & 0xFFFFF000
    lo = value - hi
    assert -0x800 <= lo < 0x800
    words = [hi | (rd << 7) | 0x37]  # lui rd, hi>>12
    if lo:
        words.append(((lo & 0xFFF) << 20) | (rd << 15) | (rd << 7) | 0x13)
    return words


def make_shim(out, dtb_addr):
    """Assemble the jump into OpenSBI.

    fw_dynamic's register contract is a0 = hart, a1 = device tree, a2 =
    struct fw_dynamic_info *. A handful of instructions, emitted here rather
    than built from .S so that flashing needs no cross toolchain.
    """
    words = [
        0x0000100F,  # fence.i   -- FEL just wrote these bytes
        0x00000513,  # li a0, 0  -- boot hart
    ]
    words += li(11, dtb_addr)  # a1
    words += li(12, INFO_ADDR)  # a2
    words += li(5, SBI_ADDR)  # t0
    words.append(0x00028067)  # jr t0
    out.write_bytes(b"".join(struct.pack("<I", w) for w in words))


def make_fw_info(out):
    # magic, version, next_addr, next_mode, options, boot_hart.
    # next_mode 1 is S-mode, which is where U-Boot expects to be entered.
    out.write_bytes(struct.pack("<6Q", 0x4942534F, 2, UBOOT_ADDR, 1, 0, 0))


def make_spl_fel(src, out):
    """Neuter the eGON magic so the SPL returns to FEL after DRAM init.

    With the magic intact the SPL decides it was loaded from MMC and chains
    onward instead of handing control back, and there is then no way to place
    anything in the DRAM it just brought up.
    """
    d = bytearray(src.read_bytes())
    if d[4:12] != b"eGON.BT0":
        sys.exit(f"{src} does not look like an SPL (magic {d[4:12]!r})")
    d[4:12] = b"eGON.FEL"
    out.write_bytes(bytes(d))


def wait_for_fel(timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if subprocess.run(["xfel", "version"], capture_output=True).returncode == 0:
            return
        time.sleep(0.4)
    sys.exit("no FEL device -- hold the FEL button and power-cycle the board")


def dfu_present():
    r = subprocess.run(["dfu-util", "-l"], capture_output=True, text=True)
    return f"Found DFU: [{DFU_VIDPID}]" in r.stdout


def wait_for_dfu(timeout=120):
    print("等待设备进入 DFU...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dfu_present():
            print(" 抓到了")
            return
        print(".", end="", flush=True)
        time.sleep(0.5)
    sys.exit("\nDFU never showed up -- check the serial console")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rev", default="n0.2", help="board revision (default n0.2)")
    ap.add_argument("--screen", default="boe_035", help="panel (default boe_035)")
    ap.add_argument(
        "--wipe", action="store_true", help="erase the user data partition too"
    )
    ap.add_argument(
        "--scrub",
        action="store_true",
        help="full-chip force erase and bad block rescan; implies --wipe",
    )
    ap.add_argument("--images", type=Path, default=IMAGES)
    args = ap.parse_args()

    flags = 0
    if args.wipe:
        flags |= FLAG_WIPE_USERDATA
    if args.scrub:
        flags |= FLAG_NAND_SCRUB | FLAG_WIPE_USERDATA

    img = args.images
    needed = ["sunxi-spl.bin", "fw_dynamic.bin", "u-boot-fel.bin", "u-boot.dtb"]
    needed += [f for _, f in DFU_STAGES]
    missing = [f for f in needed if not (img / f).is_file()]
    if missing:
        sys.exit(f"missing in {img}: {', '.join(missing)}")

    # u-boot-fel.bin is u-boot-nodtb.bin with u-boot.dtb appended, which is how
    # CONFIG_OF_SEPARATE expects to find its tree, so the dtb is the tail of the
    # image. The magic check is what keeps this honest if the build ever stops
    # appending it.
    fel = (img / "u-boot-fel.bin").read_bytes()
    dtb_off = len(fel) - (img / "u-boot.dtb").stat().st_size
    if fel[dtb_off:dtb_off + 4] != b"\xd0\x0d\xfe\xed":
        sys.exit("u-boot-fel.bin does not end in its device tree")
    dtb_addr = UBOOT_ADDR + dtb_off

    work = img / ".flash"
    work.mkdir(exist_ok=True)
    make_mailbox(args.rev, args.screen, BOOT_TYPE_NAND, flags, work / "mailbox.bin")
    make_shim(work / "shim.bin", dtb_addr)
    make_fw_info(work / "fw_info.bin")
    make_spl_fel(img / "sunxi-spl.bin", work / "spl-fel.bin")

    print(f"刷 {args.rev} / {args.screen}, flags={flags:#04x}")
    wait_for_fel()

    print("--- DRAM init (SPL, returns to FEL) ---")
    run("xfel", "write", hex(SPL_ADDR), str(work / "spl-fel.bin"))
    run("xfel", "exec", hex(SPL_ADDR))
    time.sleep(1)
    wait_for_fel(timeout=10)

    # Only now, with DRAM alive and the SPL out of the way, is it safe to put
    # anything there. The SPL runs entirely out of SRAM, so nothing it does
    # touches these addresses afterwards.
    print(f"--- payloads -> DRAM (u-boot dtb at {dtb_addr:#x}) ---")
    for addr, f in (
        (MSTM_ADDR, work / "mailbox.bin"),
        (SBI_ADDR, img / "fw_dynamic.bin"),
        (UBOOT_ADDR, img / "u-boot-fel.bin"),
        (INFO_ADDR, work / "fw_info.bin"),
        (SHIM_ADDR, work / "shim.bin"),
    ):
        run("xfel", "write", hex(addr), str(f))

    print("--- jump ---")
    run("xfel", "exec", hex(SHIM_ADDR))

    # One session for all four: U-Boot's dfu loop only exits on DFU_DETACH, so
    # the gadget stays enumerated between downloads. The settle time is not
    # decoration -- back to back dfu-util runs fail without it.
    for i, (alt, fname) in enumerate(DFU_STAGES):
        if i:
            time.sleep(2)
        wait_for_dfu()
        print(f"--- {alt} <- {fname} ---")
        run("dfu-util", "-d", DFU_VIDPID, "-a", alt, "-D", str(img / fname))

    # -R (USB reset) does not make U-Boot leave the dfu command; only
    # DFU_DETACH does. -e and -D override each other's mode, so the detach has
    # to be a run of its own.
    print("--- detach ---")
    subprocess.run(["dfu-util", "-d", DFU_VIDPID, "-a", DFU_STAGES[-1][0], "-e"])
    print("烧录完成, 板子会自己复位并启动刚写进去的系统")


if __name__ == "__main__":
    main()
