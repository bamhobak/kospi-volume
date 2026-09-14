# -*- coding: utf-8 -*-
"""**새 규칙 탐색 1 — 지수 편입·제외** (2026-09-15).

왜 여기부터인가: slot_lab 셋이 한 목소리로 **병목은 자리가 아니라 후보**라고 했다.
최대 노출을 222%→666% 로 늘려도 실제 노출은 25%→30% 다 — 살 게 없어서 자리가 빈다.
그러면 자리·비중·보유기간 조율로는 더 얻을 게 없고, **후보를 늘리는 것**만 남는다.

지수 편입·제외를 첫 타자로 고른 이유:
  ① 아직 한 번도 안 쟀다 (data/index_members.db 는 2018-02~ 월별 스냅샷 77개).
  ② 메커니즘이 가격·거래량과 **독립**이다 — 패시브 자금의 강제 매매다. 우리 9규칙은
     전부 가격·수급·재무 축이라 겹칠 이유가 없다. '빈 날을 채운다' 는 목적에 맞다.
  ③ 이벤트라 신호가 흩어져 있다(정기변경 6·12월 + 수시변경 상시).

⚠ 한계 셋 — 먼저 적어 둔다.
  · 스냅샷이 **월별**이라 정확한 편입일을 모른다. 그 달 안에서 언제 바뀌었든 우리는
    스냅샷 날에야 안다 → **그 다음날 시가 매수**로 잡는다. 늦게 사는 쪽이라 보수적이다.
  · 자료가 2018-02~ 라 학습이 5년(2018~22)뿐이다. 기존 규칙(2016~22)보다 얇다.
  · 제외는 이유가 섞여 있다 — 시총 하락도, 폐지·합병도 제외로 보인다.

판정은 늘 하던 대로: 같은 날 **유니버스 대비 초과** · 중앙값 · 상위5% 절삭평균 ·
학습/검증 분리 · 월블록 CI · 연도별 양수 비율. (vp_lib.Runner 가 전부 한다)

    python newrule_index.py
"""
import sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from vp_lib import Runner, hdr, log, BASE
import vp_lib

# 지수 자료가 2018-02 부터라 학습 시작점을 거기에 맞춘다(기본 2016 은 쓸 수 없다).
vp_lib.TR0 = "20180201"
SINCE = "20180201"

IDX = {"1028": "코스피200", "2203": "코스닥150", "1034": "코스피100", "1035": "코스피50",
       "1002": "코스피대형", "1003": "코스피중형", "1004": "코스피소형", "2004": "코스닥대형"}

A = pd.read_pickle(BASE / "data/vp_kr.pkl")
uni = ((~A.pref) & (A.close >= 1000) & (A.amt20.fillna(0) >= 10) & (~A.dil.fillna(False))).fillna(False)
log(f"국내 패널 {len(A):,}행 · 유니버스 {uni.mean()*100:.0f}%")

# ── 이벤트 만들기 ────────────────────────────────────────────────────────
con = sqlite3.connect(BASE / "data/index_members.db")
M = pd.read_sql("SELECT idx,date,ticker FROM members", con)
M["ticker"] = M.ticker.astype(str).str.zfill(6)
cal = np.array(sorted(A.date.unique()))


def onday(snap):
    """스냅샷 날짜 → 그 날 이후 첫 거래일(그 날이 거래일이면 그 날)."""
    i = np.searchsorted(cal, snap, "left")
    return cal[i] if i < len(cal) else None


EV = []          # (idx, 방향, ticker, 관측일)
for ix, g in M.groupby("idx"):
    ds = sorted(g.date.unique())
    mem = {d: set(g[g.date == d].ticker) for d in ds}
    for a, b in zip(ds, ds[1:]):
        d = onday(b)
        if d is None: continue
        for t in mem[b] - mem[a]: EV.append((ix, "편입", t, d))
        for t in mem[a] - mem[b]: EV.append((ix, "제외", t, d))
E = pd.DataFrame(EV, columns=["idx", "way", "ticker", "date"])
log(f"이벤트 {len(E):,}건 · 지수 {E.idx.nunique()}개 · {E.date.min()}~{E.date.max()}")

# 패널에 붙이기 — (종목, 날짜)로 표시한다
A["_k"] = A.ticker + A.date
KEY = {}
for (ix, way), g in E.groupby(["idx", "way"]):
    KEY[(ix, way)] = set(g.ticker + g.date)

R = Runner(A, uni, "kr", since=SINCE)
HOLDS = (5, 10, 20, 40)
NT = 0
hits = []

print("\n" + "=" * 152)
print("지수 편입·제외 단독 실측 — 다음날 시가 매수 · 비용 차감 · 같은 날 유니버스 대비 초과")
print(f"학습 {SINCE}~20221231 · 검증 20230101~ · 중복 제거(보유기간 안 재진입 금지)")
print("=" * 152)
for ix, nm in IDX.items():
    hdr(f"{nm}")
    for way in ("편입", "제외"):
        k = KEY.get((ix, way))
        if not k: continue
        cond = A._k.isin(k)
        for h in HOLDS:
            NT += 1
            r = R.run(f"{nm} {way} · {h}일", cond, hold=h, minn=25)
            if r and r["ok"]: hits.append(r)

# ── 대조군 — 아무것도 안 걸고 그 유니버스를 그냥 샀을 때 ────────────────
hdr("대조군 (유니버스 전체 · 같은 기간)")
for h in HOLDS:
    R.run(f"유니버스 baseline · {h}일", pd.Series(True, index=A.index), hold=h, minn=25)

print("\n" + "=" * 152)
print(f"시험한 칸 {NT}개 · 1차 통과 {len(hits)}개")
for r in hits:
    print(f"  ✅ {r['tag']:<28} n={r['n']:<5} 중앙 {r['med']:+.2f}% · 절삭 {r['trim']:+.2f}% · "
          f"초과 {r['ex']:+.2f}%p · 검증중앙 {r['vam']:+.2f}% · 양수해 {r['pos']}/{r['ny']}")
if not hits:
    print("  통과 없음 — 이 축은 단독으로 자리가 없다")
print("=" * 152)
