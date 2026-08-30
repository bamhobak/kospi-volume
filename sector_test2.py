# -*- coding: utf-8 -*-
"""업종 폭락 신호가 '시장 폭락'의 대리지표인지 검증 + 테마 실측"""
import io, sys, csv, time
from collections import defaultdict
import numpy as np, pandas as pd
exec(open("sector_test.py", encoding="utf-8").read().split("# ── 종목 상태 분류")[0])

D["st"] = np.select(
    [D.fromhi120 >= -0.03, D.fromlo120 <= 0.03, (D.boxw60 <= 0.30) & D.fib.between(0.3, 0.7)],
    ["고점갱신", "저점갱신", "횡보"], default="중간")
d1 = D[LIQ].groupby(["date", "up"]).agg(sret20=("ret20", "mean"), sret60=("ret60", "mean"),
                                        cnt=("ticker", "size")).reset_index()
d1 = d1[d1.cnt >= 5]
D = D.merge(d1[["date", "up", "sret20", "sret60"]], on=["date", "up"], how="left")
LIQ = (D.amt20 >= 10) & D.up.notna() & D.sret60.notna()
# 시장 60일 수익률
MK60 = D.groupby("date").ret60.mean().rename("mk60")
D = D.merge(MK60, on="date");
log(f"준비 완료 {int(LIQ.sum()):,}행")

SC = D.sret60 <= -20            # 업종 폭락
MC = D.mk60 <= -10              # 시장(전체 평균) 폭락

print("\n## ① 업종 폭락 vs 시장 폭락 — 무엇이 진짜 신호인가 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("업종 폭락(60일 -20%↓)", SC),
    ("시장 폭락(전체평균 60일 -10%↓)", MC),
    ("**업종만 폭락 · 시장은 멀쩡**", SC & ~MC),
    ("**시장만 폭락 · 업종은 아님**", ~SC & MC),
    ("둘 다 폭락", SC & MC),
    ("둘 다 아님", ~SC & ~MC),
]: row(lab, simulate((LIQ & m).values, 10))
print("\n→ '업종만 폭락'이 플러스면 업종 고유 신호, 0이면 시장 폭락의 대리지표일 뿐입니다.\n")

print("## ② 업종 낙폭 강도별 (시장 폭락 아닐 때만)\n"); print(HDR)
for lo, hi in [(-100, -30), (-30, -20), (-20, -10), (-10, 0), (0, 100)]:
    row(f"업종 60일 {lo}~{hi}%", simulate((LIQ & ~MC & D.sret60.between(lo, hi)).values, 10))

print("\n## ③ 코스피 60일선(3번 필터 조건)과의 관계 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("코스피 60일선 아래", ~D.K60),
    ("코스피 60일선 아래 + 업종 폭락", (~D.K60) & SC),
    ("코스피 60일선 아래 + 업종 멀쩡", (~D.K60) & ~SC),
    ("코스피 60일선 위 + 업종 폭락", D.K60 & SC),
    ("코스피 60일선 위 + 업종 멀쩡", D.K60 & ~SC),
]: row(lab, simulate((LIQ & m).values, 10))

print("\n## ④ 연도별 — 업종 폭락 신호\n")
s = simulate((LIQ & SC).values, 10)
yy = pd.Series(s["r"]).groupby(s["y"]).agg(["mean", "size"])
print("| 연도 | " + " | ".join(str(y) for y in yy.index) + " |\n|---|" + "---|" * len(yy))
print("| 수익 | " + " | ".join(f"**{yy.loc[y,'mean']:+.1f}%**" for y in yy.index) + " |")
print("| 건수 | " + " | ".join(f"{int(yy.loc[y,'size']):,}" for y in yy.index) + " |")
s2 = simulate((LIQ & SC & ~MC).values, 10)
if s2 is not None:
    yy2 = pd.Series(s2["r"]).groupby(s2["y"]).agg(["mean", "size"])
    print("\n업종만 폭락(시장 멀쩡):")
    print("| 연도 | " + " | ".join(str(y) for y in yy2.index) + " |\n|---|" + "---|" * len(yy2))
    print("| 수익 | " + " | ".join(f"**{yy2.loc[y,'mean']:+.1f}%**" for y in yy2.index) + " |")
    print("| 건수 | " + " | ".join(f"{int(yy2.loc[y,'size']):,}" for y in yy2.index) + " |")

print("\n\n## ⑤ 업종별 성적 (업종 폭락 구간에서, 신호 300건 이상)\n")
m = (LIQ & SC).values
sub = D[m].copy()
res = simulate(m, 10)
sub = sub.iloc[[np.where(np.flatnonzero(m) == i)[0][0] for i in res["i"]]] if False else None
idx = res["i"]; tmp = D.loc[idx, ["up"]].copy(); tmp["r"] = res["r"]
agg = tmp.groupby("up").r.agg(["size", "mean", "median", lambda x: (x > 0).mean()*100])
agg.columns = ["건수", "평균", "중앙값", "승률"]
agg = agg[agg.건수 >= 300].sort_values("평균", ascending=False)
print("| 업종 | 건수 | 평균 | 중앙값 | 승률 |\n|---|---|---|---|---|")
for g_, r_ in agg.head(12).iterrows():
    print(f"| {g_} | {int(r_['건수']):,} | **{r_['평균']:+.2f}%** | {r_['중앙값']:+.2f}% | {r_['승률']:.0f}% |")
print("| … | | | | |")
for g_, r_ in agg.tail(5).iterrows():
    print(f"| {g_} | {int(r_['건수']):,} | **{r_['평균']:+.2f}%** | {r_['중앙값']:+.2f}% | {r_['승률']:.0f}% |")

# ── 테마 (미래참조 경고) ─────────────────────────────────────
print("\n\n## ⑥ 테마별 — ⚠ 오늘 기준 테마 구성을 과거에 적용 (미래참조 위험)\n")
TH2 = {t: v for t, v in TH.items()}
rows_ = []
for th_name in ("2차전지(생산)", "반도체 대표주(생산)", "제약업체", "건설 대표주",
                "지능형로봇/인공지능(AI)", "전기차", "바이오텍(biotechnology)", "방위산업/전쟁 및 테러",
                "수소에너지(수소차/연료전지 등)", "자율주행차"):
    tks = {t for t, gs in TH2.items() if th_name in gs}
    if len(tks) < 8: continue
    mm = LIQ & D.ticker.isin(tks)
    s_ = stat(simulate(mm.values, 10))
    if s_: rows_.append((th_name, len(tks), s_))
print("| 테마 | 종목수 | 신호 | 절대수익 | 초과 | 승률 | 학습 | 검증 |\n|---|---|---|---|---|---|---|---|")
for nm, ntk, s_ in sorted(rows_, key=lambda x: -x[2]["ret"]):
    print(f"| {nm} | {ntk} | {s_['n']:,} | **{s_['ret']:+.2f}%** | {s_['ret']-BASELINE[10]:+.2f}%p | "
          f"{s_['win']:.0f}% | {s_['is_']:+.2f}% | **{s_['os_']:+.2f}%** |")
log("완료")
