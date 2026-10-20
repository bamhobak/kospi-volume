# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 종목 크기(시총·거래대금)에 따른 매수 금액 배율 찾기 (2026-10-21 사용자
"해당 종목의 시총이나 전날 거래량(거래금)에 따라 매수금의 배율을 조정하는 것도 최적화해서 찾아봐").

두 가지를 같이 본다 — 금액을 크게 넣어도 되는 종목은 ① 덜 밀리고(체결 손해 작음) ② 건당 수익도 남아야 한다.
  A. 체결 손해 모형 — 실행 실측(data/day/exec_lab.jsonl, 실제 호가창에 우리 주문을 얹어 다시 계산)의 매수(시가 지정가)·매도(종가 시장가)
     손해와 체결률을 '우리 금액 ÷ 그 종목 거래대금(20일 평균·전날)' 에 맞춘다. 종목 거래대금은 토스 일봉에서 받는다.
  B. 과거(2005~2026-08) 지금 그물의 건당 수익을 거래대금·시총·전날 거래대금 구간별로.
  C. 배율 규칙 비교 — 하루 넣는 돈 총액이 같을 때(같은 자본) 1년 손익: 균등 / 거래대금^a / 시총^a / 전날 거래대금^a,
     A 의 손해 모형을 금액마다 적용(못 산 몫은 손익 0). 기준 금액(배율 1배) 50·100·200만 셋에서.
    python research/t1_size_liq_1021.py
"""
import json, sys, time
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CACHE = BASE / "research" / "cache" / "exec_liq_1021.json"
COST = 0.23


def liq_of_exec():
    """실행 실측 종목-일마다 그 전날까지의 20일 평균 거래대금·전날 거래대금(원)."""
    E = pd.DataFrame([json.loads(l) for l in (BASE / "data/day/exec_lab.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()])
    E = E.drop_duplicates(["day", "t", "amt"], keep="last")
    have = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    need = sorted({t for t in E.t} - set(have))
    if need:
        import collect_m1 as M
        for t in need:
            c = (M.get("/api/v1/candles", symbol=t, interval="1d", count=60) or {}).get("candles") or []
            have[t] = [(x["timestamp"][:10].replace("-", ""), float(x["closePrice"]), float(x["volume"])) for x in c]
            time.sleep(0.1)
        CACHE.write_text(json.dumps(have), encoding="utf-8")
    a20, a1 = [], []
    for d, t in zip(E.day, E.t):
        c = sorted([x for x in have.get(t, []) if x[0] < d])
        if len(c) < 20: a20.append(np.nan); a1.append(np.nan); continue
        a20.append(sum(p * v for _, p, v in c[-20:]) / 20); a1.append(c[-1][1] * c[-1][2])
    E["a20"], E["a1"] = a20, a1
    return E


def fit(E):
    """금액 ÷ 20일 평균 거래대금 = 참여율 p 구간별 손해·체결."""
    X = E.dropna(subset=["a20"]).copy()
    X["p"] = X.amt * 1e4 / X.a20 * 100            # %
    X["bc"] = [r["cost"] if isinstance(r, dict) else np.nan for r in X.B2]
    X["bf"] = [r["fill"] if isinstance(r, dict) else np.nan for r in X.B2]
    X["sc"] = [r["cost"] if isinstance(r, dict) and r.get("cost") is not None else np.nan for r in X.S1]
    X["p1"] = X.amt * 1e4 / X.a1 * 100
    P("## A. 체결 손해 — 우리 금액이 그 종목 20일 평균 거래대금의 몇 %%인가 (실행 실측 %d종목-일 × 금액 %d개)" % (X.drop_duplicates(["day", "t"]).shape[0], X.amt.nunique()))
    P("| 참여율(금액 ÷ 20일 평균 거래대금) | 줄 | 매수 손해(지정가) | 매수 체결 | 매도 손해(종가 시장가) | 합(체결 몫) |"); P("|---|---|---|---|---|---|")
    bins = [0, 0.1, 0.2, 0.5, 1, 2, 5, 100]
    for lb, z in X.groupby(pd.cut(X.p, bins), observed=True):
        P("| %s%% | %d | %+.2f%% | %.0f%% | %+.2f%% | %+.2f%% |" % (lb, len(z), z.bc.mean(), z.bf.mean() * 100, z.sc.mean(), z.bc.mean() + z.sc.mean()))
    P("\n같은 표를 **전날 거래대금** 기준으로")
    P("| 참여율(금액 ÷ 전날 거래대금) | 줄 | 매수 손해 | 매수 체결 | 매도 손해 | 합 |"); P("|---|---|---|---|---|---|")
    for lb, z in X.groupby(pd.cut(X.p1, bins), observed=True):
        P("| %s%% | %d | %+.2f%% | %.0f%% | %+.2f%% | %+.2f%% |" % (lb, len(z), z.bc.mean(), z.bf.mean() * 100, z.sc.mean(), z.bc.mean() + z.sc.mean()))
    # 어느 쪽이 손해를 더 잘 설명하나 — log p 와 손해 합의 상관
    for nm, col in (("20일 평균", "p"), ("전날", "p1")):
        z = X[[col, "bc", "sc", "bf"]].dropna()
        P("· %s 기준 상관(log 참여율 ↔ 손해 합) %.2f · (↔ 체결률) %.2f" % (nm, np.corrcoef(np.log(z[col]), z.bc + z.sc)[0, 1], np.corrcoef(np.log(z[col]), z.bf)[0, 1]))
    # 매끈한 모형: 손해 = a + b·sqrt(p) · 체결 = 1/(1 + c·p)  (p 는 20일 평균 기준 %)
    z = X[["p", "bc", "sc", "bf"]].dropna()
    A = np.c_[np.ones(len(z)), np.sqrt(z.p)]
    ab = np.linalg.lstsq(A, (z.bc + z.sc).values, rcond=None)[0]
    cs = np.linspace(0.01, 3, 300)
    c = cs[np.argmin([((1 / (1 + k * z.p) - z.bf) ** 2).sum() for k in cs])]
    P("· 맞춘 모형(20일 평균 기준 p%%): 손해 = %.2f + %.2f×√p (%%) · 체결률 = 1/(1 + %.2f×p)" % (ab[0], ab[1], c))
    return ab, c


def main():
    E = liq_of_exec()
    ab, cfill = fit(E)
    impact = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p))   # 손해는 0 아래로 안 내려간다
    fill = lambda p: 1 / (1 + cfill * p)

    import lab, feats as FT
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20", "mcap", "vm"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"]).copy()
    H["oc"] = H.oc - FT.COST
    B = H[(H.rgap <= -1.5) & (H.q_gap <= 0.20) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 1 / 3)].copy()
    B["a20"] = B.amt20 * 1e8                          # 억 → 원
    B["a1"] = B.a20 * B.vm.fillna(1)                  # 전날 거래량 배수 × 20일 평균 ≈ 전날 거래대금
    B["cap"] = B.mcap * 1e8
    B["mult"] = (-B.rgap).clip(1, 5)                  # 지금 깊이 배율
    B["per"] = np.where(B.date <= "20151231", "옛날", np.where(B.date <= "20221231", "학습", "검증"))
    # 물가·시장 크기 변화를 지우려고 크기는 그날 후보 안 순위가 아니라 **그해 유니버스 대비 배수**로 쓰면 복잡 → 날짜별 원 단위 그대로, 대신 구간은 사분위
    P("\n## B. 과거 지금 그물 건당 수익 — 크기 구간별 (비용 0.23 뒤, 각 해 안의 사분위)")
    for nm, col in (("20일 평균 거래대금", "a20"), ("전날 거래대금", "a1"), ("시총", "cap")):
        B["_q"] = B.groupby(B.date.str[:4])[col].transform(lambda s: pd.qcut(s.rank(method="first"), 4, labels=["작음", "중하", "중상", "큼"]))
        P("\n**%s**" % nm); P("| 구간 | 옛날 2005~15 | 학습 2016~22 | 검증 2023~ | 2023~ 중앙 금액 |"); P("|---|---|---|---|---|")
        for q in ("작음", "중하", "중상", "큼"):
            z = B[B._q == q]; cells = []
            for p in ("옛날", "학습", "검증"):
                w = z[z.per == p]; cells.append("%d건 · %+.2f%% · %.0f%%" % (len(w), w.oc.mean(), (w.oc > 0).mean() * 100))
            P("| %s | %s | %.1f억 |" % (q, " | ".join(cells), z[z.per == "검증"][col].median() / 1e8))

    # C. 배율 규칙 — 금액_i = 기준 × 깊이배율 × 크기배율(정규화) · 같은 자본(1년 넣는 돈 합) 비교
    P("\n## C. 금액 배율 규칙 비교 — 같은 자본(넣은 돈 합 같게) · 체결 손해·못 산 몫 반영 · 2016~")
    P("크기배율 = (그 종목 값 ÷ 그날 후보 중앙값)^a, 0.3~3배로 자름 → 평균 1이 되게 다시 맞춤. 손익 = Σ 금액×체결률×(수익 − 손해).")
    S = B[B.date >= "20160101"].copy()
    yrs = H[H.date >= "20160101"].date.nunique() / 250
    P("| 기준 금액(1배) | 규칙 | 1년 손익(만원) | 넣은 돈 대비 | 평균 체결 | 평균 손해 | 2016~22 1년 | 2023~ 1년 |"); P("|---|---|---|---|---|---|---|---|")
    rules = [("균등(깊이만)", None, 0)] + [("%s^%.2f" % (nm, a), col, a) for nm, col in (("20일 거래대금", "a20"), ("전날 거래대금", "a1"), ("시총", "cap")) for a in (-0.5, -0.25, 0.25, 0.5, 0.75, 1.0, 1.5)]
    for base in (30, 50, 100, 150):
        best = None
        for nm, col, a in rules:
            if col is None: m = np.ones(len(S))
            else:
                rel = S[col] / S.groupby("date")[col].transform("median")
                m = (rel.fillna(1.0) ** a).clip(0.3, 3).values
            m = m * S.mult.values.sum() / (S.mult.values * m).sum()   # 넣는 돈 합이 균등과 같게
            amt = base * 1e4 * S.mult.values * m
            p = amt / S.a20.values * 100
            f, im = fill(p), impact(p)
            pnl = amt * f * (S.oc.values - im) / 100
            v = S.date.values >= "20230101"
            yr2 = H[H.date >= "20230101"].date.nunique() / 250; yr1 = yrs - yr2
            row = (pnl.sum() / yrs / 1e4, pnl.sum() / (amt.sum()) * 100, np.average(f, weights=amt) * 100, np.average(im, weights=amt * f), pnl[~v].sum() / yr1 / 1e4, pnl[v].sum() / yr2 / 1e4)
            P("| %d만 | %s | %+.0f | %+.2f%% | %.0f%% | %+.2f%% | %+.0f | %+.0f |" % ((base, nm) + row))
            if best is None or row[0] > best[1][0]: best = (nm, row)
        P("| %d만 | **가장 나은 것: %s** | | | | | | |" % (base, best[0]))
    (BASE / "research" / "cache" / "t1_size_liq_1021.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
