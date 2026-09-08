# -*- coding: utf-8 -*-
"""앱 아이콘 생성 — '막대그래프 + 빨간 화살표' 클리셰를 버린다.

옛 아이콘의 문제(2026-09-09 사용자 지적: "21세기에 맞게"):
  · 파란 막대 + 빨간 우상향 화살표는 금융 앱 아이콘 중 가장 흔한 형태다
  · 사이트 강조색이 보라(--acc #a78bfa)인데 아이콘은 파랑이라 브랜드가 안 맞는다
  · 화살표 폴리곤이 작은 크기(16px 파비콘)에서 뭉갠다

새 방향: 이 앱이 하는 일은 '오른다'가 아니라 **수천 종목에서 몇 개를 골라낸다**는 것.
그래서 선별(퍼널)을 형태로 쓴다. 색은 사이트 팔레트를 그대로 따른다.
  배경 #0a0b0e~#151824 · 강조 #a78bfa(보라) · 보조 #60a5fa(파랑) · 흐린 #3a4150

세 안을 만들어 비교한다.
  A 퍼널 바   — 폭이 줄어드는 가로 막대 셋 + 아래 보라 점 (걸러내려 하나를 남긴다)
  B 신호 격자 — 흐린 점들 사이에서 하나만 보라로 빛난다 (모래밭의 바늘)
  C 퍼널 실루엣 — 채워진 사다리꼴이 좁아지고 그 아래 한 점 (가장 굵고 단순)

⚠ 파비콘은 16px 에서도 읽혀야 한다. 4배로 그린 뒤 축소해 계단을 없애고,
   16px 축소본을 같이 뽑아 눈으로 확인한다.
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
from PIL import Image, ImageDraw

BASE = Path(__file__).parent
S = 512          # 최종 크기
K = 4            # 안티에일리어싱 배율
BG0, BG1 = (21, 24, 36), (10, 11, 14)      # 배경 그라데이션(좌상 → 우하)
ACC = (167, 139, 250)                       # --acc 보라
BLU = (96, 165, 250)                        # --dn 파랑
DIM = (58, 65, 80)                          # 흐린 회색
MID = (92, 104, 128)


def canvas():
    """둥근 사각형 + 대각 그라데이션 배경."""
    n = S * K
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(0, n, 8):                       # 8px 단위로 계산(속도)
            t = (x / n + y / n) / 2
            c = tuple(int(BG0[i] + (BG1[i] - BG0[i]) * t) for i in range(3))
            for dx in range(8):
                if x + dx < n:
                    px[x + dx, y] = c
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.235), fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(g, (0, 0), mask)
    # 안쪽 위 가장자리에 아주 옅은 하이라이트 — 유리 느낌
    hl = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle(
        [int(n * 0.02), int(n * 0.02), n - int(n * 0.02), n - int(n * 0.02)],
        radius=int(n * 0.22), outline=(255, 255, 255, 18), width=int(n * 0.008))
    return Image.alpha_composite(out, hl)


def glow(img, box, color, radius, alpha=70):
    """보라 점 뒤에 부드러운 번짐 — 여러 겹의 반투명 원."""
    n = img.size[0]
    lay = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cx, cy = box
    for i in range(12, 0, -1):
        r = radius * (1 + i * 0.22)
        a = int(alpha * (1 - i / 13) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return Image.alpha_composite(img, lay)


def variant_a():
    """A 퍼널 바 — 폭이 줄어드는 가로 막대 셋 + 아래 보라 점."""
    n = S * K
    img = canvas()
    d = ImageDraw.Draw(img)
    cx = n // 2
    bars = [(0.62, 0.30, DIM, 255), (0.42, 0.435, MID, 255), (0.22, 0.57, ACC, 255)]
    h = int(n * 0.072)
    for w, y, col, a in bars:
        ww = int(n * w)
        yy = int(n * y)
        d.rounded_rectangle([cx - ww // 2, yy, cx + ww // 2, yy + h],
                            radius=h // 2, fill=col + (a,))
    r = int(n * 0.052)
    img = glow(img, (cx, int(n * 0.755)), ACC, r)
    ImageDraw.Draw(img).ellipse([cx - r, int(n * 0.755) - r, cx + r, int(n * 0.755) + r],
                                fill=ACC + (255,))
    return img


def variant_b():
    """B 신호 격자 — 흐린 점 사이에서 하나만 보라로 빛난다."""
    n = S * K
    img = canvas()
    d = ImageDraw.Draw(img)
    cols, rows = 4, 4
    pad = 0.245
    step = (1 - pad * 2) / (cols - 1)
    r0 = int(n * 0.035)
    pick = (2, 1)                                   # 빛나는 칸(열, 행)
    for i in range(cols):
        for j in range(rows):
            x = int(n * (pad + step * i))
            y = int(n * (pad + step * j))
            if (i, j) == pick:
                continue
            col = DIM if (i + j) % 2 else (46, 52, 64)
            d.ellipse([x - r0, y - r0, x + r0, y + r0], fill=col + (255,))
    px_, py_ = int(n * (pad + step * pick[0])), int(n * (pad + step * pick[1]))
    r1 = int(n * 0.072)
    img = glow(img, (px_, py_), ACC, r1, alpha=90)
    ImageDraw.Draw(img).ellipse([px_ - r1, py_ - r1, px_ + r1, py_ + r1], fill=ACC + (255,))
    return img


def variant_c(hw0=0.255, hw1=0.052, top=0.245, bot=0.60, gap=0.145, rr=0.05, dotr=0.058):
    """C 퍼널 실루엣 — 모서리를 둥글린 사다리꼴 + 그 아래 한 점.

    모서리는 **안쪽으로 r 만큼 줄인 폴리곤을 채우고, 그 외곽선을 굵기 2r·둥근 조인트로
    덧그려** 만든다. 꼭짓점마다 원을 얹는 방식은 원이 변 밖으로 튀어나와 혹이 생긴다
    (2026-09-09 1차 시도의 실패).
    """
    n = S * K
    img = canvas()
    lay = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    r = n * rr
    # 원래 사다리꼴
    P = [(n * (0.5 - hw0), n * top), (n * (0.5 + hw0), n * top),
         (n * (0.5 + hw1), n * bot), (n * (0.5 - hw1), n * bot)]
    # 각 꼭짓점을 도형 중심 쪽으로 r 만큼 당긴다
    cx = sum(x for x, _ in P) / 4
    cy = sum(y for _, y in P) / 4
    Q = []
    for x, y in P:
        dx, dy = cx - x, cy - y
        L = (dx * dx + dy * dy) ** 0.5
        Q.append((x + dx / L * r, y + dy / L * r))
    d.polygon(Q, fill=BLU + (255,))
    # ⚠ joint="curve" 는 **시작점의 조인트를 안 굴린다**. 두 번째 점까지 이어 붙여
    #   시작점도 한 번은 '중간 꼭짓점' 이 되게 해야 홈이 안 생긴다.
    d.line(Q + [Q[0], Q[1]], fill=BLU + (255,), width=int(r * 2), joint="curve")
    # 위 파랑 → 아래 보라
    grad = Image.new("L", (n, n), 0)
    gp = grad.load()
    for y in range(n):
        t = max(0.0, min(1.0, (y / n - top) / (bot - top)))
        v = int(255 * t ** 1.25)
        for x in range(0, n, 8):
            for dx in range(8):
                if x + dx < n:
                    gp[x + dx, y] = v
    vio = Image.new("RGBA", (n, n), ACC + (255,))
    grad = Image.composite(grad, Image.new("L", (n, n), 0), lay.split()[3])
    lay = Image.alpha_composite(lay, Image.merge("RGBA", (*vio.split()[:3], grad)))
    img = Image.alpha_composite(img, lay)
    dr_ = int(n * dotr)
    cyd = int(n * (bot + gap))
    img = glow(img, (n // 2, cyd), ACC, dr_, alpha=62)
    ImageDraw.Draw(img).ellipse([n // 2 - dr_, cyd - dr_, n // 2 + dr_, cyd + dr_],
                                fill=ACC + (255,))
    return img


V = {"A": variant_a, "B": variant_b, "C": variant_c}
made = {}
for k, fn in V.items():
    im = fn().resize((S, S), Image.LANCZOS)
    made[k] = im
    im.save(BASE / f"icon_try_{k}.png")
    print(f"{k} 저장 icon_try_{k}.png")

# 비교 시트 — 큰 것 / 96px / 32px / 16px 을 나란히 (작은 크기에서 뭉개지는지 확인)
sizes = [S, 96, 32, 16]
pad, gapx, gapy = 40, 40, 30
W = pad * 2 + S * 3 + gapx * 2
H = pad * 2 + S + gapy + 96
sheet = Image.new("RGB", (W, H + 40), (18, 20, 26))
dr = ImageDraw.Draw(sheet)
for i, k in enumerate("ABC"):
    x = pad + i * (S + gapx)
    sheet.paste(made[k], (x, pad), made[k])
    xx = x
    for sz in sizes[1:]:
        th = made[k].resize((sz, sz), Image.LANCZOS)
        sheet.paste(th, (xx, pad + S + gapy + (96 - sz) // 2), th)
        xx += sz + 24
    dr.text((x, pad + S + gapy + 96 + 8), f"{k}", fill=(220, 225, 235))
sheet.save(BASE / "icon_compare.png")
print("비교 시트 저장 icon_compare.png")
