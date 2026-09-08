# -*- coding: utf-8 -*-
"""아이콘 4차 — 곡선을 더 '입 모양' 답게.

지금 곡선은 포물선이라 V 에 가깝다. 진짜 웃는 입은 다르다.
  · 바닥이 평평하다 (포물선은 한 점에서만 바닥)
  · 양 끝(입꼬리)이 더 가파르게 치켜올라간다
  · 폭에 비해 얕다

그래서 3차 베지에로 바꾼다. 제어점 두 개를 바닥보다 **더 아래**에 나란히 두면
가운데가 평평해지고 끝이 급하게 들린다 — 그게 입꼬리다.
제어점을 얼마나 벌리느냐(k)가 '입 같음' 을 결정하므로 세 값으로 비교한다.

  M1 지금 것(포물선)      — 기준
  M2 제어점 보통(k=0.17)  — 살짝 평평한 바닥
  M3 제어점 넓게(k=0.24)  — 확실히 평평한 바닥 + 치켜올라간 입꼬리
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
from PIL import Image, ImageDraw

BASE = Path(__file__).parent
S, K = 512, 4
BG0, BG1 = (13, 16, 32), (5, 6, 10)
DOWN, UP, GOLD = (59, 130, 246), (248, 113, 113), (251, 191, 36)


def canvas():
    n = S * K
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        t = y / n
        c = tuple(int(BG0[i] + (BG1[i] - BG0[i]) * t) for i in range(3))
        for x in range(0, n, 16):
            for dx in range(16):
                if x + dx < n:
                    px[x + dx, y] = c
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.235), fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(g, (0, 0), mask)
    hl = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle(
        [int(n * 0.018), int(n * 0.018), n - int(n * 0.018), n - int(n * 0.018)],
        radius=int(n * 0.222), outline=(255, 255, 255, 16), width=int(n * 0.007))
    return Image.alpha_composite(out, hl)


def hgrad(n, stops):
    g = Image.new("RGB", (n, n))
    px = g.load()
    for x in range(n):
        t = x / (n - 1)
        c = stops[-1][1]
        for i in range(len(stops) - 1):
            a, ca = stops[i]
            b, cb = stops[i + 1]
            if a <= t <= b:
                u = (t - a) / max(b - a, 1e-9)
                c = tuple(int(ca[j] + (cb[j] - ca[j]) * u) for j in range(3))
                break
        for y in range(0, n, 16):
            for dy in range(16):
                if y + dy < n:
                    px[x, y + dy] = c
    return g


def stamp(mask, pts, w):
    d = ImageDraw.Draw(mask)
    r = w / 2
    prev = None
    for x, y in pts:
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            L = (dx * dx + dy * dy) ** 0.5
            st = max(1, int(L / (r * 0.25)))
            for i in range(1, st + 1):
                px_, py_ = prev[0] + dx * i / st, prev[1] + dy * i / st
                d.ellipse([px_ - r, py_ - r, px_ + r, py_ + r], fill=255)
        else:
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        prev = (x, y)


def glow(img, cx, cy, radius, color, alpha=105, layers=14):
    n = img.size[0]
    lay = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for i in range(layers, 0, -1):
        r = radius * (1 + i * 0.24)
        a = int(alpha * (1 - i / (layers + 1)) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return Image.alpha_composite(img, lay)


def parab(x0, x1, ytop, depth, m=80):
    return [(x0 + (x1 - x0) * (i / m),
             ytop + (1 - 4 * (i / m - 0.5) ** 2) * depth) for i in range(m + 1)]


def smile(x0, x1, ye, ybot, k, m=120):
    """3차 베지에 웃는 입.

    제어점 두 개를 바닥선보다 아래에 나란히 둔다. 그러면 가운데가 평평해지고
    양 끝이 급하게 들린다(입꼬리). 실제 최저점은 제어점보다 위에 생기므로
    원하는 바닥 ybot 에 맞춰 제어점 높이를 역산한다: y(0.5) = (ye + 3*yc)/4.
    """
    yc = (4 * ybot - ye) / 3
    P = [(x0, ye), (x0 + k, yc), (x1 - k, yc), (x1, ye)]
    out = []
    for i in range(m + 1):
        t = i / m
        u = 1 - t
        x = u**3 * P[0][0] + 3*u*u*t * P[1][0] + 3*u*t*t * P[2][0] + t**3 * P[3][0]
        y = u**3 * P[0][1] + 3*u*u*t * P[1][1] + 3*u*t*t * P[2][1] + t**3 * P[3][1]
        out.append((x, y))
    return out


def build(pts_frac, dot_frac, w_frac=0.082, dot_r=0.082):
    n = S * K
    img = canvas()
    pts = [(x * n, y * n) for x, y in pts_frac]
    mask = Image.new("L", (n, n), 0)
    stamp(mask, pts, int(n * w_frac))
    grad = hgrad(n, [(0.0, DOWN), (0.40, DOWN), (0.52, GOLD), (0.66, UP), (1.0, UP)])
    stroke = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    stroke.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, stroke)
    bx, by = dot_frac[0] * n, dot_frac[1] * n
    r = int(n * dot_r)
    img = glow(img, bx, by, r, GOLD)
    dd = ImageDraw.Draw(img)
    dd.ellipse([bx - r, by - r, bx + r, by + r], fill=(7, 9, 16, 255))
    dd.ellipse([bx - r * 0.64, by - r * 0.64, bx + r * 0.64, by + r * 0.64], fill=GOLD + (255,))
    return img


# ⚠ k 는 **양 끝에서 제어점까지의 거리**다. k 를 키우면 제어점이 가운데로 몰려
#   오히려 V 가 된다(2026-09-09 반대로 알고 한 번 헛돌았다). 바닥을 눕히고
#   입꼬리를 세우려면 k 를 **줄여** 제어점을 끝쪽에 붙여야 한다.
V = {
    "M6": lambda: build(smile(0.142, 0.858, 0.325, 0.663, 0.17), (0.5, 0.663)),
    "M7": lambda: build(smile(0.142, 0.858, 0.320, 0.660, 0.115), (0.5, 0.660)),
    "M8": lambda: build(smile(0.142, 0.858, 0.315, 0.658, 0.065), (0.5, 0.658)),
}
made = {}
for k, fn in V.items():
    im = fn().resize((S, S), Image.LANCZOS)
    made[k] = im
    im.save(BASE / f"icon4_{k}.png")
    print(f"{k} 저장 icon4_{k}.png")

sizes = [96, 32, 16]
pad, gapx, gapy = 40, 40, 30
W = pad * 2 + S * 3 + gapx * 2
H = pad * 2 + S + gapy + 96 + 40
sheet = Image.new("RGB", (W, H), (18, 20, 26))
dr = ImageDraw.Draw(sheet)
for i, k in enumerate(("M6", "M7", "M8")):
    x = pad + i * (S + gapx)
    sheet.paste(made[k], (x, pad), made[k])
    xx = x
    for sz in sizes:
        th = made[k].resize((sz, sz), Image.LANCZOS)
        sheet.paste(th, (xx, pad + S + gapy + (96 - sz) // 2), th)
        xx += sz + 24
    dr.text((x, pad + S + gapy + 96 + 8), k, fill=(220, 225, 235))
sheet.save(BASE / "icon4_compare.png")
print("비교 시트 저장 icon4_compare.png")
