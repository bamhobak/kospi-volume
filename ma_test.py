"""이동평균선 3종 전략 실측
A. 고지로 대순환분석: 5/20/40 배열 스테이지1(안전상승기) + 박스 돌파
B. 쿨라메기 추세추종: 10/20/50 EMA, 선행 강한 상승 → 조정(매물대) → 거래량 동반 돌파, 짧은 손절·긴 추세
C. 프렉탈+정배열: 20/50/100 EMA 정배열 조정 시 윌리엄스 프렉탈 매수신호 → 20일선/50일선 이탈 시 청산
사용: python ma_test.py
"""
import io, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
cache = pickle.load(open(BASE / "data" / "macd_ohlc.pkl", "rb"))
kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean()
kup5 = {d: bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}
START = pd.Timestamp("2023-01-01")

def prep(d):
    d = d.copy()
    for n in (5, 20, 40): d[f"ma{n}"] = d["Close"].rolling(n).mean()
    for n in (10, 20, 50, 100): d[f"e{n}"] = d["Close"].ewm(span=n, adjust=False).mean()
    d["vma20"] = d["Volume"].rolling(20).mean()
    d["adr"] = ((d["High"] / d["Low"] - 1) * 100).rolling(20).mean()
    return d

P = {c: prep(d) for c, d in cache.items() if d is not None and len(d) >= 320}
print(f"종목 {len(P)}", file=sys.stderr)

def exit_sim(d, i0, stop, mode, trail_ema=None, rr=None, maxbars=120):
    """i0 시가 진입. mode: 'ema'=지정 EMA 종가이탈 청산, 'rr'=손익비 목표, 'trail'=고점대비 %"""
    o = d["Open"].iloc[i0]
    if o <= 0 or i0 >= len(d): return None
    tgt = o + rr * (o - stop) if rr else None
    hi = o
    for k in range(i0, min(i0 + maxbars, len(d))):
        lo_, hi_, cl = d["Low"].iloc[k], d["High"].iloc[k], d["Close"].iloc[k]
        if lo_ <= stop: return ((stop / o - 1) * 100, "손절")
        if tgt and hi_ >= tgt: return ((tgt / o - 1) * 100, "목표")
        if mode == "trail" and hi > o and lo_ <= hi * (1 - trail_ema / 100): return ((hi * (1 - trail_ema / 100) / o - 1) * 100, "트레일")
        hi = max(hi, hi_)
        if mode == "ema" and k > i0 and cl < d[trail_ema].iloc[k]:
            nk = min(k + 1, len(d) - 1)
            return ((d["Open"].iloc[nk] / o - 1) * 100, "이평이탈")
    j = min(i0 + maxbars, len(d)) - 1
    return ((d["Close"].iloc[j] / o - 1) * 100, "시간")

def collect(fn):
    out = []
    for code, d in P.items():
        i0 = np.searchsorted(d.index, START)
        out += fn(code, d, max(i0, 210))
    return out

# ---------- A. 대순환 스테이지1 + 박스돌파 ----------
def stage_of(d, i):
    a, b, c = d["ma5"].iloc[i], d["ma20"].iloc[i], d["ma40"].iloc[i]
    if np.isnan(a + b + c): return 0
    if a > b > c: return 1
    if b > a > c: return 2
    if b > c > a: return 3
    if c > b > a: return 4
    if c > a > b: return 5
    return 6

def sigA(code, d, s):
    H, C = d["High"].values, d["Close"].values
    out = []; last = -99
    for i in range(s, len(d) - 1):
        if i - last < 10: continue
        if stage_of(d, i) != 1: continue
        box_hi = H[i - 20:i].max()                       # 직전 20봉 박스 상단
        if not (C[i] > box_hi and C[i - 1] <= H[i - 21:i - 1].max()): continue
        box_lo = d["Low"].values[i - 20:i].min()
        stop = max(box_lo, d["ma20"].iloc[i])            # 박스 하단 또는 20일선
        if not (d["Open"].iloc[i + 1] > stop > 0): continue
        out.append(dict(code=code, i=i + 1, date=d.index[i], stop=stop, k5=kup5.get(d.index[i], False),
                        risk=(d["Open"].iloc[i + 1] - stop) / d["Open"].iloc[i + 1] * 100, y=d.index[i].year))
        last = i
    return out

# ---------- B. 쿨라메기 ----------
def sigB(code, d, s):
    H, L, C, V = d["High"].values, d["Low"].values, d["Close"].values, d["Volume"].values
    e10, e20, e50, vma, adr = d["e10"].values, d["e20"].values, d["e50"].values, d["vma20"].values, d["adr"].values
    out = []; last = -99
    for i in range(s, len(d) - 1):
        if i - last < 10: continue
        # 1) 선행 강한 상승: 최근 60봉 내 저점 대비 +30% 이상
        base = C[max(0, i - 60):i - 10].min()
        if base <= 0 or C[i] / base - 1 < 0.30: continue
        # 2) 조정/매물대: 최근 10봉 고가 범위가 ADR의 3배 이내로 수축 + 정배열 유지
        rng = (H[i - 10:i].max() / L[i - 10:i].min() - 1) * 100
        if np.isnan(adr[i]) or rng > max(8, adr[i] * 4): continue
        if not (e10[i] > e20[i] > e50[i]): continue
        # 3) 돌파 + 거래량
        box_hi = H[i - 10:i].max()
        if not (C[i] > box_hi and V[i] >= 1.5 * vma[i]): continue
        stop = min(L[i], e10[i])                          # 짧은 손절: 돌파일 저가/10EMA
        if not (d["Open"].iloc[i + 1] > stop > 0): continue
        out.append(dict(code=code, i=i + 1, date=d.index[i], stop=stop, k5=kup5.get(d.index[i], False),
                        risk=(d["Open"].iloc[i + 1] - stop) / d["Open"].iloc[i + 1] * 100, y=d.index[i].year))
        last = i
    return out

# ---------- C. 프렉탈 + 20/50/100 정배열 ----------
def sigC(code, d, s):
    H, L, C = d["High"].values, d["Low"].values, d["Close"].values
    e20, e50, e100 = d["e20"].values, d["e50"].values, d["e100"].values
    out = []; last = -99
    for i in range(s, len(d) - 1):
        if i - last < 10: continue
        if not (e20[i] > e50[i] > e100[i]): continue                    # 정배열
        j = i - 2                                                        # 프렉탈은 2봉 뒤 확정
        if j < 2: continue
        if not (L[j] == min(L[j - 2:j + 3])): continue                   # 윌리엄스 프렉탈 매수신호
        if abs(L[j] / e20[j] - 1) * 100 > 4: continue                    # 20EMA 부근 조정
        if C[i] <= C[j]: continue                                        # 반등 확인
        stop = L[j]
        if not (d["Open"].iloc[i + 1] > stop > 0): continue
        out.append(dict(code=code, i=i + 1, date=d.index[i], stop=stop, k5=kup5.get(d.index[i], False),
                        risk=(d["Open"].iloc[i + 1] - stop) / d["Open"].iloc[i + 1] * 100, y=d.index[i].year))
        last = i
    return out

def stat(rows):
    r = [x[0] for x in rows if x is not None]
    if len(r) < 15: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, med=np.median(r),
                pf=(sum(w) / abs(sum(l))) if l else 99, aw=np.mean(w) if w else 0, al=np.mean(l) if l else 0)
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / PF {s['pf']:.2f} ({s['n']})" if s else "표본부족"

EXITS = [("20EMA 이탈", dict(mode="ema", trail_ema="e20")), ("10EMA 이탈", dict(mode="ema", trail_ema="e10")),
         ("50EMA 이탈", dict(mode="ema", trail_ema="e50")), ("손익비 1:2", dict(mode="rr", rr=2)),
         ("손익비 1:4", dict(mode="rr", rr=4)), ("트레일링 10%", dict(mode="trail", trail_ema=10)),
         ("트레일링 15%", dict(mode="trail", trail_ema=15))]

print("# 이동평균선 3전략 실측 — KOSPI 거래대금 상위 200종목, 2023-01~2026-08\n")
print("표기: 평균 / 승률 / PF (건수) · IS=2023~24, OOS=2025~26 · 신호 다음날 시가 진입, 최대 120봉\n")
for name, fn in (("A. 고지로 대순환 — 스테이지1(정배열) + 20봉 박스 돌파", sigA),
                 ("B. 쿨라메기 — 강한 상승 후 수축 조정 + 거래량 동반 돌파", sigB),
                 ("C. 프렉탈 — 20/50/100 EMA 정배열 + 20EMA 조정 프렉탈", sigC)):
    S = collect(fn)
    print(f"\n## {name}\n\n신호 {len(S)}건 · 평균 손절폭 {np.mean([s['risk'] for s in S]):.1f}%\n")
    print("| 청산 규칙 | 전체 | IS | OOS | 코스피>5일선만 |\n|---|---|---|---|---|")
    for lab, kw in EXITS:
        R = [(exit_sim(P[s["code"]], s["i"], s["stop"], **kw), s) for s in S]
        R = [(r, s) for r, s in R if r]
        a = stat([r for r, s in R]); b = stat([r for r, s in R if s["y"] <= 2024])
        c = stat([r for r, s in R if s["y"] >= 2025]); k = stat([r for r, s in R if s["k5"]])
        print(f"| {lab} | {f(a)} | {f(b)} | {f(c)} | {f(k)} |")
    # 최적 청산으로 연도별
    best = max(EXITS, key=lambda e: (stat([r for r in (exit_sim(P[s["code"]], s["i"], s["stop"], **e[1]) for s in S) if r]) or {"pf": 0})["pf"])
    R = [(exit_sim(P[s["code"]], s["i"], s["stop"], **best[1]), s) for s in S]
    R = [(r, s) for r, s in R if r]
    print(f"\n**최고 PF 청산: {best[0]}** — 연도별\n\n| 연도 | 건수 | 평균 | 승률 | PF |\n|---|---|---|---|---|")
    for y in (2023, 2024, 2025, 2026):
        st_ = stat([r for r, s in R if s["y"] == y])
        print(f"| {y} | {st_['n']} | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| {y} | - | | | |")
    hows = {}
    for r, s in R: hows[r[1]] = hows.get(r[1], 0) + 1
    print(f"\n청산 사유: " + " · ".join(f"{k} {v}건({v/len(R)*100:.0f}%)" for k, v in sorted(hows.items(), key=lambda x: -x[1])))
    if stat([r for r, s in R]):
        st_ = stat([r for r, s in R]); print(f"평균이익 {st_['aw']:+.1f}% / 평균손실 {st_['al']:+.1f}% / 중앙값 {st_['med']:+.2f}%")
