# -*- coding: utf-8 -*-
"""[장전 되돌림](T5) 규칙 자체 다시 실측 — 2026-11-12 사용자 "장전 되돌림 규칙 자체 다시 실측해봐".
실전(11-04~) 19왕복 연구 기준 건당 -1.74% — 과거 369일(+1.7~1.9)과 너무 다르다. 운인지, 규칙이 낡았는지, 실전이 연구와 다른지.

자료
  과거: C:/temp/kp/pmrev5_panel_1103.pkl (토스 장전 1분봉 2025-04~2026-10, 369일 · tm=840 신호) — 규칙 그대로:
        rpre(08:40 장전가 어제 통합 종가 대비 − 시장 중앙) ≤ -3 · cum(08:01~08:40 누적 거래대금) ≤ 10.19억 · 그날 rpre 순위 ≤ 4(두꺼운 종목도 셈)
        수익: r_vwhs(08:41~45 VWAP − 반 호가 → KRX 시가, 연구 기준) · r_hi(그 5분 최고가에 샀다고 — 가장 나쁜 값) · 비용 0.23 뒤
  앞으로(실전 뒤): data/nxtpre/log.csv (11-04~, -2%p↓ 후보 전부 채점 — 1호가 기준·VWAP 기준)
나눠 보기: 기간(학습 2025 · 2026 상반기 · 2026-07~10) · 달 · 시장 장전 움직임 · 그날 신호 수 · 순위 · 깊이 · 요일
    python research/t5_recheck_1112.py
"""
import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

CUM_MAX, REL, RANK_MAX = 1_019_060_000, -3.0, 4
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def st(Z, col="r_vwhs"):
    if Z is None or not len(Z): return None
    d = Z.groupby("d")[col].mean()
    sd = d.std(ddof=1) if len(d) > 1 else np.nan
    return dict(n=len(Z), days=len(d), mean=Z[col].mean(), win=(Z[col] > 0).mean() * 100, dmean=d.mean(),
                t=d.mean() / sd * math.sqrt(len(d)) if sd and sd > 0 else 0.0, dpos=(d > 0).mean() * 100)


def row(name, Z, cols=("r_vwhs", "r_hi")):
    a = st(Z, cols[0]); b = st(Z, cols[1]) if len(cols) > 1 else None
    if not a: P("| %s | 0 | | | | | |" % name); return
    P("| %s | %d건 · %d일 | %+.2f%% | %.0f%% | %+.2f%% (t %.1f · 플러스 날 %.0f%%) | %s |" % (
        name, a["n"], a["days"], a["mean"], a["win"], a["dmean"], a["t"], a["dpos"], ("%+.2f%%" % b["mean"]) if b else "-"))


def head():
    P("| 판 | 표본 | 건당(연구 기준) | 승률 | 날 바구니 | 최고가에 샀다면 |"); P("|---|---|---|---|---|---|")


def main():
    S = pd.read_pickle(r"C:\temp\kp\pmrev5_panel_1103.pkl")
    S = S[(S.tm == 840) & S.rpre.notna() & S.o.notna() & (S.pre.abs() < 30)].copy()
    S["rk"] = S.groupby("d").rpre.rank(method="first")
    S["mkt"] = S.pre - S.rpre                                              # 그날 시장(NXT 종목 장전 중앙) 움직임
    base = S[(S.rpre <= REL) & (S.cum <= CUM_MAX)]
    R = base[base.rk <= RANK_MAX].copy()
    R["nsig"] = R.d.map(base.groupby("d").size())
    nd = S.d.nunique()
    P("과거 %d일(%s~%s) · 규칙 신호(-3%%p·얇음) %d건 · 순위 4 안 %d건(신호 날 %d일)\n" % (nd, S.d.min(), S.d.max(), len(base), len(R), R.d.nunique()))

    P("## 1. 과거 — 기간별 (지금 규칙: -3%p·얇음·순위 4 안)\n"); head()
    row("전체 369일", R)
    for nm, a, b in (("학습 2025-04~12", "20250401", "20251231"), ("2026-01~06", "20260101", "20260630"), ("2026-07~10", "20260701", "20261031")):
        row(nm, R[(R.d >= a) & (R.d <= b)])
    row("(참고) 순위 제한 없이 전부", base)
    P("\n달별(순위 4 안): " + " · ".join("%s %+.2f(%d)" % (m[2:], g.r_vwhs.mean(), len(g)) for m, g in R.groupby(R.d.str[:6])))

    P("\n## 2. 과거 — 그날 시장 장전 움직임별\n"); head()
    for nm, lo, hi in (("시장 -3%↓ (폭락 장전)", -99, -3), ("-3 ~ -1%", -3, -1), ("-1 ~ +1%", -1, 1), ("+1%↑", 1, 99)):
        row(nm, R[(R.mkt > lo) & (R.mkt <= hi)])
    P("\n## 3. 과거 — 그날 신호 수(붐비는 날)별\n"); head()
    for nm, lo, hi in (("1~2개", 0, 2), ("3~5개", 2, 5), ("6~10개", 5, 10), ("11개↑", 10, 9999)):
        row(nm, R[(R.nsig > lo) & (R.nsig <= hi)])
    P("\n## 4. 과거 — 순위·깊이별\n"); head()
    for k in (1, 2, 3, 4): row("순위 %d" % k, R[R.rk == k])
    for nm, lo, hi in (("시장 대비 -3~-4%p", -4, -3), ("-4~-5", -5, -4), ("-5~-8", -8, -5), ("-8%p↓", -99, -8)):
        row(nm, R[(R.rpre > lo) & (R.rpre <= hi)])
    P("\n요일: " + " · ".join("%s %+.2f(%d)" % ("월화수목금"[w], g.r_vwhs.mean(), len(g)) for w, g in R.groupby(pd.to_datetime(R.d).dt.weekday)))

    # ── 앞으로(실전 뒤) ──
    L = pd.read_csv(BASE / "data" / "nxtpre" / "log.csv", dtype={"날짜": str, "종목": str})
    L = L.rename(columns={"날짜": "d", "종목": "t", "어제 대비": "pre", "시장 대비": "rpre", "장전 누적 거래대금": "cum", "고름": "pick",
                          "VWAP 기준 수익": "r_vw", "1호가 기준 수익": "r_ask", "그 사이 최고가": "hi5", "KRX 시가": "o", "08:41~45 VWAP": "vw5"})
    L["mkt"] = L.pre - L.rpre
    for c in ("r_vw", "r_ask", "hi5", "o", "cum", "rpre"): L[c] = pd.to_numeric(L[c], errors="coerce")
    L["r_hi"] = (L.o / L.hi5 - 1) * 100 - 0.23
    L["rk"] = L.groupby("d").rpre.rank(method="first")
    F = L[(L.rpre <= REL) & (L.cum <= CUM_MAX) & L.r_vw.notna()]
    F4 = F[F.rk <= RANK_MAX]
    P("\n## 5. 실전 뒤(%s~%s, %d일) — 같은 규칙으로 후보 전부 채점(돈·주문과 무관)\n" % (L.d.min(), L.d.max(), L.d.nunique()))
    P("| 판 | 표본 | 건당(VWAP) | 승률 | 날 바구니 | 최고가에 샀다면 |"); P("|---|---|---|---|---|---|")
    for nm, Z in (("순위 4 안", F4), ("순위 제한 없이(-3%p·얇음)", F)):
        a, b = st(Z, "r_vw"), st(Z, "r_hi")
        if a: P("| %s | %d건 · %d일 | %+.2f%% | %.0f%% | %+.2f%% (t %.1f · 플러스 날 %.0f%%) | %+.2f%% |" % (nm, a["n"], a["days"], a["mean"], a["win"], a["dmean"], a["t"], a["dpos"], b["mean"] if b else float("nan")))
    P("\n날짜별(실전 뒤, 순위 4 안 · 전부): 시장 장전 / 신호 수 / VWAP 건당")
    for d, g in L.groupby("d"):
        f, f4 = F[F.d == d], F4[F4.d == d]
        P("  %s 시장 %+.2f%% · 신호 %d · 순위4 %s · 전부 %s" % (d, g.mkt.median(), len(f), ("%+.2f%%(%d)" % (f4.r_vw.mean(), len(f4))) if len(f4) else "-",
                                                         ("%+.2f%%" % f.r_vw.mean()) if len(f) else "-"))
    # 과거에서 같은 날 수 창이 이만큼 나쁠 확률
    dd = R.groupby("d").r_vwhs.mean()
    k = F4.d.nunique()
    if k:
        obs = F4.groupby("d").r_vw.mean().mean()
        roll = dd.rolling(k).mean().dropna()
        P("\n과거 신호 날 %d개짜리 창 중 날 바구니 평균이 실전 뒤 값(%+.2f%%) 이하인 몫: %.1f%% (과거 %d개 창)" % (k, obs, (roll <= obs).mean() * 100, len(roll)))
        mk = F4.groupby("d").mkt.median()
        P("실전 뒤 신호 날 시장 장전: " + " · ".join("%s %+.1f%%" % (d[4:], v) for d, v in mk.items()))
        sim = R[R.mkt <= mk.max() + 0.5] if len(mk) else R
        P("과거에서 시장 장전이 그 정도(≤ %+.1f%%)였던 날만: 건당 %+.2f%% · 날 바구니 %+.2f%% (%d일)" % (mk.max() + 0.5, sim.r_vwhs.mean(), sim.groupby("d").r_vwhs.mean().mean(), sim.d.nunique()))
    (ROOT / "t5_recheck_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()


def crowd():
    """붐비는 날(그날 규칙 신호 수) 거르기 — 돈 기준(100만·체결 손해: 장중 매수라 접속매매 모형 0.389+2.275√p, impact_fit cont)."""
    S = pd.read_pickle(r"C:\temp\kp\pmrev5_panel_1103.pkl")
    S = S[(S.tm == 840) & S.rpre.notna() & S.o.notna() & (S.pre.abs() < 30)].copy()
    S["rk"] = S.groupby("d").rpre.rank(method="first")
    B = S[(S.rpre <= REL) & (S.cum <= CUM_MAX)].copy(); B["nsig"] = B.d.map(B.groupby("d").size())
    R = B[B.rk <= RANK_MAX]
    nd = S.d.nunique(); yr = nd / 250
    a20 = R.val20.fillna(R.val20.median())
    P("\n## 6. 붐비는 날 거르기 — 하루 신호 수 문턱 (순위 4 안 · 100만 · 체결 손해 접속매매 모형)\n")
    P("| 판 | 건수 | 건당(연구 기준) | 건당(체결 손해 뒤) | 1년 손익(100만) | 2026-07~10만 건당 | 최악의 날 |"); P("|---|---|---|---|---|---|---|")
    for nm, cap in (("지금(거르기 없음)", 9999), ("신호 10개↑ 날 쉼", 10), ("신호 6개↑ 날 쉼", 6), ("신호 4개↑ 날 쉼", 4)):
        Z = R[R.nsig < cap]
        p = 100e4 / a20[Z.index] * 100
        net = Z.r_vwhs - np.maximum(0, 0.389 + 2.275 * np.sqrt(p))
        fill = 1 / (1 + 3.0 * p)
        dp = (100e4 * fill * net / 100).groupby(Z.d).sum()
        late = Z[Z.d >= "20260701"]
        P("| %s | %d | %+.2f%% | %+.2f%% | %+.0f만 | %+.2f%% | %+.0f만 |" % (nm, len(Z), Z.r_vwhs.mean(), (net * fill).sum() / fill.sum(),
                                                                     dp.sum() / yr / 1e4, late.r_vwhs.mean(), dp.min() / 1e4))


if __name__ == "__main__" and "crowd" in sys.argv:
    crowd()
