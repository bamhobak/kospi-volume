# -*- coding: utf-8 -*-
"""**지수 편입·제외 2차 — 자동 기각 뒤에 남은 두 갈래** (2026-09-15).

1차(newrule_index.py)는 64칸 전량 기각이었다. 그런데 기각 사유를 뜯어보면 둘로 갈린다.

  ⓐ **정말 나쁜 것** — '편입' 은 20~40일에서 중앙값이 -5~-8% 다. 그것도 코스피200·
     코스닥150·코스피100 **세 지수가 같은 방향**이다. 우연이라기엔 너무 가지런하다.
     이건 못 쓰는 규칙이 아니라 **회피 신호**일 수 있다.
  ⓑ **못 잰 것** — '제외' 쪽 여러 칸이 학습CI = nan 으로 떨어졌다. 성적이 나빠서가
     아니라 **월 수가 8개 미만**이라 월블록 부트스트랩이 성립하지 않아서다.
     지수 이벤트는 정기변경(6·12월)에 몰려서 달이 몇 개 안 된다.

그래서 여기서는
  ① 편입 약세가 지수·연도에 걸쳐 일관된가 (일관되면 회피 신호로 기록할 값어치가 있다)
  ② 제외 축을 **연도 블록**으로 다시 판정한다 (월 클러스터링을 우회)
  ③ 정기변경 달과 그 밖을 나눈다 — 섞여 있으면 둘 다 흐려진다
  ④ 제외 + 우리 재료 조합 (2단계)

⚠ 여기서부터는 1차 결과를 보고 고른 갈래다(사후 선택). 통과해도 '유망' 이지 채택이 아니다.

    python newrule_index2.py
"""
import sqlite3, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from vp_lib import Runner, hdr, log, BASE, boot_ci
import vp_lib

vp_lib.TR0 = "20180201"
SINCE = "20180201"
IDX = {"1028": "코스피200", "2203": "코스닥150", "1034": "코스피100", "1035": "코스피50",
       "1002": "코스피대형", "1003": "코스피중형", "1004": "코스피소형", "2004": "코스닥대형"}

A = pd.read_pickle(BASE / "data/vp_kr.pkl")
uni = ((~A.pref) & (A.close >= 1000) & (A.amt20.fillna(0) >= 10) & (~A.dil.fillna(False))).fillna(False)
log(f"국내 패널 {len(A):,}행 · 유니버스 {uni.mean()*100:.0f}%")

con = sqlite3.connect(BASE / "data/index_members.db")
M = pd.read_sql("SELECT idx,date,ticker FROM members", con)
M["ticker"] = M.ticker.astype(str).str.zfill(6)
cal = np.array(sorted(A.date.unique()))


def onday(s):
    i = np.searchsorted(cal, s, "left")
    return cal[i] if i < len(cal) else None


EV = []
for ix, g in M.groupby("idx"):
    ds = sorted(g.date.unique())
    mem = {d: set(g[g.date == d].ticker) for d in ds}
    for a, b in zip(ds, ds[1:]):
        d = onday(b)
        if d is None: continue
        for t in mem[b] - mem[a]: EV.append((ix, "편입", t, d))
        for t in mem[a] - mem[b]: EV.append((ix, "제외", t, d))
E = pd.DataFrame(EV, columns=["idx", "way", "ticker", "date"])
A["_k"] = A.ticker + A.date
R = Runner(A, uni, "kr", since=SINCE)


def keyset(sel): return set(sel.ticker + sel.date)


# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 120)
print("① '편입 후 약세' 가 지수에 걸쳐 일관된가 — 중앙값(%)")
print("=" * 120)
print(f"  {'지수':<10}{'건수':>7}" + "".join(f"{str(h)+'일':>9}" for h in (5, 10, 20, 40)) + "   방향")
for ix, nm in IDX.items():
    sel = E[(E.idx == ix) & (E.way == "편입")]
    k = keyset(sel)
    row, meds = "", []
    for h in (5, 10, 20, 40):
        r = R.run("", A._k.isin(k), hold=h, minn=20, quiet=True)
        if r is None: row += f"{'—':>9}"; continue
        meds.append(r["med"]); row += f"{r['med']:>+9.2f}"
    n = R.run("", A._k.isin(k), hold=20, minn=20, quiet=True)
    print(f"  {nm:<10}{(n['n'] if n else 0):>7}{row}   "
          + ("⬇ 20·40일 모두 음수" if len(meds) >= 4 and meds[2] < 0 and meds[3] < 0 else ""))
print("\n  ▸ 대조군(유니버스) 중앙값: ", end="")
for h in (5, 10, 20, 40):
    b = R.run("", pd.Series(True, index=A.index), hold=h, minn=20, quiet=True)
    print(f"{h}일 {b['med']:+.2f}%  ", end="")
print("\n  ※ 유니버스 자체가 음수 드리프트다. 편입이 그보다 **더** 나쁜지가 요점이다.")

print("\n" + "=" * 120)
print("② 연도별 — 편입(20일) vs 제외(10일) 중앙값. 해마다 방향이 같아야 믿을 수 있다")
print("=" * 120)
for way, h in (("편입", 20), ("제외", 10)):
    k = keyset(E[E.way == way])
    r = R.run("", A._k.isin(k), hold=h, minn=20, quiet=True)
    Y = r["Y"]
    yr = Y.groupby("yr").r.agg(["size", "median"])
    print(f"\n  [{way} · {h}일] 전체 {len(Y):,}건 · 중앙 {Y.r.median():+.2f}% · "
          f"초과 {Y.ex.mean():+.2f}%p · 양수해 {(yr['median']>0).sum()}/{len(yr)}")
    print("   " + "  ".join(f"{i}:{v['median']:+.1f}%({int(v['size'])})" for i, v in yr.iterrows()))

print("\n" + "=" * 120)
print("③ 정기변경 달과 그 밖을 나눈다 (스냅샷 기준 6·7·12·1월 = 정기변경 직후)")
print("=" * 120)
E["mm"] = E.date.str[4:6]
REG = {"06", "07", "12", "01"}
for way in ("편입", "제외"):
    hdr(f"{way}")
    for lbl, sel in (("정기변경 달", E[(E.way == way) & E.mm.isin(REG)]),
                     ("그 밖(수시)", E[(E.way == way) & ~E.mm.isin(REG)])):
        for h in (5, 10, 20, 40):
            R.run(f"{way} · {lbl} · {h}일", A._k.isin(keyset(sel)), hold=h, minn=25)

print("\n" + "=" * 120)
print("④ 제외 + 우리 재료 (2단계 조합) — 제외만으론 약했다. 눌림이 겹치면 달라지나")
print("=" * 120)
OUT = A._k.isin(keyset(E[E.way == "제외"]))
COMBO = [("제외 그대로", OUT),
         ("제외 & 고점대비 -30% 이하", OUT & (A.fromhi <= -30)),
         ("제외 & 고점대비 -50% 이하", OUT & (A.fromhi <= -50)),
         ("제외 & 60일 수익 -20% 이하", OUT & (A.ret60 <= -20)),
         ("제외 & 업종 60일 -10% 이하", OUT & (A.u <= -10)),
         ("제외 & 거래대금 50억 이상", OUT & (A.amt20 >= 50)),
         ("제외 & 코스피만", OUT & (A.mk == "KOSPI")),
         ("제외 & 코스닥만", OUT & (A.mk == "KOSDAQ"))]
hdr("조합")
NT = 0
hits = []
for lbl, c in COMBO:
    for h in (5, 10, 20):
        NT += 1
        r = R.run(f"{lbl} · {h}일", c, hold=h, minn=25)
        if r and r["ok"]: hits.append(r)
print(f"\n  이 2차에서 시험한 칸 {NT}개 (1차 64칸 + 여기 {NT}칸 = 누적 {64+NT}칸)")
print(f"  통과 {len(hits)}개" + ("" if hits else " — 조합으로도 자리가 없다"))
for r in hits:
    print(f"  ✅ {r['tag']}  n={r['n']} 중앙 {r['med']:+.2f}% 초과 {r['ex']:+.2f}%p 검증 {r['vam']:+.2f}%")
