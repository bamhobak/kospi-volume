# -*- coding: utf-8 -*-
"""앱 아이콘 3차 — 좌우대칭 곡선을 '웃는 얼굴' 로 완성한다.

사용자가 2차의 C안(좌우대칭 그릇)을 골랐다. 이유가 좋다 — **웃는 입 모양처럼 생겼다**.
거기에 웃는 눈을 얹으면 의미가 한 겹 더 붙는다.
  · 입   — 파랑으로 내려와 금색 저점을 찍고 빨강으로 오른다(한국 관습: 하락 파랑·상승 빨강)
  · 저점 — 금색 점. 이 앱의 아홉 규칙은 전부 '떨어진 것을 산다'
  · 눈   — 웃는 눈(^^). 남들이 무서워할 때 웃는 사람. 역발상 그 자체다

눈 색을 셋으로 만들어 비교한다(입이 주인공이라 눈이 시끄러우면 안 된다).
  E1 중립 흰색     — 입의 색 대비를 방해하지 않는다
  E2 좌 파랑·우 빨강 — 입의 그라데이션과 짝을 맞춘다
  E3 금색          — 저점 점과 같은 색으로 묶는다

⚠ 16px 에서 눈이 살아남는지 반드시 본다. 눈은 작아서 제일 먼저 뭉개진다.
⚠ 획은 원 도장으로 그린다 — joint="curve" 로 촘촘한 점을 이으면 톱니가 생긴다(2차에서 확인).
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
from PIL import Image, ImageDraw

BASE = Path(__file__).parent
S, K = 512, 4
BG0, BG1 = (13, 16, 32), (5, 6, 10)
DOWN = (59, 130, 246)
UP = (248, 113, 113)
GOLD = (251, 191, 36)
WHITE = (226, 232, 244)


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
    """획을 원 도장으로 찍는다 — 이음새·톱니가 생기지 않는다."""
    d = ImageDraw.Draw(mask)
    r = w / 2
    prev = None
    for x, y in pts:
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            L = (dx * dx + dy * dy) ** 0.5
            for i in range(1, max(1, int(L / (r * 0.25))) + 1):
                st = max(1, int(L / (r * 0.25)))
                px_, py_ = prev[0] + dx * i / st, prev[1] + dy * i / st
                d.ellipse([px_ - r, py_ - r, px_ + r, py_ + r], fill=255)
        else:
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        prev = (x, y)


def glow(img, cx, cy, radius, color, alpha=95, layers=12):
    n = img.size[0]
    lay = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for i in range(layers, 0, -1):
        r = radius * (1 + i * 0.24)
        a = int(alpha * (1 - i / (layers + 1)) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return Image.alpha_composite(img, lay)


def parab(x0, x1, ytop, depth, m=48):
    """아래로 볼록한 포물선(입). ytop 은 양 끝 높이, depth 는 바닥까지."""
    out = []
    for i in range(m + 1):
        t = i / m
        x = x0 + (x1 - x0) * t
        y = ytop + (1 - 4 * (t - 0.5) ** 2) * depth
        out.append((x, y))
    return out


def arch(cx, w, ytop, h, m=28):
    """위로 볼록한 아치(웃는 눈 ^)."""
    out = []
    for i in range(m + 1):
        t = i / m
        x = cx - w / 2 + w * t
        y = ytop + 4 * (t - 0.5) ** 2 * h
        out.append((x, y))
    return out


def face(eye_mode):
    n = S * K
    img = canvas()

    # ── 입 ── 좌우대칭 그릇. 바닥에 금색 저점.
    # 입은 눈보다 확실히 아래에 — 1차에서 눈과 입 끝이 붙어 엉켰다.
    MX0, MX1, MYT, MDEP = 0.205, 0.795, 0.565, 0.155
    pts = [(x * n, y * n) for x, y in parab(MX0, MX1, MYT, MDEP)]
    w = int(n * 0.078)
    mask = Image.new("L", (n, n), 0)
    stamp(mask, pts, w)
    grad = hgrad(n, [(0.0, DOWN), (0.40, DOWN), (0.50, GOLD), (0.60, UP), (1.0, UP)])
    stroke = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    stroke.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, stroke)

    # ── 눈 ── 웃는 눈(^^). 입보다 가늘고 짧게 — 입이 주인공이다.
    # 눈은 가늘고 짧게. 두꺼우면 눈썹으로 보인다.
    EY, EW, EH, EWID = 0.325, 0.135, 0.062, 0.050
    if eye_mode == "E1":
        cols = (WHITE, WHITE)
    elif eye_mode == "E2":
        cols = (DOWN, UP)
    else:
        cols = (GOLD, GOLD)
    for cx_, col in ((0.348, cols[0]), (0.652, cols[1])):
        em = Image.new("L", (n, n), 0)
        stamp(em, [(x * n, y * n) for x, y in arch(cx_, EW, EY, EH)], int(n * EWID))
        lay = Image.new("RGBA", (n, n), col + (255,))
        lay.putalpha(em)
        img = Image.alpha_composite(img, lay)

    # ── 저점 점 ── 입 바닥 한가운데
    bx, by = 0.5 * n, (MYT + MDEP) * n
    r = int(n * 0.077)
    img = glow(img, bx, by, int(r * 0.8), GOLD, alpha=95)
    dd = ImageDraw.Draw(img)
    dd.ellipse([bx - r, by - r, bx + r, by + r], fill=(7, 9, 16, 255))
    dd.ellipse([bx - r * 0.75, by - r * 0.75, bx + r * 0.75, by + r * 0.75], fill=GOLD + (255,))
    return img


made = {}
for k in ("E1", "E2", "E3"):
    im = face(k).resize((S, S), Image.LANCZOS)
    made[k] = im
    im.save(BASE / f"icon3_{k}.png")
    print(f"{k} 저장 icon3_{k}.png")

sizes = [96, 32, 16]
pad, gapx, gapy = 40, 40, 30
W = pad * 2 + S * 3 + gapx * 2
H = pad * 2 + S + gapy + 96 + 40
sheet = Image.new("RGB", (W, H), (18, 20, 26))
dr = ImageDraw.Draw(sheet)
for i, k in enumerate(("E1", "E2", "E3")):
    x = pad + i * (S + gapx)
    sheet.paste(made[k], (x, pad), made[k])
    xx = x
    for sz in sizes:
        th = made[k].resize((sz, sz), Image.LANCZOS)
        sheet.paste(th, (xx, pad + S + gapy + (96 - sz) // 2), th)
        xx += sz + 24
    dr.text((x, pad + S + gapy + 96 + 8), k, fill=(220, 225, 235))
sheet.save(BASE / "icon3_compare.png")
print("비교 시트 저장 icon3_compare.png")
