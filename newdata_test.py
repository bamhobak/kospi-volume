"""새로 확보한 데이터(시가총액·OHLC·실제 거래대금)로 필터 개선 검증
python newdata_test.py
"""
import io, sys, pickle, sqlite3, itertools
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
W, Q, B = 3, 40, 240; NB = 31
CF = BASE / "data" / "sig2_cache.pkl"

if CF.exists():
    SIG = pickle.load(open(CF, "rb"))
else:
    con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
    df = pd.read_sql("""SELECT date,ticker,name,close,volume,frgn,organ,open,high,low,amount,marcap
                        FROM daily WHERE ticker LIKE '%0' AND date>='20220101' ORDER BY ticker,date""", con)
    kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
    kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
    K = {d.strftime("%Y%m%d"): (bool(r["Close"] > r["ma5"]), bool(r["Close"] > r["ma20"])) for d, r in kospi.iterrows()}
    SIG = []
    for t, g in df.groupby("ticker"):
        g = g.reset_index(drop=True)
        v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float)
        if len(g) < 320: continue
        quiet = v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean()
        surge = v.rolling(W).mean() / v.shift(W).rolling(Q).mean()
        v5 = v.rolling(5).sum(); fwp = f.rolling(5).sum() / v5 * 100
        fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
        amt_real = g["amount"].astype(float).shift(W).rolling(Q).mean() / 1e8       # 실제 거래대금 2개월 평균(억)
        cap = g["marcap"].astype(float) / 1e8                                        # 시가총액(억)
        ret3 = (c / c.shift(3) - 1) * 100; ret10 = (c / c.shift(10) - 1) * 100
        base = (quiet < .7) & (surge >= 2) & (fok == 1) & (g["date"] >= "20230101")
        idx = np.where(base.values)[0]
        if len(idx) == 0: continue
        O, HH, LL, CC, DD = g["open"].values, g["high"].values, g["low"].values, g["close"].values, g["date"].values
        last = -99
        for j in idx:
            if j - last < 15 or j + NB >= len(g): continue
            if np.isnan(O[j + 1]) or O[j + 1] <= 0: continue
            last = j
            o0 = float(O[j + 1])
            SIG.append(dict(t=t, d=DD[j], y=int(str(DD[j])[:4]),
                H=(HH[j + 1:j + 1 + NB] / o0 - 1) * 100, L=(LL[j + 1:j + 1 + NB] / o0 - 1) * 100,
                C=(CC[j + 1:j + 1 + NB] / o0 - 1) * 100,
                gap=(o0 / CC[j] - 1) * 100,                                          # 신호일 종가 → 다음날 시가 갭
                sigclose=float(CC[j]),
                quiet=float(quiet.iloc[j]), surge=float(surge.iloc[j]), fwp=float(fwp.iloc[j]),
                amt=float(amt_real.iloc[j]) if not np.isnan(amt_real.iloc[j]) else 0.0,
                cap=float(cap.iloc[j]) if not np.isnan(cap.iloc[j]) else 0.0,
                ret3=float(ret3.iloc[j]), ret10=float(ret10.iloc[j]),
                k5=K.get(str(DD[j]), (False, False))[0], k20=K.get(str(DD[j]), (False, False))[1]))
    pickle.dump(SIG, open(CF, "wb"))
print(f"기본 신호 {len(SIG)}건 (2023~2026)", file=sys.stderr)

def cost(a):
    slip = 0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00
    return 0.18 + slip
def ev(s, h=10, sl=None, tp=None, entry="open"):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1)
    adj = 0.0
    if entry == "close":            # 신호일 종가(NXT) 매수 가정 → 갭만큼 보정
        adj = s["gap"]
    for i in range(n + 1):
        r = None
        if sl and L[i] <= -sl: r = -sl
        elif tp and H[i] >= tp: r = tp
        elif i == n: r = C[i]
        if r is not None:
            return ((100 + r) / (100 + (0 if entry == "open" else -adj)) - 1) * 100 - cost(s["amt"] or 3) if entry == "close" else r - cost(s["amt"] or 3)
def st(S, **kw):
    r = [x for x in (ev(s, **kw) for s in S) if x is not None]
    if len(r) < 20: return None
    r = np.array(r); w = r[r > 0]; l = r[r <= 0]
    return dict(n=len(r), avg=r.mean(), win=len(w) / len(r) * 100, pf=(w.sum() / abs(l.sum())) if len(l) else 99)
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f} ({s['n']})" if s else "-"

F1 = lambda s: s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 50 and s["quiet"] < 0.5 and 0 <= s["ret10"] <= 20 and s["k20"]
F2 = lambda s: s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 3 and s["quiet"] < 0.4 and s["ret3"] <= 0
S1 = [s for s in SIG if F1(s)]; S2 = [s for s in SIG if F2(s)]

print("# 새 데이터(시가총액·실제 거래대금·OHLC) 검증\n")
print(f"1번 필터 {len(S1)}건 · 2번 필터 {len(S2)}건 · 표기: 순수익 / 승률 / PF (건수)\n")

print("## 1) 시가총액 구간별 성과 (전체 신호, 10일 보유)\n")
print("| 시가총액 | 건수 | 성과 |\n|---|---|---|")
for lo, hi, lab in ((0, 1000, "1천억 미만"), (1000, 3000, "1천~3천억"), (3000, 10000, "3천억~1조"),
                    (10000, 50000, "1조~5조"), (50000, 10**9, "5조 이상")):
    S = [s for s in SIG if lo <= s["cap"] < hi]
    print(f"| {lab} | {len(S)} | {f(st(S))} |")

print("\n## 2) 갭(신호일 종가→다음날 시가)별 성과 (전체 신호, 10일)\n")
print("| 갭 | 건수 | 시가 매수 | 신호일 종가 매수(NXT) |\n|---|---|---|---|")
for lo, hi, lab in ((-99, -2, "-2% 이하"), (-2, 0, "-2~0%"), (0, 2, "0~+2%"), (2, 5, "+2~+5%"), (5, 99, "+5% 이상")):
    S = [s for s in SIG if lo <= s["gap"] < hi]
    print(f"| {lab} | {len(S)} | {f(st(S))} | {f(st(S, entry='close'))} |")
print(f"\n전체 갭 평균 {np.mean([s['gap'] for s in SIG]):+.2f}% · 중앙값 {np.median([s['gap'] for s in SIG]):+.2f}%")

print("\n## 3) 현재 필터 — 거래대금 기준 vs 시가총액 기준\n")
print("| 조건 | 건수 | 10일 | 15일 |\n|---|---|---|---|")
for lab, fn in (("1번 (대금 50억↑, 현재)", F1),
                ("1번 대신 시총 5천억↑", lambda s: s["surge"] >= 2 and s["fwp"] >= 2 and s["cap"] >= 5000 and s["quiet"] < 0.5 and 0 <= s["ret10"] <= 20 and s["k20"]),
                ("1번 대신 시총 1조↑", lambda s: s["surge"] >= 2 and s["fwp"] >= 2 and s["cap"] >= 10000 and s["quiet"] < 0.5 and 0 <= s["ret10"] <= 20 and s["k20"]),
                ("1번 + 시총 3천억↑ 병행", lambda s: F1(s) and s["cap"] >= 3000),
                ("2번 (대금 3억↑, 현재)", F2),
                ("2번 + 시총 1천억↑", lambda s: F2(s) and s["cap"] >= 1000),
                ("2번 + 시총 3천억↑", lambda s: F2(s) and s["cap"] >= 3000)):
    S = [s for s in SIG if fn(s)]
    print(f"| {lab} | {len(S)} | {f(st(S, h=10))} | {f(st(S, h=15))} |")

print("\n## 4) 갭 조건 추가 시 (1·2번 필터, 10일 보유)\n")
print("| 필터 + 갭 조건 | 건수 | 성과 |\n|---|---|---|")
for nm, S0 in (("1번", S1), ("2번", S2)):
    for lab, g in (("갭 무관", lambda x: True), ("갭 ≤ +2%", lambda x: x["gap"] <= 2),
                   ("갭 0~+3%", lambda x: 0 <= x["gap"] <= 3), ("갭 > +3% 제외", lambda x: x["gap"] <= 3)):
        S = [s for s in S0 if g(s)]
        print(f"| {nm} · {lab} | {len(S)} | {f(st(S, h=10))} |")

print("\n## 5) 연도별 재확인 (실제 거래대금 기준)\n")
print("| 필터 | 2023 | 2024 | 2025 | 2026 |\n|---|---|---|---|---|")
for nm, S0 in (("1번(10일)", S1), ("2번(10일·익절20%)", S2)):
    kw = dict(h=10) if nm.startswith("1") else dict(h=10, tp=20)
    print(f"| {nm} | " + " | ".join(f(st([s for s in S0 if s["y"] == y], **kw)) for y in (2023, 2024, 2025, 2026)) + " |")
