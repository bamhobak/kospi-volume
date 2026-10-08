# -*- coding: utf-8 -*-
"""정답지 역추적기 (2026-10-08 사용자 아이디어 ②) — 시험 문제를 모으는 대신 매일 '오늘 정답지'에서 거꾸로 문제를 만든다.

매일 장 끝나고(evening):
  오늘 유니버스에서 시가→종가(oc) 상위 30 · 하위 30 종목을 뽑고, 재료마다
    ic     재료와 오늘 수익의 순위 상관(스피어만)
    spread 재료 상위 10% 평균 수익 - 하위 10% 평균 수익
    top_q / bot_q  오늘 상위 30 · 하위 30 종목의 재료 백분위 평균
  → data/factory/answer/ic.csv 에 쌓고, 상위 10종목 일지(answer/YYYYMMDD.md).
후보(night): 최근 20거래일↑ 쌓인 ic 가 한쪽으로 꾸준(t ≥ 3)한 재료 → 명세(상위/하위 10%) → 깔때기.
  과거가 있는 재료는 과거 ic(학습 2016~22)와 방향이 같은지도 같이 적는다 — 요즘만 그런지, 원래 그런지.
  실시간 녹화 재료(a_*·c_*)는 과거가 없어서 이 매일 기록 자체가 시험이다(앞으로 오는 날만 쓰는 정직한 표본).
"""
import time
import numpy as np, pandas as pd

import common as C
import feats as FT

AN = C.DATA / "answer"; AN.mkdir(exist_ok=True)
ICF = AN / "ic.csv"
HIC = C.CACHE / "factory_hist_ic.pkl"
MIN_DAYS, T_MIN = 20, 3.0


def _feats(U):
    """장 전에 알 수 있는 재료만(pre·open·live 중 아침 것) — 오늘 종가 재료는 정답 자체라 뺀다."""
    return [f for f in FT.FEATS if f in U.columns and FT.FEATS[f][1] != "close" and not f.startswith("c_") and U[f].notna().sum() >= 100]


def daily(U, day, names=None):
    """U = 그날 유니버스 줄(oc 포함). 반환: 텔레그램용 줄 목록."""
    names = names or {}
    U = U[U.oc.notna()].copy()
    if len(U) < 200:
        C.log("정답지: 오늘 줄 %d — 건너뜀" % len(U)); return []
    U["r_oc"] = U.oc.rank(pct=True)
    top = U.nlargest(30, "oc"); bot = U.nsmallest(30, "oc")
    rows = []
    for f in _feats(U):
        x = U[[f, "oc", "r_oc"]].dropna()
        if len(x) < 100: continue
        q = x[f].rank(pct=True)
        ic = float(np.corrcoef(q, x.r_oc)[0, 1]) if q.std() > 0 else np.nan
        sp = float(x.oc[q >= 0.9].mean() - x.oc[q <= 0.1].mean())
        qf = U[f].rank(pct=True)
        rows.append((day, f, ic, sp, len(x), float(qf[top.index].mean()), float(qf[bot.index].mean())))
    R = pd.DataFrame(rows, columns=["date", "f", "ic", "spread", "n", "top_q", "bot_q"])
    old = pd.read_csv(ICF, dtype={"date": str}) if ICF.exists() else pd.DataFrame(columns=R.columns)
    pd.concat([old[old.date != day], R]).to_csv(ICF, index=False, encoding="utf-8-sig")
    # 일지
    L = ["# 정답지 %s" % day, "", "유니버스 %d종목 · 오늘 시가→종가 중앙 %+.2f%%" % (len(U), U.oc.median()), "",
         "## 오늘 가장 많이 오른 10종목(시가→종가)과 어제까지 모습", "",
         "| 종목 | 시가→종가 | 갭 | 어제 등락 | 어제 거래량 배수 | 20일 | 테마 열기 | 외국인 |", "|---|---|---|---|---|---|---|---|"]
    for _, r in top.head(10).iterrows():
        L.append("| %s | %+.1f%% | %+.1f%% | %+.1f%% | %.1f | %+.0f%% | %s | %s |" % (
            names.get(r.ticker, r.ticker), r.oc, r.gap, r.r1, r.vm if pd.notna(r.vm) else np.nan, r.r20,
            "-" if pd.isna(r.th) else "%.2f" % r.th, "-" if pd.isna(r.fr) else "%+.1f" % r.fr))
    tilt = R.assign(d=R.top_q - R.bot_q).sort_values("d", key=lambda s: -s.abs())
    L += ["", "## 오늘 오른 쪽·내린 쪽이 가장 달랐던 재료", "", "| 재료 | 오른 30 평균 순위 | 내린 30 | 상관 |", "|---|---|---|---|"]
    for _, r in tilt.head(8).iterrows():
        L.append("| %s | %.2f | %.2f | %+.3f |" % (FT.FEATS[r.f][0], r.top_q, r.bot_q, r.ic))
    (AN / ("%s.md" % day)).write_text("\n".join(L) + "\n", encoding="utf-8")
    msg = ["오른 30 vs 내린 30 가장 다른 재료: " + " · ".join("%s(%.2f vs %.2f)" % (FT.FEATS[r.f][0], r.top_q, r.bot_q) for _, r in tilt.head(3).iterrows()),
           "가장 오른 종목: " + ", ".join("%s %+.1f%%" % (names.get(r.ticker, r.ticker), r.oc) for _, r in top.head(5).iterrows())]
    C.log("정답지 %s: 재료 %d" % (day, len(R)))
    return msg


def hist_ic():
    """과거(학습 2016~22) 날마다 ic 평균·t — 요즘 정답지와 방향 비교용. 한 번 만들어 둔다."""
    if HIC.exists(): return pd.read_pickle(HIC)
    import lab
    U = lab.hist()
    Z = U[(U.date >= "20160101") & (U.date <= "20221231") & U.oc.notna()]
    r = Z.groupby("date").oc.rank(pct=True)
    out = {}
    for f in FT.HIST:
        if "q_" + f not in Z.columns: continue
        q = Z["q_" + f]
        ok = q.notna()
        D = pd.DataFrame({"d": Z.date[ok], "q": q[ok].astype(float), "r": r[ok]})
        if len(D) < 10000: continue
        D["qr"] = D.q * D.r; D["qq"] = D.q ** 2; D["rr"] = D.r ** 2
        g = D.groupby("d").agg(n=("q", "size"), q=("q", "mean"), r=("r", "mean"), qr=("qr", "mean"), qq=("qq", "mean"), rr=("rr", "mean"))
        ic = (g.qr - g.q * g.r) / np.sqrt((g.qq - g.q ** 2) * (g.rr - g.r ** 2))
        ic = ic[g.n >= 50].dropna()
        out[f] = (float(ic.mean()), float(ic.mean() / ic.std() * np.sqrt(len(ic))), len(ic))
    S = pd.DataFrame(out, index=["ic", "t", "days"]).T
    S.to_pickle(HIC)
    return S


def candidates():
    """쌓인 정답지에서 꾸준한 재료 → 명세. 반환: (재료, 평균 ic, t, 일수, 과거 ic, 명세)."""
    import lab
    if not ICF.exists(): return []
    R = pd.read_csv(ICF, dtype={"date": str})
    H = hist_ic()
    out = []
    for f, g in R.groupby("f"):
        g = g.dropna(subset=["ic"])
        if len(g) < MIN_DAYS: continue
        t = g.ic.mean() / g.ic.std() * np.sqrt(len(g)) if g.ic.std() > 0 else 0
        if abs(t) < T_MIN: continue
        hi = H.loc[f, "ic"] if f in H.index else np.nan
        up = g.ic.mean() > 0
        spec = {"name": "정답지: %s %s 쪽" % (FT.FEATS[f][0], "높은" if up else "낮은"), "origin": "answer",
                "source": "최근 %d거래일 정답지 ic %+.3f(t %.1f) · 과거 ic %s" % (len(g), g.ic.mean(), t, "없음" if pd.isna(hi) else "%+.3f" % hi),
                "mode": "oc", "conds": [{"f": f, "q": True, "op": ">=" if up else "<=", "v": 0.9 if up else 0.1}]}
        out.append((f, float(g.ic.mean()), float(t), len(g), hi, spec))
    return out


def recent_table(days=20):
    """보고서용 — 최근 n거래일 재료별 ic 평균·t(위 10개)."""
    if not ICF.exists(): return []
    R = pd.read_csv(ICF, dtype={"date": str})
    last = sorted(R.date.unique())[-days:]
    R = R[R.date.isin(last)]
    S = R.groupby("f").ic.agg(["mean", "std", "size"])
    S["t"] = S["mean"] / S["std"] * np.sqrt(S["size"])
    return S.sort_values("t", key=lambda s: -s.abs()).head(10)
