# -*- coding: utf-8 -*-
"""피보나치 채널·파동 영상(2oyRMRah3k0) 실측 — 되돌림 비율 / 트랩 / 페일.

영상은 채널 그리는 법과 개념(트랩·페일)까지만 보여주고 정작 '채널 매매법' 은
고급편(유료)으로 미룬다. 그래서 기계로 잴 수 있는 세 가지만 고른다.

  ① 피보나치 되돌림 — "상승 파동의 38.2~61.8% 되돌림에서 반등한다"
     → 되돌림 깊이를 구간으로 나눠 앞으로의 수익이 정말 그 구간에서 좋은가?
       특별한 구간이 없다면 되돌림 비율은 그냥 '얼마나 빠졌나' 의 다른 이름일 뿐이다.
  ② 트랩(속임수 이탈) — 파동 저점을 깼다가 곧 되돌아오면 세력의 손절 유도다
     → 깨고 복귀한 것 vs 깨고 못 온 것, 앞으로의 수익이 다른가?
  ③ 페일 — 직전 고점까지 못 가고 꺾이면 하락 신호다
     → 직전 파동 고점 대비 얼마나 못 미쳤나로 나눠 본다.

파동은 눈대중이 아니라 기계로 잡는다. 최근 60일 안의 최고 종가를 파동 고점 H,
그 고점 **이전** 60일의 최저 종가를 파동 저점 L 로 둔다. 실제 상승이었는지 확인하려고
H/L ≥ 1.2(+20% 이상)만 남기고, 고점이 최근 40일 안에 있어야 '되돌림 중' 으로 본다.

판정은 늘 쓰던 것 — 유니버스 대비 초과 · 중앙값 · 상위5% 절삭 · 학습/검증 · 월블록 CI.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [5, 20, 60]


def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    # 파동 고점 H — 최근 60일 최고 종가와 그 위치
    K["H"] = g.close.transform(lambda s: s.rolling(60, min_periods=60).max())
    K["Hago"] = g.close.transform(
        lambda s: s.rolling(60, min_periods=60).apply(lambda a: len(a) - 1 - a.argmax(), raw=True))
    # 파동 저점 L — 고점보다 앞선 60일의 최저 종가. 고점 위치가 종목마다 달라
    # 간단히 '120일 최저' 로 근사하되 고점 이후 저점이 섞이지 않게 60일 시프트한 최저를 쓴다.
    lo120 = g.close.transform(lambda s: s.rolling(60, min_periods=60).min())
    K["L"] = g.close.transform(lambda s: s.rolling(120, min_periods=120).min())
    K["Lrecent"] = lo120
    K["ret60x"] = (K.close / g.close.shift(60) - 1) * 100
    return K


KP = load("panel_kp.pkl", "KOSPI")
KQ = load("panel_kq.pkl", "KOSDAQ")


def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))


UNI = {}
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    B = K[base(K)]
    for h in HS:
        UNI[(mk, h)] = B.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()


def stat(K, mk, m, h, name):
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 200:
        return None
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di)
    X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    X = X.loc[keep]
    if len(X) < 150:
        return None
    X["ex"] = X[col] - X.date.map(UNI[(mk, h)])
    tr, va = X[X.date <= TR1].ex, X[X.date >= VA0].ex
    if len(tr) < 60 or len(va) < 30:
        return None
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(name=name, h=h, n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X[X.ex <= X.ex.quantile(0.95)].ex.mean(),
                tr=tr.mean(), va=va.mean(), ci=verdict.boot_ci(mo, 0.10),
                win=(X[col] > 0).mean() * 100,
                pos=int((yr > 0).sum()), ny=len(yr))


NT = 0
ROWS = []

# ══════════════════════════════════════════════════════════════════════
# ① 피보나치 되돌림 — 38.2~61.8% 가 정말 특별한가
# ══════════════════════════════════════════════════════════════════════
print("=" * 122)
print("① 피보나치 되돌림 구간 — 상승 파동(H/L≥1.2)에서 얼마나 되돌렸나에 따라 (2016~)")
print("=" * 122)
FIB = [(0.0, 0.236, "0~23.6%"), (0.236, 0.382, "23.6~38.2%"), (0.382, 0.500, "38.2~50%"),
       (0.500, 0.618, "50~61.8%"), (0.618, 0.786, "61.8~78.6%"), (0.786, 1.000, "78.6~100%"),
       (1.000, 9.99, "100%↑(저점붕괴)")]
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    rng = (K.H - K.L).replace(0, np.nan)
    K["fib"] = (K.H - K.close) / rng                     # 되돌림 비율
    wave = base(K) & (K.H / K.L >= 1.2) & (K.Hago <= 40) & K.fib.notna()
    print(f"\n  [{mk}] 파동 조건 만족 {int(wave.sum()):,}행")
    print(f"    {'되돌림':<16}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
          f"{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")
    for lo, hi, nm in FIB:
        for h in HS:
            NT += 1
            r = stat(K, mk, wave & (K.fib > lo) & (K.fib <= hi), h, f"되돌림 {nm}")
            if r is None:
                continue
            r["mk"] = mk; ROWS.append(r)
            print(f"    {nm:<16}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
                  f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
                  f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")

# ══════════════════════════════════════════════════════════════════════
# ② 트랩 — 파동 저점을 깼다가 곧 복귀하면 속임수인가
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 122)
print("② 트랩(속임수 이탈) — 60일 저점을 깬 뒤 며칠 안에 되돌아온 것 vs 못 돌아온 것")
print("=" * 122)
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    # ⚠ 처음엔 '깬 날' 을 신호일로 잡고 복귀 여부를 close.shift(-d)(미래)로 판정했다.
    #   복귀는 1~3일 뒤에야 알 수 있는데 수익은 신호 다음날부터 쟀으니 미리보기다
    #   (그래서 승률 68%·CI +2.0 이라는 가짜 결과가 나왔다, 2026-09-09).
    #   바로잡는다: **복귀한 날**이 신호일이고, 판정에는 과거 데이터만 쓴다.
    g = K.groupby("ticker", sort=False)
    ref = g.close.transform(lambda s: s.rolling(60, min_periods=60).min().shift(4))
    broke_recent = pd.concat([g.close.shift(k) for k in (1, 2, 3)], axis=1).min(axis=1) < ref
    recovered = K.close > ref                            # 오늘 그 저점 위로 되돌아왔다
    broke = broke_recent & recovered                     # 트랩: 깼다가 오늘 복귀
    back = pd.Series(True, index=K.index)                # (아래 표기용)
    still = broke_recent & (K.close <= ref)              # 진짜 이탈: 아직 못 돌아옴
    b = base(K)
    print(f"\n  [{mk}]")
    print(f"    {'구분':<20}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
          f"{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")
    for nm, m in (("트랩(깨고 복귀)", b & broke),
                  ("진짜 이탈(못 복귀)", b & still)):
        for h in HS:
            NT += 1
            r = stat(K, mk, m, h, nm)
            if r is None:
                continue
            r["mk"] = mk; ROWS.append(r)
            print(f"    {nm:<20}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
                  f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
                  f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")

# ══════════════════════════════════════════════════════════════════════
# ③ 페일 — 직전 고점까지 못 가고 꺾이면 하락 신호인가
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 122)
print("③ 페일 — 반등했으나 직전 60일 고점에 얼마나 못 미쳤나 (반등 5일 이상 뒤 꺾인 날)")
print("=" * 122)
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    g = K.groupby("ticker", sort=False)
    hi60 = g.close.transform(lambda s: s.rolling(60, min_periods=60).max().shift(5))
    gap = (hi60 / K.close - 1) * 100                     # 직전 고점까지 남은 거리
    turn = (K.close < g.close.shift(1)) & (g.close.shift(1) > g.close.shift(2))  # 오늘 꺾임
    b = base(K) & turn & (K.ret5 > 0)                    # 5일 반등 뒤 꺾인 날
    print(f"\n  [{mk}]")
    print(f"    {'고점까지 남은 거리':<20}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}"
          f"{'승률':>6}{'학습':>8}{'검증':>8}{'월CI':>8}")
    for lo, hi, nm in ((0, 3, "3%↓(거의 도달)"), (3, 10, "3~10%"), (10, 25, "10~25%"),
                       (25, 999, "25%↑(크게 못 감)")):
        for h in HS:
            NT += 1
            r = stat(K, mk, b & (gap > lo) & (gap <= hi), h, f"페일 {nm}")
            if r is None:
                continue
            r["mk"] = mk; ROWS.append(r)
            print(f"    {nm:<20}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
                  f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
                  f"{r['ci']:>+8.2f}")

R = pd.DataFrame(ROWS)
print("\n" + "=" * 122)
print("생존 후보 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0")
print("=" * 122)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0)]
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<20} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} CI{r.ci:+.2f}")
else:
    print("  없음")
R.to_pickle(BASE / "data" / "fib_test.pkl")
verdict.log_trials("피보나치 채널·파동", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
