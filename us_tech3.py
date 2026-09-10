# -*- coding: utf-8 -*-
"""미국 매매법 3차 — Minervini 8조건을 **제대로** 넣고, 생존자를 계좌까지 끌고 간다.

2차까지 쓴 'Minervini' 는 반쪽이었다. 원문 8조건 중 셋을 빠뜨렸다.
  ④ 50일선 > 150일선   ⑤ 종가 > 50일선   ⑧ **상대강도(RS) 등급 70 이상**
특히 ⑧ 은 그 사람 체계의 핵심이다 — '추세' 가 아니라 '**남들보다** 센 추세' 를 고르는 조건이라
이게 없으면 그냥 이평 정배열과 다를 게 없다. 여기서 8조건 전부 넣고 RS 문턱을 흔든다.

RS 등급은 IBD 방식(최근 분기에 가중)을 그날 유니버스 안에서 백분위로 낸다.
  RS원자재 = 2·(3개월 수익) + (6개월) + (12개월)   → 그날 유니버스 백분위 × 100

그리고 규칙 단위 통과는 시작일 뿐이다. 우리 집 잣대는 **계좌**다
([[kosdaq-p7-reject]] · [[stock-feargreed]] — 자리 제한이 있으면 규칙 성적과 계좌 성적이 갈린다).
신호가 하루 몇 건인지, 40일 보유면 동시에 몇 종목을 들고 있어야 하는지까지 낸다.

    python us_tech3.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
TK = K.ticker
def G(c): return K.groupby(TK, sort=False)[c]
def roll(c, n, how="mean"):
    return G(c).transform(lambda s: getattr(s.rolling(n, min_periods=n), how)())

log("지표 계산 중")
K["r1"] = G("close").pct_change() * 100
for n in (20, 50, 150, 200):
    K[f"ma{n}"] = roll("close", n)
K["ma200p"] = G("ma200").shift(21)
K["vsq"] = K.vol20 <= roll("vol20", 60) * 0.7
K["absr"] = G("r1").transform(lambda s: s.abs().rolling(60).mean())
# IBD 식 상대강도 원자재 — 최근 분기에 두 배 가중
K["rsraw"] = 2 * K.ret60 + K.ret120 + K.ret250
K["rs"] = K[UNI].groupby("date").rsraw.rank(pct=True).reindex(K.index) * 100
# Minervini 8조건
C = {}
C[1] = K.close > K.ma150
C[2] = K.close > K.ma200
C[3] = K.ma150 > K.ma200
C[4] = K.ma200 > K.ma200p              # 200일선이 한 달 이상 상승
C[5] = K.ma50 > K.ma150
C[6] = K.close > K.ma50
C[7] = (K.fromhi >= -25) & (K.fromlo >= 30)
MIN7 = C[1] & C[2] & C[3] & C[4] & C[5] & C[6] & C[7]     # RS 뺀 7조건
K["min7"] = MIN7
K["min7n"] = G("min7").transform(lambda s: s.rolling(21, min_periods=21).sum())   # 갓 통과?
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])

def trimmed(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan
BT = {h: trimmed(K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)) for h in (20, 40, 60)}
log(f"준비 완료 · {len(K):,}행 · 기준선 절삭 " + " ".join(f"{h}일 {BT[h]:.2f}" for h in BT))

def dd(cond, h, lo="20160101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<34} {'n':>7} {'일':>5} {'동시':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭Δ':>7} "
       f"{'초과':>7} {'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>7}")
OK = []; NTRY = [0]
def show(tag, cond, h=40):
    NTRY[0] += 1
    d = dd(cond, h)
    if len(d) < 80: print(f"  {tag:<34} {len(d):>7}  (표본 부족)"); return None
    st = dd(cond, h, lo="20050101", hi="20151231")
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
    per = len(d) / NDAY; dtm = trimmed(d.r) - BT[h]
    stx = st.ex.mean() if len(st) >= 80 else np.nan
    print(f"  {tag:<34} {len(d):>7,} {per:>5.2f} {per*h:>5.0f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{stx:>7.2f} {ci:>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")
    if dtm > 0 and d.ex.mean() > 0 and va.ex.mean() > 0 and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72:
        OK.append((tag, h, len(d), per * h, d.ex.mean(), va.ex.mean(), ci, int((yr > 0).sum()), len(yr)))
    return d

W = 162
print("\n" + "=" * W)
print("① 조건을 하나씩 쌓는다 — 어디서 값이 붙는가 (40일 보유)")
print("=" * W); print(HDR)
acc = pd.Series(True, index=K.index)
names = {1: "종가>150일선", 2: "+ 종가>200일선", 3: "+ 150>200", 4: "+ 200일선 상승",
         5: "+ 50>150", 6: "+ 종가>50일선", 7: "+ 고점-25%내 & 저점+30%↑"}
for i in range(1, 8):
    acc = acc & C[i]
    show(f"  {i}. {names[i]}", acc)
print()
print("  ── 8번째 조건: 상대강도(RS) 등급 ──")
for th in (50, 70, 80, 90, 95):
    show(f"  7조건 + RS ≥ {th}", MIN7 & (K.rs >= th))
print()
print("  ── RS 만 (7조건 없이) — 정말 RS 가 값을 내는가 ──")
for th in (70, 80, 90, 95):
    show(f"  RS ≥ {th} 단독", K.rs >= th)
print()
print("=" * W)
print("② 보유기간 — 추세형은 길게 쥐는 게 맞는가 (7조건 + RS>=80)")
print("=" * W); print(HDR)
FULL = MIN7 & (K.rs >= 80)
for h in (20, 40, 60):
    show(f"  {h}일 보유", FULL, h)
print("  ── RS 를 거꾸로 (7조건 + RS < 70) — ① 에서 이쪽이 더 좋았다 ──")
LOWRS = MIN7 & (K.rs < 70)
for h in (20, 40, 60):
    show(f"  {h}일 보유", LOWRS, h)

print()
print("=" * W); print("=" * W)
print("③ 신호를 줄이는 조임 — 하루 몇 건까지 내려가나 (40일 보유)")
print("=" * W); print(HDR)
show("  기준 (7조건 + RS>=80)", FULL)
show("  + 갓 통과(21일내 신규 5일이하)", FULL & (K.min7n <= 5))
show("  + 변동성 수축", FULL & K.vsq)
show("  + 일간 등락 잔잔(1.5% 이하)", FULL & (K.absr <= 1.5))
show("  + 잔잔(1.0% 이하)", FULL & (K.absr <= 1.0))
show("  + 20일선 위", FULL & (K.close > K.ma20))
show("  + RS>=90 & 잔잔(1.5% 이하)", MIN7 & (K.rs >= 90) & (K.absr <= 1.5))
show("  + RS>=90 & 잔잔 & 수축", MIN7 & (K.rs >= 90) & (K.absr <= 1.5) & K.vsq)

print()
print("=" * W)
print("④ 진짜 후보 — Frog-in-the-Pan 강화판(1년 크게 올랐는데 일간은 잔잔) 이웃 셀")
print("=" * W)
# 2차에서 유일하게 **절삭평균이 양수**로 나온 칸이다. 한 칸만 좋으면 노이즈이므로
# 문턱을 흔들어 이웃이 같이 좋은지 본다([[community-techniques]] 50일선 교훈).
for h in (20, 40):
    print(f"  == {h}일 보유 =="); print(HDR)
    for rt in (50, 80, 100, 120, 150):
        for ab in (1.0, 1.5, 2.0):
            show(f"  1년 {rt}%↑ · 일간등락 {ab}% 이하", K.multi & (K.ret250 >= rt) & (K.absr <= ab), h)
        print()
print("  ── 여집합·대조군 (40일) ──"); print(HDR)
show("  1년 100%↑ · 요란(3% 이상)", K.multi & (K.ret250 >= 100) & (K.absr >= 3), 40)
show("  1년 100%↑ · 등락 무관", K.multi & (K.ret250 >= 100), 40)
show("  1년 0~50% · 잔잔 1.5 이하", K.multi & (K.ret250 < 50) & (K.absr <= 1.5), 40)
show("  잔잔 1.5 이하만 (모멘텀 없이)", K.absr <= 1.5, 40)
show("  1년 100%↑ · 잔잔 + 7조건", MIN7 & (K.ret250 >= 100) & (K.absr <= 1.5), 40)
show("  1년 100%↑ · 잔잔 + RS>=90", (K.rs >= 90) & (K.ret250 >= 100) & (K.absr <= 1.5), 40)
print()
print("  ── 연도별 초과 (1년 100%↑ · 잔잔 1.5 이하 · 40일 · 2005~) ──")
D = dd(K.multi & (K.ret250 >= 100) & (K.absr <= 1.5), 40, lo="20050101")
ytab = D.groupby(D.date.str[:4]).agg(n=("r", "size"), m=("r", "mean"), x=("ex", "mean"))
for y, r in ytab.iterrows():
    print(f"    {y}  {int(r.n):>4}건  평균 {r.m:>7.2f}  초과 {r.x:>+7.2f}")

print(HDR)
show("  Frog 원본(1년 50%↑·잔잔 1.5)", K.multi & (K.ret250 >= 50) & (K.absr <= 1.5))
show("  Frog + 7조건", MIN7 & (K.ret250 >= 50) & (K.absr <= 1.5))
show("  Frog + RS≥90", (K.rs >= 90) & (K.ret250 >= 50) & (K.absr <= 1.5))
show("  Frog 잔잔 1.0", K.multi & (K.ret250 >= 50) & (K.absr <= 1.0))
show("  대조군: 1년 50%↑ & 요란(≥3%)", K.multi & (K.ret250 >= 50) & (K.absr >= 3))

print("\n" + "=" * W)
print("⑤ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for t, h, n, sim, ex, va, ci, y, ny in OK:
        print(f"  ✅ {t.strip():<34} {h:>2}일 · {n:>6,}건 · 동시보유 {sim:>4.0f}종목 · "
              f"초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
try:
    import verdict; print("\n누적 시행:", verdict.log_trials("us_tech_web", NTRY[0]))
except Exception as e: print(e)
