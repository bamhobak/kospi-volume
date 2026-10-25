# -*- coding: utf-8 -*-
"""ⓒ NXT 장후 신호에 '낮에 효과 본 축'을 붙여 가르나 (2026-10-26 사용자).
nxt_wide 의 Z 를 캐시만으로 재구성(네트워크 X) → lab.hist 재료(mcap·d120·lo250·vol20·age) 조인 →
안정 신호(상위절반·시장대비 2%p↓·시장-1%날 쉼·10분 3천만↑) 안에서 축별 다음날 시가 수익(r_vw) 비교.
    py314 research/nxt_axis_1026.py
"""
import sys, time
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research'); BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import lab
CK = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def build_Z():
    K = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "marcap", "pref"]]
    K = K[K.date >= "20250101"]
    K = K[(K.pref != 1) & K.marcap.notna()] if "pref" in K.columns else K[K.marcap.notna()]
    first = K.groupby(K.date.str[:6]).date.min()
    U = {}
    for ym, d0 in first.items():
        z = K[K.date == d0]
        U[ym] = set(z[z.marcap.rank(ascending=False, pct=True) <= 0.5].ticker)
    lastym = max(U)
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")[["t", "d", "o", "c"]]
    D = D[D.d >= "20250301"].copy(); D["ym"] = D.d.str[:6]
    D = D[[t in U.get(ym, U[lastym]) for t, ym in zip(D.t, D.ym)]]
    T = pd.read_parquet(ROOT / "cache" / "toss_kr_1d_wide.parquet")[["t", "d", "tc"]]
    X = D.merge(T, on=["t", "d"]).sort_values(["t", "d"])
    X["o1"] = X.groupby("t").o.shift(-1); X["d1"] = X.groupby("t").d.shift(-1)
    # ⚠ 10-26 고침: 1분봉 요약에 빠진 날이 있으면 다음 행 ≠ 다음 거래일(nxt_monthly 9차에서 찾은 버그) → 달력 다음 거래일만
    cal = sorted(D.d.unique()); nx_ = dict(zip(cal, cal[1:]))
    X = X[X.d1 == X.d.map(nx_)].dropna(subset=["o1"]).copy()
    X["AHd"] = (X.tc / X.c - 1) * 100
    X["mkt"] = X.groupby("d").AHd.transform("mean")
    X["nxt"] = X.groupby("t").AHd.transform(lambda s: (s.abs() > 1e-9).mean() > 0.3)
    have = pd.read_parquet(ROOT / "cache" / "ah_m1.parquet")
    have = have[have.hm.astype(float) >= 1541].copy(); have["hm"] = have.hm.astype(int)
    p50 = have[have.hm <= 1950].sort_values("hm").groupby(["t", "d"]).c.last().rename("p50")
    L = have[(have.hm >= 1951) & (have.hm <= 2000)]
    vw = ((L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)).rename("vw")
    a10 = (L.c * L.v).groupby([L.t, L.d]).sum().rename("a10")
    Z = X.merge(pd.concat([p50, vw, a10], axis=1).reset_index(), on=["t", "d"], how="inner")
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["rel"] = Z.AH50 - Z.mkt
    Z["r_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK
    big = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet").t.unique())
    Z["big"] = Z.t.isin(big)
    return Z


def cell(z):
    if len(z) < 12:
        return "-"
    dd = z.groupby("d").r_vw.mean()
    return "%d건·건%+.2f·승%.0f·날%+.2f" % (len(z), z.r_vw.mean(), (z.r_vw > 0).mean() * 100, dd.mean())


def main():
    t0 = time.time()
    Z = build_Z()
    H = lab.hist()[["ticker", "date", "mcap", "d120", "q_d120", "q_lo250", "q_vol20", "age", "q_mcap"]].rename(columns={"ticker": "t", "date": "d"})
    Z = Z.merge(H, on=["t", "d"], how="left")
    calm = Z.mkt > -1.0
    base = Z[(Z.rel <= -2.0) & calm & (Z.a10 >= 3e7)].copy()
    # 하루 깊은 10
    base["rk"] = base.groupby("d").rel.rank(method="first"); base = base[base.rk <= 10]
    P("# ⓒ NXT 축 실측 · %s" % time.strftime("%Y-%m-%d"))
    P("안정 신호(상위절반·시장대비 2%%p↓·쉼·10분 3천만↑·하루 깊은10): %d건 · lab 재료 있는 건 %d" % (len(base), base.mcap.notna().sum()))
    P("기간: 2025-03~2026-08(lab 한계) · 비용 0.23 · 칸=건수·건당%%·승률·날바구니%%"); P("")
    P("| 축 | 하위30%% | 중간 | 상위30%% |"); P("|---|---|---|---|")

    def tert(col, lo_lab, hi_lab, src="q"):
        if src == "rankbase":
            r = base[col].rank(pct=True)
        else:
            r = base[col]
        a = base[r <= 0.30]; b = base[(r > 0.3) & (r <= 0.7)]; c = base[r > 0.7]
        P("| %s | %s | %s | %s |" % (col_label(col, lo_lab, hi_lab), cell(a), cell(b), cell(c)))

    def col_label(col, lo, hi):
        return {"q_mcap": "시총(작을수록 왼쪽)", "q_d120": "120일선(아래일수록 왼쪽)", "q_lo250": "52주저점(가까울수록 왼쪽)",
                "q_vol20": "변동성(낮을수록 왼쪽)"}.get(col, col) + " [%s ↔ %s]" % (lo, hi)

    tert("q_mcap", "초소형", "대형")
    tert("q_d120", "장기하락", "장기상승")
    tert("q_lo250", "저점근처", "저점서멈")
    tert("q_vol20", "잔잔", "출렁")
    # 신규상장
    P("| 상장나이 | %s | %s | %s |" % (cell(base[base.age < 250]), "-", cell(base[base.age >= 250])))
    # 기준 전체
    P(""); P("기준(전체 안정신호): " + cell(base))
    (ROOT / "reports" / ("nxt_axis_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
    P(""); P("(%.0f초)" % (time.time() - t0))


if __name__ == "__main__":
    main()
