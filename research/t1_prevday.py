# -*- coding: utf-8 -*-
"""T1 후보의 **전날** 장중 모양이 T1 성적을 가르나 (2026-10-06, day4 후속).
day4: 갭 하위 10% 안에서 '어제 종가 단일가에서 밀림 · 어제 저가가 15시 뒤 · 어제 막판 1시간 약함' 이 초과를 더했다.
진짜 T1(중소형 아래 1/3 · 시장 대비 갭) 후보는 대부분 지금 상위 1,000 밖이라 → 후보 전날 1분봉을 토스에서 받아 직접 본다.
T1 성적은 1분봉 시가→종가(비용 0.23%) · 1분봉 시가가 일봉과 1%↑ 어긋난 날은 뺀다(H0295).
    python research/t1_prevday.py
"""
import sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import collect_m1 as M
import t1_exit as T
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def feats(rows):
    if len(rows) < 200: return None
    D = M.frame(rows)
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul"); D["hm"] = t.dt.strftime("%H%M").values
    D = D.sort_values("ts"); c = D.c.astype(float).values; hm = D.hm.values; v = D.v.astype(float).values
    at = lambda h: c[np.where(hm <= h)[0][-1]] if (hm <= h).any() else np.nan
    lo_t = hm[int(np.argmin(D.l.values))]; hi_t = hm[int(np.argmax(D.h.values))]
    vw = (c * v).sum() / max(v.sum(), 1)
    return {"y_auc": (c[-1] / at("1519") - 1) * 100, "y_lasth": (c[-1] / at("1400") - 1) * 100, "y_lolate": lo_t >= "1500",
            "y_hiearly": hi_t <= "1000", "y_cvw": (c[-1] / vw - 1) * 100, "y_vlate": v[hm >= "1400"].sum() / max(v.sum(), 1)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    C = T.t1()
    need = list(zip(C.ticker, C.pdate))
    with ThreadPoolExecutor(M.WORKERS) as ex:
        F = list(ex.map(lambda x: feats(M.fetch_day("KR", x[0], x[1])), need))
    C["ok"] = [f is not None for f in F]
    for k in ("y_auc", "y_lasth", "y_lolate", "y_hiearly", "y_cvw", "y_vlate"):
        C[k] = [f[k] if f else np.nan for f in F]
    R = pd.read_pickle(ROOT / "cache" / "t1_exit.pkl")
    R = R[~R.adj][["ticker", "date", "종가 단일가(지금)"]].rename(columns={"종가 단일가(지금)": "ret"})
    J = C.merge(R, on=["ticker", "date"]); J = J[J.ok]
    P("# T1 후보의 전날 장중 모양 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- T1 %d건 중 전날 1분봉 받음 %d · T1 성적(1분봉 시가→종가, 비용 0.23%%) 붙은 것 **%d건** · %.1f분" % (len(C), int(C.ok.sum()), len(J), (time.time() - t0) / 60)); P("")
    P("| 무리 | 건수 | 2022-12~24 평균·승률 | 2025~ 평균·승률 | 해마다(23·24·25·26) | 나머지 T1 와 차이(t) |"); P("|---|---|---|---|---|---|")
    def row(lab, m):
        Z, Y = J[m], J[~m]
        cells = []
        for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
            z = Z[(Z.date >= a) & (Z.date <= b)]
            cells.append("%d건 %+.2f%% · %.0f%%" % (len(z), z.ret.mean(), (z.ret > 0).mean() * 100) if len(z) >= 10 else "-")
        yr = Z.groupby(Z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
        dif = Z.ret.mean() - Y.ret.mean(); se = np.sqrt(Z.ret.var() / max(len(Z), 1) + Y.ret.var() / max(len(Y), 1))
        P("| %s | %d | %s | %s | %s | %+.2f%%p (t %.1f) |" % (lab, len(Z), cells[0], cells[1], " ".join("%+.2f" % v for v in yr.values), dif, dif / se if se else np.nan))
    row("T1 전체", J.ret.notna())
    q = lambda k: J[k].rank(pct=True)
    for k, lab in (("y_auc", "어제 종가 단일가 튐"), ("y_lasth", "어제 막판 1시간"), ("y_cvw", "어제 종가 vs VWAP"), ("y_vlate", "어제 막판 거래량 비중")):
        row("%s 하위 1/3" % lab, q(k) <= 1 / 3); row("%s 상위 1/3" % lab, q(k) >= 2 / 3)
    row("어제 종가 단일가에서 -0.5%↓ 밀림", J.y_auc <= -0.5)
    row("어제 저가가 15시 뒤", J.y_lolate == True)
    row("어제 고가가 10시 전", J.y_hiearly == True)
    P(""); log_trials("t1_prevday_%s" % time.strftime("%Y%m%d"), 14)
    J.to_pickle(ROOT / "cache" / "t1_prevday.pkl")
    (ROOT / "reports" / ("t1_prevday_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
