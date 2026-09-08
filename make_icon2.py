# -*- coding: utf-8 -*-
"""앱 아이콘 2차 — 의미를 더 밀어붙인다. 사이트 팔레트에 묶이지 않는다.

1차(퍼널)의 한계: '거른다' 는 어떤 스크리너에나 해당하는 일반명사다.
이 앱의 진짜 의미는 따로 있다 — **떨어진 것을 산다**.
아홉 규칙이 전부 하락장 규칙이다(폭락반등·낙폭과대·업종붕괴 이탈·깊은 이격·
조정매집·저PBR 낙폭). 공포에 사서 공포가 풀릴 때 판다. 그러니 아이콘의 주인공은
화살표도 퍼널도 아니고 **저점** 이어야 한다. 그 자리를 짚는 게 이 앱이 하는 일이다.

색은 한국 시장 관습을 따른다 — 하락 파랑, 반등 빨강. 저점의 기회는 금색.
사이트 강조색(보라)에 묶이지 않는다(사용자 지시).
  배경 #05060a~#0d1020 · 하락 #3b82f6 · 저점 #fbbf24 · 반등 #f87171

세 안
  A 저점 표식 — 파랑으로 내려와 금색 점에서 바닥을 찍고 빨강으로 들린다
  B 떨어지는 것 중 하나 — 파란 점 여럿이 흩어져 떨어지는데 바닥의 하나만 금색
  C 바닥 곡선 — 획을 다 빼고 완만한 그릇 모양 + 금색 점 하나 (가장 단순)

⚠ 16px 에서 읽히는지 반드시 확인한다. 1차에서 큰 화면 최고와 작은 화면 최고가 달랐다.
"""
import io, sys, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

BASE = Path(__file__).parent
S, K = 512, 4
BG0, BG1 = (13, 16, 32), (5, 6, 10)
DOWN = (59, 130, 246)      # 하락 파랑
UP = (248, 113, 113)       # 반등 빨강
GOLD = (251, 191, 36)      # 저점 금색
FAINT = (37, 45, 66)


def canvas(r_ratio=0.235):
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
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * r_ratio), fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(g, (0, 0), mask)
    hl = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle(
        [int(n * 0.018), int(n * 0.018), n - int(n * 0.018), n - int(n * 0.018)],
        radius=int(n * 0.222), outline=(255, 255, 255, 16), width=int(n * 0.007))
    return Image.alpha_composite(out, hl)


def hgrad(n, stops):
    """가로 그라데이션 이미지. stops = [(위치0~1, (r,g,b)), ...]"""
    g = Image.new("RGB", (n, n))
    px = g.load()
    for x in range(n):
        t = x / (n - 1)
        for i in range(len(stops) - 1):
            a, ca = stops[i]
            b, cb = stops[i + 1]
            if a <= t <= b:
                u = (t - a) / max(b - a, 1e-9)
                c = tuple(int(ca[j] + (cb[j] - ca[j]) * u) for j in range(3))
                break
        else:
            c = stops[-1][1]
        for y in range(0, n, 16):
            for dy in range(16):
                if y + dy < n:
                    px[x, y + dy] = c
    return g


def glow(img, cx, cy, radius, color, alpha=90, layers=14):
    n = img.size[0]
    lay = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for i in range(layers, 0, -1):
        r = radius * (1 + i * 0.24)
        a = int(alpha * (1 - i / (layers + 1)) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return Image.alpha_composite(img, lay)


def variant_a():
    """A 저점 표식 — 파랑으로 내려와 금색 점에서 바닥, 빨강으로 들린다."""
    n = S * K
    img = canvas()
    # 획: 왼쪽 위에서 내려와 아래 가운데에서 바닥을 찍고 오른쪽 위로 살짝 들린다.
    # 하락 구간을 길게, 반등 구간을 짧게 — '떨어진 것을 산다' 가 주제이므로.
    P = [(0.16, 0.27), (0.28, 0.43), (0.38, 0.545), (0.50, 0.66), (0.62, 0.575), (0.80, 0.44)]
    pts = [(x * n, y * n) for x, y in P]
    w = int(n * 0.075)
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).line(pts, fill=255, width=w, joint="curve")
    d2 = ImageDraw.Draw(mask)
    for x, y in (pts[0], pts[-1]):                     # 끝을 둥글게
        d2.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    grad = hgrad(n, [(0.0, DOWN), (0.42, DOWN), (0.55, GOLD), (0.70, UP), (1.0, UP)])
    stroke = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    stroke.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, stroke)
    # 저점에 금색 점 — 이 아이콘의 주인공
    bx, by = pts[3]
    r = int(n * 0.078)
    img = glow(img, bx, by, r, GOLD, alpha=100)
    dd = ImageDraw.Draw(img)
    dd.ellipse([bx - r, by - r, bx + r, by + r], fill=(5, 6, 10, 255))     # 획을 파내고
    dd.ellipse([bx - r * 0.66, by - r * 0.66, bx + r * 0.66, by + r * 0.66],
               fill=GOLD + (255,))
    return img


def variant_b():
    """B 떨어지는 것 중 하나 — 파란 점들이 흩어져 떨어지고 바닥의 하나만 금색."""
    n = S * K
    img = canvas()
    d = ImageDraw.Draw(img)
    # 위는 흩어진 흐린 점, 아래로 갈수록 모이고 어두워지다 바닥에 금색 하나
    dots = [(0.22, 0.24, 0.030, FAINT), (0.42, 0.20, 0.026, FAINT), (0.62, 0.26, 0.030, FAINT),
            (0.80, 0.22, 0.024, FAINT),
            (0.30, 0.39, 0.034, DOWN), (0.55, 0.36, 0.030, DOWN), (0.74, 0.42, 0.028, DOWN),
            (0.40, 0.53, 0.034, DOWN), (0.63, 0.55, 0.032, DOWN)]
    for x, y, r, c in dots:
        xx, yy, rr = x * n, y * n, r * n
        a = 255 if c is DOWN else 220
        d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], fill=c + (a,))
    bx, by, r = 0.5 * n, 0.745 * n, int(n * 0.085)
    img = glow(img, bx, by, r, GOLD, alpha=105)
    ImageDraw.Draw(img).ellipse([bx - r, by - r, bx + r, by + r], fill=GOLD + (255,))
    return img


def variant_c():
    """C 바닥 곡선 — 완만한 그릇 + 바닥의 금색 점 하나. 가장 단순해 16px 에 강하다."""
    n = S * K
    img = canvas()
    # 포물선 그릇
    pts = []
    for i in range(41):
        t = i / 40
        x = 0.155 + 0.69 * t
        y = 0.335 + 1.12 * (t - 0.5) ** 2 * -1 + 0.28     # 아래로 볼록
        y = 0.335 + (1 - 4 * (t - 0.5) ** 2) * 0.30
        pts.append((x * n, y * n))
    w = int(n * 0.082)
    mask = Image.new("L", (n, n), 0)
    stamp(mask, pts, w)
    grad = hgrad(n, [(0.0, DOWN), (0.40, DOWN), (0.52, GOLD), (0.66, UP), (1.0, UP)])
    stroke = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    stroke.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, stroke)
    bx, by = pts[20]
    r = int(n * 0.082)
    img = glow(img, bx, by, r, GOLD, alpha=105)
    dd = ImageDraw.Draw(img)
    dd.ellipse([bx - r, by - r, bx + r, by + r], fill=(5, 6, 10, 255))
    dd.ellipse([bx - r * 0.64, by - r * 0.64, bx + r * 0.64, by + r * 0.64], fill=GOLD + (255,))
    return img



def bez(P, n=80):
    """3차 베지에 샘플링 — P 는 제어점 4개."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = (u**3 * P[0][0] + 3*u*u*t * P[1][0] + 3*u*t*t * P[2][0] + t**3 * P[3][0])
        y = (u**3 * P[0][1] + 3*u*u*t * P[1][1] + 3*u*t*t * P[2][1] + t**3 * P[3][1])
        out.append((x, y))
    return out


def stamp(mask, pts, w):
    """획을 **원 도장**으로 찍어 그린다.

    joint="curve" 로 촘촘한 점을 이으면 조인트가 겹쳐 톱니가 생긴다
    (2026-09-09 D 1차 시도). 반지름 w/2 원을 경로를 따라 촘촘히 찍으면
    이음새 없이 둥근 끝·둥근 관절이 한 번에 나온다.
    """
    d = ImageDraw.Draw(mask)
    r = w / 2
    prev = None
    for x, y in pts:
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            L = (dx * dx + dy * dy) ** 0.5
            steps = max(1, int(L / (r * 0.25)))
            for i in range(1, steps + 1):
                px_, py_ = prev[0] + dx * i / steps, prev[1] + dy * i / steps
                d.ellipse([px_ - r, py_ - r, px_ + r, py_ + r], fill=255)
        else:
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        prev = (x, y)


def variant_d():
    """D 비대칭 바닥 — A 의 의미(긴 하락·짧은 반등)와 C 의 깔끔한 곡선을 합친다.

    좌우대칭이면 그냥 골짜기다. **하락을 길고 가파르게 / 반등을 짧고 완만하게** 두면
    '떨어진 것을 산다' 가 형태에 남는다. 저점은 가운데가 아니라 왼쪽으로 치우친다.
    """
    n = S * K
    img = canvas()
    # 광학 중심 보정 — 도형이 왼쪽 아래로 쏠려 보여 오른쪽·위로 조금 민다
    OX, OY = 0.018, -0.022
    trough = (0.415 + OX, 0.665 + OY)
    fall = bez([(0.155 + OX, 0.215 + OY), (0.255 + OX, 0.435 + OY),
                (0.315 + OX, 0.665 + OY), trough], 60)
    rise = bez([trough, (0.545 + OX, 0.665 + OY), (0.675 + OX, 0.575 + OY),
                (0.845 + OX, 0.395 + OY)], 60)
    pts = [(x * n, y * n) for x, y in fall + rise[1:]]
    w = int(n * 0.090)
    mask = Image.new("L", (n, n), 0)
    stamp(mask, pts, w)
    grad = hgrad(n, [(0.0, DOWN), (0.34, DOWN), (0.433, GOLD), (0.57, UP), (1.0, UP)])
    stroke = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    stroke.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, stroke)
    bx, by = trough[0] * n, trough[1] * n
    r = int(n * 0.090)
    img = glow(img, bx, by, int(r * 0.78), GOLD, alpha=95, layers=12)
    dd = ImageDraw.Draw(img)
    dd.ellipse([bx - r, by - r, bx + r, by + r], fill=(7, 9, 16, 255))
    dd.ellipse([bx - r * 0.76, by - r * 0.76, bx + r * 0.76, by + r * 0.76],
               fill=GOLD + (255,))
    return img


V = {"A": variant_a, "C": variant_c, "D": variant_d}
made = {}
for k, fn in V.items():
    im = fn().resize((S, S), Image.LANCZOS)
    made[k] = im
    im.save(BASE / f"icon2_{k}.png")
    print(f"{k} 저장 icon2_{k}.png")

sizes = [96, 32, 16]
pad, gapx, gapy = 40, 40, 30
W = pad * 2 + S * 3 + gapx * 2
H = pad * 2 + S + gapy + 96 + 40
sheet = Image.new("RGB", (W, H), (18, 20, 26))
dr = ImageDraw.Draw(sheet)
for i, k in enumerate("ACD"):
    x = pad + i * (S + gapx)
    sheet.paste(made[k], (x, pad), made[k])
    xx = x
    for sz in sizes:
        th = made[k].resize((sz, sz), Image.LANCZOS)
        sheet.paste(th, (xx, pad + S + gapy + (96 - sz) // 2), th)
        xx += sz + 24
    dr.text((x, pad + S + gapy + 96 + 8), k, fill=(220, 225, 235))
sheet.save(BASE / "icon2_compare.png")
print("비교 시트 저장 icon2_compare.png")
