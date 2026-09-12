# -*- coding: utf-8 -*-
"""**미장 상승장 20일 후보를 계좌로 판정** (2026-09-13).

2단계에서 나온 후보: 상승 국면 · **1년 평균 거래대금 상위20%(a240)** + 고점 근처 +
중기상승 · 20일 보유 · **N1 이 잡는 것 제외** → 초과 +1.32 · 절삭Δ +0.77 · 학CI +0.97.

규칙 단위 통과는 절반이다. 자리 경쟁·비중까지 넣은 계좌에서 기존 구성에 **얹으면 나아지는가**
가 진짜 판정이다([[contrib-not-removal]] · [[stock-feargreed]] 전례).

⚠ 연구 패널(us_scan)에는 사건형 필드(nh5·qage·bbnew)가 없다 — 그건 수집 스크립트에서만
만든다. 그래서 **N1·N5 는 여기서 사건형을 다시 만들고, N4(자사주)는 자료가 없어 뺀다.**
따라서 절대 배수는 사이트 값(14.42배)과 다르다. 보는 것은 **같은 기준선 위에서의 짝비교**다.

    python us_bull20.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 112


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
G = K.groupby("ticker", sort=False)
LIQ = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)   # 미장 유동성 상위40%
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
DN = ~UP
log(f"  {len(K):,}행 · 유동 {int(LIQ.sum()):,}")


def event(state, back=20):
    """상태형 → 사건형: 오늘 참인데 직전 back 봉은 내내 거짓이었던 날."""
    s = state.fillna(False)
    prev = s.groupby(K.ticker).transform(lambda x: x.shift(1).rolling(back, min_periods=1).max())
    return (s & (prev.fillna(0) == 0)).fillna(False)


# ── 기존 규칙 재구성 (N4 자사주는 자료 없음 → 제외) ─────────────────────────
nh_state = (K.fromhi >= -5) & (K.ret250 > 0)
# ⚠ vm3 는 **원시 3일평균 거래량**이다(비율이 아니다). 사이트 N1 의 remo(3일평균/한달평균)
#   에 해당하는 열은 rw1 이다(중앙 86.4 · 백분율). 처음에 vm3<=1.0 으로 걸어 신호가 0 이었다.
N1 = (LIQ & UP & event(nh_state) & (K.rw1 <= 100)).fillna(False)
N2 = (LIQ & DN & (K.ret20 <= -30) & (K.su1 >= 2) & (K.u <= -10)
      & (K["부채비율"].isna() | (K["부채비율"] <= 200)) & (K.amt20 >= 2)).fillna(False)
N3 = (LIQ & DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2)
      & (K.u <= -10) & (K.amt20 >= 2)).fillna(False)
n5_state = (K.ret250 >= 120) & (K.ret60 > 0) & (K.ret120 > 0) & (K.vol20 <= 1.5)
N5 = (LIQ & event(n5_state)).fillna(False)

# ── 후보 X ────────────────────────────────────────────────────────────
A = K[(LIQ & UP).fillna(False)]
q = {}
for c in ("a240", "fromhi", "ret120"):
    q[c] = A.groupby("date")[c].rank(pct=True).reindex(K.index)
X = (LIQ & UP & (q["a240"] >= 0.8) & (q["fromhi"] >= 0.6) & (q["ret120"] >= 0.6)
     & ~nh_state.fillna(False)).fillna(False)      # N1 영역(고점 -5% 이내) 제외
for _n, _c in (("N1", N1), ("N2", N2), ("N3", N3), ("N5", N5), ("X", X)):
    _s = _c & (K.date >= "20160101")
    print(f"  {_n}: 2016~ 원시 {int(_s.sum()):,}건")
log(f"신호: N1 {int(N1.sum()):,} · N2 {int(N2.sum()):,} · N3 {int(N3.sum()):,} · "
    f"N5 {int(N5.sum()):,} · X {int(X.sum()):,}")

RULES = {"N1": dict(cond=N1, hold=40, pct=10, mx=4),
         "N2": dict(cond=N2, hold=20, pct=5, mx=3),
         "N3": dict(cond=N3, hold=40, pct=5, mx=3),
         "N5": dict(cond=N5, hold=60, pct=5, mx=3),
         "X":  dict(cond=X,  hold=20, pct=5, mx=3)}


def build(ids):
    out = []
    for r in ids:
        v = RULES[r]; h = v["hold"]
        Z = K[v["cond"]].dropna(subset=[f"n{h}"]).copy()
        Z = Z[Z.buy > 0]
        Z["ret"] = Z[f"n{h}"].astype(float); Z["rid"] = r
        Z["pct"] = v["pct"]; Z["mx"] = v["mx"]; Z["hold"] = h
        Z = Z.sort_values("di"); keep, last = [], {}
        for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + h; keep.append(ix)
        out.append(Z.loc[keep][["date", "ticker", "di", "rid", "pct", "mx", "hold", "ret", "amt20"]])
    return pd.concat(out).sort_values(["di"]).reset_index(drop=True)


def sim(S, ds, cash_cap=1.0):
    """자리·비중·현금 제약. 매수 선택은 **거래대금 큰 순**(us_acct.py 와 같은 정책)."""
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(RULES[k[0]]["pct"] for k in held) / 100)
        g = byd.get(d)
        if g is None: continue
        for r in g.sort_values("amt20", ascending=False, na_position="last").itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(RULES[x[0]]["pct"] for x in held) / 100 + r.pct / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100); cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
SETS = [("기존 넷 (N1·N2·N3·N5)", ["N1", "N2", "N3", "N5"]),
        ("기존 넷 + X", ["N1", "N2", "N3", "N5", "X"]),
        ("X 혼자", ["X"])]

sec("계좌 짝비교 — ⚠ N4(자사주)는 자료가 없어 빠졌다. 절대값 말고 **차이**를 본다")
print(f"  {'구성':<24}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<24}" + "".join(f"{'자산':>10}{'낙폭':>8}{'노출':>8}" for _ in PER))
for nm, ids in SETS:
    S = build(ids); row = ""
    for _, lo, hi in PER:
        ds = [d for d in ud if lo <= d <= hi]
        nav, mdd, ex = sim(S, ds)
        row += f"{nav:>9.2f}배{mdd:>7.1f}%{ex*100:>7.0f}%"
    print(f"  {nm:<24}{row}")
log("끝")
