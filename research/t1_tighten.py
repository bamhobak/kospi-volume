# -*- coding: utf-8 -*-
"""데이 [갭 하락 조용주](T1) 승률 조이기 (2026-10-04, 사용자: "승률 55% 잖아 더 조일 수 있는지").
T1 후보(중소형 · 갭 하위10% · 어제 거래량 하위30%) 안에서 **장 전에 아는 재료**로 하나·둘 더 거른다.
판정: 건당 승률(비용 0.23% 뒤 플러스 비율)과 건당 평균이 학습(2016~22)·검증(2023~) **둘 다** 올라야 하고, 하루 2종목 이상 남아야 한다.
  z = (거른 무리 승률 − T1 승률) ÷ 같은 건수 무작위 표본의 표준오차 — 학습·검증 각각
    python research/t1_tighten.py
"""
import sys, time, itertools
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = 0.23


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    B = pd.read_pickle(ROOT / "cache" / "day2_T1.pkl")          # day2.py part1 — oc 는 0.22% 뺀 값
    B["r"] = B.oc + 0.22 - COST
    B["rel"] = B.gap - B.mgap
    B["wd"] = pd.to_datetime(B.date).dt.dayofweek
    B["tr"] = (B.date >= "20160101") & (B.date <= "20221231"); B["va"] = B.date >= "20230101"
    base = {k: B[B[k]] for k in ("tr", "va")}
    bw = {k: (v.r > 0).mean() for k, v in base.items()}; bm = {k: v.r.mean() for k, v in base.items()}
    days = {k: v.date.nunique() for k, v in base.items()}
    P("# T1 승률 조이기 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("기준 T1: 학습 %d건 승률 %.1f%% 평균 %+.3f · 검증 %d건 승률 %.1f%% 평균 %+.3f (건당 · 비용 %.2f%% 뒤)" % (
        len(base["tr"]), bw["tr"] * 100, bm["tr"], len(base["va"]), bw["va"] * 100, bm["va"], COST)); P("")
    q = lambda c, lo, hi: (B[c] > lo) & (B[c] <= hi)
    F = {
        "시장 대비 -3%p↓": B.rel <= -3, "시장 대비 -2%p↓": B.rel <= -2, "시장 대비 -1%p↓": B.rel <= -1,
        "갭 -3%↓": B.gap <= -3, "갭 -2%↓": B.gap <= -2, "갭 -1%↓": B.gap <= -1, "갭 -1~0%": B.gap > -1,
        "시장 갭 ≤-0.5%": B.mgap <= -0.5, "시장 갭 > 0": B.mgap > 0,
        "거래량 하위10%": B.q_vm <= 0.10, "거래량 하위20%": B.q_vm <= 0.20,
        "5일선 아래 하위30%": B.q_d5 <= 0.3, "5일선 아래 하위50%": B.q_d5 <= 0.5,
        "5일 하락 하위30%": B.q_r5 <= 0.3, "20일 하락 하위30%": B.q_r20 <= 0.3, "20일 하락 하위50%": B.q_r20 <= 0.5,
        "어제 하락 하위30%": B.q_r1 <= 0.3, "어제 상승(상위50%)": B.q_r1 >= 0.5,
        "어제 고저폭 작음 하위30%": B.q_rng <= 0.3, "어제 고저폭 큼 상위30%": B.q_rng >= 0.7,
        "20일 고점서 먼 하위30%": B.q_fh <= 0.3,
        "어제 종가 위치 낮음(clv<0.3)": B.clv < 0.3, "어제 종가 위치 높음(clv>0.7)": B.clv > 0.7,
        "어제 외국인 순매수 상위30%": B.q_fr >= 0.7, "어제 개인 순매도(하위30%)": B.q_ir <= 0.3,
        "코스닥": B.mk == "KOSDAQ" if "mk" in B else B.r == B.r, "코스피": B.mk == "KOSPI" if "mk" in B else B.r != B.r,
        "공시 없음": B.disc == "없음",
        "화~금(월요일 빼기)": B.wd != 0,
        "주가 5천원↑": B.open >= 5000, "주가 2만원↑": B.open >= 20000, "주가 5천원↓": B.open < 5000,
        "중소형 중 큰 쪽(유니버스 1/3~2/3)": B.liq > 1 / 3, "중소형 중 작은 쪽(아래 1/3)": B.liq <= 1 / 3,
    }
    rows = []
    def score(lab, m):
        out = {}
        for k in ("tr", "va"):
            z = B[m & B[k]]
            n = len(z)
            if n < 200: return None
            w = (z.r > 0).mean(); se = np.sqrt(bw[k] * (1 - bw[k]) / n) * np.sqrt(max(1 - n / len(base[k]), 1e-9))
            out[k] = dict(n=n, w=w, m=z.r.mean(), zw=(w - bw[k]) / se, perday=n / days[k],
                          ypos=(z.groupby(z.date.str[:4]).r.mean() > 0).sum(), ny=z.date.str[:4].nunique(),
                          ywin=(z.groupby(z.date.str[:4]).r.apply(lambda s: (s > 0).mean()) > bw[k]).sum())
        ok = all(out[k]["w"] > bw[k] and out[k]["m"] > bm[k] and out[k]["zw"] >= 2 for k in ("tr", "va")) and out["va"]["perday"] >= 2
        rows.append(dict(lab=lab, ok=ok, **{f"{k}_{a}": out[k][a] for k in out for a in out[k]}))
    for lab, m in F.items():
        score(lab, m.fillna(False))
    single = pd.DataFrame(rows)
    # 둘 섞기 — 하나로 승률이 올랐던 것끼리
    good = [r.lab for r in single.itertuples() if r.tr_w > bw["tr"] and r.va_w > bw["va"]]
    for a, b in itertools.combinations(good, 2):
        score(a + " + " + b, (F[a] & F[b]).fillna(False))
    R_ = pd.DataFrame(rows)
    log_trials("t1_tighten_%s" % time.strftime("%Y%m%d"), len(R_))
    R_["minw"] = R_[["tr_w", "va_w"]].min(axis=1)
    P("| 추가 조건 | 학습 승률 · 평균 · 하루 | 검증 승률 · 평균 · 하루 | 승률 z(학습/검증) | 해마다 T1보다 승률 높음 | 판정 |"); P("|---|---|---|---|---|---|")
    for r in R_.sort_values("minw", ascending=False).head(30).itertuples():
        P("| %s | %.1f%% · %+.2f · %.1f | %.1f%% · %+.2f · %.1f | %.1f / %.1f | %d/%d · %d/%d | %s |" % (
            r.lab, r.tr_w * 100, r.tr_m, r.tr_perday, r.va_w * 100, r.va_m, r.va_perday, r.tr_zw, r.va_zw,
            r.tr_ywin, r.tr_ny, r.va_ywin, r.va_ny, "✅" if r.ok else ""))
    P(""); P("(칸 %d · 통과 %d · %.1f분)" % (len(R_), R_.ok.sum(), (time.time() - t0) / 60))
    R_.to_pickle(ROOT / "cache" / "t1_tighten.pkl")
    (ROOT / "reports" / ("t1_tighten_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
