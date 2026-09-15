# -*- coding: utf-8 -*-
"""**내부자 규칙 조이기 — 복권형에서 벗어날 조건이 있나** (2026-09-15).

지금 상태(매수 100만$↑ · 40일): 1,925건 · 평균 +3.13% · 중앙 +2.39% · 승률 56%
  ❌ 절삭평균 **-0.05%** · 상위 5%가 수익의 **101%**(그 5% 빼면 전체가 마이너스)
  ❌ 2026년 중앙 **-4.5%** · 양수해 7/11

**가설**: 복권형의 정체는 **이미 무너진 회사에서 나오는 내부자 매수**다. 곤경에 빠진 회사의
임원이 사면 살아날 땐 +300%, 못 살아나면 -90% 다. 그러면 평균은 대박 몇 건이 만들고
중앙값은 바닥에 깔린다. 게다가 **미국 패널에는 망한 회사가 없어**(생존편향) 그 쪽이 통째로
빠져 성적이 위로 편향된다 — 즉 실전은 이보다 나쁘다.

→ **주가가 아직 안 무너진 것만 고르면** 복권형과 생존편향이 동시에 줄어야 한다.
   그 밖에 시총 대비 매수 규모·직위·매도 동반 여부·국면도 같이 훑는다.

판정(전부 넘어야 채택 후보):
  ① 절삭평균 > 0    ② 상위5% 기여 < 100%    ③ 2026 중앙 > 0    ④ 양수해 ≥ 8/11
  ⑤ 신호 ≥ 300건 (너무 조이면 계좌에서 의미가 없다)

    python us_ins_tight.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 150
SINCE = "20160101"
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


log("us_ins.pkl (6.2GB)")
K = pd.read_pickle(BASE / "data/us_ins.pkl")
KEEP = ["ticker", "date", "amt20", "buy", "cost", "pref", "rawclose", "n40",
        "bv", "bn", "bd", "bo", "bt", "bf", "bcap", "sv", "net60", "bv60",
        "fromhi", "fromlo", "ret20", "ret60", "dev25", "mdd60", "above20",
        "marcap", "up", "PBR", "부채비율"]
K = K[[c for c in KEEP if c in K.columns]].copy()
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False)
ud = sorted(K.date.unique())
DD = {d: i for i, d in enumerate(ud)}
BASECOND = (UNI & (K.bv >= 1e6)).fillna(False)
BEN = K[UNI].dropna(subset=["n40"]).groupby("date").n40.mean()
log("  %s행 · 기본 조건 %s행" % (f"{len(K):,}", f"{int(BASECOND.sum()):,}"))


def run(tag, cond, h=40, minn=150):
    z = K[cond.fillna(False)].dropna(subset=[f"n{h}"])
    z = z[(z.buy > 0) & (z.date >= SINCE)].sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = z.loc[keep].copy()
    if len(Y) < minn:
        print("  %-42s%6s (부족)" % (tag, f"{len(Y):,}"))
        return None
    v = Y[f"n{h}"].astype(float)
    Y["r"] = v
    ex = (v - Y.date.map(BEN)).mean()
    trim = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() != 0 else np.nan
    yr = Y.assign(y=Y.date.str[:4]).groupby("y").r.median()
    y26 = yr.get("2026", np.nan)
    pos = int((yr > 0).sum())
    ok = (trim > 0) and (t5 < 100) and (y26 > 0) and (pos >= 8)
    print("  %-42s%6s%8.2f%8.2f%7.0f%%%8.2f%8.2f%8.0f%%%8.2f%6d/%d %s"
          % (tag, f"{len(Y):,}", v.mean(), v.median(), (v > 0).mean() * 100, trim, ex, t5,
             y26, pos, len(yr), "  ✅" if ok else ""))
    return dict(tag=tag, n=len(Y), mean=v.mean(), med=v.median(), trim=trim, ex=ex,
                t5=t5, y26=y26, pos=pos, ok=ok)


HDR = ("  %-42s%6s%8s%8s%7s%8s%8s%8s%8s%8s" %
       ("조건", "n", "평균", "중앙", "승률", "절삭", "초과", "상위5%", "2026", "양수해"))
print("\n" + "=" * W)
print("내부자 조이기 — 매수 100만$↑ · 40일 보유 · 거래대금 상위40% 기준")
print("판정: 절삭>0 · 상위5%기여<100% · 2026중앙>0 · 양수해≥8/11")
print("=" * W)
hits = []


def sec(t):
    print("\n## " + t)
    print(HDR)


sec("기준선")
r = run("지금 (매수 100만$↑)", BASECOND)

sec("① 주가가 아직 안 무너진 것만 — 핵심 가설")
for lo in (-60, -50, -40, -30, -20, -10):
    r = run("고점대비 %d%% 이상 (안 무너진 쪽)" % lo, BASECOND & (K.fromhi >= lo))
    if r and r["ok"]:
        hits.append(r)
print("  [반대쪽 — 무너진 쪽만]")
for lo in (-50, -30):
    run("고점대비 %d%% 미만 (무너진 쪽)" % lo, BASECOND & (K.fromhi < lo))

sec("② 최근 20·60일 수익률")
for lo in (-20, -10, 0):
    r = run("20일 수익 %d%% 이상" % lo, BASECOND & (K.ret20 >= lo))
    if r and r["ok"]:
        hits.append(r)
for lo in (-30, -10, 0):
    r = run("60일 수익 %d%% 이상" % lo, BASECOND & (K.ret60 >= lo))
    if r and r["ok"]:
        hits.append(r)

sec("③ 매수 규모 — 절대금액 · 시총 대비")
for v in (2e6, 5e6, 1e7):
    r = run("매수 %.0f만$ 이상" % (v / 1e4), UNI & (K.bv >= v))
    if r and r["ok"]:
        hits.append(r)
if "bcap" in K.columns:
    q = K.loc[BASECOND, "bcap"]
    for p in (0.5, 0.7, 0.9):
        th = q.quantile(p)
        r = run("시총 대비 매수규모 상위 %d%%" % int((1 - p) * 100), BASECOND & (K.bcap >= th))
        if r and r["ok"]:
            hits.append(r)

sec("④ 누가 샀나 — 직위별")
for c, nm in (("bd", "이사(director)"), ("bo", "임원(officer)"), ("bt", "10% 주주")):
    if c in K.columns:
        r = run("%s 가 포함된 매수" % nm, BASECOND & (K[c].fillna(0) > 0))
        if r and r["ok"]:
            hits.append(r)

sec("⑤ 같은 날 내부자 매도가 없었나")
if "sv" in K.columns:
    r = run("매도 동반 없음 (sv==0)", BASECOND & (K.sv.fillna(0) <= 0))
    if r and r["ok"]:
        hits.append(r)
    r = run("매수액이 매도액의 3배 이상", BASECOND & (K.bv >= 3 * K.sv.fillna(0)))
    if r and r["ok"]:
        hits.append(r)
if "net60" in K.columns:
    r = run("60일 순매수 양수", BASECOND & (K.net60.fillna(0) > 0))
    if r and r["ok"]:
        hits.append(r)

sec("⑥ 시총·국면")
for v in (3e8, 1e9, 3e9):
    r = run("시총 %.1f억$ 이상" % (v / 1e8), BASECOND & (K.marcap >= v))
    if r and r["ok"]:
        hits.append(r)
r = run("상승장(S&P 60일선 위)", BASECOND & (K.up == True))
if r and r["ok"]:
    hits.append(r)
r = run("하락장", BASECOND & (K.up == False))
if r and r["ok"]:
    hits.append(r)

sec("⑦ 가장 유망한 축 두 개를 겹쳐 본다")
for lo in (-40, -30, -20):
    for v in (2e6, 5e6):
        r = run("고점대비 %d%%↑ & 매수 %.0f만$↑" % (lo, v / 1e4),
                UNI & (K.bv >= v) & (K.fromhi >= lo))
        if r and r["ok"]:
            hits.append(r)

print("\n" + "=" * W)
print("통과 %d개 (절삭>0 · 상위5%%<100%% · 2026>0 · 양수해≥8)" % len(hits))
for r in hits:
    print("  ✅ %-42s n=%-6s 중앙 %+.2f%% · 절삭 %+.2f%% · 상위5%% %.0f%% · 2026 %+.2f%%"
          % (r["tag"], f"{r['n']:,}", r["med"], r["trim"], r["t5"], r["y26"]))
if not hits:
    print("  통과 없음 — 복권형에서 벗어나는 조건이 없다")
print("총 %.0f초" % (time.time() - t0))
