"""되돌림 매수(분할 없음) 다각도 테스트
지지선 종류 × 조정 깊이 × 확인 방식 × 청산 규칙 × 시장/종목 필터
python pullback_test.py
"""
import io, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
cache = pickle.load(open(BASE / "data" / "ohlc500.pkl", "rb"))
kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
kup5 = {d: bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}
kup20 = {d: bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}
START = pd.Timestamp("2023-01-01"); PIVOT = 5

def prep(d):
    d = d.copy()
    for n in (20, 60, 120, 224): d[f"ma{n}"] = d["Close"].rolling(n).mean()
    d["vma20"] = d["Volume"].rolling(20).mean()
    return d
P = {c: prep(d) for c, d in cache.items() if d is not None and len(d) >= 340}
print(f"종목 {len(P)}", file=sys.stderr)

def swing_highs(H, L=PIVOT):
    return [(i + L, i, H[i]) for i in range(L, len(H) - L) if H[i] == max(H[i - L:i + L + 1])]

# ---- 신호 수집: 지지선 종류별 ----
SUPPORTS = ["ma20", "ma60", "ma120", "ma224", "resist"]
sigs = {k: [] for k in SUPPORTS}
for code, d in P.items():
    H, L, C, V = d["High"].values, d["Low"].values, d["Close"].values, d["Volume"].values
    VMA = d["vma20"].values
    MAs = {k: d[k].values for k in ("ma20", "ma60", "ma120", "ma224")}
    sh = swing_highs(H)
    i0 = max(np.searchsorted(d.index, START), 240)
    last = {k: -99 for k in SUPPORTS}
    for i in range(i0, len(d) - 1):
        hi20 = H[max(0, i - 20):i].max()
        drop = (C[i] / hi20 - 1) * 100                     # 직전 20봉 고점 대비 조정률
        prev_hi = H[max(0, i - 60):i].max()
        o = d["Open"].iloc[i + 1]
        if o <= 0: continue
        for k in SUPPORTS:
            if i - last[k] < 20: continue
            if k == "resist":
                cands = [v for (t, j, v) in sh if t <= i - 5 and i - j <= 120 and v < C[max(0, i - 20):i].max()]
                lvl = max([v for v in cands if v <= C[i] * 1.03] or [0])
                if lvl <= 0: continue
                trend_ok = C[i] > MAs["ma120"][i] if not np.isnan(MAs["ma120"][i]) else False
            else:
                lvl = MAs[k][i]
                if np.isnan(lvl) or lvl <= 0: continue
                trend_ok = (C[i - 40:i] > MAs[k][i - 40:i]).mean() >= 0.7
            if not (L[i] <= lvl * 1.02 and C[i] > lvl * 0.99): continue     # 지지선 접촉 후 지켜냄
            if not trend_ok: continue
            slope = (MAs["ma120"][i] / MAs["ma120"][i - 20] - 1) * 100 if not np.isnan(MAs["ma120"][i - 20]) else 0
            sigs[k].append(dict(code=code, i=i + 1, o=float(o), lvl=float(lvl), target=float(prev_hi),
                                drop=drop, vr=float(V[i] / VMA[i]) if VMA[i] else 1.0,
                                rebound=bool(C[i] > C[i - 1]), slope=slope,
                                k5=kup5.get(d.index[i], False), k20=kup20.get(d.index[i], False),
                                y=d.index[i].year, up_target=(prev_hi / o - 1) * 100))
            last[k] = i
for k in SUPPORTS: print(f"  {k}: {len(sigs[k])}건", file=sys.stderr)

def run(s, hold=60, sl=None, trail=None, target=False):
    d = P[s["code"]]; i0, o = s["i"], s["o"]; hi = o
    if i0 >= len(d): return None
    for k in range(i0, min(i0 + hold, len(d))):
        lo, h = d["Low"].iloc[k], d["High"].iloc[k]
        if sl and lo <= o * (1 - sl / 100): return -sl
        if trail and hi > o and lo <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        if target and h >= s["target"]: return (s["target"] / o - 1) * 100
        hi = max(hi, h)
    j = min(i0 + hold, len(d)) - 1
    return (d["Close"].iloc[j] / o - 1) * 100

def stat(rs):
    r = [x for x in rs if x is not None]
    if len(r) < 20: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, pf=(sum(w) / abs(sum(l))) if l else 99,
                med=np.median(r), worst=min(r))
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f}" if s else "-"

print("# 되돌림 매수(분할 없음) 다각도 테스트 — KOSPI 거래대금 상위 492종목, 2023~2026\n")
print("표기: 평균 / 승률 / PF · IS=2023~24, OOS=2025~26\n")

NAMES = {"ma20": "20일선", "ma60": "60일선", "ma120": "120일선", "ma224": "224일선", "resist": "이전 저항→지지"}
print("## 1) 지지선 종류 × 청산 방식 (조정 -5% 이상, 손절 -10%)\n")
print("| 지지선 | 건수 | 20봉 | 40봉 | 60봉 | 전고점익절 | 트레일15% |\n|---|---|---|---|---|---|---|")
for k in SUPPORTS:
    S = [s for s in sigs[k] if s["drop"] <= -5]
    cells = [f(stat([run(s, hold=h, sl=10) for s in S])) for h in (20, 40, 60)]
    cells.append(f(stat([run(s, hold=60, sl=10, target=True) for s in S])))
    cells.append(f(stat([run(s, hold=60, trail=15) for s in S])))
    print(f"| {NAMES[k]} | {len(S)} | " + " | ".join(cells) + " |")

BEST = "ma120"
S0 = [s for s in sigs[BEST]]
print(f"\n## 2) 조정 깊이별 ({NAMES[BEST]} 지지, 40봉 보유, 손절 -10%)\n")
print("| 20봉 고점 대비 | 건수 | 전체 | IS | OOS |\n|---|---|---|---|---|")
for lo, hi_, lab in ((-999, -15, "-15% 이하(깊은 조정)"), (-15, -10, "-15~-10%"), (-10, -7, "-10~-7%"), (-7, -5, "-7~-5%"), (-5, -2, "-5~-2%"), (-2, 999, "-2% 이내(고점 부근)")):
    S = [s for s in S0 if lo <= s["drop"] < hi_]
    a = stat([run(s, hold=40, sl=10) for s in S])
    b = stat([run(s, hold=40, sl=10) for s in S if s["y"] <= 2024]); c = stat([run(s, hold=40, sl=10) for s in S if s["y"] >= 2025])
    print(f"| {lab} | {len(S)} | {f(a)} | {f(b)} | {f(c)} |")

print(f"\n## 3) 추가 조건 효과 ({NAMES[BEST]}, 조정 -5% 이상, 40봉, 손절 -10%)\n")
S = [s for s in S0 if s["drop"] <= -5]
print("| 조건 | 건수 | 전체 | IS | OOS |\n|---|---|---|---|---|")
CONDS = [("없음", lambda s: True),
         ("반등 확인(전일 종가 상회)", lambda s: s["rebound"]),
         ("조정 시 거래량 감소(<0.8배)", lambda s: s["vr"] < 0.8),
         ("조정 시 거래량 증가(>1.2배)", lambda s: s["vr"] > 1.2),
         ("코스피 5일선 위", lambda s: s["k5"]),
         ("코스피 20일선 위", lambda s: s["k20"]),
         ("120일선 상승 중(+2%↑/20봉)", lambda s: s["slope"] >= 2),
         ("전고점까지 10% 이상 여유", lambda s: s["up_target"] >= 10),
         ("반등+코스피5일선+거래량감소", lambda s: s["rebound"] and s["k5"] and s["vr"] < 0.8)]
for lab, fn in CONDS:
    SS = [s for s in S if fn(s)]
    a = stat([run(s, hold=40, sl=10) for s in SS])
    b = stat([run(s, hold=40, sl=10) for s in SS if s["y"] <= 2024]); c = stat([run(s, hold=40, sl=10) for s in SS if s["y"] >= 2025])
    print(f"| {lab} | {len(SS)} | {f(a)} | {f(b)} | {f(c)} |")

print(f"\n## 4) 손절 × 보유기간 ({NAMES[BEST]}, 조정 -5%↑ + 반등확인 + 코스피 5일선 위)\n")
SB = [s for s in S0 if s["drop"] <= -5 and s["rebound"] and s["k5"]]
print(f"대상 {len(SB)}건\n")
print("| 손절＼보유 | 10봉 | 20봉 | 40봉 | 60봉 | 90봉 |\n|---|---|---|---|---|---|")
for sl in (None, 5, 7, 10, 15, 20):
    cells = [f(stat([run(s, hold=h, sl=sl) for s in SB])) for h in (10, 20, 40, 60, 90)]
    print(f"| {'없음' if sl is None else f'-{sl}%'} | " + " | ".join(cells) + " |")

print(f"\n## 5) 연도별 (최종안: 120일선 + 조정-5%↑ + 반등확인 + 코스피5일선위, 40봉 보유, 손절 -10%)\n")
print("| 연도 | 건수 | 평균 | 승률 | PF | 중앙값 |\n|---|---|---|---|---|---|")
for y in (2023, 2024, 2025, 2026):
    s_ = stat([run(s, hold=40, sl=10) for s in SB if s["y"] == y])
    print(f"| {y} | {s_['n']} | {s_['avg']:+.2f}% | {s_['win']:.0f}% | {s_['pf']:.2f} | {s_['med']:+.2f}% |" if s_ else f"| {y} | 표본부족 | | | | |")

print(f"\n## 6) 지지선 조합 — 여러 지지선이 겹치는 자리\n")
bykey = {}
for k in SUPPORTS:
    for s in sigs[k]:
        bykey.setdefault((s["code"], s["i"]), []).append(k)
multi = [(kk, v) for kk, v in bykey.items() if len(v) >= 2]
allsig = {(s["code"], s["i"]): s for k in SUPPORTS for s in sigs[k]}
print("| 겹친 지지선 수 | 건수 | 40봉·손절-10% |\n|---|---|---|")
for n in (1, 2, 3):
    SS = [allsig[kk] for kk, v in bykey.items() if len(v) == n]
    a = stat([run(s, hold=40, sl=10) for s in SS])
    print(f"| {n}개 | {len(SS)} | {f(a)} |")
