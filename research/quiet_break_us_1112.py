# -*- coding: utf-8 -*-
"""잔잔하다 깨진 종목 — 미장판 (2026-11-12, quiet_break_1112.py 와 같은 정의). 종목을 묶음으로 나눠 계산(연구 하나당 RAM 6GB 규칙 — 한 번에 다 올리면 9.6GB).
자료: data/us/raw/chunk_*.pkl(살아 있는 종목, 수정주가 adj) + data/us/tiingo_dead.db(폐지 종목 adjClose) — 2007~.
유니버스: 종가 $3↑ · 20일 평균 거래대금 $100만↑ · |등락| < 40% · 앞으로 수익 -95~+500% 로 자름(깨진 수정주가). 매수 = 신호 날 종가 → h일째 종가 · 비용 0.20.
    python research/quiet_break_us_1112.py
"""
import glob, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import quiet_break_1112 as Q

Q.COST = 0.20
HS = Q.HS
VARS = [(L, q, B) for L in (60, 120) for q in (0.8, 0.9) for B in ("B1", "B3")]


def prep(D):
    D["date"] = D.date.astype(str).str[:10].str.replace("-", "")
    D = D[D.date >= "20070101"]
    for k in ("adj", "close", "volume"): D[k] = pd.to_numeric(D[k], errors="coerce").astype("float32")
    D = D.dropna(subset=["adj", "close"]).drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    D["change"] = (D.groupby("ticker").adj.pct_change() * 100).astype("float32")
    D["amount"] = (D.close * D.volume).astype("float32")
    D = D.dropna(subset=["change"]).reset_index(drop=True)
    D["open"] = np.nan
    return D[["ticker", "date", "open", "close", "change", "amount"]]


def batches():
    have = set()
    for f in sorted(glob.glob(str(BASE / "data" / "us" / "raw" / "chunk_*.pkl"))):
        X = pd.read_pickle(f)[["ticker", "date", "adj", "close", "volume"]]
        have |= set(X.ticker.unique())
        yield prep(X)
    c = sqlite3.connect("file:" + str(BASE / "data" / "us" / "tiingo_dead.db") + "?mode=ro", uri=True)
    dead = [t for (t,) in c.execute("select distinct ticker from px") if t not in have]
    for i in range(0, len(dead), 250):
        part = dead[i:i + 250]
        E = pd.read_sql("select ticker, date, adjClose as adj, close, volume from px where ticker in (%s)" % ",".join("?" * len(part)), c, params=part)
        if len(E): yield prep(E)


def main():
    sums = {h: [] for h in HS}
    ev = []
    nb = 0
    for D in batches():
        D = Q.build(D)
        D["di"] = D.groupby("ticker").cumcount().astype("int32")         # 종목별 거래일 번호(60거래일 안 다시 안 셈)
        for h in HS: D["f%d" % h] = D["f%d" % h].clip(-95, 500)                 # 폐지 종목 수정주가가 깨진 줄(병합 등) — -2,600% 같은 값이 섞였었다
        D = D[D.change.abs() < 40]                                               # 하루 ±40%↑ 는 자료 깨짐으로 보고 잔잔 계산 전에 버리진 않지만 신호·시장에선 뺀다
        U = D[(D.close >= 3) & (D.a20 >= 1e6)]
        for h in HS:
            g = U.groupby("date")["f%d" % h].agg(["sum", "count"]); sums[h].append(g)
        for L, q, B in VARS:
            base = U[(U["q%d_%s" % (L, B[1])] >= q) & (U["calm5_%s" % B[1]] >= 1)]
            br = base[base.change.abs() > 1.0] if B == "B1" else base[base.out3 >= 2]
            mag = br.change if B == "B1" else br.r3
            keep = ["ticker", "date", "di"] + ["f%d" % h for h in HS]
            for side in ("위", "아래"):
                for m in (1, 2, 3):
                    Z = br[(mag > m) if side == "위" else (mag < -m)][keep]
                    if len(Z): ev.append(Z.assign(L=L, q=q, B=B, side=side, m=m))
            C = base[base.change.abs() <= 1.0][keep]
            if len(C): ev.append(C.sample(frac=0.2, random_state=1).assign(L=L, q=q, B=B, side="대조(안 깨짐)", m=0) if len(C) > 5000 else C.assign(L=L, q=q, B=B, side="대조(안 깨짐)", m=0))
        nb += 1
        if nb % 10 == 0: print("묶음", nb, flush=True)
        del D, U
    mk = {}
    for h in HS:
        S = pd.concat(sums[h]).groupby(level=0).sum(); mk[h] = S["sum"] / S["count"]
    E = pd.concat(ev, ignore_index=True)
    rows = []
    for key, Z in E.groupby(["L", "q", "B", "side", "m"]):
        Z = Q.dedup(Z.reset_index(drop=True))
        for h in HS:
            s = Q.stats(Z, h, mk[h])
            if s: rows.append(dict(zip(["L", "q", "B", "side", "m"], key), h=h, **s))
    R = pd.DataFrame(rows)
    R.to_pickle(ROOT / "cache" / "quiet_break_1112_us.pkl")
    Q.OUT.clear()
    Q.P("미장 자료 2007~ · 신호 후보 %d줄\n" % len(E))
    fmt = lambda e: "%+.2f (%d)" % (e[0], e[1]) if e[1] else "-"
    for h in HS:
        Q.P("\n## 보유 %d일 — 시장 대비 초과(건당, 비용 뒤)\n" % h)
        Q.P("| 잔잔 L·q | 깨짐 | 방향·크기 | 건수 | 건당 | 승률 | 시장 대비 | 2007~15 | 학습 16~22 (t) | 검증 23~ (t) | 해 플러스 |")
        Q.P("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in R[R.h == h].itertuples():
            Q.P("| %d일·%.0f%% | %s | %s %s | %d | %+.2f%% | %.0f%% | %+.2f%%p (t %.1f) | %s | %+.2f (%d, t %.1f) | %+.2f (%d, t %.1f) | %d/%d |" % (
                r.L, r.q * 100, "오늘 처음" if r.B == "B1" else "3일 중 2일", r.side, ("%d%%↑" % r.m) if r.m else "", r.n, r.mean, r.win, r.ex, r.t,
                fmt(r.e0), r.e1[0], r.e1[1], r.e1[2], r.e2[0], r.e2[1], r.e2[2], r.ypos, r.ny))
    (ROOT / "quiet_break_us_1112.out").write_text("\n".join(Q.OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
