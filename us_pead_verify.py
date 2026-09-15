# -*- coding: utf-8 -*-
"""**[실적 서프라이즈] 사이트 정의 대조** (2026-09-15).

⚠ 이 단계를 건너뛰면 안 된다. [자사주 낙폭] 은 재구성이 사이트의 **2.35배**로 헐거웠는데
   그걸 모르고 "계좌에서 마이너스" 라고 보고했다가 하루를 날렸다. 규칙을 넣기 전에
   **사이트가 쓸 재료·조건 그대로** 만들어 백테스트 신호 건수와 맞는지 먼저 본다.

사이트가 쓸 조건(collect_us_daily.py 가 만드는 재료로):
    usliq(거래대금 상위40%) & close>=3 & !pref
    & peadq >= 0.7          (서프라이즈 백분위 — 그날 발표분 안)
    & peadgap >= 3          (발표 **다음 거래일**의 전일 대비 등락률)
    & peadage <= 7          (그 신호일로부터 7거래일 안 — 주 1회 수집의 지연을 흡수)
    → 다음날 시가 매수 · 60거래일 보유

백테스트(us_pead.py)는 **peadage = 0** (발표 다음날 당일)만 봤다. 그래서 건수는
사이트 쪽이 더 많아야 정상이다 — 같은 사건이 최대 8일간 후보로 남기 때문이다.
**중복 제거 뒤 건수**가 맞는지를 본다(같은 종목을 보유기간 안에 다시 안 산다).

  ① peadage=0 만 — 백테스트와 **같은 정의**. 건수가 맞아야 한다.
  ② peadage<=7 — 사이트가 실제로 쓸 정의. 중복 제거 뒤 건수와 성적.
  ③ 둘의 성적 차이 — 유예를 두는 대가

    python us_pead_verify.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 124
SINCE = "20160101"
HOLD = 60
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# ── 실적 (백테스트와 같은 원천) ───────────────────────────────────────────
fs = sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
E["sur"] = E["Surprise(%)"].astype(float)

log("us_scan.pkl")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
UNI = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}

# ⚠ 사이트는 **발표일 안에서** 백분위를 매긴다(collect_us_daily.py 후처리).
#   백테스트(us_pead.py)는 **다음 거래일(bdate)** 안에서 매겼다. 휴일이 끼면 서로 다른
#   발표일이 같은 bdate 가 되므로 미세하게 다를 수 있다 — 그 차이도 여기서 확인한다.
sz = E.groupby("edate").sur.transform("size")
E["q_edate"] = E.groupby("edate").sur.rank(pct=True)
E = E[sz >= 5].copy()
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
sz2 = E.groupby("bdate").sur.transform("size")
E["q_bdate"] = E.groupby("bdate").sur.rank(pct=True)

A["_k"] = A.ticker + A.date
A["qe"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q_edate)))     # 사이트 방식
A["qb"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q_bdate)))     # 백테스트 방식
A["gap"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
log("  신호일 후보 %s행" % f"{int(A.qe.notna().sum()):,}")


def dedup(z, h=HOLD):
    z = z.sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return z.loc[keep]


def show(tag, cond):
    z = A[cond.fillna(False)].dropna(subset=[f"n{HOLD}"])
    z = z[(z.buy > 0) & (z.date >= SINCE)]
    raw = len(z)
    Y = dedup(z).copy()
    v = Y[f"n{HOLD}"].astype(float)
    trim = v[v <= v.quantile(0.95)].mean()
    yr = Y.assign(y=Y.date.str[:4]).groupby("y")[f"n{HOLD}"].median()
    print("  %-34s%8s%8s%9.2f%9.2f%7.0f%%%9.2f%8.2f%7d/%d"
          % (tag, f"{raw:,}", f"{len(Y):,}", v.mean(), v.median(), (v > 0).mean() * 100,
             trim, yr.get("2026", np.nan), int((yr > 0).sum()), len(yr)))
    return len(Y), v


print("\n" + "=" * W)
print("[실적 서프라이즈] 사이트 정의 대조 — 백테스트 5,009건과 맞는가")
print("=" * W)
print("  %-34s%8s%8s%9s%9s%7s%9s%8s%8s"
      % ("정의", "중복전", "중복후", "평균", "중앙", "승률", "절삭", "2026", "양수해"))

BT = UNI & A.qb.notna() & (A.qb >= 0.7) & (A.gap >= 3)
n_bt, v_bt = show("백테스트 정의 (bdate 백분위)", BT)

SITE0 = UNI & A.qe.notna() & (A.qe >= 0.7) & (A.gap >= 3)
n_s0, v_s0 = show("사이트 정의 · peadage=0", SITE0)

# peadage<=7 — 신호일로부터 7거래일 안이면 계속 후보
sig = np.zeros(len(A), bool)
si = np.where(SITE0.fillna(False).values)[0]
tick = A.ticker.values
for k in range(0, 8):
    j = np.minimum(si + k, len(A) - 1)
    ok = tick[j] == tick[si]
    sig[j[ok]] = True
SITE7 = UNI & pd.Series(sig, index=A.index) & (A.rawclose >= 3)
n_s7, v_s7 = show("사이트 정의 · peadage<=7", SITE7)

print("\n" + "=" * W)
print("판정")
print("=" * W)
rt = n_s0 / max(n_bt, 1)
print("  ① 백테스트(5,009) vs 사이트 peadage=0 : %s vs %s  → %.2fx  %s"
      % (f"{n_bt:,}", f"{n_s0:,}", rt, "✅ 같다" if 0.9 <= rt <= 1.1 else "⚠ 어긋난다"))
print("     (둘의 차이는 백분위를 **발표일**에서 매기느냐 **다음 거래일**에서 매기느냐뿐이다)")
rt7 = n_s7 / max(n_s0, 1)
print("  ② peadage<=7 은 중복 제거 뒤 %s건 (peadage=0 의 %.2fx)" % (f"{n_s7:,}", rt7))
print("     유예를 둬도 중복 제거가 같은 사건을 한 번만 세므로 크게 안 는 게 정상이다.")
print("  ③ 성적 — 유예의 대가")
print("     peadage=0  평균 %+.2f%% · 중앙 %+.2f%% · 승률 %.0f%%"
      % (v_s0.mean(), v_s0.median(), (v_s0 > 0).mean() * 100))
print("     peadage<=7 평균 %+.2f%% · 중앙 %+.2f%% · 승률 %.0f%%"
      % (v_s7.mean(), v_s7.median(), (v_s7 > 0).mean() * 100))
print("\n총 %.0f초" % (time.time() - t0))
