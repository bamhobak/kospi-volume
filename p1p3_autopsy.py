# -*- coding: utf-8 -*-
"""**[폭락반등]·[조용한 신고가] 해부** (2026-09-16 요청).

홀드아웃(2005~2015)에서 9규칙 중 둘만 미달했다.
  [조용한 신고가] 중앙 -3.37 · 절삭 -3.42 · 승률 35% · 양수해 1/7 (n=276)
  [폭락반등]     중앙 -6.36 · 절삭 -2.56 · 승률 45% · **상위5%기여 681%** (n=77)

그런데 그 구간엔 **가격제한폭 ±15%** 라는 제도 차이가 있어서 전 규칙이 낮게 나온다.
그러니 "홀드아웃에서 나빴다" 만으로는 규칙 탓인지 제도 탓인지 알 수 없다.

**가르는 방법: 제도는 모든 규칙에 똑같이 걸린다.** 같은 구간·같은 제도 아래에서
다른 규칙이 멀쩡히 통과했다면 제도 탓이 아니다. [깊은 이격]은 같은 2005~2015 에서
중앙 +11.31 · 승률 68% 였고, [외인 매집]은 +4.89 · 62% 였다.

  ① 같은 제도 아래 짝비교 — 2005~2015 전 규칙을 한 표에
  ② [폭락반등] 상위5% 해부 — 몇 건이 만든 숫자인가, 빼면 무엇이 남나
  ③ [폭락반등] 구간·사건별 — 2008 · 2011 · 2020-03 · 2022
  ④ [조용한 신고가] 해부 — 상승 규칙인데 왜 홀드아웃에서 죽나
  ⑤ 둘의 최근 성적 — 지금도 나쁜가, 옛날에만 나빴나

판정은 새 기준이다 — 무제한 자금 · 전 신호 동일금액 · 유니버스 초과는 안 본다.

    python p1p3_autopsy.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 126
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
hit = S.stop.notna() & ((S.low / S.buy - 1) * 100 <= -S.stop * 100)
S["ret"] = np.where(hit, -S.stop * 100 - S.cost, (S.exit / S.buy - 1) * 100 - S.cost)
S["yr"] = S.date.str[:4]
NM = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
      "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
      "D1": "낙폭과대", "D2": "저PBR 낙폭"}
ORD = ["P1", "P7", "P2", "P3", "P4", "P5", "P6", "D1", "D2"]
HO = (S.date <= "20151231")


def st(v, lab=""):
    if len(v) < 5:
        return None
    tr = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() else np.nan
    return dict(n=len(v), mean=v.mean(), med=v.median(), trim=tr,
                win=(v > 0).mean() * 100, t5=t5, worst=v.min(), best=v.max())


sec("① 같은 제도 아래 짝비교 — 2005~2015 (전 규칙 · 가격제한폭 ±15%)")
P("  제도는 모든 규칙에 똑같이 걸린다. 여기서 갈리면 **제도 탓이 아니다**.\n")
P("  %-16s%8s%9s%9s%9s%8s%11s%9s" % ("규칙", "n", "평균", "중앙", "절삭", "승률", "상위5%기여", "최악"))
for r in ORD:
    s = st(S[(S.rid == r) & HO].ret)
    if not s:
        P("  %-16s%8s  (부족)" % (NM[r], f"{int(((S.rid == r) & HO).sum()):,}")); continue
    mark = "  ← 미달" if not (s["med"] > 0 and s["trim"] > 0) else ""
    P("  %-16s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%10.0f%%%+9.1f%s"
      % (NM[r], f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], s["t5"], s["worst"], mark))

sec("② [폭락반등] 상위 몇 건이 만든 숫자인가")
v = S[(S.rid == "P3") & HO].ret.sort_values(ascending=False)
P("  홀드아웃 %d건 · 합계 %+.0f%%p · 평균 %+.2f%%\n" % (len(v), v.sum(), v.mean()))
P("  %-14s%10s%10s%10s%9s" % ("빼는 개수", "남은 n", "평균", "중앙", "승률"))
for k in (0, 1, 2, 3, 5, 8):
    z = v.iloc[k:]
    P("  %-14s%10s%+10.2f%+10.2f%8.0f%%" % ("상위 %d건" % k, f"{len(z):,}", z.mean(), z.median(),
                                            (z > 0).mean() * 100))
P("\n  상위 5건: " + " · ".join("%+.0f%%" % x for x in v.head(5)))
P("  하위 5건: " + " · ".join("%+.0f%%" % x for x in v.tail(5)))
z3 = S[(S.rid == "P3") & HO].nlargest(5, "ret")
P("\n  %-12s%-10s%10s%10s" % ("날짜", "종목", "수익", "거래대금"))
for t in z3.itertuples():
    P("  %-12s%-10s%+9.1f%%%10.1f" % (t.date, str(t.name)[:9], t.ret, t.amt20))

sec("③ [폭락반등] 사건별 — 큰 폭락마다 어땠나")
EV = [("2008 금융위기", "20080101", "20081231"), ("2009 회복", "20090101", "20091231"),
      ("2011 유럽위기", "20110101", "20111231"), ("2015 중국쇼크", "20150101", "20151231"),
      ("2018 조정", "20180101", "20181231"), ("2020 코로나", "20200101", "20201231"),
      ("2022 긴축", "20220101", "20221231"), ("2023~26", "20230101", "20301231")]
P("  %-16s%8s%9s%9s%9s%8s%11s" % ("사건", "n", "평균", "중앙", "절삭", "승률", "상위5%기여"))
for lbl, a, b in EV:
    s = st(S[(S.rid == "P3") & (S.date >= a) & (S.date <= b)].ret)
    if not s:
        P("  %-16s%8s  (부족)" % (lbl, f"{int(((S.rid == 'P3') & (S.date >= a) & (S.date <= b)).sum()):,}"))
        continue
    P("  %-16s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%10.0f%%"
      % (lbl, f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], s["t5"]))

sec("④ [조용한 신고가] 해부 — 상승 규칙인데 왜 홀드아웃에서 죽나")
P("  ⚠ 상승 규칙은 '반등이 제한폭에 막혀서' 로 설명하기 어렵다. 급반등을 먹는 규칙이 아니다.\n")
P("  %-16s%8s%9s%9s%9s%8s%11s" % ("구간", "n", "평균", "중앙", "절삭", "승률", "상위5%기여"))
for lbl, a, b in [("홀드 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"),
                  ("검증 23~26", "20230101", "20301231"),
                  ("05~09", "20050101", "20091231"), ("10~15", "20100101", "20151231")]:
    s = st(S[(S.rid == "P1") & (S.date >= a) & (S.date <= b)].ret)
    if not s:
        P("  %-16s  (부족)" % lbl); continue
    P("  %-16s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%10.0f%%"
      % (lbl, f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], s["t5"]))
P("\n  같은 상승 규칙 [외인 매집] 을 같은 구간에 놓고 보면:")
for lbl, a, b in [("홀드 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"),
                  ("검증 23~26", "20230101", "20301231")]:
    s = st(S[(S.rid == "P7") & (S.date >= a) & (S.date <= b)].ret)
    if s:
        P("  %-16s%8s%+9.2f%+9.2f%+9.2f%7.0f%%%10.0f%%"
          % ("  " + lbl, f"{s['n']:,}", s["mean"], s["med"], s["trim"], s["win"], s["t5"]))

sec("⑤ 최근 성적 — 지금도 나쁜가, 옛날에만 나빴나")
P("  %-16s" % "규칙" + "".join("%8s" % y for y in range(2016, 2027)))
for r in ["P1", "P3", "P7", "P6"]:
    z = S[S.rid == r]
    row = ""
    for y in range(2016, 2027):
        vv = z[z.yr == str(y)].ret
        row += ("%8.1f" % vv.median()) if len(vv) >= 5 else "%8s" % "—"
    P("  %-16s%s" % (NM[r], row))
P("\n  (건수)")
for r in ["P1", "P3"]:
    z = S[S.rid == r]
    P("  %-16s" % NM[r] + "".join("%8d" % int((z.yr == str(y)).sum()) for y in range(2016, 2027)))

P("\n총 %.0f초" % (time.time() - t0))
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(OUT))
