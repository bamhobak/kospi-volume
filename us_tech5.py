# -*- coding: utf-8 -*-
"""후보를 **계좌**에 넣어 본다 — 규칙 단위 통과는 절반이다.

후보: [잔잔한 급등주] — 1년 수익 120%↑ 인데 최근 60일 일간 등락 평균이 1.5% 이하.
      웹에서 모은 미국 기법 배터리(us_tech.py ~ us_tech4.py) 중 유일한 생존자다.
      Frog-in-the-Pan(정보 이산성) 계열이고, 여집합(같은 상승폭·요란한 쪽)은
      초과 -2.03 · 승률 42.3% 로 정확히 갈렸다.

왜 계좌로 재나: 규칙에서 통과해도 자리 경쟁·현금 제약에서 뒤집힌 전례가 많다
([[short-program-combo]] 5.74배 · [[stock-feargreed]] 전량 기각 · [[flow-5week]]).
그리고 [[averaging-down-test]] 에서 배웠듯 **노출을 맞추지 않은 비교는 거짓말**이다.
그래서 후보를 넣을 때 기존 규칙 비중을 줄여 **총 투입을 맞춘 판**을 따로 낸다.

현행 미장 장부 재현: [상승장 신고가](N1) · [낙폭과대](D1) · [저PBR 낙폭](D2).
  ⚠ [자사주 낙폭](N4)은 자사주 집행 이력이 최근분만 있어 21년 계좌에 못 넣는다. 빠져 있다.

    python us_tech5.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr

BASE = Path(__file__).parent; SEEDS = 30
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
dates = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(dates)}
K["di"] = K.date.map(ADI).astype(np.int32)
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
K["up60"] = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60)))
UP = K.up60 == True; DN = K.up60 == False
log("지표 계산 중")
TK = K.ticker
BASE3 = pd.Series(True, index=K.index)                      # 위에서 이미 걸렀다
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI_N = (K.amt_q >= 0.6).fillna(False)                      # 거래대금 상위 40%
U2 = K.amt20.fillna(0) >= 2.0
K["r1"] = K.groupby(TK, sort=False).close.pct_change() * 100
K["absr"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
# [상승장 신고가] 원본 재현 — 52주 고점 -5% 안에 오늘 처음 들어온 날 · 조용한 진입
_within = (K.fromhi >= -5).fillna(False)
_seen = (_within.groupby(TK).shift(1).fillna(False).astype(bool)
         .groupby(TK).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
_a20 = K.groupby(TK, sort=False).volume.transform(lambda s: s.shift(3).rolling(20).mean())
_remo = K.vm3 / _a20 * 100
N1 = (UNI_N & UP & _within & ~_seen & (_remo <= 100)).fillna(False)
D1 = (U2 & DN & (K.ret20 <= -30) & (K.su1 >= 2) & (K.u <= -10)
      & (K["부채비율"].isna() | (K["부채비율"] <= 200))).fillna(False)
D2 = (U2 & DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10)).fillna(False)
FROG = (UNI_N & K.multi & (K.ret250 >= 120) & (K.absr <= 1.5)).fillna(False)
FROG150 = (UNI_N & K.multi & (K.ret250 >= 150) & (K.absr <= 1.5)).fillna(False)

RULES = {
    "N1":  dict(name="상승장 신고가", hold=40, cond=N1),
    "D1":  dict(name="낙폭과대", hold=20, cond=D1),
    "D2":  dict(name="저PBR 낙폭", hold=40, cond=D2),
    "FG":  dict(name="잔잔한 급등주 120", hold=40, cond=FROG),
    "FG6": dict(name="잔잔한 급등주 120·60일", hold=60, cond=FROG),
    "F15": dict(name="잔잔한 급등주 150", hold=40, cond=FROG150),
}
SIG = {}
for rid, r in RULES.items():
    h = r["hold"]
    X = K[r["cond"]].dropna(subset=[f"n{h}"]).copy(); X = X[X.buy > 0]
    X["ret"] = X[f"n{h}"].astype(float); X["rid"] = rid; X["hold"] = h
    X = X.sort_values("di"); keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    SIG[rid] = X.loc[keep][["date", "ticker", "hold", "rid", "ret", "di"]].reset_index(drop=True)
    log(f"  {rid} {r['name']:<18} {len(SIG[rid]):>6,}건 · 하루 {len(SIG[rid])/len(dates):.2f}건")


def build(alloc):
    """alloc: {rid: (pct, mx)} — 종목당 투입비중(%)과 규칙별 동시보유 상한."""
    out = []
    for rid, (pct, mx) in alloc.items():
        z = SIG[rid].copy(); z["pct"] = pct; z["mx"] = mx; out.append(z)
    return pd.concat(out, ignore_index=True).sort_values("di").reset_index(drop=True)


def sim(S, ds, seed, cash_cap=1.0):
    """같은 날 여러 신호가 오면 무작위 순서로 자리를 채운다(시드마다 다른 순서)."""
    rng = np.random.default_rng(seed); nav, held = 1.0, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(v[2] for v in held.values()) / 100)
        gg = byd.get(d)
        if gg is None: continue
        for r in gg.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            k = (r.rid, r.ticker)
            if k in held: continue
            if sum(1 for x in held if x[0] == r.rid) >= r.mx: continue
            if sum(v[2] for v in held.values()) / 100 + r.pct / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100, r.pct)
    for v in held.values(): nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


PER = [("전구간 2005~26", "20050101"), ("학습 2016~22", "20160101"), ("검증 2023~26", "20230101")]
def run(nm, alloc):
    S = build(alloc)
    row = ""
    for lab, lo in PER:
        hi = "20221231" if lab.startswith("학습") else "20991231"
        ds = [d for d in dates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        row += (f"{np.median([x[0] for x in R]):>10.2f}배{np.median([x[1] for x in R]):>6.0f}%"
                f"{np.median([x[2] for x in R])*100:>5.0f}%")
    print(f"  {nm:<36}{row}")


W = 132
print("\n" + "=" * W)
print("① 후보를 얹으면 계좌가 좋아지는가 (시드 30 · 중앙값 · 배수/최대낙폭/평균노출)")
print("=" * W)
print(f"  {'구성':<36}" + "".join(f"{lab:>21}" for lab, _ in PER))
CUR = {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3)}
run("A 현행 3규칙 (N1·D1·D2)", CUR)
run("B A + 잔잔한급등 120 (5%×3)", {**CUR, "FG": (5, 3)})
run("C A + 잔잔한급등 120 (10%×3)", {**CUR, "FG": (10, 3)})
run("D A + 잔잔한급등 150 (10%×3)", {**CUR, "F15": (10, 3)})
run("E A + 잔잔한급등 120·60일(10%×3)", {**CUR, "FG6": (10, 3)})
print()
print("  ── 노출을 맞춘 판 — N1 비중을 줄여 총 투입을 A 와 같게 ──")
run("F N1 10→5% · 잔잔한급등 120 5%×3", {"N1": (5, 4), "D1": (5, 3), "D2": (5, 3), "FG": (5, 3)})
run("G N1 10→5% · 잔잔한급등 150 5%×3", {"N1": (5, 4), "D1": (5, 3), "D2": (5, 3), "F15": (5, 3)})
print()
print("=" * W)
print("② 노출을 진짜로 맞춘다 — 같은 투입이면 N1 에 더 넣는 게 나은가, 후보를 넣는 게 나은가")
print("=" * W)
# 위 F·G 는 노출 맞춤이 아니었다. 후보 신호가 하루 0.21건뿐이라 N1 에서 뺀 자리를
# 못 채워 노출이 43%→34% 로 **줄었다**. 줄어든 계좌가 진 건 당연하다.
# 그래서 A 쪽 비중을 올려 노출을 B~E 와 같은 높이로 맞춘 뒤 나란히 놓는다.
print(f"  {chr(39)}구성{chr(39):<32}" + "".join(f"{lab:>21}" for lab, _ in PER))
CAND = [
 ("A  N1 10%x4 (기준)", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3)}),
 ("A+ N1 10%x5", {"N1": (10, 5), "D1": (5, 3), "D2": (5, 3)}),
 ("A+ N1 12%x5", {"N1": (12, 5), "D1": (5, 3), "D2": (5, 3)}),
 ("A+ N1 10%x6", {"N1": (10, 6), "D1": (5, 3), "D2": (5, 3)}),
 ("A+ N1 12%x6", {"N1": (12, 6), "D1": (5, 3), "D2": (5, 3)}),
 ("A+ N1 10%x8", {"N1": (10, 8), "D1": (5, 3), "D2": (5, 3)}),
 ("B  + 잔잔120 5%x3", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG": (5, 3)}),
 ("C  + 잔잔120 10%x3", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG": (10, 3)}),
 ("E  + 잔잔120·60일 10%x3", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG6": (10, 3)}),
 ("E+ + 잔잔120·60일 10%x5", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG6": (10, 5)}),
]
for nm, al in CAND: run(nm, al)
print("  → 노출(세 번째 숫자)이 비슷한 줄끼리 배수를 견줘야 한다.")

print()
print("  ── 단독 — 후보만으로는 ──")
run("H 잔잔한급등 120 단독 (10%×5)", {"FG": (10, 5)})
run("I 잔잔한급등 150 단독 (10%×5)", {"F15": (10, 5)})
run("J N1 단독 (10%×4)", {"N1": (10, 4)})

print("\n" + "=" * W)
print("③ 상승장 규칙끼리 겹치는가 — 자리를 나눠 쓰면 분산이 아니라 집중이다")
print("=" * W)
a = SIG["N1"].assign(ym=lambda z: z.date.str[:6]).groupby("ym").ret.mean()
for rid in ("FG", "F15"):
    b = SIG[rid].assign(ym=lambda z: z.date.str[:6]).groupby("ym").ret.mean()
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    ov = len(set(zip(SIG["N1"].date, SIG["N1"].ticker)) & set(zip(SIG[rid].date, SIG[rid].ticker)))
    print(f"  N1 vs {RULES[rid]['name']:<20} 월별 상관 {j.corr().iloc[0,1]:+.2f} "
          f"({len(j)}개월) · 같은 날 같은 종목 {ov}건 ({ov/len(SIG[rid])*100:.1f}%)")
print("  → [[us-market-character-n1]] 에서 N2 를 뺀 이유가 상관 0.80 이었다. 그 문턱으로 본다.")
