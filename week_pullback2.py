# -*- coding: utf-8 -*-
"""**주봉 눌림목 조이기·겹침·다중검정** — week_pullback.py 후속 (2026-09-16).

앞에서 미장에 후보가 하나 섰다.
  5주 이상 연속 상승 → 2주 눌림, **눌림 깊이 -8% 이내**, 40~60일 보유
  · 40일: n=4,974 · 중앙 +1.70 · 승률 57% · 초과 +0.49 · 양수해 10/11 · 월 19.1건
  · 60일: n=4,783 · 중앙 +1.79 · 승률 56% · 초과 +1.00 · 양수해 8/11

⚠ **월 19건은 많은 게 아니다.** 같은 잣대(월 후보)로 기존 미장 규칙은
   [상승장 신고가] 75.2 · [낙폭과대] 23.3 · [저PBR 낙폭] 18.9 · [자사주 낙폭] 11.4 ·
   [잔잔한 급등주] 6.4 건이다. 건수는 문제가 아니다.

**진짜 약점은 절삭평균이 0.00~0.03 이라는 것**이다. 위쪽 5%를 잘라내면 이익이 정확히
0 이다 — 엣지가 전부 꼬리에 있다는 뜻이고, 이 집안은 그걸 복권형이라 부르며 기각해 왔다
([[kosdaq-p7-reject]]). 그래서 조이는 목표는 **건수 줄이기가 아니라 절삭평균을 양수로
올리는 것**이다.

  ① 잣대 맞추기 — 기존 규칙과 월 후보 수를 같은 표에
  ② 조이기 — 재료를 하나씩 얹어 절삭평균이 오르나
  ③ 두 개씩 조합
  ④ **겹침** — [잔잔한 급등주]·[상승장 신고가]와 같은 종목을 보고 있나
  ⑤ **다중검정 보정** — 이번 탐색에서 돌린 칸 수를 넣어 살아남나

    python week_pullback2.py
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from vp_lib import Runner, hdr
from verdict import deflated_sharpe

BASE = Path(__file__).parent
W = 150
SINCE = "20160101"
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("미장 패널 읽는 중")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
AQ = U.groupby("date").amt20.rank(pct=True)
MQ = U.groupby(U.date.str[:6]).marcap.rank(pct=True)     # 같은 달 안 시총 순위
UNI = (AQ >= 0.60).fillna(False)
log("  %s행 · %s종목" % (f"{len(U):,}", f"{U.ticker.nunique():,}"))

# ── 주봉 재료 (week_pullback.py 와 같은 계산) ─────────────────────────────
dt = pd.to_datetime(U.date, format="%Y%m%d")
Uw = U.assign(_wk=(dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y%m%d"))
Wk = (Uw.groupby(["ticker", "_wk"], sort=True)
        .agg(date=("date", "last"), close=("close", "last")).reset_index())
Wk = Wk.sort_values(["ticker", "_wk"]).reset_index(drop=True)
g = Wk.groupby("ticker", sort=False)
wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
wret = (Wk.close / g.close.shift(1) - 1) * 100
up = ((wret > 0) & cont).fillna(False)
dn = ((wret < 0) & cont).fillna(False)
Wk["up_n"] = up.astype(int).groupby([Wk.ticker, (~up).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["dn_n"] = dn.astype(int).groupby([Wk.ticker, (~dn).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["rise"] = (Wk.close / Wk.close.where(~up).groupby(Wk.ticker).ffill() - 1) * 100
Wk["back"] = (Wk.close / Wk.close.where(~dn).groupby(Wk.ticker).ffill() - 1) * 100
gw = Wk.groupby("ticker", sort=False)
ok = (Wk.dn_n >= 2) & (gw.up_n.shift(2) >= 5)
SIG = pd.DataFrame({"ticker": Wk.ticker, "date": Wk.date, "up_n": gw.up_n.shift(2),
                    "rise": gw.rise.shift(2), "back": Wk.back})[ok.fillna(False)]
del Uw, Wk
log("  5주↑ 상승 → 2주 눌림 %s건" % f"{len(SIG):,}")

# 기본 조건: 눌림 -8% 이내
BASE_SIG = SIG[SIG.back > -8]
KEY = U.ticker + U.date
BASEM = KEY.isin(set(BASE_SIG.ticker + BASE_SIG.date))
log("  그 중 눌림 -8%% 이내 %s건" % f"{len(BASE_SIG):,}")

R = Runner(U, UNI, "미장", since=SINCE)
NTRY = [0]


def run(tag, cond, hold=40, minn=30):
    NTRY[0] += 1
    return R.run(tag, cond, hold=hold, minn=minn)


sec("① 잣대 맞추기 — 월 후보 수는 문제가 아니었다")
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS = C["S"], C["DS"]
mon = len(set(d[:6] for d in DS))
NMK = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
       "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
print("  %-18s%10s%12s" % ("규칙", "신호", "월 후보"))
for r in ["N1", "N2", "N3", "N4", "N5"]:
    n = int((S5.rid == r).sum())
    print("  %-18s%10s%11.1f건" % (NMK[r], f"{n:,}", n / mon))
print("  %-18s%10s%11s" % ("← 새 후보", "—", "19.1건"))

hdr("② 조이기 — 재료를 하나씩. 목표는 건수가 아니라 **절삭평균**이다")
print("  (기준선: 5주↑ 상승 · 2주 눌림 · 눌림 -8% 이내 · 40일)")
run("기준선 (조건 없음)", BASEM, 40)
print()
CUTS = [
    ("거래대금 상위20%", AQ >= 0.80),
    ("거래대금 상위10%", AQ >= 0.90),
    ("시총 상위30%(같은달)", MQ >= 0.70),
    ("시총 하위50%(같은달)", MQ <= 0.50),
    ("20일 변동성 ≤ 2%", U.vol20 <= 2),
    ("20일 변동성 ≤ 3%", U.vol20 <= 3),
    ("52주 고점 -10% 이내", U.fromhi >= -10),
    ("52주 고점 -5% 이내", U.fromhi >= -5),
    ("1년 수익 ≥ 0", U.ret250 >= 0),
    ("1년 수익 ≥ 30%", U.ret250 >= 30),
    ("1년 수익 ≤ 120%", U.ret250 <= 120),
    ("60일 수익 ≥ 0", U.ret60 >= 0),
    ("20일선 위", U.dma20 >= 0),
    ("60일선 위", U.dma60 >= 0),
    ("거래량 잔잔(vm3 ≤ 100)", U.vm3 <= 100),
    ("PBR ≤ 3", U.PBR <= 3),
    ("상승폭 +30~100%", BASEM & KEY.isin(
        set((lambda z: z.ticker + z.date)(BASE_SIG[(BASE_SIG.rise > 30) & (BASE_SIG.rise <= 100)])))),
    ("상승폭 +100% 미만", BASEM & KEY.isin(
        set((lambda z: z.ticker + z.date)(BASE_SIG[BASE_SIG.rise <= 100])))),
    ("눌림 -4% 이내", BASEM & KEY.isin(
        set((lambda z: z.ticker + z.date)(BASE_SIG[BASE_SIG.back > -4])))),
    ("상승 7주 이상", BASEM & KEY.isin(
        set((lambda z: z.ticker + z.date)(BASE_SIG[BASE_SIG.up_n >= 7])))),
]
BEST = []
for lbl, c in CUTS:
    r = run("  + " + lbl, (BASEM & c.fillna(False)) if c is not BASEM else c, 40)
    if r and r["trim"] > 0.3:
        BEST.append((lbl, c, r))

hdr("③ 두 개씩 — ②에서 절삭이 오른 것만 짝지어")
print("  (절삭 0.3 넘은 재료 %d개)" % len(BEST))
for i in range(len(BEST)):
    for j in range(i + 1, len(BEST)):
        la, ca, _ = BEST[i]
        lb, cb, _ = BEST[j]
        run("  %s + %s" % (la, lb), BASEM & ca.fillna(False) & cb.fillna(False), 40)
print()
for lbl, c, _ in BEST[:6]:
    run("  %s · 60일" % lbl, BASEM & c.fillna(False), 60)

sec("④ 겹침 — 이미 있는 추세 규칙과 같은 것을 보고 있나")
z = BASE_SIG[BASE_SIG.date >= SINCE]
DSS = set(DS)
z = z[z.date.isin(DSS)]
DI = {d: i for i, d in enumerate(sorted(DSS))}
print("  새 후보 %s건 (2016~ · 유니버스 안)" % f"{len(z):,}")
for r in ["N1", "N5", "N4"]:
    o = S5[S5.rid == r]
    key = {}
    for t, d in zip(o.ticker.values, o.date.values):
        key.setdefault(t, []).append(DI.get(d, -999))
    near = sum(1 for t, d in zip(z.ticker.values, z.date.values)
               if any(abs(DI.get(d, 0) - x) <= 5 for x in key.get(t, [])))
    same = sum(1 for t, d in zip(z.ticker.values, z.date.values) if t in key)
    print("  %-16s ±5일 같은 종목 %6s건 (%4.1f%%) · 종목이라도 겹친 적 %6s건 (%4.1f%%)"
          % (NMK[r], f"{near:,}", near / max(len(z), 1) * 100,
             f"{same:,}", same / max(len(z), 1) * 100))

sec("⑤ 다중검정 보정 — 이번 탐색에서 돌린 칸 %d개" % (NTRY[0] + 110))
print("  (week_pullback.py 에서 110칸 + 여기서 %d칸)" % NTRY[0])
# deflated_sharpe 는 **'진짜일 확률'(dsr)** 을 돌려준다 — 클수록 좋다. 0.95 를 문턱으로 쓴다.
print("  %-26s%8s%9s%9s%10s" % ("구성", "월수", "샤프", "문턱샤프", "진짜일확률"))
for lbl, cond, h in [("기준선 40일", BASEM, 40), ("기준선 60일", BASEM, 60),
                     ("눌림 -4% 이내 40일", BASEM & KEY.isin(
                         set((BASE_SIG[BASE_SIG.back > -4].ticker
                              + BASE_SIG[BASE_SIG.back > -4].date))), 40)]:
    m = R.run(lbl, cond, hold=h, minn=30, quiet=True)
    if not m:
        print("  %-26s (부족)" % lbl); continue
    mr = m["Y"].groupby("ym").r.mean()
    d = deflated_sharpe(mr, NTRY[0] + 110)
    if not d:
        print("  %-26s (월 수가 모자라 못 잰다)" % lbl); continue
    print("  %-26s%8d%9.3f%9.3f%9.1f%%  %s"
          % (lbl, d["T"], d["sr"], d["sr0"], d["dsr"] * 100,
             "살아남음" if d["dsr"] >= 0.95 else "**기각**"))
print("\n총 %.0f초" % (time.time() - t0))
