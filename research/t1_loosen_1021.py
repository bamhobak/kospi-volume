# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 그물 넓히기 — 종목당 금액을 낮추고 후보를 더 많이 걸면 어디까지가 좋은가 (2026-10-21 사용자
"한 종목당 많은 금액을 사면 불리하니 금액을 낮게 하고 후보를 더 많이 걸리게 해도 될 것 같아. 어느 정도 선이 좋을지 실측").

지금 그물: 유니버스(거래대금 상위 40%) 아래 1/3 · 어제 거래량 하위 30% · 갭 하위 20% · 시장 대비 -1.5%p 이하(실제 시가) → 시가→종가.
넓히는 축 넷을 하나씩, 그리고 같이:
  ① 시장 대비 문턱 -1.5 → -1.0 · -0.5 · 0     ② 갭 순위 하위 20 → 30 · 40 · 50%
  ③ 어제 거래량 하위 30 → 50 · 70 · 100%(조건 없음)   ④ 종목 크기 아래 1/3 → 1/2 · 2/3 · 전부
핵심 잣대 = **새로 걸린 몫만의 건당 평균**(한계 수익). 종목당 금액이 같다면 그게 비용 + 체결 손해보다 크면 넓힐 만하다.
체결 손해(실행 실측 10-12~20, 50만): 매수 지정가 +0.04% · 종가 시장가 매도 +0.45% → 0.5% 안팎을 문턱으로 본다(비용 0.23 은 이미 뺌).
구간: 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/t1_loosen_1021.py
"""
import sys
from itertools import product
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT

PERS = ("옛날", "학습", "검증")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def main():
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq"]].dropna(subset=["oc", "rgap", "q_gap", "liq"]).copy()
    H["oc"] = H.oc - FT.COST
    H["q_vm"] = H.q_vm.fillna(1.0)
    H["per"] = np.where(H.date <= "20151231", "옛날", np.where(H.date <= "20221231", "학습", "검증"))
    yrs = {p: H.loc[H.per == p, "date"].nunique() / 250 for p in PERS}

    def mask(rg=-1.5, qg=0.20, qv=0.30, lq=1 / 3):
        return (H.rgap <= rg) & (H.q_gap <= qg) & (H.q_vm <= qv) & (H.liq <= lq)

    BASE_M = mask()

    def cell(Z, p, full=True):
        q = Z[Z.per == p]
        if len(q) < 30: return "-"
        s = "%.0f건 · %+.2f%% · %.0f%%" % (len(q) / yrs[p], q.oc.mean(), (q.oc > 0).mean() * 100)
        return s + (" · 연 %+.0f" % (q.oc.sum() / yrs[p]) if full else "")

    def row(nm, m):
        Z, A = H[m], H[m & ~BASE_M]
        P("| %s | %s | %s |" % (nm, " | ".join(cell(Z, p) for p in PERS), " | ".join(cell(A, p, False) for p in PERS)))

    hdr = "| 판 | 옛날 2005~15 | 학습 2016~22 | 검증 2023~ | 새로 걸린 몫: 옛날 | 학습 | 검증 |"
    P("칸 = 연 건수 · 건당 평균(비용 0.23 뒤) · 승률 · 연 합계(종목당 같은 금액일 때 '건당 %'의 1년 합 — 금액 × 이 숫자/100 = 1년 손익)")
    P("'새로 걸린 몫' = 지금 그물엔 없고 넓힌 그물에만 있는 종목의 성적(한계 수익). 실행 손해 0.5% 안팎보다 커야 넓힐 만하다.\n")
    for title, items in (
        ("① 시장 대비 문턱", [("-1.5%%p(지금)", mask())] + [("%+.1f%%p" % v, mask(rg=v)) for v in (-1.0, -0.5, 0.0)]),
        ("② 갭 순위", [("하위 %d%%" % (v * 100), mask(qg=v)) for v in (0.30, 0.40, 0.50)]),
        ("③ 어제 거래량", [("하위 %d%%" % (v * 100), mask(qv=v)) for v in (0.50, 0.70)] + [("조건 없음", mask(qv=1.01))]),
        ("④ 종목 크기(유니버스 안 거래대금 순위)", [("아래 1/2", mask(lq=0.5)), ("아래 2/3", mask(lq=2 / 3)), ("전부", mask(lq=1.01))]),
    ):
        P("## " + title); P(hdr); P("|---|---|---|---|---|---|---|")
        for nm, m in items: row(nm, m)
        P("")

    # 같이 넓히기 — 검증 구간 건당 평균이 0.8% 이상 남는 판 중 연 합계 큰 순 (학습 구간도 같이 보여 준다)
    P("## ⑤ 같이 넓히기 — 건당 평균(검증)이 +0.8% 이상인 판 중 연 합계(검증) 큰 순 15개")
    P("| 시장 대비 | 갭 순위 | 거래량 | 크기 | 옛날 | 학습 | 검증 | 새로 걸린 몫(검증) | 하루 건수(검증: 중앙/90%) |"); P("|---|---|---|---|---|---|---|---|---|")
    res = []
    for rg, qg, qv, lq in product((-1.5, -1.0, -0.5), (0.2, 0.3, 0.4), (0.3, 0.5, 1.01), (1 / 3, 0.5, 2 / 3)):
        m = mask(rg, qg, qv, lq); q = H[m & (H.per == "검증")]
        if len(q) < 100: continue
        res.append((q.oc.sum() / yrs["검증"], q.oc.mean(), rg, qg, qv, lq, m))
    res.sort(key=lambda x: -x[0])
    k = 0
    for tot, avg, rg, qg, qv, lq, m in res:
        if avg < 0.8: continue
        q = H[m & (H.per == "검증")]; n = q.groupby("date").size()
        P("| %+.1f | 하위 %d%% | %s | %s | %s | %s | %s | %s | %d / %d |" % (rg, qg * 100, "없음" if qv > 1 else "하위 %d%%" % (qv * 100),
          {1 / 3: "1/3", 0.5: "1/2", 2 / 3: "2/3"}[lq], cell(H[m], "옛날"), cell(H[m], "학습"), cell(H[m], "검증"),
          cell(H[m & ~BASE_M], "검증", False), n.median(), n.quantile(0.9)))
        k += 1
        if k >= 15: break
    n = H[BASE_M & (H.per == "검증")].groupby("date").size()
    P("\n지금 그물 하루 건수(검증, 신호 난 날): 중앙 %d · 90%% %d · 최대 %d" % (n.median(), n.quantile(0.9), n.max()))
    (BASE / "research" / "cache" / "t1_loosen_1021.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
