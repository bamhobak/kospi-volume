# -*- coding: utf-8 -*-
"""미국 매매법 2차 — 기준선을 바로잡고, 1차에서 빠진 계열을 잰다.

1차(us_tech.py)에서 두 가지가 잘못됐다. 둘 다 [[backtest-pitfalls]] 넷째 함정
'기준선' 의 변형이다.

 ① **절삭평균을 0 과 견줬다.** 미장 유니버스는 수익이 소수 종목에 쏠려 있어
    상위 5% 를 자르면 **유니버스 자체가 음수**다. 0 을 넘으라는 건 아무도 못 넘는 잣대다.
    → 여기서는 같은 날 유니버스의 절삭평균을 같이 찍고 **그것과** 견준다.
 ② **캘린더를 종목 초과로 쟀다.** 날짜 조건은 그날 모두에게 똑같이 걸리므로
    초과가 구조적으로 0 이다. → 날짜 기법은 '아무 날 평균' 과 견준다.

재는 것
  ① 기준선 — 유니버스의 평균·중앙·절삭 (모든 판단의 바닥)
  ② 캘린더 — 아무 날 평균 대비 (Turn of Month 는 **거래일** 기준)
  ③ Williams %R(14) — 종가 기준 근사
  ④ 추세 눌림목 — 20일선 되돌림(Trend Pullback · Holy Grail 근사)
  ⑤ Stockbee 4% 버스트 — 미국산인데 한국 패널로만 쟀던 것
  ⑥ Quantpedia 횡단면 팩터 — 이벤트가 아니라 '줄 세워 한쪽 끝을 산다'
  ⑦ 1차 최고 생존자(Minervini · Frog-in-the-Pan) 조이기

출처: quantifiedstrategies.com(Turn of the Month · Williams %R) · quantpedia.com 스크리너
     · sofus-nl/swing-trading-strategies · Stockbee(Pradeep Bonde)

    python us_tech2.py
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
for n in (10, 20, 21, 50, 150, 200):
    K[f"ma{n}"] = roll("close", n)
K["ma200p"] = G("ma200").shift(21)
K["up200"] = K.close > K.ma200
K["hi14"] = roll("close", 14, "max"); K["lo14"] = roll("close", 14, "min")
# Williams %R — 슬림 캐시에 고가·저가가 없어 **종가 기준** 근사로 쓴다.
# -90 이하면 최근 14일 종가 범위의 아래쪽 10% 에 있다는 뜻.
K["wr"] = np.where(K.hi14 > K.lo14, -100 * (K.hi14 - K.close) / (K.hi14 - K.lo14), -50.0)
K["d20"] = (K.close / K.ma20 - 1) * 100                    # 20일선 이격
K["pull20"] = (K.d20 < 0) & (G("d20").shift(1) >= 0)       # 위에 있다가 20일선 아래로 되돌림
K["v20"] = roll("volume", 20)
K["burst"] = (K.r1 >= 4) & (K.volume >= K.v20 * 1.5) & (K.volume >= 100_000)   # Stockbee
K["vsq"] = K.vol20 <= roll("vol20", 60) * 0.7              # 변동성 수축(VCP 근사)
K["miner"] = ((K.close > K.ma150) & (K.close > K.ma200) & (K.ma150 > K.ma200)
              & (K.ma200 > K.ma200p) & (K.fromhi >= -25) & (K.fromlo >= 30))
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
K["absr"] = G("r1").transform(lambda s: s.abs().rolling(60).mean())
K["minew"] = G("miner").transform(lambda s: s.rolling(21, min_periods=21).sum())   # 갓 통과했나
# 거래일 기준 달력 — Turn of Month 는 '달의 몇 번째 거래일' 이지 며칠이 아니다
_nd = pd.DataFrame({"date": ud}); _d = pd.to_datetime(_nd.date, format="%Y%m%d")
_nd["ym"] = _d.dt.strftime("%Y%m")
TDM = dict(zip(_nd.date, _nd.groupby("ym").cumcount() + 1))
TDMR = dict(zip(_nd.date, _nd.groupby("ym").cumcount(ascending=False) + 1))
DOW = dict(zip(_nd.date, _d.dt.dayofweek))
_gap = (pd.to_datetime(_nd.date.shift(-1), format="%Y%m%d") - _d).dt.days
PREHOL = dict(zip(_nd.date, (_gap >= 4).values))           # 다음 거래일까지 4일↑ = 연휴 전날
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (5, 20, 40)}
NDAY = len([d for d in ud if d >= "20160101"])
log(f"준비 완료 · {len(K):,}행")

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

def trimmed(r):
    """상위 5% 를 자른 평균 — 복권형(소수 대박이 끌어올린 평균)을 걸러내는 값."""
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan

# 유니버스 기준선 — 절삭평균은 반드시 이 값과 견줘야 한다
BASE_TRIM, BASE_MED, BASE_MEAN = {}, {}, {}
for h in (5, 20, 40):
    u = K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)
    BASE_TRIM[h], BASE_MED[h], BASE_MEAN[h] = trimmed(u), u.median(), u.mean()

HDR = (f"  {'기법':<32} {'n':>8} {'일':>6} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'절삭Δ':>7} "
       f"{'초과':>7} {'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>7}")
OK = []; NTRY = [0]
def show(tag, cond, h=5):
    NTRY[0] += 1
    d = dd(cond, h)
    if len(d) < 80: print(f"  {tag:<32} {len(d):>8}  (표본 부족)"); return
    st = dd(cond, h, lo="20050101", hi="20151231")
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    ci = boot_ci(d.groupby("ym").ex.mean()); yr = d.groupby(d.date.str[:4]).ex.mean()
    tm = trimmed(d.r); dtm = tm - BASE_TRIM[h]
    stx = st.ex.mean() if len(st) >= 80 else np.nan
    print(f"  {tag:<32} {len(d):>8,} {len(d)/NDAY:>6.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {tm:>7.2f} {dtm:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} "
          f"{va.ex.mean():>7.2f} {stx:>7.2f} {ci:>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")
    # 잣대: 절삭평균이 **유니버스보다** 높고 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑
    if dtm > 0 and d.ex.mean() > 0 and va.ex.mean() > 0 and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72:
        OK.append((tag, h, len(d), d.ex.mean(), va.ex.mean(), ci, int((yr > 0).sum()), len(yr)))

def cal(tag, mask, h=5):
    """날짜 기법 전용 — 그날 유니버스 평균을 나머지 날 평균과 견준다."""
    NTRY[0] += 1
    B = BEN[h]; B = B[B.index >= "20160101"]
    sel = pd.Series([bool(mask.get(d, False)) for d in B.index], index=B.index)
    a, b = B[sel], B[~sel]
    if len(a) < 40: print(f"  {tag:<32} {len(a):>8}  (날 부족)"); return
    diff = (a.groupby(a.index.str[:6]).mean() - b.groupby(b.index.str[:6]).mean()).dropna()
    yr = (a.groupby(a.index.str[:4]).mean() - b.groupby(b.index.str[:4]).mean()).dropna()
    print(f"  {tag:<32} {len(a):>7,}일 {'':>6} {'':>6} {a.mean():>7.2f} {a.median():>7.2f} "
          f"{'':>7} {'':>7} {a.mean()-b.mean():>7.2f} {'':>7} {'':>7} {'':>7} "
          f"{boot_ci(diff):>7.2f} {int((yr>0).sum()):>4}/{len(yr)}")

W = 166
print()
print("=" * W); print("① 기준선 — 유니버스(거래대금 상위 40% · $3↑ · 우선주 제외) 2016~"); print("=" * W)
print(f"  {'보유':<8}{'평균':>9}{'중앙':>9}{'절삭(상위5% 제거)':>22}")
for h in (5, 20, 40):
    print(f"  {h}일     {BASE_MEAN[h]:>9.2f}{BASE_MED[h]:>9.2f}{BASE_TRIM[h]:>18.2f}")
print("  → 절삭이 음수인 건 미장 수익이 소수 종목에 쏠려 있다는 뜻이다.")
print("    기법의 절삭평균은 0 이 아니라 **이 값**과 견줘야 한다(절삭Δ 열).")

print()
print("=" * W)
print("② 캘린더 — '아무 날' 과 견준다 (초과 = 그날 유니버스 평균 − 나머지 날 평균)")
print("=" * W)
print(f"  {'조건':<32} {'해당일':>8} {'':>6} {'':>6} {'평균':>7} {'중앙':>7} {'':>7} {'':>7} "
      f"{'차이':>7} {'':>7} {'':>7} {'':>7} {'CI':>7} {'연양수':>7}")
for h in (5, 20):
    print(f"  ── {h}일 보유 ──")
    cal("  월 뒤에서 5번째 거래일(TOM)", {d: TDMR[d] == 5 for d in ud}, h)
    cal("  월 뒤에서 5~1번째 거래일", {d: TDMR[d] <= 5 for d in ud}, h)
    cal("  월 첫 3거래일", {d: TDM[d] <= 3 for d in ud}, h)
    cal("  TOM 구간(뒤5 ~ 앞3)", {d: (TDMR[d] <= 5 or TDM[d] <= 3) for d in ud}, h)
    cal("  월 중간(그 외)", {d: not (TDMR[d] <= 5 or TDM[d] <= 3) for d in ud}, h)
    cal("  연휴 전날", PREHOL, h)
    cal("  월요일", {d: DOW[d] == 0 for d in ud}, h)
    cal("  화요일", {d: DOW[d] == 1 for d in ud}, h)
    cal("  11~4월", {d: int(d[4:6]) in (11, 12, 1, 2, 3, 4) for d in ud}, h)
    cal("  5~10월", {d: int(d[4:6]) in (5, 6, 7, 8, 9, 10) for d in ud}, h)
    print()

print("=" * W); print("③ Williams %R (종가 기준 근사) · 5일 보유"); print("=" * W); print(HDR)
show("%R ≤ -90 & 200일선 위", (K.wr <= -90) & K.up200)
show("%R ≤ -90 (필터 없음)", K.wr <= -90)
show("%R ≤ -80 & 200일선 위", (K.wr <= -80) & K.up200)
show("%R ≥ -10 & 200일선 위(반대쪽)", (K.wr >= -10) & K.up200)
show("%R ≤ -90 & 200위 & 20일선 위", (K.wr <= -90) & K.up200 & (K.close > K.ma20))

print()
print("=" * W); print("④ 추세 눌림목 (Trend Pullback · Holy Grail 근사)"); print("=" * W); print(HDR)
STRONG = (K.close > K.ma50) & (K.ma50 > K.ma200) & (K.ret60 >= 15)
show("20일선 되돌림 & 50>200 상승", K.pull20 & STRONG)
show("20일선 되돌림 & 200일선 위", K.pull20 & K.up200)
show("이격 -3~0% & 강추세", STRONG & (K.d20 <= 0) & (K.d20 >= -3))
show("이격 -3~0% & 강추세 · 20일", STRONG & (K.d20 <= 0) & (K.d20 >= -3), h=20)
show("20일선 되돌림 & 강추세 · 20일", K.pull20 & STRONG, h=20)

print()
print("=" * W); print("⑤ Stockbee 4% 버스트 (미국산 · 미국서 처음 잰다)"); print("=" * W); print(HDR)
show("4% 상승 & 거래량 1.5배", K.burst)
show("4% 버스트 & 200일선 위", K.burst & K.up200)
show("4% 버스트 & 200일선 아래", K.burst & ~K.up200)
show("4% 버스트 · 20일 보유", K.burst, h=20)

print()
print("=" * W); print("⑥ Quantpedia 횡단면 팩터 (한쪽 끝 10% 매수 · 20일 보유)"); print("=" * W); print(HDR)
Z = K[UNI]
def decile(name, col, asc, h=20):
    """asc=True 면 값이 작은 쪽을 산다(단기반전은 최근 수익이 낮은 쪽)."""
    r = Z.groupby("date")[col].rank(pct=True, ascending=asc)
    sel = pd.Series(False, index=K.index)
    sel.loc[r.index[(r <= 0.10).fillna(False).values]] = True
    show(name, sel, h)
decile("단기반전 5일수익 하위10%", "ret5", True)
decile("단기반전 20일수익 하위10%", "ret20", True)
decile("모멘텀 250일수익 상위10%", "ret250", False)
decile("저변동성 vol20 하위10%", "vol20", True)
decile("소형주 시총 하위10%", "marcap", True)
decile("저PBR 하위10%", "PBR", True)
decile("저PER 하위10%", "PER", True)

print()
print("=" * W)
print("⑦ 1차 최고 생존자 조이기 — Minervini 추세템플릿 · Frog-in-the-Pan")
print("=" * W); print(HDR)
FROG = K.multi & (K.ret250 >= 50) & (K.absr <= 1.5)
for h in (20, 40):
    print(f"  ── {h}일 보유 ──")
    show("  Minervini 원본", K.miner, h)
    show("  Minervini · 갓 통과(21일내 신규)", K.miner & (K.minew <= 5), h)
    show("  Minervini + 변동성 수축", K.miner & K.vsq, h)
    show("  Minervini + 20일선 위", K.miner & (K.close > K.ma20), h)
    show("  Frog-in-the-Pan 원본", FROG, h)
    show("  Frog + 변동성 수축", FROG & K.vsq, h)
    show("  Frog · 이산성 1.0 이하", K.multi & (K.ret250 >= 50) & (K.absr <= 1.0), h)
    show("  Frog · 1년수익 100%↑", K.multi & (K.ret250 >= 100) & (K.absr <= 1.5), h)
    show("  Minervini ∩ Frog", K.miner & FROG, h)
    print()

print("=" * W)
print("⑧ 집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for t, h, n, ex, va, ci, y, ny in OK:
        print(f"  ✅ {t:<32} {h:>2}일 · {n:>7,}건 · 초과 {ex:+.2f} · 검증 {va:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
try:
    import verdict; print("\n누적 시행:", verdict.log_trials("us_tech_web", NTRY[0]))
except Exception as e: print(e)
