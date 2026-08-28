"""3중 이동평균(10/20/50 EMA) 추세 매매 실측
- 정배열(10>20>50)에서만 롱
- '하락 후 첫 반등'은 버리고, 변동성 수축(VCP) 후 거래량 동반 전고점 돌파를 공략
- 청산: 중기선(20EMA) 하향 이탈 (+ 다른 청산과 비교)
python ema3_test.py
"""
import io, sys, sqlite3, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
CF = BASE / "data" / "ema3_cache.pkl"

if CF.exists():
    TR = pickle.load(open(CF, "rb"))
else:
    con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
    df = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,amount
                        FROM daily WHERE ticker LIKE '%0' AND date>='20220601' AND open IS NOT NULL
                        ORDER BY ticker,date""", con)
    kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
    kospi["ma20"] = kospi["Close"].rolling(20).mean()
    K = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}
    TR = []
    for t, g in df.groupby("ticker"):
        g = g.reset_index(drop=True)
        if len(g) < 200: continue
        c = g["close"].astype(float); h = g["high"].astype(float); l = g["low"].astype(float)
        o = g["open"].astype(float); v = g["volume"].astype(float); am = g["amount"].astype(float)
        e10 = c.ewm(span=10, adjust=False).mean(); e20 = c.ewm(span=20, adjust=False).mean(); e50 = c.ewm(span=50, adjust=False).mean()
        vma = v.rolling(20).mean(); amt20 = am.rolling(20).mean() / 1e8
        atrp = ((h / l - 1) * 100).rolling(20).mean()
        align = (e10 > e20) & (e20 > e50)
        D = g["date"].values; N = len(g)
        E10, E20, E50 = e10.values, e20.values, e50.values
        C, H, L, O, V, VMA, AMT, ATR, AL = c.values, h.values, l.values, o.values, v.values, vma.values, amt20.values, atrp.values, align.values
        last = -99
        for i in range(60, N - 1):
            if str(D[i]) < "20230101" or i - last < 10: continue
            if not AL[i] or np.isnan(ATR[i]) or np.isnan(AMT[i]) or AMT[i] < 10: continue    # 정배열 + 유동성
            # 변동성 수축: 최근 10봉 고저폭이 20일 평균 일중폭의 4배 이내
            rng = (H[i - 10:i].max() / L[i - 10:i].min() - 1) * 100
            if rng > max(6, ATR[i] * 4): continue
            # 전고점 돌파 + 거래량
            box = H[i - 10:i].max()
            if not (C[i] > box and V[i] >= 1.5 * VMA[i]): continue
            # '하락 후 첫 반등' 배제: 정배열이 최소 5봉 이상 유지되고 있어야 함
            align_days = 0
            for k in range(i, max(-1, i - 30), -1):
                if AL[k]: align_days += 1
                else: break
            first_bounce = align_days < 5
            # 정배열 초입 여부(최근 20봉 내 정배열 시작)
            fresh = align_days <= 20
            if O[i + 1] <= 0: continue
            last = i
            j0 = i + 1; nb = min(121, N - j0)
            TR.append(dict(t=t, d=str(D[i]), y=int(str(D[i])[:4]), o=float(O[j0]),
                           H=(H[j0:j0 + nb] / O[j0] - 1) * 100, L=(L[j0:j0 + nb] / O[j0] - 1) * 100,
                           C=(C[j0:j0 + nb] / O[j0] - 1) * 100, OP=(O[j0:j0 + nb] / O[j0] - 1) * 100,
                           e10=(E10[j0:j0 + nb] / O[j0] - 1) * 100, e20=(E20[j0:j0 + nb] / O[j0] - 1) * 100,
                           e50=(E50[j0:j0 + nb] / O[j0] - 1) * 100,
                           amt=float(AMT[i]), vr=float(V[i] / VMA[i]), rng=float(rng),
                           align_days=align_days, first_bounce=first_bounce, fresh=fresh,
                           k20=K.get(str(D[i]), False)))
    pickle.dump(TR, open(CF, "wb"))
print(f"신호 {len(TR)}건", file=sys.stderr)

def cost(a):
    slip = 0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70
    return 0.18 + slip

def run(s, exit_ema=None, hold=120, sl=None, tp=None):
    """exit_ema: 'e10'/'e20'/'e50' 종가 이탈 시 다음날 시가 청산"""
    C, H, L, OP = s["C"], s["L"], s["H"], s["OP"]
    n = min(hold, len(C) - 1)
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - cost(s["amt"])
        if tp and H[i] >= tp: return tp - cost(s["amt"])
        if exit_ema and i > 0 and C[i] < s[exit_ema][i]:
            k = min(i + 1, len(OP) - 1); return OP[k] - cost(s["amt"])
        if i == n: return C[i] - cost(s["amt"])

def st(S, **kw):
    r = [x for x in (run(s, **kw) for s in S) if x is not None]
    if len(r) < 15: return None
    r = np.array(r); w = r[r > 0]; l = r[r <= 0]
    return dict(n=len(r), avg=r.mean(), win=len(w) / len(r) * 100, pf=(w.sum() / abs(l.sum())) if len(l) else 99,
                med=np.median(r), worst=r.min())
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f} ({s['n']})" if s else "-"

REAL = [s for s in TR if not s["first_bounce"]]      # 첫 반등 제외 (영상 규칙)
print("# 3중 이동평균(10/20/50 EMA) 전략 실측 — 2023~2026, 슬리피지·수수료 반영\n")
print(f"전체 신호 {len(TR)}건 · 첫 반등 제외 {len(REAL)}건 · 표기: 순수익 / 승률 / PF (건수)\n")

print("## 1) 청산 방식 비교 (첫 반등 제외 기준)\n")
print("| 청산 | 전체 | 2023 | 2024 | 2025 | 2026 |\n|---|---|---|---|---|---|")
for lab, kw in (("20EMA 이탈 (영상 규칙)", dict(exit_ema="e20")), ("10EMA 이탈", dict(exit_ema="e10")),
                ("50EMA 이탈", dict(exit_ema="e50")), ("10일 보유", dict(hold=10)), ("20일 보유", dict(hold=20)),
                ("손익비 목표 +20%", dict(exit_ema="e20", tp=20)), ("20EMA + 손절 -10%", dict(exit_ema="e20", sl=10))):
    ys = [f(st([s for s in REAL if s["y"] == y], **kw)) for y in (2023, 2024, 2025, 2026)]
    print(f"| {lab} | {f(st(REAL, **kw))} | " + " | ".join(ys) + " |")

print("\n## 2) '하락 후 첫 반등 버리기' 검증 (20EMA 이탈 청산)\n")
print("| 구분 | 건수 | 성과 |\n|---|---|---|")
print(f"| 전체 | {len(TR)} | {f(st(TR, exit_ema='e20'))} |")
print(f"| 첫 반등만 (정배열 5일 미만) | {len([s for s in TR if s['first_bounce']])} | {f(st([s for s in TR if s['first_bounce']], exit_ema='e20'))} |")
print(f"| 첫 반등 제외 | {len(REAL)} | {f(st(REAL, exit_ema='e20'))} |")

print("\n## 3) 정배열 지속일수별 (20EMA 이탈)\n")
print("| 정배열 유지 | 건수 | 성과 |\n|---|---|---|")
for lo, hi, lab in ((0, 5, "5일 미만(첫 반등)"), (5, 20, "5~20일(초입)"), (20, 60, "20~60일"), (60, 9999, "60일 이상(성숙)")):
    S = [s for s in TR if lo <= s["align_days"] < hi]
    print(f"| {lab} | {len(S)} | {f(st(S, exit_ema='e20'))} |")

print("\n## 4) 추가 조건 효과 (첫 반등 제외 + 20EMA 이탈)\n")
print("| 조건 | 건수 | 성과 |\n|---|---|---|")
for lab, fn in (("없음", lambda s: True),
                ("코스피 20일선 위", lambda s: s["k20"]),
                ("거래량 2배↑", lambda s: s["vr"] >= 2), ("거래량 3배↑", lambda s: s["vr"] >= 3),
                ("수축 강함(범위 ≤4%)", lambda s: s["rng"] <= 4),
                ("거래대금 50억↑", lambda s: s["amt"] >= 50), ("거래대금 100억↑", lambda s: s["amt"] >= 100),
                ("정배열 초입(≤20일)", lambda s: s["fresh"]),
                ("초입 + 코스피20일선 + 거래량2배", lambda s: s["fresh"] and s["k20"] and s["vr"] >= 2)):
    S = [s for s in REAL if fn(s)]
    print(f"| {lab} | {len(S)} | {f(st(S, exit_ema='e20'))} |")

best = [s for s in REAL if s["fresh"] and s["k20"] and s["vr"] >= 2]
if len(best) >= 15:
    print(f"\n## 5) 최적 조합 연도별 (초입+코스피20일선+거래량2배, 20EMA 이탈)\n")
    print("| 연도 | 건수 | 성과 |\n|---|---|---|")
    for y in (2023, 2024, 2025, 2026):
        print(f"| {y} | {len([s for s in best if s['y']==y])} | {f(st([s for s in best if s['y']==y], exit_ema='e20'))} |")
    s_ = st(best, exit_ema="e20")
    print(f"\n중앙값 {s_['med']:+.2f}% · 최악 {s_['worst']:+.1f}%")
