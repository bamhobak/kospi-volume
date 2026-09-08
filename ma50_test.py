# -*- coding: utf-8 -*-
"""50일선 매매법 실측 (dcinside krstock 3416237).

규칙
  매수 ① 주가가 50일선 위로 올라올 때(상향 돌파)
       ② 50일선 위에 있던 주가가 눌렸다가 50일선을 찍고 반등할 때
  매도 · 종가가 50일선 아래로 → 절반
       · 5일선이 50일선 아래로 → 전량
  보유 · 50일선 위면 계속. 오래 들수록 크게 번다
  금지 · 50일선 아래에서는 진입하지 않는다

재는 것
  ① 진입 신호로 환산 — 보유 5·20·60일, 유니버스 대비 초과(우리 규칙과 같은 잣대)
  ② **50이 특별한가** — 20·30·40·50·60·80·120 을 나란히 놓는다.
     전부 비슷하면 '50' 은 서양에서 그렇게 쓴다는 관습일 뿐 숫자에 정보가 없는 것이다.
  ③ 시스템 전체 — 50일선 위면 보유·아래면 절반·5일선까지 깨면 전량, 항상보유와 머리 맞대기
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
MAS = [20, 30, 40, 50, 60, 80, 120]


def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    for m in MAS:
        K[f"m{m}"] = g.close.transform(lambda s: s.rolling(m, min_periods=m).mean())
    K["m5"] = g.close.transform(lambda s: s.rolling(5, min_periods=5).mean())
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
HDR = (f"    {'조건':<26}{'보유':>4}{'건수':>7}{'초과':>8}{'중앙':>8}{'절삭':>8}{'승률':>6}"
       f"{'학습':>8}{'검증':>8}{'월CI':>8}{'양수해':>7}")


def show(K, mk, nm, m):
    global NT
    for h in HS:
        NT += 1
        r = stat(K, mk, m, h, nm)
        if r is None:
            continue
        r["mk"] = mk; ROWS.append(r)
        print(f"    {nm:<26}{h:>4}{r['n']:>7,}{r['ex']:>+8.2f}{r['med']:>+8.2f}"
              f"{r['trim']:>+8.2f}{r['win']:>5.0f}%{r['tr']:>+8.2f}{r['va']:>+8.2f}"
              f"{r['ci']:>+8.2f}{r['pos']:>4}/{r['ny']}")


print("=" * 122)
print("① 50일선 매매법 두 진입 — 상향돌파 / 눌림 후 지지반등 (2016~)")
print("=" * 122)
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    g = K.groupby("ticker", sort=False)
    b = base(K)
    ma = K.m50
    cross = (K.close > ma) & (g.close.shift(1) <= g.m50.shift(1))          # 상향 돌파
    # 지지반등 — 50일선 위에 있었고, 저가가 선을 찍었으며, 종가는 위
    above5 = (g.close.shift(1) > g.m50.shift(1)) & (g.close.shift(5) > g.m50.shift(5))
    touch = (K.low <= ma * 1.02) & (K.close > ma)
    print(f"\n  [{mk}]")
    print(HDR)
    show(K, mk, "50일선 상향돌파", b & cross)
    show(K, mk, "50일선 지지반등", b & above5 & touch)
    show(K, mk, "돌파 + 장대양봉(+3%↑)", b & cross & ((K.close - K.open) / K.open * 100 >= 3))
    show(K, mk, "돌파 + 거래량 2배↑", b & cross & (K.su1 >= 2))
    show(K, mk, "참고: 50일선 아래(금지구간)", b & (K.close < ma))

print("\n" + "=" * 122)
print("② 50 이 특별한가 — 이평 기간을 바꿔 상향돌파를 나란히 (보유 20일만)")
print("=" * 122)
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    g = K.groupby("ticker", sort=False)
    b = base(K)
    print(f"\n  [{mk}]  {'기간':<8}{'건수':>8}{'초과':>9}{'중앙':>9}{'절삭':>9}{'승률':>7}"
          f"{'학습':>9}{'검증':>9}{'월CI':>9}")
    for m in MAS:
        NT += 1
        c = b & (K.close > K[f"m{m}"]) & (g.close.shift(1) <= g[f"m{m}"].shift(1))
        r = stat(K, mk, c, 20, f"{m}일선 돌파")
        if r is None:
            continue
        r["mk"] = mk; ROWS.append(r)
        star = " ←" if m == 50 else ""
        print(f"        {str(m)+'일선':<8}{r['n']:>8,}{r['ex']:>+9.2f}{r['med']:>+9.2f}"
              f"{r['trim']:>+9.2f}{r['win']:>6.0f}%{r['tr']:>+9.2f}{r['va']:>+9.2f}"
              f"{r['ci']:>+9.2f}{star}")

print("\n" + "=" * 122)
print("③ 시스템 전체 — 50일선 위면 보유 / 아래면 절반 / 5일선까지 깨면 전량")
print("=" * 122)
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    Z = K[base(K)].copy()
    g = Z.groupby("ticker", sort=False)
    Z["r"] = (g.close.shift(-1) / Z.close - 1) * 100          # 다음날 수익
    Z["w"] = np.where(Z.close > Z.m50, 1.0,
                      np.where(Z.m5 > Z.m50, 0.5, 0.0))        # 오늘 판정 → 내일 비중
    Z["w"] = g.w.shift(0)
    Z = Z.dropna(subset=["r", "w"])
    Z = Z[Z.date >= "20050101"]
    D = Z.groupby("date").apply(lambda x: pd.Series(
        {"sys": (x.w * x.r).sum() / max(len(x), 1), "bh": x.r.mean(), "on": x.w.mean()}))
    D = D.sort_index()
    cost = D.on.diff().abs().fillna(0) * 1.15                  # 비중 바뀐 만큼 왕복비용
    D["sys"] = D.sys - cost
    def mdd(s):
        v = (1 + s / 100).cumprod()
        return float((v / v.cummax() - 1).min() * 100)
    print(f"\n  [{mk}] 평균 투입비중 {D.on.mean()*100:.0f}% · 거래일 {len(D):,}")
    for pn, lo, hi in (("학습 2016~22", "20160101", "20221231"),
                       ("검증 2023~26", "20230101", "20991231"),
                       ("전구간 2005~26", "20050101", "20991231")):
        z = D[(D.index >= lo) & (D.index <= hi)]
        if len(z) < 250:
            continue
        s = (1 + z.sys / 100).prod(); bb = (1 + z.bh / 100).prod(); yr = len(z) / 250
        print(f"    {pn:<14} 50일선 {s:>7.2f}배(연{(s**(1/yr)-1)*100:>6.1f}%) 낙폭{mdd(z.sys):>6.0f}%"
              f"  |  항상보유 {bb:>7.2f}배(연{(bb**(1/yr)-1)*100:>6.1f}%) 낙폭{mdd(z.bh):>6.0f}%")

R = pd.DataFrame(ROWS)
print("\n" + "=" * 122)
print("생존 후보 — 중앙>0 · 절삭>0 · 학습·검증 둘 다>0 · 월CI>0 · 양수해 70%↑")
print("=" * 122)
G = R[(R.med > 0) & (R.trim > 0) & (R.tr > 0) & (R.va > 0) & (R.ci > 0) & (R.pos / R.ny >= 0.7)]
if len(G):
    for _, r in G.sort_values("ci", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<26} {r.h}일 · {r.n:>6,}건 · 초과 {r.ex:+.2f}%p "
              f"중앙 {r.med:+.2f} 절삭 {r.trim:+.2f} CI{r.ci:+.2f} 양수해 {r.pos}/{r.ny}")
else:
    print("  없음")
verdict.log_trials("50일선 매매법", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
