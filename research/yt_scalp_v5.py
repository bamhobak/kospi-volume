# -*- coding: utf-8 -*-
"""유튜브 V5 a6LRWJZIhDI '단타 천재가 알려준 3가지' (타네샤 가르그 캔들) — 5분봉 (2026-10-07, yt_scalp 의 다섯째).
매수: 5분봉 상승장악형(음봉 몸통을 양봉 몸통이 덮음) & 두 봉을 합친 10분봉이 망치형(아래꼬리 ≥ 몸통 2배 · 종가가 위 1/3) &
      지지 구역 안 — 지지 구역 = 직전 2시간(24봉, 최근 3봉 제외) 저점을 만든 '전환 직전 마지막 캔들'의 고~저 범위.
목표: 저항 구역 = 직전 2시간 고점 캔들의 저가(구역 아래 끝 — 구역에 닿으면 익절) · 반대 신호(하락장악형) 나오면 그 봉 종가에 정리 ·
손절: 장악형 두 봉 저점 아래 · 장 끝 정리. 장악형만(지지·망치 조건 없음) 판도 같이 잰다.
비용·표본은 yt_scalp 와 같음.
    python research/yt_scalp_v5.py
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


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    T = []
    for d, g in D.groupby("date", sort=True):
        if len(g) < 300: continue
        b = Y.bars5(g); o, h, l, c = b.o.values, b.h.values, b.l.values, b.c.values; n = len(c)
        busy = -1
        for j in range(27, n - 1):
            if j <= busy: continue
            if not (c[j - 1] < o[j - 1] and c[j] > o[j] and o[j] <= c[j - 1] and c[j] >= o[j - 1]): continue
            # 10분봉 합치기
            O, H, L, C = o[j - 1], max(h[j - 1], h[j]), min(l[j - 1], l[j]), c[j]
            body = abs(C - O); lw = min(O, C) - L
            hammer = lw >= 2 * body and (C - L) >= (H - L) * 2 / 3 and H > L
            w = slice(j - 27, j - 2)
            k = (j - 27) + int(np.argmin(l[w])); zl, zh = l[k], h[k]
            insup = L <= zh and L >= zl * 0.995
            r_ = (j - 27) + int(np.argmax(h[w])); res = l[r_]
            stop = L * 0.999; px = c[j]
            for lab, ok, tg in (("V5 장악형+망치형+지지 구역 → 저항 구역", hammer and insup, res if res > px else None),
                                ("V5 장악형+지지 구역(망치 조건 없음) → 저항 구역", insup, res if res > px else None),
                                ("V5 장악형만 → 장 끝(견줌)", True, None)):
                if not ok: continue
                ret = None; sl = 1
                for q in range(j + 1, n):
                    if l[q] <= stop: ret = (min(stop, o[q]) / px - 1) * 100; sl = 2; break
                    if tg is not None and h[q] >= tg: ret = (max(tg, o[q]) / px - 1) * 100; break
                    if c[q] < o[q] and c[q - 1] > o[q - 1] and o[q] >= c[q - 1] and c[q] <= o[q - 1]:
                        ret = (c[q] / px - 1) * 100; sl = 2; break
                if ret is None: ret = (c[-1] / px - 1) * 100
                T.append((lab, d, ret, sl))
            busy = j
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
        for r in ex.map(one, jobs, chunksize=2): rows += r
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    R.to_pickle(ROOT / "cache" / "yt_scalp_v5.pkl")
    P("# 유튜브 V5 캔들(장악형·망치형·지지/저항 구역) 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 기법 | 건수 | 비용 전 평균 | 학습: 평균·승률 | 검증: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
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
    log_trials("yt_scalp_v5_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("yt_scalp_v5_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
