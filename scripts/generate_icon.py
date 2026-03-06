#!/usr/bin/env python3
"""Generate a simple .icns icon for the app.

Creates a Claude-styled icon using basic drawing.
Requires no external dependencies beyond Python stdlib + sips (macOS built-in).
"""

import os
import struct
import subprocess
import tempfile


def create_png_icon(size):
    """Create a minimal PNG with a Claude-inspired design.

    This generates a simple colored circle PNG using raw bytes.
    For a production icon, replace resources/icon.icns with a proper design.
    """
    # We'll create a simple solid-color icon using sips from a basic TIFF
    # For simplicity, generate via Python + macOS sips
    width = height = size

    # Create raw RGBA pixel data: a circle on transparent background
    pixels = bytearray(width * height * 4)
    cx, cy = width // 2, height // 2
    r = width // 2 - 2

    for y in range(height):
        for x in range(width):
            dx, dy = x - cx, y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            idx = (y * width + x) * 4

            if dist <= r:
                # Claude tan/brown color: #D4A574
                pixels[idx] = 0xD4      # R
                pixels[idx + 1] = 0xA5  # G
                pixels[idx + 2] = 0x74  # B
                pixels[idx + 3] = 0xFF  # A

                # Add a subtle inner shadow ring
                if dist > r - 3:
                    pixels[idx] = 0xBE
                    pixels[idx + 1] = 0x90
                    pixels[idx + 2] = 0x62
            else:
                # Transparent
                pixels[idx] = 0
                pixels[idx + 1] = 0
                pixels[idx + 2] = 0
                pixels[idx + 3] = 0

    return create_png_from_rgba(pixels, width, height)


def create_png_from_rgba(pixels, width, height):
    """Create a PNG file from raw RGBA pixel data."""
    import zlib

    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # IDAT - raw pixel data with filter bytes
    raw_data = b""
    for y in range(height):
        raw_data += b"\x00"  # No filter
        offset = y * width * 4
        raw_data += bytes(pixels[offset:offset + width * 4])

    compressed = zlib.compress(raw_data)
    idat = chunk(b"IDAT", compressed)

    # IEND
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resources_dir = os.path.join(project_dir, "resources")
    os.makedirs(resources_dir, exist_ok=True)

    icns_path = os.path.join(resources_dir, "icon.icns")

    # If icon already exists, skip
    if os.path.exists(icns_path):
        print(f"Icon already exists at {icns_path}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = os.path.join(tmpdir, "icon.iconset")
        os.makedirs(iconset_dir)

        # Generate required icon sizes
        sizes = [16, 32, 64, 128, 256, 512]
        for size in sizes:
            png_data = create_png_icon(size)

            # Standard resolution
            png_path = os.path.join(iconset_dir, f"icon_{size}x{size}.png")
            with open(png_path, "wb") as f:
                f.write(png_data)

            # @2x (retina) - half the name size
            if size >= 32:
                half = size // 2
                png_path_2x = os.path.join(iconset_dir, f"icon_{half}x{half}@2x.png")
                with open(png_path_2x, "wb") as f:
                    f.write(png_data)

        # Convert iconset to icns using macOS iconutil
        subprocess.run(
            ["iconutil", "-c", "icns", iconset_dir, "-o", icns_path],
            check=True,
        )

    print(f"Icon generated at {icns_path}")


if __name__ == "__main__":
    main()
