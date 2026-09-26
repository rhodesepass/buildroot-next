#!/usr/bin/env python3
"""Flash an Arknights ePass Next over USB FEL/DFU.

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

USB 系统需要 xfel/dfu-util；WCH 与 ESP 通过 uopbridge 可选烧录，默认不更新。
ESP 仅更新已有有效 OTA 安装，不负责首次分区初始化。

Usage: ./flash.py [--wch | --no-wch] [--esp | --no-esp]
"""

import argparse
import importlib.util
import shlex
import shutil
import struct
import subprocess
import sys
import time
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGES = HERE.parent if (HERE.parent / "u-boot.itb").is_file() else HERE.parent / "output" / "images"


def workspace_path(relative):
    for parent in HERE.parents:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return HERE / relative

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
# Keep a stable write order; detach targets the last selected stage.
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


def select_stages(only=None, scrub=False):
    names = {alt for alt, _ in DFU_STAGES}
    selected = names if only is None else set(only)
    if not selected or selected - names:
        raise ValueError("select at least one valid partition")
    if scrub and selected != names:
        raise ValueError("--scrub requires all partitions; cannot combine with partial --only")
    return [stage for stage in DFU_STAGES if stage[0] in selected]


def required_images(stages):
    bootstrap = ["sunxi-spl.bin", "fw_dynamic.bin", "u-boot-fel.bin", "u-boot.dtb"]
    return list(dict.fromkeys(bootstrap + [filename for _, filename in stages]))


def missing_images(images, stages):
    return [name for name in required_images(stages) if not (images / name).is_file()]


def detach_command(stages):
    return ["dfu-util", "-d", DFU_VIDPID, "-a", stages[-1][0], "-e"]


def parser():
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
    ap.add_argument("--only", nargs="+", choices=[alt for alt, _ in DFU_STAGES],
                    help="write only these partitions (default: all)")
    ap.add_argument("--system", action=argparse.BooleanOptionalAction, default=True,
                    help="是否烧录 D1s 系统（默认全部分区）")
    ap.add_argument("--wch", action=argparse.BooleanOptionalAction, default=False,
                    help="是否烧录 WCH 触控固件（默认否）")
    ap.add_argument("--esp", action=argparse.BooleanOptionalAction, default=False,
                    help="是否烧录 ESP 应用（默认否，仅 USB）")
    ap.add_argument("--wch-image", type=Path, help="默认 images/ch32-touch.bin")
    ap.add_argument("--esp-image", type=Path, help="ESP 应用 bin，默认 images/esp/epass_bmc.bin")
    ap.add_argument("--esp-bootloader", type=Path, help="同时更新 ESP bootloader，默认保留")
    ap.add_argument("--esp-port", help="uopbridge CDC 串口，如 /dev/ttyACM0")
    ap.add_argument("--bridge-bin", type=Path, default=workspace_path("uopbridge/bridge.bin"))
    ap.add_argument("--minichlink", default=str(workspace_path("uopbridge/host/build/ch32fun/minichlink/minichlink")))
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--dry-run", action="store_true", help="验证文件并显示计划，不连接设备")
    return ap


def prepare(args):
    if not (args.system or args.wch or args.esp):
        raise ValueError("至少选择 --system、--wch、--esp 中的一项")
    if not args.system and (args.only or args.wipe or args.scrub):
        raise ValueError("--no-system 不能与 --only/--wipe/--scrub 同用")
    if args.timeout <= 0:
        raise ValueError("timeout 必须为正数")
    if args.wch_image and not args.wch:
        raise ValueError("--wch-image 需要 --wch")
    if (args.esp_image or args.esp_bootloader or args.esp_port) and not args.esp:
        raise ValueError("ESP 参数需要 --esp")
    if args.esp and not args.esp_port:
        raise ValueError("--esp 需要 --esp-port")
    if args.esp:
        args.esp_image = args.esp_image or args.images / "esp/epass_bmc.bin"
    selected = args.only
    stages = select_stages(selected, args.scrub) if args.system else []
    files = [args.images / name for _, name in stages]
    if args.system:
        files += [args.images / name for name in required_images(stages)]
    if args.wch:
        args.wch_image = args.wch_image or args.images / "ch32-touch.bin"
        files.append(args.wch_image)
    if args.esp:
        files += [args.esp_image, HERE / "flash_esp.py"]
        if args.esp_bootloader:
            files.append(args.esp_bootloader)
    if args.wch or args.esp:
        files.append(args.bridge_bin)
    for path in dict.fromkeys(files):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"镜像或工具不存在/为空：{path}")
    limits = {"spl": 256 << 10, "uboot": 1 << 20, "boot": 10 << 20, "rootfs": 28 << 20}
    for target, name in stages:
        size = (args.images / name).stat().st_size
        if size > limits[target] or (target == "rootfs" and size % (128 << 10)):
            raise ValueError(f"{name} 大小越界或未按 128 KiB 对齐")
    if args.wch and (args.wch_image.stat().st_size > 63488 or args.wch_image.stat().st_size % 4):
        raise ValueError("WCH 镜像必须为非空、4 字节对齐、最多 63488 字节的 raw bin")
    if args.esp_bootloader and args.esp_bootloader.stat().st_size > 0x8000:
        raise ValueError("ESP bootloader 超出 0x8000 字节")
    if args.esp:
        spec = importlib.util.spec_from_file_location("flash_esp", HERE / "flash_esp.py")
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.validate_firmware(args.esp_image)
        if args.esp_bootloader:
            helper.validate_firmware(args.esp_bootloader)
    if args.system:
        fel = (args.images / "u-boot-fel.bin").read_bytes()
        dtb_size = (args.images / "u-boot.dtb").stat().st_size
        if dtb_size > len(fel) or fel[len(fel) - dtb_size:][:4] != b"\xd0\x0d\xfe\xed":
            raise ValueError("u-boot-fel.bin does not end in its device tree")
        if (args.images / "sunxi-spl.bin").read_bytes()[4:12] != b"eGON.BT0":
            raise ValueError("sunxi-spl.bin 缺少 eGON.BT0 头")
    return stages


def esp_command(args):
    cmd = [sys.executable, str(HERE / "flash_esp.py"), "--port", args.esp_port,
           "--app", str(args.esp_image), "--connect-mode", "default-reset"]
    if args.esp_bootloader:
        cmd += ["--bootloader", str(args.esp_bootloader)]
    return cmd


def bridge_present():
    for device in Path("/sys/bus/usb/devices").glob("*"):
        try:
            if ((device / "idVendor").read_text().strip(),
                    (device / "idProduct").read_text().strip()) == ("1209", "d1c3"):
                return True
        except OSError:
            continue
    return False


def is_bridge_port(port):
    device = Path("/sys/class/tty") / Path(port).resolve().name / "device"
    for parent in device.resolve().parents:
        try:
            return ((parent / "idVendor").read_text().strip(),
                    (parent / "idProduct").read_text().strip()) == ("1209", "d1c3")
        except OSError:
            continue
    return False


def flash_peripherals(args):
    if not bridge_present():
        print("请让 D1s 重新进入 FEL，将加载 uopbridge（不操作串口 RTS/DTR 复位 D1s）。", flush=True)
        wait_for_fel(args.timeout)
        run("xfel", "write", hex(SPL_ADDR), str(args.bridge_bin))
        # USB ownership changes inside exec, so its return code cannot prove boot success.
        subprocess.run(["xfel", "exec", hex(SPL_ADDR)])
        deadline = time.monotonic() + args.timeout
        while not bridge_present():
            if time.monotonic() >= deadline:
                sys.exit("uopbridge 未枚举，停止烧录")
            time.sleep(.2)
    if args.esp:
        deadline = time.monotonic() + args.timeout
        while not is_bridge_port(args.esp_port):
            if time.monotonic() >= deadline:
                sys.exit(f"{args.esp_port} 不是已枚举的 uopbridge CDC 串口，停止烧录")
            time.sleep(.2)
    if args.wch:
        with tempfile.TemporaryDirectory(prefix="epass-wch-") as directory:
            readback = Path(directory) / "readback.bin"
            run(args.minichlink, "-C", "uopbridge", "-w", str(args.wch_image), "flash")
            run(args.minichlink, "-C", "uopbridge", "-r", str(readback), "flash", str(args.wch_image.stat().st_size))
            if readback.read_bytes() != args.wch_image.read_bytes():
                sys.exit("WCH 回读不一致，停止烧录")
            run(args.minichlink, "-C", "uopbridge", "-b")
            print("WCH 烧录及完整回读通过")
    if args.esp:
        run(*esp_command(args))
    print("外设烧录完成；若 D1s 仍运行 uopbridge，请正常复位启动系统。")


def main():
    ap = parser()
    args = ap.parse_args()
    try:
        stages = prepare(args)
    except (ValueError, OSError) as error:
        ap.error(str(error))
    print(f"通道=USB，系统={[name for name, _ in stages]}，WCH={args.wch}，ESP={args.esp}")
    if args.dry_run:
        for target, filename in stages:
            print(f"USB FEL/DFU: {target} <- {args.images / filename}")
        if args.wipe or args.scrub:
            print(f"擦除用户数据：wipe={args.wipe}, scrub={args.scrub}")
        if args.wch or args.esp:
            print(f"USB FEL -> uopbridge: {args.bridge_bin}；系统烧录后需重新进入 FEL")
        if args.wch:
            print(f"WCH: {args.wch_image}，使用 {args.minichlink} 写入并完整回读")
        if args.esp:
            print(shlex.join(esp_command(args)))
            print("ESP 读取现有分区/OTA 状态选择应用槽，写后回读；保留 NVS/SPL/storage")
        return
    for command in ["xfel"] + (["dfu-util"] if args.system else []) + ([args.minichlink] if args.wch else []):
        if shutil.which(command) is None:
            ap.error(f"找不到工具：{command}")
    if args.esp and importlib.util.find_spec("esptool") is None:
        ap.error("当前 Python 缺少 esptool，请先安装再运行")
    if args.system:
        flash_usb(args, stages)
    if args.wch or args.esp:
        flash_peripherals(args)


def flash_usb(args, stages):

    flags = 0
    if args.wipe:
        flags |= FLAG_WIPE_USERDATA
    if args.scrub:
        flags |= FLAG_NAND_SCRUB | FLAG_WIPE_USERDATA

    img = args.images
    missing = missing_images(img, stages)
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
    wait_for_fel(args.timeout)

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

    # One session for the selected stages: U-Boot's dfu loop only exits on DFU_DETACH, so
    # the gadget stays enumerated between downloads. The settle time is not
    # decoration -- back to back dfu-util runs fail without it.
    for i, (alt, fname) in enumerate(stages):
        if i:
            time.sleep(2)
        wait_for_dfu()
        print(f"--- {alt} <- {fname} ---")
        run("dfu-util", "-d", DFU_VIDPID, "-a", alt, "-D", str(img / fname))

    # -R (USB reset) does not make U-Boot leave the dfu command; only
    # DFU_DETACH does. -e and -D override each other's mode, so the detach has
    # to be a run of its own.
    print("--- detach ---")
    subprocess.run(detach_command(stages))
    print("烧录完成, 板子会自己复位并启动刚写进去的系统")


if __name__ == "__main__":
    main()
