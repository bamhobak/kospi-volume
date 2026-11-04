# -*- coding: utf-8 -*-
"""1억 1년 굴리기(2026-11-05 사용자 "작년 이맘때 1억 줬다 — 받은 때부터 너만의 투자법으로 1년 불려 봐").
규율: **2025-11-04 까지 자료만으로 고르고**(학습 2016-01~2025-10), 고른 것을 고치지 않고 2025-11-05~2026-11-04 에 굴린다.
  A 데이(갭 하락 되돌림 계열) 108칸: 크기 liq ≤ 1/3·4/9·2/3 · 갭 순위 ≤ 10·20·40% · 전날 거래량 순위 ≤ 30%·조건 없음
     · 시장 대비 ≤ -1·-1.5·-2%p · 깊이 배율 없음·최대 3배. 시가 매수(실제 시가 기준) → 종가 매도 · 비용 0.23
     · 금액 = 자산 × 기본(0.3·0.5·1%) × 깊이 × 거래대금 배율(0.3~3) · 하루 쓰는 돈 ≤ 그 칸 자산 · 깊은 순으로 담음
       (11-05 1차: 기본 1% 고정이었더니 1억에선 체결 손해가 몫을 다 먹음 → 기본도 고르는 칸에 넣음, 324칸)
     · 체결 손해·덜 사짐 = 실행 실측 모형(t1_size_liq_1021.fit) · 놓치는 후보 11%(CAPTURE 0.89, 장전 예상가 오차)
  B 지수 띠: 코스피 60일선 +3% 위면 들고 -3% 아래면 현금(종가 판정 다음 날부터 · 바꿀 때 0.1%)
  나눔: A 에 0·25·50·75·100% (나머지 B) — 각 칸이 따로 복리.
  고르는 잣대(미리 고정): 해마다 수익률(2016~2024 + 2025-01~10) **중앙값** 최대 · 같으면 최악의 해가 나은 쪽.
  참고(답 본 것): 지금 실전 [갭 하락 조용주] 설정 · 코스피·코스닥 그냥 들고 있기.
    python research/y1_sim.py
"""
import io, contextlib, sys, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import feats as FT

COST, CAPTURE, IXC = 0.23, 0.89, 0.10
SEL = ("20160101", "20251031")          # 고르는 구간
RUN = ("20251105", "20261104")          # 굴리는 구간
CACHE = BASE / "data" / "y1_hist.pkl"
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def hist():
    if CACHE.exists(): return pd.read_pickle(CACHE)
    A = pd.read_pickle(BASE / "data" / "y1_kr.pkl")
    A = A[A.date >= "20150101"].copy()
    X = FT.make(A, mk="KR")
    U = X[X.uni].reset_index(drop=True)
    U = U[["ticker", "date", "gap", "rgap", "vm", "amt20", "liq", "oc", "mgap"]].copy()
    gd = U.groupby("date")
    U["q_gap"] = gd.gap.rank(pct=True); U["q_vm"] = gd.vm.rank(pct=True)
    U.to_pickle(CACHE); return U


def impact():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    return (lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p))), (lambda p: 1 / (1 + cf * p)), ab, cf


def day_sim(U, cfg, lo, hi, imp, fill, eq0=1e8, isc=1.0):
    """한 칸(데이) 자산 경로 — 날짜별 자산(장 마감 뒤). 쓰는 돈 ≤ 전날 자산."""
    liq, qg, qv, rel, dmax, base = cfg
    W = U[(U.date >= lo) & (U.date <= hi) & (U.liq <= liq) & (U.q_gap <= qg) & (U.rgap <= rel)]
    if qv < 1: W = W[W.q_vm.fillna(1) <= qv]
    W = W.dropna(subset=["oc", "amt20"])
    W = W.assign(dep=(-W.rgap).clip(1, dmax) if dmax > 1 else 1.0,
                 lm=(W.amt20 / W.groupby("date").amt20.transform("median")).clip(0.3, 3)).sort_values(["date", "rgap"])
    days = sorted(U[(U.date >= lo) & (U.date <= hi)].date.unique())
    G = {d: g for d, g in W.groupby("date")}
    eq, path, n = eq0, {}, 0
    for d in days:
        g = G.get(d)
        if g is not None:
            amt = eq * base * g.dep.to_numpy() * g.lm.to_numpy()
            ok = np.cumsum(amt) <= eq
            amt = amt[ok]; oc = g.oc.to_numpy()[ok]; a20 = g.amt20.to_numpy()[ok] * 1e8
            p = amt / a20 * 100
            fl = 1 / (1 + isc * (1 / fill(p) - 1))
            eq += float(np.sum(amt * fl * (oc - COST - isc * imp(p)) / 100) * CAPTURE)
            n += len(amt)
        path[d] = eq
    return pd.Series(path), n


def ix_band(lo, hi, eq0=1e8):
    X = fdr.DataReader("KS11", "2014-01-01"); X = X[X.Close > 0]
    c = X.Close; ma = c.rolling(60).mean(); pos, st = [], 0
    for v, m in zip(c, ma):
        if np.isnan(m): pos.append(0); continue
        if st == 0 and v > m * 1.03: st = 1
        elif st == 1 and v < m * 0.97: st = 0
        pos.append(st)
    pos = pd.Series(pos, index=c.index).shift(1).fillna(0)                 # 종가 판정 → 다음 날부터
    r = c.pct_change().fillna(0) * pos - pos.diff().abs().fillna(0) * IXC / 100
    r.index = r.index.strftime("%Y%m%d")
    r = r[(r.index >= lo) & (r.index <= hi)]
    return eq0 * (1 + r).cumprod()


def yearly(path, eq0=1e8):
    s = path.copy(); s.index = s.index.str[:4]
    out = {}
    prev = eq0
    for y, v in s.groupby(level=0):
        out[y] = (v.iloc[-1] / prev - 1) * 100; prev = v.iloc[-1]
    return out


def main():
    U = hist()
    P("자료 %s줄 · %s~%s" % (f"{len(U):,}", U.date.min(), U.date.max()))
    imp, fill, ab, cf = impact()
    P("체결 손해 모형: 손해 max(0, %.2f + %.2f√p) · 체결 1/(1+%.2fp) (p = 금액 ÷ 20일 평균 거래대금 %%)" % (ab[0], ab[1], cf))
    grid = list(itertools.product((1 / 3, 4 / 9, 2 / 3), (0.10, 0.20, 0.40), (0.30, 1.0), (-1.0, -1.5, -2.0), (1, 3), (0.003, 0.005, 0.01)))
    IXP = ix_band(*SEL)
    ixy = yearly(IXP)
    rows = []
    for cfg in grid:
        path, n = day_sim(U, cfg, *SEL, imp, fill)
        y = yearly(path)
        for f in (0.25, 0.5, 0.75, 1.0):
            yy = {k: f * y[k] + (1 - f) * ixy.get(k, 0) for k in y}         # 칸마다 해 초에 다시 나눈다고 보고 해 수익을 섞음
            v = np.array(list(yy.values()))
            rows.append(dict(cfg=cfg, f=f, med=np.median(v), worst=v.min(), mean=v.mean(), n=n, ys=yy))
    v = np.array(list(ixy.values()))
    rows.append(dict(cfg=None, f=0.0, med=np.median(v), worst=v.min(), mean=v.mean(), n=0, ys=ixy))
    R = sorted(rows, key=lambda r: (-r["med"], -r["worst"]))
    nm = lambda r: "지수 띠 100%" if r["cfg"] is None else "데이 %d%%(크기 %s·갭 %d%%·거래량 %s·시장 대비 %.1f·깊이 %s) + 지수 띠 %d%%" % (
        r["f"] * 100, {1 / 3: "1/3", 4 / 9: "4/9", 2 / 3: "2/3"}[r["cfg"][0]], r["cfg"][1] * 100, "30%" if r["cfg"][2] < 1 else "없음",
        r["cfg"][3], "3배" if r["cfg"][4] > 1 else "없음", (1 - r["f"]) * 100) + " · 기본 %.1f%%" % (r["cfg"][5] * 100)
    P("\n## 고르기(2016-01~2025-10만) — 위 15칸\n")
    P("| 순위 | 판 | 해 중앙 | 최악의 해 | 해 평균 | 데이 건수 |"); P("|---|---|---|---|---|---|")
    for i, r in enumerate(R[:15], 1):
        P("| %d | %s | %+.1f%% | %+.1f%% | %+.1f%% | %d |" % (i, nm(r), r["med"], r["worst"], r["mean"], r["n"]))
    pick = R[0]
    P("\n**고른 것: %s**" % nm(pick))
    P("해별: " + " · ".join("%s %+.1f%%" % kv for kv in pick["ys"].items()))
    # ── 굴리기 ──
    P("\n## 굴리기 %s~%s (1억, 고친 것 없음)\n" % RUN)
    days = sorted(U[(U.date >= RUN[0]) & (U.date <= RUN[1])].date.unique())
    P("거래일 %d · 마지막 %s" % (len(days), days[-1]))
    res = {}
    f = pick["f"]
    dp = day_sim(U, pick["cfg"], *RUN, imp, fill, 1e8 * f)[0] if pick["cfg"] else pd.Series(0.0, index=days)
    ip = ix_band(*RUN, 1e8 * (1 - f)) if f < 1 else pd.Series(0.0, index=days)
    res["고른 것"] = (dp.reindex(days).ffill().fillna(1e8 * f) + ip.reindex(days).ffill().fillna(1e8 * (1 - f)))
    if pick["cfg"]:
        for isc, lb in ((0.5, "체결 손해 절반이면"), (0.0, "체결 손해 없으면")):
            d2 = day_sim(U, pick["cfg"], *RUN, imp, fill, 1e8 * f, isc)[0]
            res["고른 것 — " + lb] = d2.reindex(days).ffill().fillna(1e8 * f) + ip.reindex(days).ffill().fillna(1e8 * (1 - f))
    cur = (2 / 3, 0.40, 0.30, -1.5, 3, 0.005)                              # 지금 실전 설정(답 본 것 — 참고, 기본 50만 = 1억의 0.5%)
    res["참고: 지금 실전 데이 설정 100%"] = day_sim(U, cur, *RUN, imp, fill)[0].reindex(days).ffill()
    res["참고: 지수 띠 100%"] = ix_band(*RUN).reindex(days).ffill().fillna(1e8)
    for sym, k in (("KS11", "코스피 그냥 들고 있기"), ("KQ11", "코스닥 그냥 들고 있기")):
        X = fdr.DataReader(sym, "2025-10-01"); X.index = X.index.strftime("%Y%m%d")
        b = X.Close[X.index < RUN[0]].iloc[-1]
        res["참고: " + k] = (1e8 * X.Close / b).reindex(days).ffill()
    P("| 판 | 1년 뒤 | 수익 | 가장 크게 빠진 폭 |"); P("|---|---|---|---|")
    for k, s in res.items():
        s = s.dropna(); dd = (s / s.cummax() - 1).min() * 100
        P("| %s | %s원 | %+.1f%% | %.1f%% |" % (k, f"{s.iloc[-1]:,.0f}", (s.iloc[-1] / 1e8 - 1) * 100, dd))
    M = pd.DataFrame(res); M.index = pd.to_datetime(M.index)
    me = M.resample("ME").last()
    P("\n월말 자산(만원):")
    P("| 월 | " + " | ".join(k.replace("참고: ", "") for k in res) + " |"); P("|---" * (len(res) + 1) + "|")
    for d, r in me.iterrows():
        P("| %s | %s |" % (d.strftime("%Y-%m"), " | ".join("%s" % f"{v / 1e4:,.0f}" for v in r)))
    M.to_pickle(BASE / "data" / "y1_paths.pkl")
    (ROOT / "y1_sim.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
