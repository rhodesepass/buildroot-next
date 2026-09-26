#!/usr/bin/env python3
"""ePass BLE/Wi-Fi OTA：默认更新 boot/rootfs，保留可写 overlay 和外设固件。"""
import argparse
import asyncio
import getpass
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGES = HERE.parent if (HERE.parent / "u-boot.itb").is_file() else HERE.parent / "output/images"
SPEC = importlib.util.spec_from_file_location("epass_ota_client", HERE / "bmc_ota.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)
ESP_SPEC = importlib.util.spec_from_file_location("epass_esp_image", HERE / "flash_esp.py")
esp_image = importlib.util.module_from_spec(ESP_SPEC)
ESP_SPEC.loader.exec_module(esp_image)


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transport", choices=("ble", "wifi"), default="ble")
    ap.add_argument("--images", type=Path, default=IMAGES)
    ap.add_argument("--uboot-fit", type=Path, help="每次先加载到 RAM 的完整 U-Boot，默认 images/u-boot.itb")
    ap.add_argument("--only", nargs="+", choices=("uboot", "boot", "rootfs"),
                    help="系统更新目标，默认 boot rootfs；uboot 需显式选择")
    ap.add_argument("--system", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--wch", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--wch-image", type=Path, help="默认 images/ch32-touch.bin")
    ap.add_argument("--esp", action=argparse.BooleanOptionalAction, default=False,
                    help="同时更新 ESP 应用（默认否，需设备已有 ESP OTA 支持）")
    ap.add_argument("--esp-image", type=Path, help="默认 images/esp/epass_bmc.bin")
    ap.add_argument("--address", help="BLE 目标地址，BLE 上传或 Wi-Fi 配网时必填")
    route = ap.add_mutually_exclusive_group()
    route.add_argument("--wifi-sta", metavar="SSID")
    route.add_argument("--wifi-ap", action="store_true")
    route.add_argument("--url", help="复用已有 HTTP 会话，令牌交互输入")
    ap.add_argument("--boot", action=argparse.BooleanOptionalAction, default=True,
                    help="提交后启动系统；包含 ESP 时重启 ESP（默认是）")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--att-payload", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="校验镜像并显示计划，不连接设备")
    return ap


def prepare(args):
    if not (args.system or args.wch or args.esp):
        raise ValueError("至少选择系统、WCH 或 ESP 固件")
    if args.only and not args.system:
        raise ValueError("--only 不能与 --no-system 同用")
    if args.wch_image and not args.wch:
        raise ValueError("--wch-image 需要 --wch")
    if args.esp_image and not args.esp:
        raise ValueError("--esp-image 需要 --esp")
    if args.timeout <= 0 or not 5 <= args.att_payload <= 244:
        raise ValueError("timeout 必须为正数，att-payload 必须在 5..244")
    wifi = args.wifi_sta is not None or args.wifi_ap or args.url is not None
    if args.transport == "wifi" and not wifi:
        raise ValueError("Wi-Fi 需要 --wifi-sta、--wifi-ap 或 --url")
    if args.transport == "ble" and wifi:
        raise ValueError("Wi-Fi 参数需要 --transport wifi")
    if not args.url and not args.address:
        raise ValueError("请通过 --address 指定目标 BLE 地址")
    selected = set(args.only or ("boot", "rootfs")) if args.system else set()
    args.extra_images = [f"{name}={args.images / filename}"
                         for name, filename in (("uboot", "u-boot.itb"), ("boot", "boot.itb"),
                                                ("rootfs", "rootfs.ubi")) if name in selected]
    if args.wch:
        args.extra_images.append(f"touch={args.wch_image or args.images / 'ch32-touch.bin'}")
    if args.esp:
        args.esp_image = args.esp_image or args.images / "esp/epass_bmc.bin"
        esp_image.validate_firmware(args.esp_image)
        args.extra_images.insert(0, f"bmc={args.esp_image}")
    if args.system or args.wch:
        args.uboot_fit = args.uboot_fit or args.images / "u-boot.itb"
        if not args.uboot_fit.is_file() or not 0 < args.uboot_fit.stat().st_size <= client.LIMITS[4]:
            raise ValueError(f"U-Boot FIT 不存在、为空或超过 4 MiB：{args.uboot_fit}")
    args.target = args.image = args.sha256 = args.token = args.wifi_password = None
    client.load_images(args)
    return args


def main():
    ap = parser()
    try:
        args = prepare(ap.parse_args())
    except (OSError, ValueError) as error:
        ap.error(str(error))
    print(f"OTA 通道={args.transport}，RAM U-Boot={args.uboot_fit}")
    print("更新目标：" + ", ".join(args.extra_images))
    if args.esp:
        print("顺序：暂存 ESP → 更新所选系统/WCH → 统一提交" + (" → 重启 ESP" if args.boot else "；不重启"))
        if args.boot:
            print("ESP 重启后 Wi-Fi 会话失效；需通过 BLE 重新配网后查询运行槽和版本。")
    if any(image.startswith("rootfs=") for image in args.extra_images):
        print("保留 data 中的可写 overlay；同路径旧覆盖文件仍可能遮住新 rootfs。")
    if args.dry_run:
        return
    try:
        if args.wifi_sta is not None:
            args.wifi_password = getpass.getpass("现有 Wi-Fi 密码（开放网络留空）：")
        asyncio.run(client.run(args))
    except (Exception, KeyboardInterrupt) as error:
        ap.exit(1, f"更新未完成：{error}\n")


if __name__ == "__main__":
    main()
