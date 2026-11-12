# -*- coding: utf-8 -*-
"""[반대매매] 갭-3%·7일 판이 몰리는 날 = 다른 규칙도 몰리는 날인가 (2026-11-12 사용자).
날마다: T8 매수 수(종목당 200만·하루 5천만) · 스윙 신규 신호 수와 스윙 보유(종목당 300만 × 보유일) · 데이 [갭하락] T1 매수 수.
T8 몰림 상위 날에 다른 규칙이 얼마나 겹치나 · 같이 묶이는 돈(T8 보유 + 스윙 보유) 최대.
"""
import os, sys, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
OUTD = Path("C:/temp/kp/crmap"); KD = Path("C:/temp/kp/kind"); COST = 0.23
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values; nd = len(cal)
ci = {d: i for i, d in enumerate(cal)}
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
del Px
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[(E["var"] == "지도 k1.4 m0.4 L3") & (E.F >= 0.3)][["d", "t", "F", "amt20"]]
E = E[cal[E.d.values] >= "20160101"].copy()
e = E.d.values + 2; ok = e + 8 < nd; E = E[ok]; e = e[ok]; t = E.t.values
E["e"] = e; E["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
E = E[np.isfinite(E.g) & (E.g <= -3) & (E.g > -29.5)].sort_values(["e", "F"], ascending=[True, False]).drop_duplicates(["e", "t"])
E["k"] = E.groupby("e").cumcount(); E = E[E.k < 25]                              # 200만 × 25 = 하루 5천만
idx = np.arange(nd)
t8_new = pd.Series(0, index=idx).add(E.groupby("e").size(), fill_value=0)
t8_hold = sum(pd.Series(0, index=idx).add(E.groupby("e").size().rename(lambda x: x + s), fill_value=0) for s in range(7)).reindex(idx, fill_value=0) * 200
# 스윙: 신호 날 다음 거래일 매수 · 보유 hold 일
sw = pickle.load(open(KD / "swing.pkl", "rb"))
sw_new = pd.Series(0.0, index=idx); sw_hold = pd.Series(0.0, index=idx)
for rid, o in sw.items():
    T = o["T"]; T = T[T.date >= "20160101"]
    ee = np.array([ci.get(d, -1) for d in T.date]) + 1; ee = ee[(ee > 0) & (ee < nd)]
    s = pd.Series(1, index=ee).groupby(level=0).sum()
    sw_new = sw_new.add(s, fill_value=0)
    for k in range(int(o["hold"])): sw_hold = sw_hold.add(s.rename(lambda x: x + k), fill_value=0)
sw_hold = sw_hold.reindex(idx, fill_value=0) * 300
T1 = pickle.load(open(KD / "t1.pkl", "rb"))["T"]; T1 = T1[T1.date >= "20160101"]
t1_new = pd.Series(0.0, index=idx).add(pd.Series(1, index=[ci.get(d, -1) for d in T1.date]).groupby(level=0).sum(), fill_value=0)
D = pd.DataFrame({"date": cal, "t8": t8_new.reindex(idx, fill_value=0), "t8cap": t8_hold, "sw": sw_new.reindex(idx, fill_value=0), "swcap": sw_hold, "t1": t1_new.reindex(idx, fill_value=0)})
D = D[(D.date >= "20160101") & (D.date <= cal[-9])]
D["cap"] = D.t8cap + D.swcap
print("날 %d · T8 매수 있는 날 %d" % (len(D), (D.t8 > 0).sum()))
print("하루 수 상관(같은 날): T8~스윙 신규 %.2f · T8~갭하락 %.2f · T8 보유돈~스윙 보유돈 %.2f" % (D.t8.corr(D.sw), D.t8.corr(D.t1), D.t8cap.corr(D.swcap)))
print()
print("| 날 무리 | 날 수 | T8 매수/일 | 스윙 신규/일 | 스윙 신규 있는 날 | 갭하락 매수/일 | T8 보유돈 | 스윙 보유돈 | 합계 |")
print("|---|---|---|---|---|---|---|---|---|")
top = D[D.t8 > 0].t8.quantile(0.9)
for nm, m in (("T8 없는 날", D.t8 == 0), ("T8 1~%d종목" % (top - 1), (D.t8 > 0) & (D.t8 < top)), ("T8 몰린 날(상위 10%%, %d종목↑)" % top, D.t8 >= top),
              ("전체 평균", D.t8 >= 0)):
    z = D[m]
    print("| %s | %d | %.1f | %.1f | %.0f%% | %.1f | %.0f만 | %.0f만 | %.0f만 |" % (nm, len(z), z.t8.mean(), z.sw.mean(), (z.sw > 0).mean() * 100, z.t1.mean(), z.t8cap.mean(), z.swcap.mean(), z.cap.mean()))
print()
print("같이 묶이는 돈(T8 보유 + 스윙 보유, 스윙 종목당 300만): 95%% %.0f만 · 99%% %.0f만 · 최대 %.0f만(%s)" % (D.cap.quantile(0.95), D.cap.quantile(0.99), D.cap.max(), D.loc[D.cap.idxmax(), "date"]))
print("스윙 혼자: 95%% %.0f만 · 최대 %.0f만 / T8 혼자: 95%% %.0f만 · 최대 %.0f만" % (D.swcap.quantile(0.95), D.swcap.max(), D.t8cap.quantile(0.95), D.t8cap.max()))
big = D.sort_values("t8", ascending=False).head(12)
print("T8 가장 몰린 12날: " + " · ".join("%s T8 %d·스윙신규 %d·갭하락 %d" % (r.date, r.t8, r.sw, r.t1) for r in big.itertuples()))
