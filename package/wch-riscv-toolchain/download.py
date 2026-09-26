#!/usr/bin/env python3
"""Fetch the pinned archive using MounRiver's public signed-download API."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.parse
import urllib.request


ARCHIVE = "MRS_Toolchain_Linux_X64_V240.tar.xz"
API = (
    "https://api.mounriver.com/mountriver/api/version/"
    "fetchRecentOpenOcdUrl?resourceId=2030114123741700098"
)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    directory = Path(sys.argv[1])
    hashes = Path(sys.argv[2]).read_text().splitlines()
    expected = next(
        fields[1] for line in hashes
        if len(fields := line.split()) == 3
        and fields[0] == "sha256" and fields[2] == ARCHIVE
    )
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ARCHIVE
    if target.exists():
        if digest(target) != expected:
            raise RuntimeError(f"SHA256 mismatch: {target}; remove it before retrying")
        return

    with urllib.request.urlopen(API, timeout=60) as response:
        metadata = json.load(response)
    if not metadata.get("success"):
        raise RuntimeError("MounRiver download API failed")
    url = metadata.get("result", "")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "file-oss.mounriver.com"
            or parsed.path != f"/tools/{ARCHIVE}"):
        raise RuntimeError("MounRiver API returned an unexpected archive URL")

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(url, timeout=120) as response:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(block)
        if digest(temporary) != expected:
            raise RuntimeError("Downloaded WCH toolchain SHA256 mismatch")
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
