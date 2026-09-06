#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""アイコンを作る。外部ライブラリなしで PNG を書く。

  python3 make_icon.py

売店の軒先に新聞が3紙並んでいる図。3本の色はアプリ内のソース色（宇野／PLANETS／
Slow Times の hue）と揃えてある。
"""

import zlib
import struct
import math

BG = (0x12, 0x14, 0x1a)
AWNING = (0xe8, 0xb0, 0x4b)
BARS = [(14, 0.92), (268, 0.78), (196, 0.86)]     # (hue, 明るさ係数)


def hsl(h, s, l):
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return tuple(int(round((v + m) * 255)) for v in (r, g, b))


class Canvas:
    def __init__(self, n, bg):
        self.n = n
        self.px = [[bg for _ in range(n)] for _ in range(n)]

    def blend(self, x, y, color, a):
        if a <= 0 or not (0 <= x < self.n and 0 <= y < self.n):
            return
        a = min(1.0, a)
        old = self.px[y][x]
        self.px[y][x] = tuple(int(round(old[i] * (1 - a) + color[i] * a)) for i in range(3))

    def rrect(self, x0, y0, x1, y1, r, color):
        """角丸長方形。境界は 3x3 のサブサンプルでならす。"""
        for y in range(max(0, int(y0) - 1), min(self.n, int(y1) + 2)):
            for x in range(max(0, int(x0) - 1), min(self.n, int(x1) + 2)):
                hits = 0
                for sy in range(3):
                    for sx in range(3):
                        px, py = x + (sx + 0.5) / 3.0, y + (sy + 0.5) / 3.0
                        if not (x0 <= px <= x1 and y0 <= py <= y1):
                            continue
                        cx = min(max(px, x0 + r), x1 - r)
                        cy = min(max(py, y0 + r), y1 - r)
                        if math.hypot(px - cx, py - cy) <= r:
                            hits += 1
                if hits:
                    self.blend(x, y, color, hits / 9.0)

    def png(self, path):
        raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in self.px)
        def chunk(tag, data):
            c = tag + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        out = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", self.n, self.n, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 9))
               + chunk(b"IEND", b""))
        open(path, "wb").write(out)
        print(path, self.n, "px")


def draw(n):
    c = Canvas(n, BG)
    u = n / 100.0                                   # 1% を単位に置く

    # 軒（オーニング）
    c.rrect(14 * u, 17 * u, 86 * u, 27 * u, 4 * u, AWNING)
    # 支柱
    c.rrect(17 * u, 27 * u, 21 * u, 84 * u, 2 * u, (0x33, 0x38, 0x46))
    c.rrect(79 * u, 27 * u, 83 * u, 84 * u, 2 * u, (0x33, 0x38, 0x46))
    # 台
    c.rrect(14 * u, 80 * u, 86 * u, 86 * u, 3 * u, (0x33, 0x38, 0x46))

    # 並んだ3紙
    w, gap = 15.0, 4.0
    left = 50 - (3 * w + 2 * gap) / 2
    for i, (hue, lf) in enumerate(BARS):
        x = left + i * (w + gap)
        top = 36 + (i % 2) * 3                      # 少しずらして「並べてある」感じに
        c.rrect(x * u, top * u, (x + w) * u, 80 * u, 1.6 * u, hsl(hue, 0.60, 0.62))
        # 見出しの線
        for k in range(3):
            y = top + 5 + k * 5
            c.rrect((x + 3) * u, y * u, (x + w - 3) * u, (y + 1.6) * u, 0.8 * u,
                    hsl(hue, 0.55, 0.24))
    return c


if __name__ == "__main__":
    draw(180).png("icon-180.png")
    draw(512).png("icon-512.png")
