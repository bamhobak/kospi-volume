# -*- coding: utf-8 -*-
"""H0415 [반대매매] 연 수익금 키우기 격자 (2026-11-12 사용자 "연수익금이 너무 적네, 이거 토대로 더 나은 규칙 … 다양하게 조합해서 실측").
지도 모델 사건(research/crmap_1112 ev.pkl) 위에서:
  판(k·m)   : 지도 k1.3/k1.4/k1.5 (m 0.4) · k1.4 m0.5   — 신용 지연 L3
  F 문턱     : 0.3 · 0.5 · 1 · 2
  진입       : 사건 날 D 의 +1 · +2 · +3 거래일 시가 (그 날 시가 갭이 문턱 이하일 때만 — 지정가 = 어제 종가 × (1+문턱))
  갭 문턱    : 없음(0 이하 아무거나 = 9) · -1 · -2 · -3 · -5 %
  보유       : 그날 종가(oc) · 다음 날 시가(on) · 3일(o3 = +2일 종가) · 5일(o5)
  금액       : 고정 200만 · 20일 거래대금의 0.5% · 1% · 2% (종목당 상한 1천만) — 하루 새 매수 상한 5천만(F 큰 순)
  체결 손해 0.143+1.321√p · 체결률 1/(1+3p) (p = 금액÷20일 거래대금 %) · 비용 0.23
판정: 연 손익(만원) 학습 16~22 / 검증 23~ 둘 다 · 필요 자금 = 하루 들고 있는 돈 95% · 날 바구니 t
    python research/crmap4_1112.py → research/reports/crmap4_1112.md · C:/temp/kp/crmap/grid4.pkl
"""
import os, sys, itertools, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap")
COST = 0.23
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values
nd = len(cal)
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
del Px
E0 = pd.read_pickle(OUTD / "ev.pkl")
E0 = E0[E0["var"].isin(["지도 k1.3 m0.4 L3", "지도 k1.4 m0.4 L3", "지도 k1.5 m0.4 L3", "지도 k1.4 m0.5 L3"]) & (E0.F >= 0.3)][["var", "d", "t", "F", "amt20"]].copy()
E0 = E0[cal[E0.d.values] >= "20151201"]
print("사건", len(E0), flush=True)
YRS = {"학습": 7.0, "검증": len(cal[cal >= "20230101"]) / 250}
HOLD = {"oc": 0, "on": 1, "o3": 2, "o5": 4}       # 들고 있는 추가 거래일 수(돈 묶임)


def legs(E, off):
    e = E.d.values + off
    ok = e + 5 < nd
    E = E[ok].copy(); e = e[ok]; t = E.t.values
    E["e"] = e; E["date"] = cal[e]
    E["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
    o = OP[e, t]
    E["oc"] = (CL[e, t] / o - 1) * 100 - COST
    E["on"] = (OP[e + 1, t] / o - 1) * 100 - COST
    E["o3"] = (CL[e + 2, t] / o - 1) * 100 - COST
    E["o5"] = (CL[e + 4, t] / o - 1) * 100 - COST
    for c in ("oc", "on", "o3", "o5"): E.loc[(E[c].abs() > 60) | ~np.isfinite(E[c]), c] = np.nan
    E = E[np.isfinite(E.g) & (E.g > -29.5)]
    return E


LEG = {off: legs(E0, off) for off in (1, 2, 3)}
SIZES = (("고정 200만", None, 200e4), ("거래대금 0.5%", 0.005, 1000e4), ("거래대금 1%", 0.01, 1000e4), ("거래대금 2%", 0.02, 1000e4))
rows = []
for (var, F, off, gth, ex) in itertools.product(sorted(E0["var"].unique()), (0.3, 0.5, 1.0, 2.0), (1, 2, 3), (9, -1, -2, -3, -5), ("oc", "on", "o3", "o5")):
    z = LEG[off]; z = z[(z["var"] == var) & (z.F >= F) & (z.g <= (0 if gth == 9 else gth))].dropna(subset=[ex])
    # 같은 종목·같은 매수 날 겹침(F 큰 것 하나)
    z = z.sort_values(["date", "F"], ascending=[True, False]).drop_duplicates(["date", "t"])
    if len(z) < 30: continue
    dd = z.groupby("date")[ex].mean()
    for snm, frac, cap in SIZES:
        amt = np.full(len(z), cap) if frac is None else np.minimum(frac * z.amt20.values, cap)
        amt = np.where(np.isfinite(amt), amt, 0)
        # 하루 새 매수 상한 5천만(F 큰 순)
        cum = pd.Series(amt).groupby(z.date.values).cumsum().values
        amt = np.where(cum <= 5e7, amt, 0)
        p = amt / z.amt20.values * 100
        imp = np.maximum(0, 0.143 + 1.321 * np.sqrt(p)); fill = 1 / (1 + 3 * p)
        inv = amt * fill; pnl = inv * (z[ex].values - imp) / 100
        tr = z.date.values < "20230101"
        ya, yb = pnl[tr].sum() / YRS["학습"] / 1e4, pnl[~tr].sum() / YRS["검증"] / 1e4
        # 필요 자금: 매수 날부터 HOLD 거래일 동안 묶임
        h = HOLD[ex]
        cap_day = pd.Series(inv, index=z.e.values).groupby(level=0).sum()
        if h: cap_day = cap_day.reindex(range(cap_day.index.min(), cap_day.index.max() + h + 1), fill_value=0).rolling(h + 1, min_periods=1).sum()
        cd = cap_day[cap_day > 0]
        need = float(cd.quantile(0.95)) / 1e4 if len(cd) else 0.0           # 돈이 묶인 날만(빈 날 빼고)
        mx = float(cd.max()) / 1e4 if len(cd) else 0.0
        rows.append(dict(var=var, F=F, off=off, gap=gth, ex=ex, size=snm, n_yr=len(z) / 10.85, n_buy=float((amt > 0).sum()) / 10.85, mx=mx, per=float(z[ex].mean()), day_t=float(dd.mean() / dd.std() * np.sqrt(len(dd))) if dd.std() > 0 else 0,
                         net=float(pnl.sum() / max(inv.sum(), 1) * 100), ya=ya, yb=yb, need=need, roi=(ya + yb) / 2 / max(need, 1) * 100))
    if len(rows) % 400 == 0: print(len(rows), flush=True)
R = pd.DataFrame(rows); R.to_pickle(OUTD / "grid4.pkl")
R["worst"] = R[["ya", "yb"]].min(axis=1)
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
P("# [반대매매] 연 수익금 키우기 격자 (H0415) · 2026-11-12"); P("")
P("- 칸 %d개(판 4 × F 4 × 진입 3 × 갭 5 × 보유 4 × 금액 4) · 연 손익 = 체결 손해·체결률 뒤 만원 · 필요 자금 = 하루 들고 있는 돈 95%%" % len(R))
P("- 지금 판(k1.4 · F≥1 · D+2 · 갭 -1 · 그날 종가 · 고정 200만, 하루 10종목 상한 없음)도 표에 있음"); P("")
cur = R[(R["var"] == "지도 k1.4 m0.4 L3") & (R.F == 1) & (R.off == 2) & (R.gap == -1) & (R.ex == "oc") & (R["size"] == "고정 200만")]
fmt = lambda r: "| %s | %.1f | D+%d | %s | %s | %s | %.0f / %.0f | %+.2f%% | %.1f | %+.2f%% | %+.0f | %+.0f | %.0f | %.0f%% |" % (
    r["var"].replace("지도 ", "").replace(" L3", ""), r.F, r.off, "없음" if r.gap == 9 else "%d%%" % r.gap, {"oc": "그날 종가", "on": "다음 날 시가", "o3": "3일", "o5": "5일"}[r.ex], r["size"],
    r.n_yr, r.n_buy, r.per, r.day_t, r.net, r.ya, r.yb, r.need, r.roi)
HDR = "| 판 | F | 진입 | 갭 | 보유 | 금액 | 연 신호 / 산 것 | 건당(신호 전부·손해 전) | 날 t | 건당(산 것·손해 뒤) | 연 손익 학습(만) | 연 손익 검증(만) | 필요 자금 95%(만) | 연 손익÷자금 |"
SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
P("## 지금 판"); P(""); P(HDR); P(SEP)
for _, r in cur.iterrows(): P(fmt(r))
P("")
P("## 학습·검증 중 나쁜 쪽 연 손익 상위 25"); P(""); P(HDR); P(SEP)
for _, r in R.sort_values("worst", ascending=False).head(25).iterrows(): P(fmt(r))
P("")
P("## 연 손익 ÷ 필요 자금 상위 15 (나쁜 쪽 연 손익 +100만 이상)"); P(""); P(HDR); P(SEP)
for _, r in R[R.worst >= 100].sort_values("roi", ascending=False).head(15).iterrows(): P(fmt(r))
P("")
P("## 손잡이별 효과 — 나머지는 지금 판 고정, 나쁜 쪽 연 손익(만)"); P("")
base = dict(var="지도 k1.4 m0.4 L3", F=1.0, off=2, gap=-1, ex="oc", size="고정 200만")
for knob, vals in (("size", [s for s, _, _ in SIZES]), ("ex", ["oc", "on", "o3", "o5"]), ("gap", [9, -1, -2, -3, -5]), ("F", [0.3, 0.5, 1.0, 2.0]), ("off", [1, 2, 3]),
                   ("var", sorted(R["var"].unique()))):
    cells = []
    for v in vals:
        q = R
        for k_, v_ in base.items(): q = q[q[k_] == (v if k_ == knob else v_)]
        cells.append("%s %s" % (v if not isinstance(v, str) else v.replace("지도 ", "").replace(" L3", ""), ("%+.0f/%+.0f" % (q.ya.iloc[0], q.yb.iloc[0])) if len(q) else "-"))
    P("- **%s**: %s" % ({"size": "금액", "ex": "보유", "gap": "갭 문턱", "F": "F 문턱", "off": "진입", "var": "판"}[knob], " · ".join(cells)))
P("")
P("## 금액 '거래대금 1%' 고정 · 보유별 × 갭 문턱별 나쁜 쪽 연 손익(만) — k1.4 · F≥0.5 · D+2"); P("")
P("| 보유 \\ 갭 | 없음 | -1% | -2% | -3% | -5% |"); P("|---|---|---|---|---|---|")
for ex in ("oc", "on", "o3", "o5"):
    q = R[(R["var"] == "지도 k1.4 m0.4 L3") & (R.F == 0.5) & (R.off == 2) & (R["size"] == "거래대금 1%") & (R.ex == ex)]
    P("| %s | %s |" % ({"oc": "그날 종가", "on": "다음 날 시가", "o3": "3일", "o5": "5일"}[ex], " | ".join(("%+.0f" % q[q.gap == g].worst.iloc[0]) if len(q[q.gap == g]) else "-" for g in (9, -1, -2, -3, -5))))
P(""); P("(칸 %d)" % len(R))
(ROOT / "reports" / "crmap4_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
pass  # 같은 칸 다시 잼(필요 자금 계산만 고침) — 칸 수 안 늘림
