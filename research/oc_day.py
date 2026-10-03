# -*- coding: utf-8 -*-
"""A — 데이 1단계: **시가에 사서 같은 날 종가에 판다** (2026-10-03, 사용자: a b c 해줘).
1분봉 없이 일봉 20년치로 '전날까지의 어떤 특징이 오늘 시가→종가를 올리나' 를 본다. 통과한 조건 = 데이 후보군 규칙.

수익 = 오늘 종가 ÷ 오늘 시가 − 1 − 비용(국장 0.22% · 미장 0.25% 왕복: 수수료·거래세·단일가 체결 미끄러짐)
재료(전부 어제까지 — 오늘 것은 갭 하나뿐):
  r1 어제 등락 · r5 5일 · r20 20일 · clv 어제 종가 위치(고저 사이) · rng 어제 고저폭 · vm 어제 거래량 ÷ 그 전 20일 평균
  fh 어제 종가의 20일 고점 대비 · d5 어제 종가의 5일선 대비 · gap 오늘 시가 갭(⚠ 장전 예상체결가로만 미리 보인다 — 따로 표시)
  국장만 2018~: fr 어제 외국인 순매수 ÷ 20일 평균 거래대금 · ir 개인
판정: 같은 날 유니버스(거래대금 상위 40%) 안에서 재료 10분위 → 분위별 '그날 평균'을 다시 평균(하루 = 한 표)
  학습 2016~22 · 검증 2023~ · 참고 2005~15. 통과 = 둘 다 비용 뒤 플러스 & 학습 해별 플러스 60%↑ & 일별 t ≥ 3
    python research/oc_day.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import run_spec as R
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = {"KR": 0.22, "US": 0.25}
FEATS = ["r1", "r5", "r20", "clv", "rng", "vm", "fh", "d5", "gap"]
NAME = {"r1": "어제 등락", "r5": "5일 등락", "r20": "20일 등락", "clv": "어제 종가 위치", "rng": "어제 고저폭", "vm": "어제 거래량 배수",
        "fh": "20일 고점 대비", "d5": "5일선 대비", "gap": "오늘 갭(장전 예상)", "fr": "어제 외국인 순매수", "ir": "어제 개인 순매수"}


def build(mk):
    A, uni, since = R.load_market(mk)
    A = A[["ticker", "date", "open", "high", "low", "close", "volume", "amt20", "gap0"] + (["mk"] if "mk" in A.columns else [])].copy()
    A["uni"] = uni.values
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    A["oc"] = (A.close / A.open - 1) * 100
    A["r1"] = (pc / g.close.shift(2) - 1) * 100
    A["r5"] = (pc / g.close.shift(6) - 1) * 100
    A["r20"] = (pc / g.close.shift(21) - 1) * 100
    ph, pl = g.high.shift(1), g.low.shift(1)
    A["clv"] = (pc - pl) / (ph - pl).replace(0, np.nan)
    A["rng"] = (ph - pl) / pc * 100
    pv = g.volume.shift(1)
    A["vm"] = pv / g.volume.transform(lambda s: s.shift(2).rolling(20, min_periods=15).mean()).replace(0, np.nan)
    A["fh"] = (pc / g.high.transform(lambda s: s.shift(1).rolling(20, min_periods=15).max()) - 1) * 100
    A["d5"] = (pc / g.close.transform(lambda s: s.shift(1).rolling(5).mean()) - 1) * 100
    A["gap"] = A.gap0
    # 오버나이트(종가 단일가 매수 → 다음날 시가 매도)용 — **오늘** 값과 다음날 시가(2026-10-03 day2.py)
    #   ⚠ 걸러내기(유니버스·이음새) 전에 계산해야 다음 '거래일' 시가가 맞다
    A["on"] = (g.open.shift(-1) / A.close - 1) * 100
    A["r1t"] = (A.close / pc - 1) * 100
    A["clvt"] = (A.close - A.low) / (A.high - A.low).replace(0, np.nan)
    A["vmt"] = A.volume / g.volume.transform(lambda s: s.shift(1).rolling(20, min_periods=15).mean()).replace(0, np.nan)
    A["rngt"] = (A.high - A.low) / A.close * 100
    A["r5t"] = (A.close / g.close.shift(5) - 1) * 100
    A["r20t"] = (A.close / g.close.shift(20) - 1) * 100
    feats = list(FEATS)
    if mk == "KR":
        c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
        F = pd.read_sql("SELECT ticker, date, indiv, frgn FROM flow11", c).sort_values(["ticker", "date"])
        F["frgn_p"] = F.groupby("ticker").frgn.shift(1); F["indiv_p"] = F.groupby("ticker").indiv.shift(1)
        m = A[["ticker", "date"]].merge(F[["ticker", "date", "frgn_p", "indiv_p"]], on=["ticker", "date"], how="left")
        amt = A.amt20.values * 1e8
        A["fr"] = m.frgn_p.values / amt * 100; A["ir"] = m.indiv_p.values / amt * 100
        feats += ["fr", "ir"]
        # 시가가 상한가 근처면 못 산다 · 거래 없는 날 제외
        A = A[(A.gap0 < 29) & (A.volume > 0)]
        # ⚠ 2026-10-03: kr_scan 에 시가·종가 기준이 섞인 줄(이음새)이 있다 — 갭 -50%·장중 +60% 처럼 ±30% 가격제한으로 불가능한 줄.
        #   그대로 두면 '갭 -5%↓' 칸이 가짜로 부푼다(494120·183300·327260, 2026-06~07). 가격제한·고저 범위를 벗어난 줄은 버린다.
        bad = (A.gap0.abs() > 30.5) | ((A.close / pc - 1).abs() > 0.305) | (A.open > A.high * 1.001) | (A.open < A.low * 0.999)               | (A.close > A.high * 1.001) | (A.close < A.low * 0.999)
        A = A[~bad.reindex(A.index).fillna(False)]
    A = A[A.uni & A.oc.notna() & (A.date >= "20050101")].copy()
    A["oc"] = A.oc.clip(-60, 60) - COST[mk]
    return A, feats


def per_day(sub):
    d = sub.groupby("date").oc.mean()
    return d


def stat(d):
    if len(d) < 50: return None
    t = d.mean() / (d.std() / np.sqrt(len(d)))
    yr = d.groupby(d.index.str[:4]).mean()
    return dict(n=len(d), m=d.mean(), win=(d > 0).mean() * 100, t=t, ypos=(yr > 0).sum(), ny=len(yr))


def run(mk):
    A, feats = build(mk)
    P("## %s — 종목-일 %s · 비용 %.2f%% 왕복" % ("국장" if mk == "KR" else "미장", f"{len(A):,}", COST[mk])); P("")
    base = {}
    for per, lo, hi in (("참고 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231")):
        s = stat(per_day(A[(A.date >= lo) & (A.date <= hi)]))
        if s: base[per] = s
    P("유니버스 전체(아무거나 시가에 사서 종가에 팔면): " + " · ".join("%s %+.3f%%/일(승률 %.0f%%)" % (k, v["m"], v["win"]) for k, v in base.items())); P("")
    rows = []
    for f in feats:
        z = A[["date", f, "oc"]].dropna()
        z["q"] = z.groupby("date")[f].rank(pct=True)
        for lab, lo_, hi_ in (("하위 1%", 0, 0.01), ("하위 10%", 0, 0.1), ("상위 10%", 0.9, 1.01), ("상위 1%", 0.99, 1.01)):
            sub = z[(z.q > lo_) & (z.q <= hi_)] if lo_ > 0 else z[z.q <= hi_]
            res = {}
            for per, a, b in (("old", "20050101", "20151231"), ("tr", "20160101", "20221231"), ("va", "20230101", "20991231")):
                res[per] = stat(per_day(sub[(sub.date >= a) & (sub.date <= b)]))
            tr, va = res["tr"], res["va"]
            ok = bool(tr and va and tr["m"] > 0 and va["m"] > 0 and tr["t"] >= 3 and tr["ypos"] / tr["ny"] >= 0.6)
            rows.append(dict(f=f, lab=lab, res=res, ok=ok, trades=len(sub[sub.date >= "20230101"]) / max(sub[sub.date >= "20230101"].date.nunique(), 1)))
    log_trials("oc_day_%s_%s" % (mk, time.strftime("%Y%m%d")), len(rows))
    fmt = lambda s: ("%+.3f · %.0f%% · t%.1f · %d/%d해" % (s["m"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "-"
    P("| 재료 | 구간 | 참고 05~15 | 학습 16~22 (평균%/일 · 승률 · t · 플러스 해) | 검증 23~ | 하루 종목 수 | 판정 |"); P("|---|---|---|---|---|---|---|")
    for x in rows:
        tr = x["res"]["tr"]
        if x["ok"] or (tr and tr["m"] > 0):
            P("| %s | %s | %s | %s | %s | %.1f | %s |" % (NAME[x["f"]], x["lab"], fmt(x["res"]["old"]), fmt(tr), fmt(x["res"]["va"]), x["trades"], "✅" if x["ok"] else ""))
    P(""); P("(학습에서 비용 뒤 플러스가 아닌 칸은 생략 — 전체 %d칸 중 %d칸 표시 · 통과 %d)" % (len(rows), sum(1 for x in rows if x["ok"] or (x["res"]["tr"] and x["res"]["tr"]["m"] > 0)), sum(x["ok"] for x in rows)))
    P("")
    return A, rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    P("# A — 데이 1단계: 시가 매수 → 같은 날 종가 매도 · %s" % time.strftime("%Y-%m-%d")); P("")
    for mk in ("KR", "US"):
        A, rows = run(mk)
        pd.to_pickle(rows, ROOT / "cache" / ("oc_day_%s.pkl" % mk))
    P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("oc_day_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
