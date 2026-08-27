"""224일선(1년선) 스윙 전략 실측
- 오랜 기간 224선 아래(겨울) → 224선 강하게 돌파(봄) 시점 공략
- 돌파 직후 매수 vs 돌파 후 눌림목 매수 비교
- '짧게 익절' 검증: 목표 3/5/7/10% vs 추세 보유
- '많이 오른 자리(여름)는 위험' 검증: 224선 이격도 구간별 성과
사용: python ma224_test.py [종목수]
"""
import io, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
N_UNIV = int(sys.argv[1]) if len(sys.argv) > 1 else 500
CACHE = BASE / "data" / "ohlc500.pkl"

lst = fdr.StockListing("KOSPI")
lst = lst[lst["Code"].str.endswith("0")].sort_values("Amount", ascending=False).head(N_UNIV)
codes = list(lst["Code"])
cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
old = pickle.load(open(BASE / "data" / "macd_ohlc.pkl", "rb")) if (BASE / "data" / "macd_ohlc.pkl").exists() else {}
cache.update({k: v for k, v in old.items() if k not in cache})
new = [c for c in codes if c not in cache]
print(f"신규 다운로드 {len(new)}종목", file=sys.stderr)
for i, c in enumerate(new):
    try: cache[c] = fdr.DataReader(c, "2021-06-01", "2026-08-28")
    except Exception: cache[c] = pd.DataFrame()
    if i % 50 == 0: pickle.dump(cache, open(CACHE, "wb")); print(f"  {i}/{len(new)}", file=sys.stderr)
pickle.dump(cache, open(CACHE, "wb"))

def prep(d):
    d = d.copy()
    d["ma224"] = d["Close"].rolling(224).mean()
    d["e20"] = d["Close"].ewm(span=20, adjust=False).mean()
    d["e60"] = d["Close"].ewm(span=60, adjust=False).mean()
    d["vma20"] = d["Volume"].rolling(20).mean()
    return d

P = {c: prep(cache[c]) for c in codes if c in cache and cache[c] is not None and len(cache[c]) >= 320}
print(f"분석 종목 {len(P)}", file=sys.stderr)
START = pd.Timestamp("2023-01-01")

WINTER = 60        # 224선 아래 겨울 최소 봉수(직전 120봉 중)
def signals():
    brk, pull = [], []
    for code, d in P.items():
        C, H, L, V = d["Close"].values, d["High"].values, d["Low"].values, d["Volume"].values
        MA, E20, VMA = d["ma224"].values, d["e20"].values, d["vma20"].values
        i0 = max(np.searchsorted(d.index, START), 230)
        last_b = last_p = -99
        for i in range(i0, len(d) - 1):
            if np.isnan(MA[i]) or MA[i] <= 0: continue
            below = (C[i - 120:i] < MA[i - 120:i]).sum()      # 최근 120봉 중 224선 아래였던 봉수 = 겨울
            # ---- 돌파(봄) ----
            if i - last_b >= 20 and below >= WINTER and C[i] > MA[i] and C[i - 1] <= MA[i - 1] \
               and V[i] >= 1.5 * VMA[i] and C[i] / C[i - 1] - 1 >= 0.02:     # 강하게 = 거래량 1.5배 + 당일 +2%
                o = d["Open"].iloc[i + 1]
                stop = min(L[max(0, i - 5):i + 1])
                if o > stop > 0:
                    brk.append(dict(code=code, i=i + 1, date=d.index[i], o=o, stop=stop, ma=MA[i],
                                    gap=(o / MA[i] - 1) * 100, y=d.index[i].year, bi=i))
                    last_b = i
            # ---- 눌림목 ----
            # 최근 40봉 내 돌파 이력 + 현재 224선 위 + 20EMA 근처로 조정 후 반등
            if i - last_p >= 15 and C[i] > MA[i]:
                crossed = any(C[k] > MA[k] and C[k - 1] <= MA[k - 1] and (C[k - 120:k] < MA[k - 120:k]).sum() >= WINTER
                              for k in range(max(i0, i - 40), i))
                if crossed and L[i - 1] <= E20[i - 1] * 1.03 and C[i] > C[i - 1] and C[i] > E20[i]:
                    o = d["Open"].iloc[i + 1]
                    stop = min(L[max(0, i - 5):i + 1])
                    if o > stop > 0:
                        pull.append(dict(code=code, i=i + 1, date=d.index[i], o=o, stop=stop, ma=MA[i],
                                         gap=(o / MA[i] - 1) * 100, y=d.index[i].year, bi=i))
                        last_p = i
    return brk, pull

BRK, PULL = signals()
print(f"돌파 {len(BRK)}건 · 눌림목 {len(PULL)}건", file=sys.stderr)

def run(s, tp=None, sl=None, ema=None, trail=None, maxbars=120):
    d = P[s["code"]]; i0, o, stop = s["i"], s["o"], s["stop"]
    if sl: stop = o * (1 - sl / 100)
    hi = o
    for k in range(i0, min(i0 + maxbars, len(d))):
        lo_, hi_, cl = d["Low"].iloc[k], d["High"].iloc[k], d["Close"].iloc[k]
        if lo_ <= stop: return ((stop / o - 1) * 100, "손절")
        if tp and hi_ >= o * (1 + tp / 100): return (tp, "익절")
        if trail and hi > o and lo_ <= hi * (1 - trail / 100): return ((hi * (1 - trail / 100) / o - 1) * 100, "트레일")
        hi = max(hi, hi_)
        if ema and k > i0 and cl < d[ema].iloc[k]:
            nk = min(k + 1, len(d) - 1); return ((d["Open"].iloc[nk] / o - 1) * 100, "이평이탈")
    j = min(i0 + maxbars, len(d)) - 1
    return ((d["Close"].iloc[j] / o - 1) * 100, "시간")

def stat(rs):
    r = [x[0] for x in rs if x]
    if len(r) < 15: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, med=np.median(r),
                pf=(sum(w) / abs(sum(l))) if l else 99)
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / PF {s['pf']:.2f} ({s['n']})" if s else "표본부족"

RULES = [("+3% 익절 / -5% 손절", dict(tp=3, sl=5)), ("+5% 익절 / -5% 손절", dict(tp=5, sl=5)),
         ("+7% 익절 / -7% 손절", dict(tp=7, sl=7)), ("+10% 익절 / -7% 손절", dict(tp=10, sl=7)),
         ("+5% 익절 / 변곡점 손절", dict(tp=5)), ("+10% 익절 / 변곡점 손절", dict(tp=10)),
         ("20EMA 이탈까지 보유", dict(ema="e20")), ("60EMA 이탈까지 보유", dict(ema="e60")),
         ("트레일링 10%", dict(trail=10)), ("무조건 20봉 보유", dict(maxbars=20)), ("무조건 60봉 보유", dict(maxbars=60))]

print(f"# 224일선(1년선) 스윙 전략 실측 — KOSPI 거래대금 상위 {len(P)}종목, 2023-01~2026-08\n")
print(f"조건: 최근 120봉 중 {WINTER}봉 이상 224선 아래(겨울) → 224선 돌파(거래량 1.5배 + 당일 +2% 이상)\n")
print(f"표기: 평균 / 승률 / PF (건수) · IS=2023~24, OOS=2025~26\n")

for lab, S in (("① 돌파 당일 진입 (다음날 시가)", BRK), ("② 돌파 후 눌림목 진입 (20EMA 조정 후 반등)", PULL)):
    print(f"\n## {lab} — {len(S)}건\n")
    print("| 청산 규칙 | 전체 | IS(2023~24) | OOS(2025~26) |\n|---|---|---|---|")
    for rl, kw in RULES:
        R = [(run(s, **kw), s) for s in S]
        a = stat([r for r, _ in R]); b = stat([r for r, s in R if s["y"] <= 2024]); c = stat([r for r, s in R if s["y"] >= 2025])
        print(f"| {rl} | {f(a)} | {f(b)} | {f(c)} |")

print("\n## ③ '많이 오른 자리는 위험' 검증 — 224선 이격도별 (눌림목 진입, +5% 익절/-5% 손절)\n")
print("| 224선 대비 | 건수 | 평균 | 승률 | PF |\n|---|---|---|---|---|")
for lo, hi_, lab in ((-99, 5, "0~5% (막 돌파)"), (5, 15, "5~15%"), (15, 30, "15~30%"), (30, 60, "30~60%"), (60, 999, "60% 이상 (한여름)")):
    S = [s for s in PULL if lo <= s["gap"] < hi_]
    st_ = stat([run(s, tp=5, sl=5) for s in S])
    print(f"| {lab} | {len(S)} | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| {lab} | {len(S)} | 표본부족 | | |")

print("\n## ④ 같은 조건에서 '보유기간별' 단순 수익률 (돌파 진입, 청산규칙 없음)\n")
print("| 보유 | 평균 | 승률 | 중앙값 |\n|---|---|---|---|")
for h in (5, 10, 20, 40, 60, 120):
    rs = []
    for s in BRK:
        d = P[s["code"]]; i0 = s["i"]
        if i0 + h < len(d): rs.append(((d["Close"].iloc[i0 + h] / s["o"] - 1) * 100, ""))
    st_ = stat(rs)
    print(f"| {h}봉 | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['med']:+.2f}% |" if st_ else f"| {h}봉 | - | | |")

print("\n## ⑤ 연도별 (눌림목 + '+5% 익절/-5% 손절' = 영상 취지에 가장 근접)\n")
print("| 연도 | 건수 | 평균 | 승률 | PF |\n|---|---|---|---|---|")
for y in (2023, 2024, 2025, 2026):
    st_ = stat([run(s, tp=5, sl=5) for s in PULL if s["y"] == y])
    print(f"| {y} | {st_['n']} | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| {y} | - | | | |")
