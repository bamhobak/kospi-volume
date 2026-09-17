# -*- coding: utf-8 -*-
"""**미장 일봉 공급처 바꾸기 — 전체 규모 예행연습** (2026-09-18).

물음: "야후 미장 데이터 불안정한 것 같은데 다른 데서 받아올 수 없어?"

야후가 이번 주에만 두 번 문제를 냈다.
  · 2026-09-16 마감 5시간 46분 뒤에도 그날 일봉을 **5%(303/5,683)** 만 올려 놓았다
  · 실적 수집에서 YFRateLimitError

표본 300종목 측정(2026-09-18):
  | | 야후(오늘 실측) | Stooq(FinanceDataReader) |
  |---|---|---|
  | 9/17 보유 | 94.0% (5,325/5,664) | **99.0%** (297/300) |
  | 속도 | 180초 | 종목당 0.071초(12스레드) → 6,092종목 추정 7분 |
  | 값 | — | 시가·종가·거래량 **완전 일치** |
  | 기준 | 원종가(분할반영·배당미조정) | **동일** (KO/XOM/JNJ 2024-01-02 로 확인) |

⚠ 아직 모르는 것: **6,000종목을 실제로 때리면 막히는가.** 표본 300개로는 알 수 없다.
   여기서 전체 규모로 한 번 돌려 본다 — 수집기는 건드리지 않고 **재보기만** 한다.

보는 것:
  ① 전체 커버리지·속도·차단 여부
  ② 야후가 못 받은 종목을 Stooq 는 받았나 (이게 바꾸는 이유다)
  ③ 겹치는 종목의 값이 정말 같은가 (한 칸이라도 다르면 기준이 어긋난 것이다)

    python us_source_test.py
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

BASE = Path(__file__).parent
OUT = []
t0 = time.time()
TARGET = "20260917"          # 지금 기준 마지막 미장 거래일
WORK = 12


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


import FinanceDataReader as fdr
import json

syms = [x for x in pd.read_csv(BASE / "data/us/tickers.csv", dtype=str).Symbol.tolist()
        if isinstance(x, str) and x.strip()]
log("종목 %s개" % f"{len(syms):,}")


def get(t):
    try:
        d = fdr.DataReader(t, "2026-09-08")
        if not len(d):
            return t, None, None
        r = d.iloc[-1]
        return t, d.index[-1].strftime("%Y%m%d"), (float(r.Open), float(r.High),
                                                   float(r.Low), float(r.Close), float(r.Volume))
    except Exception:
        return t, "ERR", None


res = []
done = [0]
with ThreadPoolExecutor(WORK) as ex:
    for r in ex.map(get, syms):
        res.append(r)
        done[0] += 1
        if done[0] % 1000 == 0:
            log("  %s/%s · %.0f초" % (f"{done[0]:,}", f"{len(syms):,}", time.time() - t0))
el = time.time() - t0

from collections import Counter
cnt = Counter(d for _, d, _ in res)
ok = {t: v for t, d, v in res if d == TARGET and v}
P("=" * 100)
P("① Stooq 전체 규모 — 종목 %s개 · %.0f초 (%.1f분)" % (f"{len(syms):,}", el, el / 60))
P("=" * 100)
P("  %-14s%10s%10s" % ("마지막 거래일", "종목", "비율"))
for k, v in sorted(cnt.items(), key=lambda x: str(x[0]), reverse=True)[:8]:
    P("  %-14s%10s%9.1f%%" % (k, f"{v:,}", v / len(syms) * 100))
P("\n  %s 보유 %s종목 (%.1f%%)" % (TARGET, f"{len(ok):,}", len(ok) / len(syms) * 100))

# ── 야후(방금 수집한 표)와 견주기 ────────────────────────────────────────
U = json.loads((BASE / "site" / "data" / "table_us.json").read_text(encoding="utf-8"))
yrows = {r["t"]: r for r in U.get("rows", [])}
yasof = U.get("asof")
P()
P("=" * 100)
P("② 야후가 못 받은 종목을 Stooq 는 받았나  (야후 표 기준일 %s)" % yasof)
P("=" * 100)
ydates = {}
for t, r in yrows.items():
    v = r.get("v") or []
    ydates[t] = r.get("asof") or None
P("  야후 표 종목 %s개 · Stooq %s 보유 %s개" % (f"{len(yrows):,}", TARGET, f"{len(ok):,}"))
only_stooq = [t for t in ok if t not in yrows]
only_yahoo = [t for t in yrows if t not in ok]
P("  Stooq 에만 있는 종목 %s개 · 야후 표에만 있는 종목 %s개"
  % (f"{len(only_stooq):,}", f"{len(only_yahoo):,}"))
P("  (야후 표는 수집기가 조건을 걸어 걸러낸 뒤라 수가 더 적다 — 순수 비교는 ③)")

P()
P("=" * 100)
P("③ 겹치는 종목의 값이 같은가 — 야후 표의 종가(c)와 Stooq 종가")
P("=" * 100)
same = diff = 0
bad = []
for t, r in yrows.items():
    if t not in ok:
        continue
    yc = r.get("c")
    sc = ok[t][3]
    if yc is None or not np.isfinite(sc) or sc <= 0:
        continue
    if abs(sc / yc - 1) <= 0.001:
        same += 1
    else:
        diff += 1
        if len(bad) < 10:
            bad.append((t, yc, sc, (sc / yc - 1) * 100))
tot = same + diff
P("  견준 종목 %s개 · 일치(0.1%% 이내) %s (%.2f%%) · 불일치 %s"
  % (f"{tot:,}", f"{same:,}", same / max(tot, 1) * 100, f"{diff:,}"))
if bad:
    P("\n  %-8s%12s%12s%10s" % ("종목", "야후", "Stooq", "차이"))
    for t, yc, sc, d in bad:
        P("  %-8s%12.2f%12.2f%9.2f%%" % (t, yc, sc, d))

P("\n총 %.0f초" % (time.time() - t0))
io.open(BASE / "_ussrc_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 _ussrc_out.txt 에 썼다")
