# -*- coding: utf-8 -*-
"""**미장 PEAD — 실적 발표 후 표류** (2026-09-15).

왜 이 축인가: 오늘 내내 나온 결론이 "미장은 규칙을 늘려야 한다" 였다. 그런데 가격·거래량
축은 이미 바닥까지 팠고([상승장 신고가] 9차까지), 자금흐름·13F 는 축이 없었다.
남은 것 중 **한 번도 안 판 것**이 실적이다 — `data/us/analyst/` 에 EPS 추정·실제·서프라이즈가
21만 건(4,493종목 · 2002~2026) 있다. PEAD 는 학술적으로 가장 오래 살아남은 아노말리이고,
우리 5규칙(가격·자사주·밸류)과 겹칠 이유가 없다.

⚠ 함정 셋을 먼저 막는다.
  ① **서프라이즈 %는 극단값이 심하다** — EPS 가 0 근처면 분모가 0 이라 ±769,900% 같은 값이 나온다.
     그대로 쓰면 그 몇 건이 전부를 결정한다. **그날 발표분 안의 백분위 순위**로 바꿔 쓴다.
  ② **시점** — 장전 발표(ET 6~9시)는 그날 시가에 이미 반영된다. 장후 발표는 다음날이다.
     섞여 있으므로 보수적으로 **발표일 다음 거래일 시가 매수**로 통일한다(늦게 사는 쪽).
  ③ **생존편향** — 현재 상장 종목만 담긴 자료다. 미국 패널도 같은 한계라 방향은 위쪽이다.

  ① 자료 결합·커버리지
  ② 서프라이즈 구간별 성적 — **단조성**이 있어야 진짜다(한 칸만 좋으면 우연)
  ③ 발표일 반응(갭)과 묶기 — 문헌에서는 SUE 보다 발표일 수익률이 더 강할 때가 많다
  ④ 대조군 — 유니버스를 그냥 산 것

    python us_pead.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from vp_lib import Runner, hdr, log, BASE
import vp_lib

SINCE = "20160101"
W = 152

# ── 실적 자료 ────────────────────────────────────────────────────────────
fs = sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["et"] = E.dt.dt.tz_convert("US/Eastern")
E["edate"] = E.et.dt.strftime("%Y%m%d")
E["hour"] = E.et.dt.hour
E = E.drop_duplicates(["ticker", "edate"], keep="last")
log(f"실적 {len(E):,}건 · 종목 {E.ticker.nunique():,} · {E.edate.min()}~{E.edate.max()}")

# ── 패널 ─────────────────────────────────────────────────────────────────
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
uni = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
log(f"패널 {len(A):,}행 · 유니버스 {uni.mean()*100:.0f}%")


def nextday(s):
    """발표일 **다음** 거래일 — 장전·장후가 섞여 있으니 늦게 사는 쪽으로 통일한다."""
    i = np.searchsorted(cal, s, "right")
    return cal[i] if i < len(cal) else None


E["bdate"] = [nextday(d) for d in E.edate.values]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
# ⚠ 백분위는 **그날 발표분 안에서** 매긴다 — 극단값의 영향을 지우면서 시점 정보도 안 샌다
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E["n_day"] = E.groupby("bdate").sur.transform("size")
E = E[E.n_day >= 5]                      # 발표가 몇 건뿐인 날은 백분위가 의미 없다
log(f"매수일 붙인 실적 {len(E):,}건 · 하루 평균 {E.groupby('bdate').size().mean():.0f}건")

A["_k"] = A.ticker + A.date
KQ = dict(zip(E.ticker + E.bdate, E.q))
KS = dict(zip(E.ticker + E.bdate, E.sur))
A["peadq"] = A._k.map(KQ)
A["peads"] = A._k.map(KS)
has = A.peadq.notna()
log(f"패널에 붙은 실적 이벤트 {int(has.sum()):,}행 (유니버스 안 {int((has & uni).sum()):,})")

R = Runner(A, uni, "us", since=SINCE)
HOLDS = (20, 40, 60)
NT = 0
hits = []

print("\n" + "=" * W)
print("미장 PEAD — 발표 다음 거래일 시가 매수 · 비용 차감 · 같은 날 유니버스 대비 초과")
print(f"학습 {SINCE}~20221231 · 검증 20230101~ · 중복 제거 · 서프라이즈는 **그날 발표분 안 백분위**")
print("=" * W)

hdr("① 서프라이즈 백분위 구간별 — 단조성이 있어야 진짜다")
for lo, hi, lbl in [(0.9, 1.01, "상위 10% (가장 좋은 서프라이즈)"), (0.8, 0.9, "상위 10~20%"),
                    (0.6, 0.8, "상위 20~40%"), (0.4, 0.6, "중간 40~60%"),
                    (0.2, 0.4, "하위 20~40%"), (0.0, 0.2, "하위 20% (가장 나쁜 서프라이즈)")]:
    c = has & (A.peadq > lo) & (A.peadq <= hi)
    for h in HOLDS:
        NT += 1
        r = R.run(f"{lbl} · {h}일", c, hold=h, minn=40)
        if r and r["ok"]:
            hits.append(r)
    print()

hdr("② 더 조인 구간 — 상위 5% · 3%")
for lo, lbl in [(0.95, "상위 5%"), (0.97, "상위 3%")]:
    c = has & (A.peadq > lo)
    for h in HOLDS:
        NT += 1
        r = R.run(f"{lbl} · {h}일", c, hold=h, minn=40)
        if r and r["ok"]:
            hits.append(r)
    print()

hdr("③ 절대 서프라이즈 문턱 (백분위 대신) — 클리핑해서")
A["surc"] = A.peads.clip(-100, 100)
for lo, lbl in [(10, "서프라이즈 +10%↑"), (25, "+25%↑"), (50, "+50%↑")]:
    c = has & (A.surc >= lo)
    for h in HOLDS:
        NT += 1
        r = R.run(f"{lbl} · {h}일", c, hold=h, minn=40)
        if r and r["ok"]:
            hits.append(r)
    print()

hdr("④ 발표일 반응과 묶기 — 문헌에서는 SUE 보다 '시장이 어떻게 받았나' 가 더 강하다")
g = A.groupby("ticker", sort=False)
A["ret1"] = (A.close / g.close.shift(1) - 1) * 100
for lo, lbl in [(3, "서프라이즈 상위30% & 발표 다음날 갭 +3%↑"),
                (5, "서프라이즈 상위30% & 갭 +5%↑")]:
    c = has & (A.peadq >= 0.7) & (A.ret1 >= lo)
    for h in HOLDS:
        NT += 1
        r = R.run(f"{lbl} · {h}일", c, hold=h, minn=40)
        if r and r["ok"]:
            hits.append(r)
    print()
c = has & (A.peadq >= 0.7) & (A.ret1 <= 0)
for h in HOLDS:
    NT += 1
    r = R.run(f"서프라이즈 상위30% & 갭 음수(무시당함) · {h}일", c, hold=h, minn=40)
    if r and r["ok"]:
        hits.append(r)

hdr("⑤ 대조군")
for h in HOLDS:
    R.run(f"유니버스 baseline · {h}일", pd.Series(True, index=A.index), hold=h, minn=40)
for h in HOLDS:
    R.run(f"실적 발표 전체(선별 없음) · {h}일", has, hold=h, minn=40)

print("\n" + "=" * W)
print(f"시험한 칸 {NT}개 · 1차 통과 {len(hits)}개")
for r in hits:
    print(f"  ✅ {r['tag']:<44} n={r['n']:<6} 중앙 {r['med']:+.2f}% · 절삭 {r['trim']:+.2f}% · "
          f"초과 {r['ex']:+.2f}%p · 검증중앙 {r['vam']:+.2f}% · 양수해 {r['pos']}/{r['ny']}")
if not hits:
    print("  통과 없음")
print("=" * W)
