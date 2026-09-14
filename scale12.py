# -*- coding: utf-8 -*-
"""**비중 1.2배를 재본다** (2026-09-15 요청).

slot_lab3 격자에서 국내 계좌는 비중 1.2배일 때 20.14배 / 낙폭 -12.4% 였다
(지금 1.0배는 15.99배 / -10.7%). 수익 +26% 에 낙폭 +1.7%p — 교환비가 나쁘지 않다.
그래서 한 경로가 아니라 제대로 재본다.

  ① 국내 — 1.0 / 1.1 / 1.2 / 1.3 배 랜덤 시드 짝비교 (자산·낙폭·시드 폭)
  ② **경로분포** — 백테스트 낙폭은 '실제로 겪을 낙폭' 이 아니다. 우리가 아는 역사는
     하나뿐이라 월블록 부트스트랩으로 '일어날 수 있었던 경로' 를 만들어 하위 꼬리를 본다.
     실전에서 백테스트에 없던 낙폭을 만나면 시스템이 깨졌다고 오판하고 그만두게 된다.
  ③ 미장 — 이미 노출 68% 라 여지가 다르다. 따로 잰다(캐시 사용).
  ④ 종목당 실제 금액 환산

    python scale12.py            (시드 12)
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
SCALES = (1.0, 1.1, 1.2, 1.3)
W = 100


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(SRC, "portfolio.py", "exec"), ns)
S0, simulate = ns["S"], ns["simulate"]
print(f"패널·신호 준비 {time.time()-t0:.0f}초")


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def monthly(C):
    return C.assign(ym=C.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100


sec("① 국내 계좌 — 배율별 (거래대금 큰 순 · 2005~26)")
CUR = {}
print(f"  {'배율':<8}{'노출':>7}{'최종자산':>11}{'연복리':>9}{'최대낙폭':>10}{'거래':>8}")
for s in SCALES:
    ns["S"] = S0
    C, L = simulate(1.0, s, "", quiet=True)
    CUR[s] = C
    yrs = len(C) / 252
    cagr = C.nav.iloc[-1] ** (1 / yrs) - 1
    print(f"  {str(s)+'배':<8}{C.expo.mean()*100:>6.0f}%{C.nav.iloc[-1]:>10.2f}배{cagr*100:>8.2f}%"
          f"{((C.nav/C.nav.cummax())-1).min()*100:>9.1f}%{len(L):>8,}")

sec(f"② 랜덤 {SEEDS}시드 짝비교 — 1.0배와 같은 시드에서 견준다")
print(f"  {'배율':<8}{'중앙':>9}{'최악':>9}{'최고':>9}{'폭':>7}{'낙폭중앙':>10}{'낙폭최악':>10}{'자산승':>8}{'낙폭승':>8}")
SEEDR = {}
for s in SCALES:
    rows = []
    for k in range(SEEDS):
        ns["S"] = shuffled(S0, k); x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(S0, k); y, _ = simulate(1.0, s, "", quiet=True)
        rows.append((y.nav.iloc[-1], x.nav.iloc[-1],
                     ((y.nav/y.nav.cummax())-1).min()*100, ((x.nav/x.nav.cummax())-1).min()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd"]); SEEDR[s] = R
    print(f"  {str(s)+'배':<8}{R.nav.median():>8.2f}배{R.nav.min():>8.2f}배{R.nav.max():>8.2f}배"
          f"{R.nav.max()/R.nav.min():>6.2f}x{R.mdd.median():>9.1f}%{R.mdd.min():>9.1f}%"
          f"{int((R.nav>R.base).sum()):>6}/{SEEDS}{int((R.mdd>R.bmdd).sum()):>6}/{SEEDS}")

sec("③ 경로분포 — '일어난 일' 말고 '일어날 수 있었던 일' (월블록 부트스트랩 5,000경로)")
print("  ⚠ 백테스트 낙폭은 우리가 아는 하나뿐인 역사의 값이다. 실전에서 그보다 깊은 낙폭을")
print("    만나면 시스템이 깨졌다고 오판하게 된다. 하위 꼬리를 미리 본다.\n")
from verdict import block_paths
print(f"  {'배율':<8}{'실제낙폭':>10}{'낙폭중앙':>10}{'하위5%':>9}{'하위1%':>9}"
      f"{'최장 언더워터(중앙/하위5%)':>26}{'자산중앙':>10}{'자산하위5%':>12}")
for s in SCALES:
    m = monthly(CUR[s])
    P = block_paths(m, n_paths=5000, mean_block=3)
    act = ((CUR[s].nav/CUR[s].nav.cummax())-1).min()*100
    print(f"  {str(s)+'배':<8}{act:>9.1f}%{P.mdd.median():>9.1f}%"
          f"{np.percentile(P.mdd,5):>8.1f}%{np.percentile(P.mdd,1):>8.1f}%"
          f"{P.under.median()/12:>13.1f}년{np.percentile(P.under,95)/12:>11.1f}년"
          f"{P.nav.median():>9.2f}배{np.percentile(P.nav,5):>11.2f}배")
print("\n  ※ '최장 언더워터' = 전고점을 회복하지 못한 채 보낸 가장 긴 기간. 실제로 버텨야 하는 시간이다.")

sec("④ 미장 — 이미 노출 68% 라 여지가 다르다")
CACHE = BASE / "data" / "sector_drop_us_sig.pkl"
if CACHE.exists():
    with open(CACHE, "rb") as f: Cc = pickle.load(f)
    SU, DS, ADI, PCT = Cc["S"], Cc["DS"], Cc["ADI"], Cc["PCT"]

    def usim(S, ds, scale=1.0, seed=None, cash_cap=1.0):
        rng = np.random.default_rng(seed) if seed is not None else None
        nav, held, cnt = 1.0, {}, {}
        byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
        peak, mdd, inv, cv = 1.0, 0.0, [], []
        for d in ds:
            di = ADI[d]
            for k in [k for k, v in held.items() if v[0] <= di]:
                nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
            peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
            inv.append(sum(PCT[k[0]] * scale for k in held) / 100); cv.append((d, nav))
            g = byd.get(d)
            if g is None: continue
            g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
                 else g.sort_values("amt20", ascending=False, na_position="last"))
            for r in g.itertuples():
                if cnt.get(r.rid, 0) >= r.mx: continue
                k = (r.rid, r.ticker, d)
                if k in held: continue
                if sum(PCT[x[0]] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap: continue
                held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100); cnt[r.rid] = cnt.get(r.rid, 0) + 1
        for v in held.values(): nav *= 1 + v[1] / 100
        return nav, mdd * 100, float(np.mean(inv)), pd.DataFrame(cv, columns=["date", "nav"])

    print(f"  {'배율':<8}{'노출':>7}{'자산':>10}{'낙폭':>9}   랜덤 30시드: {'중앙':>8}{'자산승':>8}{'낙폭승':>8}")
    b30 = [usim(SU, DS, 1.0, seed=k)[:2] for k in range(30)]
    for s in SCALES:
        nav, mdd, ex, _ = usim(SU, DS, s)
        r30 = [usim(SU, DS, s, seed=k)[:2] for k in range(30)]
        wn = sum(1 for a, b in zip(r30, b30) if a[0] > b[0])
        wm = sum(1 for a, b in zip(r30, b30) if a[1] > b[1])
        print(f"  {str(s)+'배':<8}{ex*100:>6.0f}%{nav:>9.2f}배{mdd:>8.1f}%"
              f"                 {np.median([x[0] for x in r30]):>8.2f}배{wn:>6}/30{wm:>6}/30")
else:
    print("  캐시 없음 — sector_drop_us.py 를 먼저 돌릴 것")

sec("⑤ 종목당 실제 금액 — 계좌가 1,000만원 / 3,000만원 / 5,000만원일 때")
print("  (비중은 계좌 100 기준. 1.2배면 아래 값에 1.2를 곱한 것이 실제 투입액이다)")
ALLOC = [("조용한 신고가", 12, 7), ("조정매집", 15, 2), ("폭락반등", 5, 3), ("업종붕괴 이탈", 3, 4),
         ("자사주 낙폭", 5, 3), ("깊은 이격", 4, 4), ("외인 매집", 4, 5),
         ("낙폭과대", 5, 3), ("저PBR 낙폭", 5, 3)]
for cap in (1000, 3000, 5000):
    print(f"\n  계좌 {cap:,}만원")
    print(f"    {'규칙':<16}{'지금(1.0배)':>13}{'1.2배':>12}{'차이':>10}")
    for nm, pct, mx in ALLOC:
        a = cap * pct / 100; b = a * 1.2
        print(f"    {nm:<16}{a:>10,.0f}만원{b:>9,.0f}만원{b-a:>+8,.0f}만원")
    break                     # 표가 길어 1,000만원 한 벌만 — 나머지는 비례
print(f"\n총 {time.time()-t0:.0f}초")
