# -*- coding: utf-8 -*-
"""채널 매매 실측 — 영상(2oyRMRah3k0)의 본체를 제대로 구현해 본다.

1차(fib_test.py)에서는 되돌림·트랩·페일만 쟀고 **채널 자체**는 안 건드렸다.
영상이 가르치는 건 세 점으로 채널을 잡고 그 안에서 지지·저항·돌파를 보는 것이다.
눈대중을 기계로 옮기려면 회귀 채널이 가장 정직하다.

  · 최근 L일 로그종가에 직선을 적합(OLS)한다 → 기울기 = 채널 방향
  · 잔차 표준편차 σ 로 폭을 잡는다 → pos = (오늘 - 적합값)/σ 가 채널 안 위치
  · 영상의 강조점 반영: 이탈 판정은 **종가** 기준이다(꼬리로 판단하지 않는다)

재는 것
  ① 채널 위치별 — 상승/하락/평행 채널 각각에서 하단·중간·상단에 있을 때
  ② 돌파 — 채널 밖으로 종가 마감(상단 위 / 하단 아래)
  ③ 복귀 — 밖으로 나갔다가 **다시 안으로 종가 마감한 날**(확정일이 신호일이다)
  ④ 살아남은 것에 우리 재료 얹기(업종·이격·기관·공매도·국면)

⚠ ③ 은 fib_test 에서 미리보기 버그가 났던 형태다. 신호일 = 복귀가 확정된 날로 잡는다.
⚠ OLS 는 롤링 합으로 닫힌 형태로 계산한다(rolling.apply 는 500만 행에서 못 쓴다).
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HS = [5, 20]
LB = 60                       # 채널 길이


def chan(K, L=LB):
    """회귀 채널. 롤링 합만으로 기울기·잔차σ·위치를 구한다."""
    g = K.groupby("ticker", sort=False)
    y = np.log(K.close.clip(lower=1))
    idx = g.cumcount().astype(float)                 # 종목별 전역 위치
    z = idx * y
    S1 = y.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).sum())
    Sz = z.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).sum())
    Vy = y.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).var(ddof=0))
    ybar = S1 / L
    start = idx - (L - 1)                            # 창의 첫 전역 위치
    Sxy = Sz - start * S1                            # 창 내부 좌표로 환산한 Σt·y
    tbar = (L - 1) / 2.0
    Stt = (L - 1) * L * (2 * L - 1) / 6.0
    slope = (Sxy - L * tbar * ybar) / (Stt - L * tbar ** 2)
    fit_last = ybar + slope * (L - 1 - tbar)         # 오늘 자리의 적합값
    vt = (L * L - 1) / 12.0
    sd = np.sqrt(np.clip(Vy - slope ** 2 * vt, 1e-12, None))
    K["slope"] = slope * 100 * 250                  # 연율 %로 보기 좋게
    K["pos"] = (y - fit_last) / sd                  # 채널 안 위치(σ 단위)
    K["chw"] = sd * 100                             # 채널 폭(로그·%)
    return K


def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["dev25"] = (K.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
    return chan(K)


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
    if len(X) < 300:
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
    if len(X) < 200:
        return None
    X["ex"] = X[col] - X.date.map(UNI[(mk, h)])
    tr, va = X[X.date <= TR1].ex, X[X.date >= VA0].ex
    if len(tr) < 80 or len(va) < 40:
        return None
    mo = X.assign(mm=X.date.str[:6]).groupby("mm").ex.mean()
    yr = X.assign(y=X.date.str[:4]).groupby("y").ex.mean()
    return dict(name=name, h=h, n=len(X), ex=X.ex.mean(), med=X.ex.median(),
                trim=X[X.ex <= X.ex.quantile(0.95)].ex.mean(),
                tr=tr.mean(), va=va.mean(), ci=verdict.boot_ci(mo, 0.10),
                win=(X[col] > 0).mean() * 100, pos=int((yr > 0).sum()), ny=len(yr))


NT, ROWS = 0, []
HDR = (f"    {'조건':<28}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
       f"{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")


def show(K, mk, nm, m):
    global NT
    for h in HS:
        NT += 1
        r = stat(K, mk, m, h, nm)
        if r is None:
            continue
        r["mk"] = mk; ROWS.append(r)
        print(f"    {nm:<28}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
              f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")


for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    b = base(K) & K.pos.notna()
    up, dn, flat = K.slope > 20, K.slope < -20, K.slope.abs() <= 20
    print("=" * 126)
    print(f"[{mk}] ① 채널 위치별 — 60일 회귀채널, 기울기로 상승/하락/평행 구분 (2016~)")
    print("=" * 126)
    print(HDR)
    for dnm, dm in (("상승채널", up), ("평행채널", flat), ("하락채널", dn)):
        for lo, hi, pnm in ((-99, -1.5, "하단밖"), (-1.5, -0.5, "하단"),
                            (-0.5, 0.5, "중간"), (0.5, 1.5, "상단"), (1.5, 99, "상단밖")):
            show(K, mk, f"{dnm} {pnm}", b & dm & (K.pos > lo) & (K.pos <= hi))
    print(f"\n[{mk}] ②③ 이탈과 복귀 — 판정은 종가. 복귀는 **확정된 날**이 신호일")
    print(HDR)
    g = K.groupby("ticker", sort=False)
    out_lo = K.pos <= -1.5
    out_hi = K.pos >= 1.5
    was_lo = pd.concat([g.pos.shift(k) for k in (1, 2, 3)], axis=1).min(axis=1) <= -1.5
    was_hi = pd.concat([g.pos.shift(k) for k in (1, 2, 3)], axis=1).max(axis=1) >= 1.5
    show(K, mk, "하단 이탈(오늘 종가 밖)", b & out_lo)
    show(K, mk, "하단 이탈 → 오늘 복귀", b & was_lo & (K.pos > -1.5))
    show(K, mk, "상단 이탈(오늘 종가 밖)", b & out_hi)
    show(K, mk, "상단 이탈 → 오늘 복귀", b & was_hi & (K.pos < 1.5))
    show(K, mk, "하락채널 상단 돌파", b & dn & out_hi)
    show(K, mk, "상승채널 하단 이탈", b & up & out_lo)
    print(f"\n[{mk}] ④ 우리 재료 얹기 — 하락장·업종붕괴·이격·기관·공매도")
    print(HDR)
    cand = b & dn & out_lo                                  # 하락채널 하단 이탈(가장 '떨어진' 자리)
    for nm2, extra in (("+ 업종 -10%↓", K.u <= -10), ("+ 25일선 -12%↓", K.dev25 <= -12),
                       ("+ 기관20일 0%↑", K.ow20 >= 0), ("+ 공매도 감소", K.srd == True),
                       ("+ 업종+이격", (K.u <= -10) & (K.dev25 <= -12))):
        show(K, mk, f"하락채널 하단이탈 {nm2}", cand & extra)
    print()

R = pd.DataFrame(ROWS)
print("=" * 126)
print("생존 후보 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0 · 양수해 70%↑")
print("=" * 126)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0) &
      (R.pos / R.ny >= 0.7)]
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<28} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} CI{r.ci:+.2f} 양수해 {r.pos}/{r.ny}")
else:
    print("  없음")
R.to_pickle(BASE / "data" / "chan_test.pkl")
verdict.log_trials("채널 매매", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
