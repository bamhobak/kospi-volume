# -*- coding: utf-8 -*-
"""**[상승장 신고가] — 비중 재검증 + 변형 탐색** (2026-09-15).

⚠ 먼저 정정: us_n1_worth3.py 의 '단독 계좌(노출 20% 맞춤)' 는 **설계가 틀렸다**.
   배율로 노출을 맞추려 했는데, 배율을 올리면 종목당 비중이 cash_cap(100%)을 넘어
   **아무것도 못 사게 되고 노출이 0으로 떨어진다**([상승장 신고가]가 딱 그 경우 —
   배율 20·노출 0%·1.00배). 노출은 배율에 대해 단조증가가 아니다.
   그리고 규칙마다 신호 빈도가 달라 같은 노출을 만들면 **집중도가 달라진다**
   ([낙폭과대]는 한 종목에 63%를 걸게 되어 낙폭 -63%가 나왔다 — 규칙 성적이 아니다).
   → 단독 비교는 **자연 노출 그대로** 두고 '노출 1%당' 으로 견주는 게 맞다.

그 다음 변형 탐색. 이미 판 것(반복 금지):
   진입 조이기·시총·보유일 → 계좌 손해 / 거래량 식음(remo≤100) → **채택** /
   청산(손절·익절·국면이탈·트레일) → **전부 기각** / 이벤트형(nh5) → **채택** /
   pinned·DEAD → **채택** / a240 상위20% → 기각 / 상승장 2호 → 기각

아직 안 판 축 — 오늘 발견에서 따라온 것들이다. 미장 낙폭 꼬리가 -52.9% 인 이유가
**자리 4개가 한꺼번에 물리는 것**이라면, 답은 진입 조건이 아니라 **분산**에 있다.
   ① 자리 수 (1~6)                — 노출 맞춤에서 4→2 가 유일하게 기준을 이겼다
   ② 하루 진입 상한               — 같은 날 다 채우지 말고 며칠에 걸쳐 (시간 분산)
   ③ 섹터 상한                     — 같은 업종 몇 개까지 (업종 분산)
   ④ 둘을 겹친 것

    python us_n1_lab.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 30
W = 112
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f: C = pickle.load(f)
S0, DS, ADI, PCT0 = C["S"], C["DS"], C["ADI"], C["PCT"]
RID = ["N1", "N2", "N3", "N4", "N5"]
TK = pd.read_csv(BASE / "data/us/tickers.csv")
SEC = dict(zip(TK.Symbol.astype(str), TK.Industry.astype(str)))
YRS = len(DS) / 252


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


def sim(S, PCT, ds, scale=1.0, seed=None, cash_cap=1.0, curve=False,
        perday=None, persec=None, mxover=None):
    """perday: 그 규칙의 하루 진입 상한 · persec: 같은 업종 동시보유 상한 · mxover: 자리 수 덮어쓰기"""
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv, log = 1.0, 0.0, [], [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] * scale for k in held) / 100)
        if curve: cv.append((d, nav))
        g = byd.get(d)
        if g is None: continue
        g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
             else g.sort_values("amt20", ascending=False, na_position="last"))
        today = 0
        for r in g.itertuples():
            mx = mxover.get(r.rid, r.mx) if mxover else r.mx
            if cnt.get(r.rid, 0) >= mx: continue
            if perday and r.rid in perday and today >= perday[r.rid]: continue
            if persec and r.rid in persec:
                s_ = SEC.get(r.ticker, "?")
                if sum(1 for x in held if x[0] == r.rid and SEC.get(x[1], "?") == s_) >= persec[r.rid]:
                    continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(PCT[x[0]] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1; today += 1
            log.append((r.rid, r.ret, r.pct * scale / 100))
    for v in held.values(): nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("① [정정] 단독 계좌 — 자연 노출 그대로. 배율로 노출을 맞추면 안 된다")
print(f"  {'규칙':<16}{'체결':>7}{'노출':>7}{'자산':>9}{'연복리':>9}{'낙폭':>9}{'노출1%당 연수익':>16}")
for r in RID:
    S = S0[S0.rid == r].reset_index(drop=True)
    a = sim(S, {r: PCT0[r]}, DS)
    cg = (a["nav"] ** (1 / YRS) - 1) * 100
    e = a["expo"] * 100
    print(f"  {NM[r]:<16}{len(a['L']):>7,}{e:>6.1f}%{a['nav']:>8.2f}배{cg:>8.2f}%{a['mdd']:>8.1f}%"
          f"{cg/max(e,0.01):>15.2f}")
print("\n  ※ '노출1%당 연수익' 이 자본 효율이다. 신호 빈도가 달라 노출 자체를 맞출 수는 없다.")

# ══════════════════════════════════════════════════════════════════════════
base = sim(S0, PCT0, DS)
b30 = [sim(S0, PCT0, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b30]; BM = [x["mdd"] for x in b30]


def show(lbl, **kw):
    a = sim(S0, PCT0, DS, curve=True, **kw)
    r30 = [sim(S0, PCT0, DS, seed=k, **kw) for k in range(NS)]
    n30 = [x["nav"] for x in r30]; m30 = [x["mdd"] for x in r30]
    wn = sum(1 for x, y in zip(n30, BN) if x > y); wm = sum(1 for x, y in zip(m30, BM) if x > y)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    P = block_paths(m, n_paths=3000, mean_block=3)
    print(f"  {lbl:<26}{a['expo']*100:>6.0f}%{a['nav']:>8.2f}배{a['mdd']:>8.1f}%"
          f"{np.median(n30):>9.2f}배{wn:>5}/{NS}{wm:>5}/{NS}"
          f"{np.percentile(P.mdd,1):>10.1f}%{np.percentile(P.nav,5):>9.2f}배")
    return a


HDR = (f"  {'구성':<26}{'노출':>7}{'자산':>9}{'낙폭':>9}{'30시드중앙':>11}{'자산승':>7}{'낙폭승':>7}"
       f"{'낙폭하위1%':>11}{'자산하위5%':>11}")
sec("② 자리 수 — [상승장 신고가]만 바꾼다 (비중 10 고정)")
print(HDR)
show("지금 (자리 4)")
for m in (1, 2, 3, 5, 6):
    show(f"자리 {m}", mxover={"N1": m})

sec("③ 하루 진입 상한 — 같은 날 다 채우지 말고 며칠에 걸쳐 (시간 분산)")
print(HDR)
for p in (1, 2):
    show(f"하루 {p}개까지", perday={"N1": p})
for p in (1, 2):
    show(f"하루 {p}개 · 자리 6", perday={"N1": p}, mxover={"N1": 6})

sec("④ 업종 상한 — 같은 업종을 몇 개까지 (업종 분산)")
print(HDR)
for s in (1, 2):
    show(f"업종당 {s}개까지", persec={"N1": s})
for s in (1, 2):
    show(f"업종당 {s}개 · 자리 6", persec={"N1": s}, mxover={"N1": 6})

sec("⑤ 겹치기 — 시간 분산 + 업종 분산")
print(HDR)
show("하루1 · 업종1 · 자리 4", perday={"N1": 1}, persec={"N1": 1})
show("하루1 · 업종1 · 자리 6", perday={"N1": 1}, persec={"N1": 1}, mxover={"N1": 6})
show("하루1 · 업종2 · 자리 6", perday={"N1": 1}, persec={"N1": 2}, mxover={"N1": 6})
show("하루2 · 업종2 · 자리 6", perday={"N1": 2}, persec={"N1": 2}, mxover={"N1": 6})
