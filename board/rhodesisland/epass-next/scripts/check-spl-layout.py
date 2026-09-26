#!/usr/bin/env python3
"""Check the D1s ROM image against RISC-V pre-DRAM reservations."""
import argparse
import json
import re
import struct
from pathlib import Path


def check(build):
    config = dict(re.findall(r"^CONFIG_(\w+)=(.+)$", (build / ".config").read_text(), re.M))
    number = lambda key: int(config[key], 0)
    if config.get("SPL_SMP") == "y":
        raise ValueError("SMP layout is not supported by this D1s check")
    offsets = (build / "spl/include/generated/generic-asm-offsets.h").read_text()
    gd_size = int(re.search(r"^#define GD_SIZE (\d+)", offsets, re.M)[1])
    data = (build / "spl/sunxi-spl.bin").read_bytes()
    if data[4:12] != b"eGON.BT0":
        raise ValueError("missing eGON SPL header")
    image_size = struct.unpack_from("<I", data, 16)[0]
    if image_size != len(data):
        raise ValueError("eGON load length differs from the complete SPL file")
    image_end = 0x20000 + image_size
    stack_top = number("SPL_STACK") & ~15
    stack_bottom = stack_top - (1 << number("STACK_SIZE_SHIFT"))
    heap_bottom = stack_bottom - number("SPL_SYS_MALLOC_F_LEN")
    gd_bottom = (heap_bottom - gd_size) & ~15
    if stack_top > 0x40000:
        raise ValueError("SPL stack overlaps the BROM FEL scratch region")
    if image_end > gd_bottom:
        raise ValueError(f"ROM image ends at {image_end:#x}, overlapping GD at {gd_bottom:#x}")
    return {"image_end": image_end, "gd_bottom": gd_bottom,
            "heap_bottom": heap_bottom, "stack_bottom": stack_bottom,
            "stack_top": stack_top, "gap_bytes": gd_bottom - image_end}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.build), indent=2))
