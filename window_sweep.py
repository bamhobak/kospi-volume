# -*- coding: utf-8 -*-
"""1·2번 필터 거래량 윈도우 스윕
   기준창(1년=240) · 잠잠창(2개월=40) · 급등창(3일) 을 각각 바꿔가며 지수 대비 초과수익 측정
   나머지 조건(외국인 5일 2%, 거래대금, 주가, 지수 20일선, 업종 상대강도)은 현행 유지
"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WB = [120, 180, 240, 360, 480, 660]        # 기준창: 6개월·9개월·1년·1.5년·2년·2년9개월
WQ = [20, 30, 40, 60, 90]                  # 잠잠창: 1개월·45일·2개월·3개월·4.5개월
WS = [1, 2, 3, 5, 10]                      # 급등창: 1·2·3·5·10일
H = 10                                     # 보유
ALLW = sorted(set(WB + WQ + WS))

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
T2G = dict(sec.values)
Z = pickle.load(open("data/sector_index.pkl", "rb")); RS = Z["upjong"]["rs20"]
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].reindex(dates).ffill().values
KC = ki["Close"].reindex(dates).ffill().values
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).reindex(dates).ffill().fillna(False).values
# 지수 수익: 매수일(p+1) 시가 → p+1+k 종가
ND = len(dates)
IDX = np.full((ND, H + 1), np.nan)
for p in range(ND - H - 2):
    o = KO[p + 1]
    if not np.isfinite(o) or o <= 0: continue
    for k in range(H + 1):
        IDX[p, k] = (KC[p + 1 + k] / o - 1) * 100

def rmean(a, w):
    c = np.concatenate(([0.0], np.nancumsum(np.nan_to_num(a))))
    out = np.full(len(a), np.nan)
    out[w-1:] = (c[w:] - c[:-w]) / w
    return out

def cost(a):
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)

NC = len(WB) * len(WQ) * len(WS)
COMBO = [(b, q, s) for b in WB for q in WQ for s in WS]
CIX = {c: i for i, c in enumerate(COMBO)}
YEARS = list(range(2019, 2027))
YIX = {y: i for i, y in enumerate(YEARS)}
# 누적: [filter, combo, year] -> (n, sum_ret, sum_alpha, n_alpha_pos)
ACC = np.zeros((2, NC, len(YEARS), 4))

for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 700: continue
    g = g.reset_index(drop=True)
    n = len(g)
    O = g.open.values.astype(float); Hh = g.high.values.astype(float)
    L = g.low.values.astype(float); C = g.close.values.astype(float)
    V = g.volume.values.astype(float); F = np.nan_to_num(g.frgn.values.astype(float))
    D = g.date.values
    gp = np.array([POS.get(x, -1) for x in D])
    VM = {w: rmean(V, w) for w in ALLW}
    AM = {w: rmean(V * C, w) for w in WQ}
    v5 = pd.Series(V).rolling(5).sum().values
    f5 = pd.Series(F).rolling(5).sum().values
    with np.errstate(invalid="ignore", divide="ignore"):
        fwp = f5 / v5 * 100
        ret3 = (C / np.roll(C, 3) - 1) * 100; ret3[:3] = np.nan
        ret10 = (C / np.roll(C, 10) - 1) * 100; ret10[:10] = np.nan
    # 업종 상대강도
    gn = T2G.get(t)
    rs = np.full(n, np.nan)
    if gn and gn != "기타" and gn in RS.columns:
        sr = RS[gn]
        rs = np.array([sr.get(x, np.nan) for x in D])
    # 청산 수익 (규칙1: 손절15·익절30, 규칙2: 무손절) + 청산일 offset
    ex1 = np.full(n, np.nan); hh1 = np.zeros(n, int)
    ex2 = np.full(n, np.nan); hh2 = np.zeros(n, int)
    for j in range(n - H - 2):
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0: continue
        c_ = cost(AM[40][j] / 1e8 if np.isfinite(AM[40][j]) else 3)
        r1 = None
        for k in range(H + 1):
            lo = (L[j+1+k] / o0 - 1) * 100; hi = (Hh[j+1+k] / o0 - 1) * 100
            if lo <= -15: r1 = (-15 - c_, k); break
            if hi >= 30: r1 = (30 - c_, k); break
            if k == H: r1 = ((C[j+1+k] / o0 - 1) * 100 - c_, k)
        ex1[j], hh1[j] = r1
        ex2[j], hh2[j] = (C[j+1+H] / o0 - 1) * 100 - c_, H
    yr = np.array([int(x[:4]) for x in D])
    base_ok = np.isfinite(fwp) & np.isfinite(ret3) & np.isfinite(ret10) & (gp >= 0)
    for (b, q, s) in COMBO:
        ci = CIX[(b, q, s)]
        vq = np.roll(VM[q], s); vq[:s] = np.nan            # 잠잠창 (급등창 이전)
        vb = np.roll(VM[b], s + q); vb[:s+q] = np.nan      # 기준창 (잠잠창 이전)
        aq = np.roll(AM[q], s) / 1e8; aq[:s] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            quiet = vq / vb; surge = VM[s] / vq
        ok = base_ok & np.isfinite(quiet) & np.isfinite(surge) & np.isfinite(aq) & np.isfinite(ex1)
        m1 = ok & (quiet < 0.5) & (surge >= 2) & (fwp >= 2) & (aq >= 50) & (ret10 >= 0) & (ret10 <= 20) \
             & np.isfinite(rs) & (rs > 0) & K20[np.clip(gp, 0, ND-1)]
        m2 = ok & (quiet < 0.3) & (surge >= 2) & (fwp >= 2) & (aq >= 3) & (ret3 <= 0)
        for fi, (m, ex, hh) in enumerate(((m1, ex1, hh1), (m2, ex2, hh2))):
            idx = np.where(m)[0]
            if len(idx) == 0: continue
            # 같은 종목 15일 이내 중복 제거
            keep = []; last = -99
            for j in idx:
                if j - last >= 15: keep.append(j); last = j
            if not keep: continue
            keep = np.array(keep)
            r = ex[keep]; p = gp[keep]; k = hh[keep]
            mk = IDX[p, k]
            good = np.isfinite(r) & np.isfinite(mk)
            for j2, rr, mm in zip(keep[good], r[good], mk[good]):
                y = yr[j2]
                if y not in YIX: continue
                yi = YIX[y]
                ACC[fi, ci, yi] += (1, rr, rr - mm, 1 if rr - mm > 0 else 0)

def table(fi, title, fixed, axis):
    print(f"\n## {title}\n")
    rows = []
    for c, ci in CIX.items():
        b, q, s = c
        if not fixed(b, q, s): continue
        a = ACC[fi, ci]
        n = a[:, 0].sum()
        if n < 25: continue
        al = a[:, 2].sum() / n
        ret = a[:, 1].sum() / n
        yal = np.divide(a[:, 2], a[:, 0], out=np.zeros(len(YEARS)), where=a[:, 0] >= 3)
        pos = int(((yal > 0) & (a[:, 0] >= 3)).sum()); tot = int((a[:, 0] >= 3).sum())
        alw = a[:, 3].sum() / n * 100
        rows.append((axis(b, q, s), int(n), ret, al, alw, f"{pos}/{tot}"))
    rows.sort(key=lambda x: -x[3])
    print("| 설정 | 건수 | 절대수익 | **초과수익** | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|")
    for lab, n, ret, al, alw, pos in rows:
        print(f"| {lab} | {n} | {ret:+.2f}% | **{al:+.2f}%** | {alw:.0f}% | {pos} |")

M = {120: "6개월", 180: "9개월", 240: "1년(현행)", 360: "1.5년", 480: "2년", 660: "2년9개월"}
Q = {20: "1개월", 30: "45일", 40: "2개월(현행)", 60: "3개월", 90: "4.5개월"}
for fi, fname, cq in ((0, "1번 필터", 40), (1, "2번 필터", 40)):
    print(f"\n\n# {fname}")
    table(fi, "① 기준창 변경 (잠잠 2개월 · 급등 3일 고정)",
          lambda b, q, s: q == 40 and s == 3, lambda b, q, s: f"기준 {M[b]}")
    table(fi, "② 잠잠창 변경 (기준 1년 · 급등 3일 고정)",
          lambda b, q, s: b == 240 and s == 3, lambda b, q, s: f"잠잠 {Q[q]}")
    table(fi, "③ 급등창 변경 (기준 1년 · 잠잠 2개월 고정)",
          lambda b, q, s: b == 240 and q == 40, lambda b, q, s: f"급등 {s}일")
    table(fi, "④ 전체 조합 상위 12",
          lambda b, q, s: True, lambda b, q, s: f"기준{M[b]}·잠잠{Q[q]}·급등{s}일")
np.save("data/window_sweep.npy", ACC)
