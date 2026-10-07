# -*- coding: utf-8 -*-
"""유튜브 eTFnJAZi6Tg 김직선 '매일 1시간이면 충분한 시초가 단타매매' (2026-10-07) — 개장 첫 1시간봉 박스.
박스 = 개장 첫 60분 고가·저가 · 중간선 50%. 박스가 끝난 뒤 2시간 안에서만 5분봉으로 진입(영상: '첫 두 시간 동안 가장 유효').
  ① 박스 하단 반등: 5분봉 저가가 박스 하단(+0.1%) 이하로 닿고 종가는 하단 위 · 아래꼬리 ≥ 몸통 → 종가 매수 · 그 봉 저가 손절 ·
     목표 = 중간선 / 상단 / 장 끝
  ② 상단 돌파 뒤 되돌림: 5분봉 종가가 박스 상단 위로 마감(돌파) → 이후 저가가 상단(+0.1%) 이하로 되돌리고 종가는 상단 위 · 아래꼬리 ≥ 몸통 →
     종가 매수 · 손절 = 박스 하단(영상) / 중간선(좁은 판) · 목표 = 상단 + 박스 폭 1배 / 2배 / 장 끝
  (영상의 매도 쪽 — 상단 저항 숏 · 하단 이탈 되돌림 숏 — 은 국장 공매도가 안 돼서 뺐다)
비용·표본은 yt_scalp 와 같음(국장 0.23%+미끄러짐 0.05%×횟수 · 미장 0.20%+0.02% · 같은 봉 손절 우선).
    python research/yt_scalp8.py
"""
import json, sys, time, random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import yt_scalp as Y
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
BOX = {"KR": ("1000", "1200"), "US": ("1030", "1230")}       # (박스 끝, 진입 마감)


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    bend, wend = BOX[mk]; T = []
    for d, g in D.groupby("date", sort=True):
        if len(g) < 300: continue
        b = Y.bars5(g.reset_index(drop=True)); o, h, l, c, hm = b.o.values, b.h.values, b.l.values, b.c.values, b.hm.values
        bi = np.where(hm <= bend)[0]
        if len(bi) < 10: continue
        bh, bl = h[bi].max(), l[bi].min(); mid = (bh + bl) / 2; rng = bh - bl
        if rng <= 0: continue
        n = len(c); st = bi[-1] + 1
        body = np.abs(c - o); lw = np.minimum(o, c) - l
        # ① 박스 하단 반등
        for j in range(st, n - 1):
            if hm[j] > wend: break
            if l[j] <= bl * 1.001 and c[j] > bl and lw[j] >= body[j] and lw[j] > 0:
                px = c[j]; stp = l[j] * 0.999
                for nm, tg in (("중간선", mid), ("상단", bh), ("장 끝", None)):
                    if tg is not None and tg <= px: continue
                    r, s = Y.run_trade(o, h, l, c, j, px, stp, tg); T.append(("① 박스 하단 반등 → %s" % nm, d, r, 1 + s))
                break
        # ② 상단 돌파 뒤 되돌림
        brk = None
        for j in range(st, n - 1):
            if hm[j] > wend: break
            if brk is None:
                if c[j] > bh: brk = j
                continue
            if l[j] <= bh * 1.001 and c[j] >= bh and lw[j] >= body[j] and lw[j] > 0:
                px = c[j]
                for sn, stp in (("손절 박스 하단(영상)", bl * 0.999), ("손절 중간선", mid * 0.999)):
                    for nm, tg in (("+박스 1배", bh + rng), ("+박스 2배", bh + 2 * rng), ("장 끝", None)):
                        r, s = Y.run_trade(o, h, l, c, j, px, stp, tg); T.append(("② 상단 돌파 뒤 되돌림 · %s → %s" % (sn, nm), d, r, 1 + s))
                break
    return [(mk,) + x for x in T]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:")); random.seed(7); kr = random.sample(kr, 300)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for r in ex.map(one, jobs, chunksize=4): rows += r
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    P("# 유튜브 김직선 '시초가 1시간 박스' 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d · 미장 대형주 %d · 2022-12~2026-10 · 비용 뒤" % (len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"]))); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수 | 비용 전 평균 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            cell = []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            P("| %s | %d | %+.3f%% | %s | %s | %s |" % (s, len(z), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values)))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("yt_scalp8_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("yt_scalp8_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
