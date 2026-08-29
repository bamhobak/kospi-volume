# -*- coding: utf-8 -*-
"""① NXT 당일 종가 매수 vs 다음날 시가 매수  ② MACD 3대 시스템 실측"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ─────────────── ① NXT 당일 종가 매수 비교
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
N = len(P); GP = P.gp.values.astype(int)
SRD = P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]
px = pd.read_sql("SELECT date,ticker,close,open,high,low,volume FROM daily WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date", con); con.close()
k2 = px.sort_values(["ticker", "date"]).copy()
k2["nopen"] = k2.groupby("ticker")["open"].shift(-1)
j = P[["t", "d"]].merge(k2.rename(columns={"ticker": "t", "date": "d"})[["t", "d", "close", "nopen"]], on=["t", "d"], how="left")
ADJ = (j.nopen / j.close).values          # 종가매수 환산 계수
GAP = (ADJ - 1) * 100
ki = fdr.DataReader("KS11", "2017-01-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
c = ki["Close"].reindex(dates).ffill()
MA = {w: (c > c.rolling(w).mean()).reindex([dates[i] for i in GP]).values for w in (5, 20)}

def ev(mask, h=10, sl=None, tp=None, entry="open"):
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    if entry == "close": r = (1 + r/100) * ADJ * 100 - 100
    r = r - COSTV
    r = r[mask]; y = P.y.values[mask]
    ok = np.isfinite(r); r, y = r[ok], y[ok]
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); o2 = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(o2>0).sum()}/{len(o2)}", tot=r.sum()/100*1_000_000)
F1 = ((P.quiet < 0.5) & (P.amt >= 50) & P.ret10.between(0, 20) & P.rs.notna() & (P.rs > 0)
      & SRD & (P.fwp >= 3)).values & MA[5] & MA[20]
F2 = ((P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & (P.ret10 <= 0) & SRD & (~P.dil)).values & ~MA[20]
print("# ① NXT 당일 종가 매수 vs 다음날 시가 매수\n")
print("| 필터 | 진입 방식 | 건수 | **절대수익** | 중앙값 | 승률 | PF | +연도 | 100만원씩 |")
print("|---|---|---|---|---|---|---|---|---|")
for lab, m, tp in (("1번", F1, 20), ("2번", F2, None)):
    for e, el in (("open", "다음날 시가 (현행)"), ("close", "**당일 종가 (NXT)**")):
        s = ev(m, 10, None, tp, e)
        print(f"| {lab} | {el} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['pos']} | **{s['tot']/10000:+,.0f}만** |")
    s = ev(m & (GAP <= 5), 10, None, tp, "open")
    print(f"| {lab} | 다음날 시가 · 갭+5%↑ 제외 | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['pos']} | **{s['tot']/10000:+,.0f}만** |")

# ─────────────── ② MACD 3대 시스템
print("\n\n# ② MACD 매매 시스템 실측 (일봉 · 절대수익 · 다음날 시가 매수 · 비용 반영)\n")
NB = 41
KO = ki["Open"].reindex(dates).ffill().values; KC = ki["Close"].reindex(dates).ffill().values
POS = {d: i for i, d in enumerate(dates)}
SIG = {k: [] for k in "ABCDEF"}
for t, g in px.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 300: continue
    g = g.reset_index(drop=True); n = len(g)
    O, H, L, C = (g[x].values.astype(float) for x in ("open", "high", "low", "close"))
    V = g.volume.values.astype(float); D = g.date.values
    S = pd.Series(C)
    e12 = S.ewm(span=12, adjust=False).mean(); e26 = S.ewm(span=26, adjust=False).mean()
    macd = (e12 - e26).values
    sig = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    hist = macd - sig
    amt = (pd.Series(V * C).rolling(20).mean() / 1e8).values
    scale = pd.Series(np.abs(macd)).rolling(120).mean().values      # 영선 근접 판정 기준
    lo20 = pd.Series(L).rolling(20).min().values
    mlo20 = pd.Series(macd).rolling(20).min().values
    last = {k: -99 for k in SIG}
    def push(key, jj):
        if jj + 1 >= n or jj - last[key] < 10: return
        o0 = O[jj + 1]
        if not np.isfinite(o0) or o0 <= 0 or not np.isfinite(amt[jj]) or amt[jj] < 3: return
        e = min(jj + 1 + NB, n)
        if e - (jj + 1) < 30: return
        SIG[key].append(dict(t=t, d=D[jj], y=int(D[jj][:4]), amt=amt[jj], gp=POS.get(D[jj], -1),
                             H=(H[jj+1:e]/o0-1)*100, L=(L[jj+1:e]/o0-1)*100, C=(C[jj+1:e]/o0-1)*100))
        last[key] = jj
    for jj in range(130, n - NB - 2):
        gc = macd[jj] > sig[jj] and macd[jj-1] <= sig[jj-1]         # 골든크로스
        if gc: push("A", jj)                                        # A. 단순 골든크로스
        if gc and macd[jj] > 0: push("B", jj)                       # B. + 제로라인 위 (추세 매매)
        if gc and macd[jj] > 0 and abs(macd[jj]) > 0.5 * scale[jj]: push("C", jj)   # C. + 영선 근처 배제
        if hist[jj] > 0 and hist[jj-1] <= 0 and macd[jj] > 0: push("D", jj)         # D. 히스토그램 양전환
        # E. 상승 다이버전스: 가격 20일 신저가인데 MACD는 신저가 아님 + 히스토그램 양전환
        if (L[jj] <= lo20[jj] * 1.001 and macd[jj] > mlo20[jj] * 0.999 and hist[jj] > hist[jj-1]):
            push("E", jj)
        # F. E + 히스토그램 양전환 확정
        if (L[jj-3:jj+1].min() <= lo20[jj] * 1.001 and macd[jj] > mlo20[jj] * 0.999
            and hist[jj] > 0 and hist[jj-1] <= 0): push("F", jj)
print("신호 수:", {k: len(v) for k, v in SIG.items()})
def cost(a): return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev2(S_, h, sl=None, tp=None, timestop=None):
    rows = []
    for s in S_:
        Cc, Ll, Hh2 = s["C"], s["L"], s["H"]
        nn = min(h, len(Cc) - 1); c_ = cost(s["amt"]); r = None
        for i in range(nn + 1):
            if sl and Ll[i] <= -sl: r = -sl - c_; break
            if tp and Hh2[i] >= tp: r = tp - c_; break
            if timestop and i == timestop and abs(Cc[i]) < 3: r = Cc[i] - c_; break
            if i == nn: r = Cc[i] - c_
        rows.append((s["y"], r))
    if len(rows) < 20: return None
    d = pd.DataFrame(rows, columns=["y", "r"])
    yy = d.groupby("y").r.mean(); cnt = d.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(d), ret=d.r.mean(), med=d.r.median(), win=(d.r > 0).mean()*100,
                pf=(d.r[d.r>0].sum()/abs(d.r[d.r<=0].sum())) if (d.r<=0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", tot=d.r.sum()/100*1_000_000)
NAMES = {"A": "단순 골든크로스 (비교용)", "B": "+ 제로라인 위 (추세매매)", "C": "+ 영선 근처 배제",
         "D": "히스토그램 양전환 + 영선 위", "E": "상승 다이버전스", "F": "다이버전스 + 히스토그램 확정"}
for h in (10, 20, 26):
    print(f"\n## 보유 {h}일\n")
    print("| 시스템 | 건수 | **절대수익** | 중앙값 | 승률 | PF | +연도 | 100만원씩 |\n|---|---|---|---|---|---|---|---|")
    for k in "ABCDEF":
        s = ev2(SIG[k], h)
        if not s: print(f"| {NAMES[k]} | {len(SIG[k])} | 부족 |" + " - |" * 5); continue
        print(f"| {NAMES[k]} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['pos']} | **{s['tot']/10000:+,.0f}만** |")
print("\n## 26캔들 타임스톱 · 손절 적용 (시스템 B 기준)\n")
print("| 규칙 | 건수 | **절대수익** | 승률 | PF | +연도 |\n|---|---|---|---|---|---|")
for lab, kw in (("26일 보유", dict(h=26)), ("26일 + 타임스톱(13일차 ±3% 미만시 청산)", dict(h=26, timestop=13)),
                ("26일 + 손절10%", dict(h=26, sl=10)), ("26일 + 익절20%", dict(h=26, tp=20)),
                ("10일 보유", dict(h=10)), ("40일 보유", dict(h=40))):
    s = ev2(SIG["B"], **kw)
    if s: print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['win']:.0f}% | {s['pf']:.2f} | {s['pos']} |")
