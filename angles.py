# -*- coding: utf-8 -*-
"""① 2번 필터 — 코스피 이평선 변형  ② 1번 필터 — 진입타이밍·갭·요일·업종집중도"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int); N = len(P)
SRD = P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]
px = pd.read_sql("SELECT date,ticker,close,open FROM daily WHERE market='KOSPI'", con); con.close()
px = px.sort_values(["ticker", "date"])
px["nopen"] = px.groupby("ticker")["open"].shift(-1)
key = px.rename(columns={"ticker": "t", "date": "d"})[["t", "d", "close", "nopen"]]
j = P[["t", "d"]].merge(key, on=["t", "d"], how="left")
GAP = (j.nopen / j.close - 1).values * 100          # 신호일 종가 → 다음날 시가 갭(%)
SIGCLOSE = j.close.values; NOPEN = j.nopen.values
DOW = pd.to_datetime(P.d).dt.dayofweek.values       # 0=월
MON = pd.to_datetime(P.d).dt.month.values
ki = fdr.DataReader("KS11", "2017-01-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
c = ki["Close"].reindex(dates).ffill()
MA = {w: (c > c.rolling(w).mean()).reindex([dates[i] for i in GP]).values for w in (5, 10, 15, 20, 25, 30, 40, 60)}

def rets(h, sl=None, tp=None, entry="open"):
    """entry='open': 다음날 시가 매수(기본) / 'close': 신호일 종가 매수"""
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    if entry == "close":                    # o0 기준 수익 → 신호일 종가 기준으로 환산
        adj = NOPEN / SIGCLOSE
        r = (1 + r / 100) * adj * 100 - 100
    return r - COSTV, kk
def stat(m, h=10, sl=None, tp=None, entry="open", mn=12):
    mv = np.asarray(m)
    if mv.sum() < mn: return None
    r, kk = rets(h, sl, tp, entry); r = r[mv]; y = P.y.values[mv]
    ok_ = np.isfinite(r); r = r[ok_]; y = y[ok_]
    if len(r) < mn: return None
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                tot=r.sum()/100*1_000_000)
def show(title, rows, **kw):
    print(f"\n## {title}\n")
    print("| 설정 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 학습 | 검증 | +연도 | 100만원씩 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for lab, m, kk2 in rows:
        s = stat(m, **{**kw, **kk2})
        if not s: print(f"| {lab} | 부족 |" + " - |" * 8); continue
        print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
              f"{s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} | **{s['tot']/10000:+,.0f}만** |")

# ── ① 2번 필터: 코스피 이평선 변형
F2 = ((P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & (P.ret10 <= 0) & SRD & (~P.dil)).values
print(f"# ① 2번 필터 — 시장 조건 변형 (시장조건 제외 시 {F2.sum()}건)")
show("이평선 아래 조건", [("조건 없음", F2, {})] +
     [(f"코스피 {w}일선 아래", F2 & ~MA[w], {}) for w in (5, 10, 15, 20, 25, 30, 40, 60)],
     h=10, sl=None, tp=None)
show("두 이평선 조합", [("10+20 둘 다 아래", F2 & ~MA[10] & ~MA[20], {}),
      ("5+20 둘 다 아래", F2 & ~MA[5] & ~MA[20], {}),
      ("20+60 둘 다 아래", F2 & ~MA[20] & ~MA[60], {}),
      ("15+30 둘 다 아래", F2 & ~MA[15] & ~MA[30], {}),
      ("20일선 아래 & 5일선 위(반등초입)", F2 & ~MA[20] & MA[5], {}),
      ("20일선 아래 & 5일선도 아래", F2 & ~MA[20] & ~MA[5], {})], h=10, sl=None, tp=None)

# ── ② 1번 필터: 새로운 각도
F1 = ((P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.rs.notna() & (P.rs > 0)
      & SRD & (P.fwp >= 3) & MA[5] & MA[20]).values
print(f"\n\n# ② 1번 필터 — 새로운 각도 (현행 {F1.sum()}건)")
show("가. 진입 타이밍", [("다음날 시가 매수 (현행)", F1, dict(entry="open")),
      ("신호일 종가 매수", F1, dict(entry="close"))], h=10, tp=20)
gv = GAP
show("나. 시가 갭 (신호일 종가 → 다음날 시가)",
     [("전체", F1, {}), ("갭 -2% 이하(하락출발)", F1 & (gv <= -2), {}), ("갭 -2~0%", F1 & (gv > -2) & (gv <= 0), {}),
      ("갭 0~2%", F1 & (gv > 0) & (gv <= 2), {}), ("갭 +2% 이상(급등출발)", F1 & (gv > 2), {}),
      ("갭 +5% 이상 제외", F1 & (gv <= 5), {}), ("갭 0% 이하만", F1 & (gv <= 0), {})], h=10, tp=20)
show("다. 요일", [(f"{d}요일", F1 & (DOW == i), {}) for i, d in enumerate("월화수목금")], h=10, tp=20)
show("라. 월", [(f"{m}월", F1 & (MON == m), {}) for m in range(1, 13)], h=10, tp=20)
# 업종 집중도: 같은 날 같은 업종에서 몇 개 신호가 났는가
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'", con); con.close()
T2G = dict(sec.values)
gn = P.t.map(T2G).fillna("기타").values
dfc = pd.DataFrame({"d": P.d.values, "g": gn, "f": F1})
cnt = dfc[dfc.f].groupby(["d", "g"]).size().rename("c").reset_index()
mp = {(r.d, r.g): r.c for r in cnt.itertuples()}
CONC = np.array([mp.get((P.d.values[i], gn[i]), 0) for i in range(N)])
show("마. 같은 날·같은 업종 신호 수", [("1개(단독)", F1 & (CONC == 1), {}), ("2개", F1 & (CONC == 2), {}),
      ("3개 이상(테마 쏠림)", F1 & (CONC >= 3), {}), ("2개 이상", F1 & (CONC >= 2), {})], h=10, tp=20)
show("바. 익절 수준 미세조정", [(f"익절 +{v}%", F1, dict(tp=v)) for v in (10, 15, 20, 25, 30, 40)] +
     [("익절 없음", F1, dict(tp=None))], h=10)
