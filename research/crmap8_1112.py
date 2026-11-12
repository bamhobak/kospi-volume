# -*- coding: utf-8 -*-
"""H0415 후속 4 — 스윙 후보 3판 상세 비교 (2026-11-12 사용자 "3가지 상세 비교표" · "200만이든 300만이든 다 살 수 있어 매수벽 매도벽").
판: C 갭≤-2%·3일 / B 갭≤-3%·5일 / 갭≤-3%·7일 (지도 k1.4 · F≥0.3 · D+2 시가 지정가 = 어제 종가×(1+갭) · 보유 h 거래일째 종가)
금액: 200만·하루 5천만 / 300만·하루 1억 · 가정: 보수(체결 손해 0.143+1.321√p · 체결률 1/(1+3p)) / 다 산다(체결 100% · 체결 손해만)
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
E0 = pd.read_pickle(OUTD / "ev.pkl")
E0 = E0[(E0["var"] == "지도 k1.4 m0.4 L3") & (E0.F >= 0.3)][["d", "t", "F", "amt20"]]
E0 = E0[cal[E0.d.values] >= "20151201"].copy()
e = E0.d.values + 2; ok = e + 8 < nd; E0 = E0[ok]; e = e[ok]; t = E0.t.values
E0["e"] = e; E0["date"] = cal[e]; E0["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
YB = len(cal[cal >= "20230101"]) / 250
imp = lambda p: np.maximum(0, 0.143 + 1.321 * np.sqrt(p))
PLANS = [("C 갭-2%·3일", -2, 3), ("B 갭-3%·5일", -3, 5), ("갭-3%·7일", -3, 7)]


def run(gth, h, amt, dc, full):
    z = E0[(E0.g > -29.5) & (E0.g <= gth)].copy()
    ee = z.e.values; tt = z.t.values
    z["r"] = (CL[ee + h - 1, tt] / OP[ee, tt] - 1) * 100 - COST
    z["sell"] = cal[ee + h - 1]
    z = z[np.isfinite(z.r) & (z.r.abs() < 80)].sort_values(["date", "F"], ascending=[True, False]).drop_duplicates(["date", "t"]).reset_index(drop=True)
    a = np.full(len(z), amt); cum = pd.Series(a).groupby(z.date.values).cumsum().values; a = np.where(cum <= dc, a, 0.0)
    p = a / z.amt20.values * 100
    inv = a if full else a / (1 + 3 * p)
    z["inv"] = inv; z["net"] = z.r - imp(p); z["pnl"] = inv * z.net / 100
    z = z[z.inv > 0].copy()
    # 계좌 손익 곡선: 매도 날에 손익 확정 · 묶인 돈
    pnl_day = z.groupby("sell").pnl.sum().reindex(cal[(cal >= "20151201")], fill_value=0).cumsum() / 1e4
    mdd = float((pnl_day - pnl_day.cummax()).min())
    cd = pd.Series(z.inv.values, index=z.e.values).groupby(level=0).sum()
    cd = cd.reindex(range(cd.index.min(), cd.index.max() + h + 1), fill_value=0).rolling(h, min_periods=1).sum(); cd = cd[cd > 0]
    yrs = z.groupby(z.date.str[:4]).pnl.sum() / 1e4; yrs = yrs[yrs.index >= "2016"]
    dp = z.groupby("date").pnl.sum().sort_values(ascending=False)
    dd = z.groupby("date").r.mean(); tstat = dd.mean() / dd.std() * np.sqrt(len(dd))
    tr = z.date < "20230101"
    no2003 = z[tr & ~z.date.str.startswith("202003")].pnl.sum() / 7 / 1e4
    return dict(n=len(z) / 10.85, days=z.date.nunique() / 10.85, per=z.r.mean(), net=z.pnl.sum() / z.inv.sum() * 100, win=(z.net > 0).mean() * 100, t=tstat,
                ya=z[tr].pnl.sum() / 7 / 1e4, yb=z[~tr].pnl.sum() / YB / 1e4, y2325=yrs.reindex(["2023", "2024", "2025"]).mean(), no2003=no2003,
                pos=int((yrs > 0).sum()), ny=len(yrs), worst=float(yrs.min()), worst_y=yrs.idxmin(), best=float(yrs.max()), best_y=yrs.idxmax(),
                mdd=mdd, need=float(cd.quantile(0.95)) / 1e4, avgcap=float(cd.mean()) / 1e4, mx=float(cd.max()) / 1e4,
                top10=float(dp.iloc[:10].sum() / z.pnl.sum() * 100), yrs=yrs)


OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
P("# [반대매매] 스윙 후보 3판 상세 비교 (H0415 후속 4) · 2026-11-12"); P("")
P("공통: 신용 지도(담보 140%) 강제 물량 ÷ 20일 거래대금 F≥0.3 · 사건 이틀 뒤(D+2) 시가에 지정가(어제 종가×(1+갭)) — 시가가 그 아래로 열려야 체결 · 보유 h 거래일째(매수일=1일째) 종가 매도 · 하루 새 매수 상한 넘으면 F 큰 순 · 비용 0.23 · 2016~2026-11"); P("")
ROWS = [("연 매수 건수", "n", "%.0f건"), ("매수 있는 날/년", "days", "%.0f일"), ("건당 평균(손해 전)", "per", "%+.2f%%"), ("건당(손해 뒤, 산 것)", "net", "%+.2f%%"), ("승률", "win", "%.0f%%"),
        ("날 바구니 t", "t", "%.1f"), ("연 손익 2016~22", "ya", "%+.0f만"), ("연 손익 2023~", "yb", "%+.0f만"), ("연 손익 2023~25 평균", "y2325", "%+.0f만"),
        ("2016~22 (2020-03 빼고)", "no2003", "%+.0f만"), ("플러스 해", None, None), ("최악의 해", None, None), ("최고의 해", None, None), ("계좌 최대 낙폭(손익 누적)", "mdd", "%+.0f만"),
        ("필요 자금 95%", "need", "%.0f만"), ("평균 묶인 돈", "avgcap", "%.0f만"), ("최대 묶인 돈", "mx", "%.0f만"), ("좋은 날 10개 몫", "top10", "%.0f%%")]
for amt, dc in ((200e4, 5e7), (300e4, 1e8)):
    for full in (False, True):
        R = {nm: run(g, h, amt, dc, full) for nm, g, h in PLANS}
        P("## 종목당 %d만 · 하루 상한 %d천만 · %s" % (amt / 1e4, dc / 1e7, "다 산다(체결 100%)" if full else "보수(체결률 깎음)")); P("")
        P("| 항목 | " + " | ".join(nm for nm, _, _ in PLANS) + " |"); P("|---|---|---|---|")
        for lab, k, f in ROWS:
            if lab == "플러스 해": cells = ["%d/%d" % (R[nm]["pos"], R[nm]["ny"]) for nm, _, _ in PLANS]
            elif lab == "최악의 해": cells = ["%+.0f만(%s)" % (R[nm]["worst"], R[nm]["worst_y"]) for nm, _, _ in PLANS]
            elif lab == "최고의 해": cells = ["%+.0f만(%s)" % (R[nm]["best"], R[nm]["best_y"]) for nm, _, _ in PLANS]
            else: cells = [f % R[nm][k] for nm, _, _ in PLANS]
            P("| %s | %s |" % (lab, " | ".join(cells))); n += 1
        P("")
        if amt == 200e4 and not full:
            ys = sorted(set().union(*[set(R[nm]["yrs"].index) for nm, _, _ in PLANS]))
            P("해마다(만원): " + " · ".join("%s %s" % (y, "/".join("%+.0f" % R[nm]["yrs"].get(y, 0) for nm, _, _ in PLANS)) for y in ys) + "  (C/B/7일 순)"); P("")
(ROOT / "reports" / "crmap8_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap8_1112", n)
