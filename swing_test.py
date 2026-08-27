"""스윙 매매(지지 되돌림 + 5분할 매수) 실측
A. 120일선 지지 매수 — 단일 매수 vs 5분할 매수
B. 이전 저항(전고점) 지지전환 매수
청산: 전고점 도달 / 2~3개월 분할매도 / 고정보유
사용: python swing_test.py
"""
import io, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
cache = pickle.load(open(BASE / "data" / "ohlc500.pkl", "rb"))

def prep(d):
    d = d.copy()
    d["ma120"] = d["Close"].rolling(120).mean()
    d["ma20"] = d["Close"].rolling(20).mean()
    d["vma20"] = d["Volume"].rolling(20).mean()
    return d

P = {c: prep(d) for c, d in cache.items() if d is not None and len(d) >= 320}
print(f"종목 {len(P)}", file=sys.stderr)
START = pd.Timestamp("2023-01-01")
PIVOT = 5

def swing_highs(H, L=PIVOT):
    return [(i + L, i, H[i]) for i in range(L, len(H) - L) if H[i] == max(H[i - L:i + L + 1])]

# ---------------- 신호 ----------------
def signals():
    A, B = [], []
    for code, d in P.items():
        H, L, C, V = d["High"].values, d["Low"].values, d["Close"].values, d["Volume"].values
        MA, MA20, VMA = d["ma120"].values, d["ma20"].values, d["vma20"].values
        sh = swing_highs(H)
        i0 = max(np.searchsorted(d.index, START), 130)
        lastA = lastB = -99
        for i in range(i0, len(d) - 1):
            if np.isnan(MA[i]) or MA[i] <= 0: continue
            # 최근 60봉 전고점 = 목표
            prev_hi = H[max(0, i - 60):i].max()
            # ---- A. 120일선 지지 ----
            if i - lastA >= 20:
                above = (C[i - 40:i] > MA[i - 40:i]).mean()          # 최근 40봉 대부분 120선 위 = 상승추세 유지
                touched = L[i] <= MA[i] * 1.02                        # 120선 ±2% 접촉
                held = C[i] > MA[i] * 0.99                            # 종가는 120선 부근 이상 유지
                fell = C[i] / H[max(0, i - 20):i].max() - 1 <= -0.07  # 직전 고점 대비 7% 이상 조정 (급등 추격 아님)
                if above >= 0.7 and touched and held and fell:
                    o = d["Open"].iloc[i + 1]
                    if o > 0 and prev_hi / o - 1 >= 0.03:
                        A.append(dict(code=code, i=i + 1, date=d.index[i], o=o, ma=MA[i], target=prev_hi, y=d.index[i].year))
                        lastA = i
            # ---- B. 이전 저항 → 지지 전환 ----
            if i - lastB >= 20:
                cands = [v for (t, j, v) in sh if t <= i - 5 and i - j <= 120 and v < C[max(0, i - 20):i].max()]
                if cands:
                    lvl = max([v for v in cands if v <= C[i] * 1.03] or [0])
                    if lvl > 0 and L[i] <= lvl * 1.02 and C[i] > lvl * 0.99 and C[i] / H[max(0, i - 20):i].max() - 1 <= -0.05:
                        o = d["Open"].iloc[i + 1]
                        if o > 0 and prev_hi / o - 1 >= 0.03:
                            B.append(dict(code=code, i=i + 1, date=d.index[i], o=o, ma=lvl, target=prev_hi, y=d.index[i].year))
                            lastB = i
    return A, B

A, B = signals()
print(f"120일선 지지 {len(A)}건 · 저항전환 {len(B)}건", file=sys.stderr)

# ---------------- 청산 ----------------
def single(s, exit_mode, stop_pct=10, maxbars=60, split_sell=None):
    """단일 매수. exit_mode: 'target'(전고점) / 'time'(만기) """
    d = P[s["code"]]; i0, o = s["i"], s["o"]
    stop = o * (1 - stop_pct / 100)
    for k in range(i0, min(i0 + maxbars, len(d))):
        if d["Low"].iloc[k] <= stop: return ((stop / o - 1) * 100, "손절")
        if exit_mode == "target" and d["High"].iloc[k] >= s["target"]:
            return ((s["target"] / o - 1) * 100, "전고점")
    j = min(i0 + maxbars, len(d)) - 1
    return ((d["Close"].iloc[j] / o - 1) * 100, "만기")

def split5(s, steps=(0, 3, 6, 9, 12), stop_pct=20, maxbars=60, exit_mode="target"):
    """5분할: 첫 진입 후 -3/-6/-9/-12%마다 1/5씩 추가. 반환 (평단수익률, 전체자금수익률, 사유, 투입비율)"""
    d = P[s["code"]]; i0, o = s["i"], s["o"]
    prices = [o]; filled = 1
    hard = o * (1 - stop_pct / 100)
    for k in range(i0, min(i0 + maxbars, len(d))):
        lo, hi = d["Low"].iloc[k], d["High"].iloc[k]
        while filled < 5 and lo <= o * (1 - steps[filled] / 100):
            prices.append(o * (1 - steps[filled] / 100)); filled += 1
        avg = np.mean(prices)
        if lo <= hard:
            r = (hard / avg - 1) * 100
            return (r, r * filled / 5, "손절", filled / 5)
        if exit_mode == "target" and hi >= s["target"]:
            r = (s["target"] / avg - 1) * 100
            return (r, r * filled / 5, "전고점", filled / 5)
    j = min(i0 + maxbars, len(d)) - 1
    avg = np.mean(prices); r = (d["Close"].iloc[j] / avg - 1) * 100
    return (r, r * filled / 5, "만기", filled / 5)

def split_sell(s, sell_bars=(20, 40, 60), stop_pct=15):
    """2~3개월 분할 매도: 20/40/60봉에 1/3씩 종가 매도"""
    d = P[s["code"]]; i0, o = s["i"], s["o"]
    stop = o * (1 - stop_pct / 100); got = []; rem = 3
    for k in range(i0, min(i0 + 61, len(d))):
        if d["Low"].iloc[k] <= stop:
            got += [(stop / o - 1) * 100] * rem; rem = 0; break
        if k - i0 in sell_bars and rem > 0:
            got.append((d["Close"].iloc[k] / o - 1) * 100); rem -= 1
    if rem > 0:
        j = min(i0 + 60, len(d)) - 1
        got += [(d["Close"].iloc[j] / o - 1) * 100] * rem
    return (np.mean(got), "분할매도")

def stat(rs):
    r = [x[0] for x in rs if x]
    if len(r) < 15: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, med=np.median(r),
                pf=(sum(w) / abs(sum(l))) if l else 99)
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / PF {s['pf']:.2f} ({s['n']})" if s else "표본부족"

print("# 스윙 매매(지지 되돌림 + 분할매수) 실측 — KOSPI 거래대금 상위 492종목, 2023-01~2026-08\n")
print("표기: 평균 / 승률 / PF (건수) · IS=2023~24, OOS=2025~26\n")

for lab, S in (("A. 120일선 지지 매수", A), ("B. 이전 저항 → 지지 전환 매수", B)):
    print(f"\n## {lab} — {len(S)}건\n")
    print("| 매수·청산 방식 | 전체 | IS(2023~24) | OOS(2025~26) |\n|---|---|---|---|")
    runs = [("단일매수 · 전고점 익절 / -10% 손절 / 60봉", lambda s: single(s, "target", 10, 60)),
            ("단일매수 · 전고점 익절 / -7% 손절", lambda s: single(s, "target", 7, 60)),
            ("단일매수 · 60봉 보유(익절없음) / -10% 손절", lambda s: single(s, "time", 10, 60)),
            ("단일매수 · 2~3개월 분할매도(20/40/60봉)", lambda s: split_sell(s)),
            ("5분할매수 · 전고점 익절 (평단 기준)", lambda s: (split5(s)[0], split5(s)[2])),
            ("5분할매수 · 전고점 익절 (전체자금 기준)", lambda s: (split5(s)[1], split5(s)[2])),
            ("5분할매수 · 60봉 보유 (평단 기준)", lambda s: (split5(s, exit_mode="time")[0], "만기")),
            ]
    for rl, fn in runs:
        R = [(fn(s), s) for s in S]
        a = stat([r for r, _ in R]); b = stat([r for r, s in R if s["y"] <= 2024]); c = stat([r for r, s in R if s["y"] >= 2025])
        print(f"| {rl} | {f(a)} | {f(b)} | {f(c)} |")
    # 분할 상세
    sp = [split5(s) for s in S]
    print(f"\n분할 소진: " + " · ".join(f"{int(x*5)}차 {sum(1 for y in sp if abs(y[3]-x)<1e-9)}건({sum(1 for y in sp if abs(y[3]-x)<1e-9)/len(sp)*100:.0f}%)" for x in (0.2, 0.4, 0.6, 0.8, 1.0)))
    hows = pd.Series([x[2] for x in sp]).value_counts()
    print("청산 사유(5분할): " + " · ".join(f"{k} {v}건({v/len(sp)*100:.0f}%)" for k, v in hows.items()))
    print(f"평균 목표수익(전고점까지 거리): {np.mean([(s['target']/s['o']-1)*100 for s in S]):.1f}%")
    print(f"\n연도별 (단일매수·전고점 익절/-10% 손절)\n\n| 연도 | 건수 | 평균 | 승률 | PF |\n|---|---|---|---|---|")
    for y in (2023, 2024, 2025, 2026):
        st_ = stat([single(s, "target", 10, 60) for s in S if s["y"] == y])
        print(f"| {y} | {st_['n']} | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| {y} | - | | | |")

print("\n## 참고: 손절 폭별 (A 120일선 지지, 단일매수·전고점 익절)\n")
print("| 손절 | 전체 | 승률 | PF |\n|---|---|---|---|")
for sp_ in (5, 7, 10, 15, 20):
    st_ = stat([single(s, "target", sp_, 60) for s in A])
    print(f"| -{sp_}% | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| -{sp_}% | - | | |")
