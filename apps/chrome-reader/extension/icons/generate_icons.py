#!/usr/bin/env python3
"""Generate simple speaker icons for the Chrome Reader extension."""

import struct
import zlib
import os


def create_png(width, height, pixels):
    """Create a minimal PNG file from RGBA pixel data."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter: none
        for x in range(width):
            idx = (y * width + x) * 4
            raw += bytes(pixels[idx:idx+4])

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def draw_icon(size):
    """Draw a speaker icon at the given size."""
    pixels = [0] * (size * size * 4)

    def set_pixel(x, y, r, g, b, a=255):
        if 0 <= x < size and 0 <= y < size:
            idx = (y * size + x) * 4
            # Alpha blend
            old_a = pixels[idx + 3] / 255.0
            new_a = a / 255.0
            out_a = new_a + old_a * (1 - new_a)
            if out_a > 0:
                pixels[idx] = int((r * new_a + pixels[idx] * old_a * (1 - new_a)) / out_a)
                pixels[idx+1] = int((g * new_a + pixels[idx+1] * old_a * (1 - new_a)) / out_a)
                pixels[idx+2] = int((b * new_a + pixels[idx+2] * old_a * (1 - new_a)) / out_a)
                pixels[idx+3] = int(out_a * 255)

    def fill_rect(x1, y1, x2, y2, r, g, b, a=255):
        for y in range(max(0, y1), min(size, y2)):
            for x in range(max(0, x1), min(size, x2)):
                set_pixel(x, y, r, g, b, a)

    def fill_circle(cx, cy, radius, r, g, b, a=255):
        for y in range(size):
            for x in range(size):
                dx, dy = x - cx, y - cy
                if dx*dx + dy*dy <= radius*radius:
                    set_pixel(x, y, r, g, b, a)

    # Colors
    bg_r, bg_g, bg_b = 26, 26, 46       # #1a1a2e
    fg_r, fg_g, fg_b = 255, 213, 79     # #ffd54f (gold)

    s = size
    pad = max(1, s // 8)

    # Background circle
    fill_circle(s//2, s//2, s//2 - 1, bg_r, bg_g, bg_b)

    # Speaker body (rectangle)
    bx1 = pad + s // 8
    bx2 = bx1 + s // 5
    by1 = s // 2 - s // 8
    by2 = s // 2 + s // 8
    fill_rect(bx1, by1, bx2, by2, fg_r, fg_g, fg_b)

    # Speaker cone (triangle)
    cone_tip_x = bx2
    cone_end_x = bx2 + s // 4
    cone_top = s // 2 - s // 5
    cone_bot = s // 2 + s // 5
    for y in range(cone_top, cone_bot):
        t = (y - cone_top) / max(1, cone_bot - cone_top)
        x_start = cone_tip_x
        x_end = cone_end_x
        y_mid = s // 2
        if y < y_mid:
            row_x1 = int(x_start + (x_end - x_start) * (y - cone_top) / max(1, cone_bot - cone_top) * 0.5)
        else:
            row_x1 = x_start
        fill_rect(x_start, y, cone_end_x, y+1, fg_r, fg_g, fg_b)

    # Sound waves (arcs using circles with cutout)
    wave_cx = cone_end_x + s // 16
    wave_cy = s // 2
    for wave_i, radius in enumerate([s // 5, s // 3]):
        thickness = max(1, s // 16)
        for y in range(size):
            for x in range(size):
                dx, dy = x - wave_cx, y - wave_cy
                dist = (dx*dx + dy*dy) ** 0.5
                if radius - thickness <= dist <= radius and dx > 0:
                    # Limit angle
                    import math
                    angle = abs(math.atan2(dy, dx))
                    if angle < math.pi / 3:
                        alpha = max(0, min(255, int(255 * (1 - abs(dist - radius + thickness/2) / (thickness/2)))))
                        set_pixel(x, y, fg_r, fg_g, fg_b, alpha)

    return pixels


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for sz in [16, 32, 48, 128]:
        pixels = draw_icon(sz)
        png_data = create_png(sz, sz, pixels)
        path = os.path.join(script_dir, f"icon{sz}.png")
        with open(path, "wb") as f:
            f.write(png_data)
        print(f"Generated {path} ({len(png_data)} bytes)")


if __name__ == "__main__":
    main()
