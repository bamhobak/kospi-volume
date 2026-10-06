# -*- coding: utf-8 -*-
"""국장 데이 — **전날 장중 모양**으로 고르고 오늘 시가 단일가에 사서 종가 단일가에 판다 (2026-10-06, 사용자 "1번").
H0296: 장중에 사면 미끄러짐·세금에 다 먹힌다 → T1 처럼 장 전에 고르고 단일가로만 사고판다(비용 0.23%, 미끄러짐 0).
전날 재료(1분봉에서만 보이는 것):
  막판 1시간 등락(14:00→종가) · 종가 단일가 튐(15:19→종가) · 저가가 15시 뒤 · 오전 오름 뒤 오후 꺾임 / 반대 ·
  종가 vs 하루 VWAP · 거래량이 첫 30분에 몰림 / 막판 1시간에 몰림 · 고가가 오전 10시 전(뒤로 흘러내림)
각 재료 상·하위 10% 단독 + T1 꼴(오늘 갭 하위 10%)과 겹침.
견줄 것: 같은 날 유니버스 시가→종가 평균(초과). 판정은 day3 와 같음(학습 22-12~24 · 검증 25~ · 둘 다 플러스·초과 플러스 · t≥3 · 해마다 · 하루 0.3건↑).
    python research/day4.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
FEE = 0.23


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A = pd.read_pickle(ROOT / "cache" / "m1_panel_KR.pkl").sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    # 전날 재료(그날 값 → 다음 줄로 민다)
    F = pd.DataFrame(index=A.index)
    F["lasth"] = (A.c / A.p1400 - 1) * 100
    F["auc"] = (A.c / A.p1519 - 1) * 100
    F["lolate"] = (A.lo_t >= "1500").astype(float)
    F["amup_pmdn"] = (A.p1200 / A.o - 1) * 100 - (A.c / A.p1200 - 1) * 100       # 클수록 오전 오르고 오후 꺾임
    F["cvw"] = (A.c / (A.amt / A.vol.replace(0, np.nan)) - 1) * 100
    F["vfront"] = A.v0930 / A.vol.replace(0, np.nan)
    F["vlate"] = 1 - A.v1400 / A.vol.replace(0, np.nan)
    F["hiearly"] = (A.hi_t <= "1000").astype(float)
    F["dayret"] = (A.c / A.pc - 1) * 100
    for k in F.columns:
        A["y_" + k] = F[k].groupby(A.ticker).shift(1)
    A["gap"] = (A.o / A.pc - 1) * 100
    A = A[A.pc.notna() & (A.gap.abs() < 30) & ((A.c / A.pc - 1).abs() < 0.31)]
    A["rk"] = A.groupby("date").amt20.rank(pct=True)
    A = A[(A.rk >= 0.2) & (A.amt20 >= 3e9) & (A.pc >= 1000)].copy()
    A["ret"] = (A.c / A.o - 1) * 100 - FEE
    raw = (A.c / A.o - 1) * 100
    A["ex"] = raw - A.date.map(raw.groupby(A.date).mean())
    q = lambda c: A.groupby("date")[c].rank(pct=True)
    gapq = q("gap")
    S = {}
    for k, lab in (("y_lasth", "어제 막판 1시간"), ("y_auc", "어제 종가 단일가 튐"), ("y_amup_pmdn", "어제 오전↑·오후↓ 정도"), ("y_cvw", "어제 종가 vs VWAP"),
                   ("y_vfront", "어제 첫 30분 거래량 비중"), ("y_vlate", "어제 막판 1시간 거래량 비중"), ("y_dayret", "어제 등락(참고)")):
        qq = q(k)
        S["%s 하위 10%%" % lab] = qq <= 0.1
        S["%s 상위 10%%" % lab] = qq >= 0.9
    S["어제 저가가 15시 뒤"] = A.y_lolate == 1
    S["어제 고가가 10시 전"] = A.y_hiearly == 1
    base = list(S.items())
    for nm, m in base:                                                 # T1 꼴(오늘 갭 하위 10%)과 겹침
        S["T1꼴(갭 하위10%) & " + nm] = m & (gapq <= 0.1)
    S["T1꼴(갭 하위10%) 단독(견줌)"] = gapq <= 0.1
    nd = A.date.nunique()
    P("# 국장 데이 — 전날 장중 모양 → 오늘 시가 단일가 매수·종가 단일가 매도 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 유니버스 %s 종목-일 · %d일 · 비용 %.2f%%(단일가끼리 — 미끄러짐 0) · 초과 = 같은 날 유니버스 시가→종가 평균 대비" % (f"{len(A):,}", nd, FEE)); P("")
    P("| 조건 | 건수(하루) | 학습 22.12~24: 평균·승률·초과 | 검증 25~: 평균·승률·초과 | 초과 t | 플러스 해 | 판정 |"); P("|---|---|---|---|---|---|---|")
    res = []
    for nm, m in S.items():
        Z = A[m.fillna(False).astype(bool) & A.ret.abs().lt(40)]
        if len(Z) < 50: continue
        o = {"name": nm, "n": len(Z), "perday": len(Z) / nd}
        for k, (a, b) in {"tr": ("20221201", "20241231"), "va": ("20250101", "20991231")}.items():
            z = Z[(Z.date >= a) & (Z.date <= b)]
            o[k] = (len(z), z.ret.mean(), (z.ret > 0).mean() * 100, z.ex.mean()) if len(z) >= 20 else None
        d = Z.groupby("date").ex.mean(); o["t"] = d.mean() / (d.std() / np.sqrt(len(d)))
        yr = Z.groupby(Z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
        o["yp"], o["ny"] = int((yr > 0).sum()), len(yr)
        tr, va = o["tr"], o["va"]
        o["ok"] = bool(tr and va and tr[1] > 0 and va[1] > 0 and tr[3] > 0 and va[3] > 0 and o["t"] >= 3 and o["yp"] >= o["ny"] - 1 and o["perday"] >= 0.3)
        res.append(o)
        c = lambda z: "-" if not z else "%d건 %+.2f%% · %.0f%% · %+.2f" % z
        P("| %s | %d (%.1f) | %s | %s | %.1f | %d/%d | %s |" % (nm, o["n"], o["perday"], c(tr), c(va), o["t"], o["yp"], o["ny"], "✅ 통과" if o["ok"] else "—"))
    P(""); P("(칸 %d · 통과 %d · %.1f분)" % (len(res), sum(o["ok"] for o in res), (time.time() - t0) / 60))
    log_trials("day4_%s" % time.strftime("%Y%m%d"), len(res))
    pd.to_pickle((A, res), ROOT / "cache" / "day4.pkl")
    (ROOT / "reports" / ("day4_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
