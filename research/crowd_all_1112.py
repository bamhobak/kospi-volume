# -*- coding: utf-8 -*-
"""붐비는 날 쉬기 — 다른 규칙들도 [장전 되돌림]처럼 '그날 신호가 몰린 날'이 약한가 (2026-11-12 사용자 "다른 규칙들도 이와 비슷한 상황일 때 쉬는 게 좋은지 봐봐").
규칙마다 그날 신호 수로 날을 나눠(그 규칙의 신호 날 분포 기준: 위 5%·10%·20%) 건당 수익·시장 대비·총합(신호 나면 다 사니 총합 = 돈)을 본다.
학습(2016~22)·검증(2023~) 따로 — 두 구간 다 같은 방향이고 총합도 안 줄어야 '쉬기' 후보.
  데이 [갭하락](T1): data/y1_hist.pkl — 유니버스 아래 2/3·갭 하위 40%·어제 거래량 하위 30%·실제 시장 대비 갭 ≤ -1.5 → 시가→종가 − 0.23 (2015~2026-11)
       시장 = 그날 같은 유니버스(아래 2/3) 시가→종가 평균
  데이 [장후 낙폭](T6): C:/temp/kp/nxt_full0_panel.pkl — 장후 19:50 ≤ -2.5% · 낮 ±1% 빼기 → 19:51~20:00 VWAP → 다음 날 시가(g_vw, 비용 뒤) (2025-03~)
       시장 = 그날 패널 전 종목 g_vw 평균
  국장 스윙 P·D · 미장 스윙 N: research/cache/kr_rules_recheck.pkl · us_rules_recheck.pkl(10-07 규칙 정의) — ret(비용 뒤) · idx(같은 보유기간 지수)
  [미장 폭락](T4)는 나스닥 -2.5% 날만 켜지는 규칙이라 뺌 · [장전 되돌림](T5)는 11-12 이미 넣음(10개↑ 쉼)
    python research/crowd_all_1112.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
KR = {"P1": "P1", "P2": "P2", "P3": "P3", "P4": "P4 업종붕괴", "P5": "P5", "P6": "P6 깊은 이격", "P7": "P7", "D1": "D1", "D2": "D2"}
US = {"N1": "N1 상승장 신고가", "N2": "N2 낙폭과대", "N3": "N3 저PBR 낙폭", "N4": "N4 자사주 낙폭", "N5": "N5 잔잔 급등", "N6": "N6 실적 깜짝",
      "N8": "N8 분사주", "N9": "N9 S&P 편출"}


def t1():
    U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
    U = U[(U.liq <= 2 / 3)].dropna(subset=["oc"])
    mk = U.groupby("date").oc.mean() - 0.23
    T = U[(U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= -1.5)].copy()
    T["ret"] = T.oc - 0.23
    T["ex"] = T.ret - T.date.map(mk)
    return T[["date", "ret", "ex"]]


def t6():
    Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl").dropna(subset=["g_vw", "d1"])
    mk = Z.groupby("d1").g_vw.mean()
    T = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].copy()
    T["date"], T["ret"] = T.d1, T.g_vw
    T["ex"] = T.ret - T.date.map(mk)
    return T[["date", "ret", "ex"]]


def swing(path, names):
    A = pd.read_pickle(ROOT / "cache" / path)
    out = {}
    for k, v in A.items():
        X = v[0] if isinstance(v, tuple) else v
        if k not in names or X is None or not len(X): continue
        X = X.copy(); X["date"] = X.date.astype(str); X["ex"] = X.ret - X.idx
        out[k] = X[["date", "ret", "ex"]]
    return out


def judge(name, T, split="20230101"):
    n = T.groupby("date").size()
    T = T.assign(n=T.date.map(n))
    days = len(n)
    rows = []
    for q in (0.95, 0.90, 0.80):
        cut = max(2, int(np.ceil(n.quantile(q))))
        crowd = T[T.n >= cut]; calm = T[T.n < cut]
        if len(crowd) < 10: continue
        seg = lambda Z, a: Z[(Z.date < split) if a == "L" else (Z.date >= split)]
        cells = []
        ok = True
        for a in ("L", "V"):
            c, k = seg(crowd, a), seg(calm, a)
            if len(c) < 5 or len(k) < 5: cells.append("-"); ok = False; continue
            cells.append("%+.2f vs %+.2f (%d건)" % (c.ret.mean(), k.ret.mean(), len(c)))
            if not (c.ret.mean() < k.ret.mean() and c.ex.mean() < k.ex.mean()): ok = False
        d_sum = -crowd.ret.sum() / T.ret.sum() * 100 if T.ret.sum() else np.nan          # 쉬면 총합이 몇 % 바뀌나(+ = 늘어남)
        if crowd.ret.sum() > 0: ok = False                                                # 붐비는 날도 벌고 있으면 쉬면 돈이 준다
        rows.append((q, cut, len(crowd), crowd.d if False else crowd.date.nunique(), crowd.ret.mean(), calm.ret.mean(), crowd.ex.mean(), calm.ex.mean(), d_sum, cells, ok))
    P("| %s | 신호 날 %d · 하루 중앙 %d · 최대 %d | | | | | | |" % (name, days, n.median(), n.max()))
    for q, cut, nc, ndc, cr, ca, cx, kx, ds, cells, ok in rows:
        P("| 　위 %d%% 날(%d개↑) | %d건·%d일 | %+.2f%% vs %+.2f%% | %+.2f vs %+.2f | %s | %s | %+.0f%% | %s |" % (
            round((1 - q) * 100), cut, nc, ndc, cr, ca, cx, kx, cells[0] if cells else "-", cells[1] if len(cells) > 1 else "-", ds, "✅ 쉬기 후보" if ok else ""))
    return rows


def main():
    P("붐비는 날(그날 그 규칙 신호 수가 그 규칙 신호 날 중 위 N%) vs 나머지 — 건당 수익(비용 뒤)·시장(지수) 대비·학습/검증·쉬면 총합 변화\n")
    P("| 규칙 · 붐비는 날 | 표본 | 건당 붐빔 vs 나머지 | 시장 대비 붐빔 vs 나머지 | 학습 2016~22 | 검증 2023~ | 쉬면 총합 | 판정 |")
    P("|---|---|---|---|---|---|---|---|")
    res = {}
    res["T1"] = judge("데이 [갭하락]", t1())
    res["T6"] = judge("데이 [장후 낙폭] (2025-03~, 검증=2026)", t6(), split="20260101")
    for k, X in swing("kr_rules_recheck.pkl", KR).items(): res[k] = judge("국장 " + KR[k], X)
    for k, X in swing("us_rules_recheck.pkl", US).items(): res[k] = judge("미장 " + US[k], X)
    P("\n✅ = 두 구간 모두 붐비는 날이 건당·시장 대비 다 낮고, 붐비는 날 총합이 마이너스(쉬면 돈이 는다)")
    (ROOT / "crowd_all_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
