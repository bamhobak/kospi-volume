# -*- coding: utf-8 -*-
"""**국내 9규칙 — 2005~2015 홀드아웃** (2026-09-16 요청).

왜 이걸 하나: 검증(2023~26) 표본이 하락장 규칙에서 너무 적다.
  [폭락반등] 33건 · [자사주 낙폭] 27건 · [낙폭과대] 23건 · [깊은 이격] 201건
  2018·2020-03·2022 — 현대 표본의 폭락이 **전부 학습에 있다**. 2023~26 엔 진짜 하락장이 없었다.
  이 규칙들의 "검증 통과" 는 사실상 의미가 없다.

경계를 옮기는 건 자기기만이다(이미 본 데이터다). **한 번도 판정에 안 쓴 구간**이 필요하다.

⚠ **미장은 못 쓴다.** `us_scan.pkl` 은 지금 상장된 티커로 과거를 역추적한 판이라
   2008년 2,143종목 중 2,142개(100%)가 2016년에도 살아 있다. 그 사이 폐지된 수천 종목이
   통째로 빠져 있어 낙폭 규칙을 재면 거짓이 된다.
   **국내 패널은 깨끗하다** — 2016 이전에 사라진 종목이 656개(16.4%), 2008년 종목 중
   2026년까지 간 것은 64% 다. 폐지가 제대로 들어 있다.

제도 차이는 있다(가격제한폭 ±15% → 2015-06 부터 ±30% · 공매도 금지기 2008-10~2009-05 등).
다만 그 방향은 **보수적**이다 — 반등폭이 제한돼 성적이 낮게 나온다. 통과하면 믿을 만하다.

판정은 2026-09-16 부터의 새 기준이다 — **무제한 자금 · 전 신호 동일금액 · 유니버스 초과는 안 본다.**

  ① 구간별 신호 수 (앞서 라벨을 잘못 붙였던 표를 3구간으로 다시)
  ② 홀드아웃 2005~2015 성적 vs 학습 2016~22 vs 검증 2023~26
  ③ 2008년만 따로 — 금융위기에서 어땠나
  ④ 연도별 중앙값 (2005~2015)
  ⑤ 제도 구간 쪼개기 — 가격제한폭 ±15% 시절(~2015-06) vs ±30%

    python kr_holdout.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 128
OUT = []
t0 = time.time()


def P(x=""):
    OUT.append(x)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
S = ns["S"].copy()

# 신호별 수익률 — portfolio.py simulate 와 **같은 식**이다(손절은 저가 기준, 비용 차감).
hit = S.stop.notna() & ((S.low / S.buy - 1) * 100 <= -S.stop * 100)
S["ret"] = np.where(hit, -S.stop * 100 - S.cost, (S.exit / S.buy - 1) * 100 - S.cost)
S["yr"] = S.date.str[:4]
NM = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
      "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
      "D1": "낙폭과대", "D2": "저PBR 낙폭"}
ORD = ["P1", "P7", "P2", "P3", "P4", "P5", "P6", "D1", "D2"]
HOLD = {"P1": "20050101", "P2": "20160101", "P3": "20230101"}
SEG = [("홀드아웃 05~15", "20050101", "20151231"),
       ("학습 16~22", "20160101", "20221231"),
       ("검증 23~26", "20230101", "20301231")]

sec("① 구간별 신호 수 — 앞서 '학습16~22' 라 쓴 칸은 실은 2005~2022 였다(라벨 정정)")
P("  %-16s%12s%12s%12s%10s" % ("규칙", "홀드아웃 05~15", "학습 16~22", "검증 23~26", "합계"))
for r in ORD:
    z = S[S.rid == r]
    c = [len(z[(z.date >= a) & (z.date <= b)]) for _, a, b in SEG]
    P("  %-16s%12s%12s%12s%10s" % (NM[r], f"{c[0]:,}", f"{c[1]:,}", f"{c[2]:,}", f"{len(z):,}"))
P("\n  ※ 홀드아웃은 **한 번도 판정에 쓴 적 없는** 구간이다. 2008 금융위기가 들어 있다.")


def stat(v):
    if len(v) < 10:
        return None
    tr = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() else np.nan
    return dict(n=len(v), mean=v.mean(), med=v.median(), trim=tr,
                win=(v > 0).mean() * 100, t5=t5, worst=v.min())


sec("② 구간별 성적 — 무제한 자금 · 전 신호 동일금액 (유니버스 초과는 안 본다)")
P("  %-16s%-14s%8s%9s%9s%9s%8s%11s%9s" %
  ("규칙", "구간", "n", "평균", "중앙", "절삭", "승률", "상위5%기여", "최악"))
HO = {}
for r in ORD:
    z = S[S.rid == r]
    for lbl, a, b in SEG:
        v = z[(z.date >= a) & (z.date <= b)].ret
        s = stat(v)
        if s is None:
            P("  %-16s%-14s%8s%9s" % (NM[r] if lbl.startswith("홀드") else "", lbl,
                                      f"{len(v):,}", "(부족)"))
            continue
        if lbl.startswith("홀드"):
            HO[r] = s
        P("  %-16s%-14s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%10.0f%%%+9.1f"
          % (NM[r] if lbl.startswith("홀드") else "", lbl, f"{s['n']:,}", s["mean"],
             s["med"], s["trim"], s["win"], s["t5"], s["worst"]))
    P()

sec("③ 홀드아웃 판정 — 중앙값과 절삭평균이 둘 다 양수인가")
P("  %-16s%9s%9s%9s%9s%10s" % ("규칙", "중앙", "절삭", "승률", "상위5%", "판정"))
for r in ORD:
    s = HO.get(r)
    if not s:
        P("  %-16s%9s" % (NM[r], "(부족)")); continue
    ok = s["med"] > 0 and s["trim"] > 0
    P("  %-16s%+9.2f%+9.2f%8.0f%%%9.0f%%%10s"
      % (NM[r], s["med"], s["trim"], s["win"], s["t5"], "통과" if ok else "**미달**"))
P("\n  ※ 상위5% 기여가 100%% 를 넘으면 나머지 95%% 가 합쳐서 마이너스다(복권형).")

sec("④ 2008 금융위기만 따로 — 하락장 규칙이 진짜 위기를 견디나")
P("  %-16s%9s%9s%9s%8s%10s" % ("규칙", "n", "평균", "중앙", "승률", "최악"))
for r in ORD:
    v = S[(S.rid == r) & (S.yr == "2008")].ret
    if len(v) < 5:
        P("  %-16s%9s%9s" % (NM[r], f"{len(v):,}", "(부족)")); continue
    P("  %-16s%9s%+9.2f%+9.2f%7.0f%%%+10.1f"
      % (NM[r], f"{len(v):,}", v.mean(), v.median(), (v > 0).mean() * 100, v.min()))

sec("⑤ 연도별 중앙값 — 홀드아웃 구간")
yrs = [str(y) for y in range(2005, 2016)]
P("  %-16s" % "규칙" + "".join("%8s" % y[2:] for y in yrs) + "%10s" % "양수해")
for r in ORD:
    z = S[S.rid == r]
    row, pos, tot = "", 0, 0
    for y in yrs:
        v = z[z.yr == y].ret
        if len(v) < 5:
            row += "%8s" % "—"; continue
        m = v.median(); row += "%8.1f" % m
        tot += 1; pos += 1 if m > 0 else 0
    P("  %-16s%s%9s" % (NM[r], row, "%d/%d" % (pos, tot)))

sec("⑥ 제도 구간 — 가격제한폭 ±15% 시절(2015-06 이전) vs ±30%")
P("  (제한폭이 좁으면 반등이 막혀 성적이 **낮게** 나온다. 홀드아웃이 보수적이라는 근거다)")
P("\n  %-16s%12s%9s%9s%12s%9s%9s" %
  ("규칙", "±15% n", "중앙", "절삭", "±30% n", "중앙", "절삭"))
for r in ORD:
    z = S[S.rid == r]
    a = z[z.date < "20150615"].ret
    b = z[z.date >= "20150615"].ret
    sa, sb = stat(a), stat(b)
    P("  %-16s%12s%9s%9s%12s%9s%9s"
      % (NM[r], f"{len(a):,}", ("%+.2f" % sa["med"]) if sa else "—",
         ("%+.2f" % sa["trim"]) if sa else "—", f"{len(b):,}",
         ("%+.2f" % sb["med"]) if sb else "—", ("%+.2f" % sb["trim"]) if sb else "—"))

P("\n총 %.0f초" % (time.time() - t0))
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(OUT))
