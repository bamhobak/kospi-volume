# -*- coding: utf-8 -*-
"""H0415 후속 2 — C 판(k1.4 · F≥0.3 · D+2 시가 갭 ≤-2% · 3일째 종가) 종목당 금액 늘리기 (2026-11-12 사용자 "종목당 매수금을 좀 더 늘릴 수 있는 방법").
 ① 고정 금액 200/300/500/700/1000만 × 하루 새 매수 상한 5천만/1억/없음
 ② 거래대금 비례 0.5/1/2% × 종목당 상한 500/1000/2000만
 ③ 나눠 사기: 절반 D+2 시가 + 절반 D+3 시가(D+3 시가가 D+2 시가 이하일 때만 — 더 싸면 보탬) / 무조건 D+3 시가
 ④ 거래대금 크기별 건당(손해 전) — 큰 종목에 돈을 더 넣으면 왜 손해인지
 체결 손해 0.143+1.321√p · 체결률 1/(1+3p). 매도도 같은 크기라 손해 모형은 한 번(왕복 근사, 지금 쓰는 것과 같음).
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap"); COST = 0.23
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values; nd = len(cal)
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
del Px
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[(E["var"] == "지도 k1.4 m0.4 L3") & (E.F >= 0.3)][["d", "t", "F", "amt20"]]
E = E[cal[E.d.values] >= "20151201"].copy()
e = E.d.values + 2; ok = e + 6 < nd; E = E[ok]; e = e[ok]; t = E.t.values
E["e"] = e; E["date"] = cal[e]
E["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
o2, o3, c4 = OP[e, t], OP[e + 1, t], CL[e + 2, t]
E["r"] = (c4 / o2 - 1) * 100 - COST                     # D+2 시가 → 3일째(D+4) 종가
E["r3"] = (c4 / o3 - 1) * 100 - COST                    # D+3 시가 → 같은 매도
E["cheaper"] = o3 <= o2
E = E[np.isfinite(E.g) & (E.g > -29.5) & (E.g <= -2) & np.isfinite(E.r) & (E.r.abs() < 60) & np.isfinite(E.r3)]
E = E.sort_values(["date", "F"], ascending=[True, False]).drop_duplicates(["date", "t"]).reset_index(drop=True)
YB = len(cal[cal >= "20230101"]) / 250
imp = lambda p: np.maximum(0, 0.143 + 1.321 * np.sqrt(p)); fill = lambda p: 1 / (1 + 3 * p)


def acct(amt, daycap, ret=None, legs=None):
    """amt: 종목당 금액 배열. legs: [(비율, 수익 배열, 가능 여부)] 나눠 사기."""
    amt = np.where(np.isfinite(amt), amt, 0)
    cum = pd.Series(amt).groupby(E.date.values).cumsum().values
    if daycap: amt = np.where(cum <= daycap, amt, 0)
    pnl = np.zeros(len(E)); inv = np.zeros(len(E))
    for w, r, can in (legs or [(1.0, E.r.values, np.ones(len(E), bool))]):
        a = amt * w * can; p = a / E.amt20.values * 100
        iv = a * fill(p); pnl += np.nan_to_num(iv * (r - imp(p)) / 100); inv += np.nan_to_num(iv)
    tr = E.date.values < "20230101"
    cap_day = pd.Series(inv, index=E.e.values).groupby(level=0).sum()
    cap_day = cap_day.reindex(range(cap_day.index.min(), cap_day.index.max() + 4), fill_value=0).rolling(3, min_periods=1).sum()
    cd = cap_day[cap_day > 0]
    yrs = pd.Series(pnl).groupby(E.date.str[:4].values).sum() / 1e4
    return dict(ya=pnl[tr].sum() / 7 / 1e4, yb=pnl[~tr].sum() / YB / 1e4, y2325=yrs.reindex(["2023", "2024", "2025"]).mean(), net=pnl.sum() / max(inv.sum(), 1) * 100,
                n=(amt > 0).sum() / 10.85, need=float(cd.quantile(0.95)) / 1e4, mx=float(cd.max()) / 1e4)


OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
P("# [반대매매] C 판 종목당 금액 늘리기 (H0415 후속 2) · 2026-11-12"); P("")
P("C 판 = 지도 k1.4 · F≥0.3 · D+2 시가 갭 ≤-2%% → 3일째 종가 · 2016~ 신호 %d건(연 %.0f) · 20일 거래대금 중앙 %.0f억" % (len(E), len(E) / 10.85, E.amt20.median() / 1e8)); P("")
H = "| 방법 | 산 것/년 | 건당(손해 뒤) | 연 손익 16~22 | 연 손익 23~ | 2023~25 평균 | 필요 자금 95% | 최대 |"
S = "|---|---|---|---|---|---|---|---|"
row = lambda nm, r: P("| %s | %.0f | %+.2f%% | %+.0f만 | %+.0f만 | %+.0f만 | %.0f만 | %.0f만 |" % (nm, r["n"], r["net"], r["ya"], r["yb"], r["y2325"], r["need"], r["mx"]))
P("## ① 고정 금액 × 하루 새 매수 상한"); P(""); P(H); P(S)
for a in (200e4, 300e4, 500e4, 700e4, 1000e4):
    for dc in (5e7, 1e8, None):
        row("%d만 · 상한 %s" % (a / 1e4, "%d천만" % (dc / 1e7) if dc else "없음"), acct(np.full(len(E), a), dc)); n += 1
P(""); P("## ② 거래대금 비례 × 종목당 상한 (하루 상한 1억)"); P(""); P(H); P(S)
for fr in (0.005, 0.01, 0.02):
    for cap in (500e4, 1000e4, 2000e4):
        row("거래대금 %.1f%% · 종목당 %d만" % (fr * 100, cap / 1e4), acct(np.minimum(fr * E.amt20.values, cap), 1e8)); n += 1
P(""); P("## ③ 나눠 사기 (종목당 합계, 하루 상한 1억)"); P(""); P(H); P(S)
one = np.ones(len(E), bool)
for a in (300e4, 500e4, 700e4, 1000e4):
    row("%d만 한 번에(D+2 시가)" % (a / 1e4), acct(np.full(len(E), a), 1e8)); n += 1
    row("%d만 절반 D+2 + 절반 D+3(무조건)" % (a / 1e4), acct(np.full(len(E), a), 1e8, legs=[(0.5, E.r.values, one), (0.5, E.r3.values, one)])); n += 1
    row("%d만 절반 D+2 + 절반 D+3(더 쌀 때만)" % (a / 1e4), acct(np.full(len(E), a), 1e8, legs=[(0.5, E.r.values, one), (0.5, E.r3.values, E.cheaper.values)])); n += 1
P(""); P("## ④ 거래대금 크기별 건당(손해 전·비용 뒤)"); P("")
q = pd.qcut(E.amt20, 5, labels=["가장 작음", "작음", "중간", "큼", "가장 큼"])
P("| 20일 거래대금 | 건수 | 거래대금 중앙 | 건당 2016~22 | 건당 23~ |"); P("|---|---|---|---|---|")
for lb, z in E.groupby(q):
    P("| %s | %d | %.0f억 | %+.2f%% | %+.2f%% |" % (lb, len(z), z.amt20.median() / 1e8, z[z.date < "20230101"].r.mean(), z[z.date >= "20230101"].r.mean())); n += 2
(ROOT / "reports" / "crmap6_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap6_1112", n)
