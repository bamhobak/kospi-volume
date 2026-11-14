# -*- coding: utf-8 -*-
"""2026-11-14 새 관문 4종이 쓸모 있나 — 공장에서 학습(G1)을 통과한 명세 전부에 **학습 구간만으로** 관문을 돌리고,
관문 통과/탈락 묶음의 검증(2023~) 성적을 비교한다. 관문이 학습 자료만으로 '검증에서 망할 것'을 미리 골라내면 G1 에 붙일 가치가 있다.
검증 성적은 등록부에 이미 적힌 res.va(그때 판정 값). 등록부는 안 고친다.
    python research/factory/regate2_1114.py   → research/reports/factory/regate2_1114.md"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, gates as GT
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
L = lab.load()
X = [x for x in L if (x.get("stage") or 0) >= 1 and not lab.uses_live(x) and (x.get("res") or {}).get("va")]
U = lab.hist(); t0 = time.time(); rows = []
for i, x in enumerate(X):
    try:
        T = lab.trades(U, x)
        _, TR_, VA_ = lab.periods(x)
        tr0 = max("20180101", TR_[0]) if any(c["f"] in lab.FT.FLOW for c in x["conds"]) else TR_[0]
        if x["mode"].startswith("sw"):
            tg = lab.FT.TARGET[x["mode"]]; T = T.assign(ex=T.ret - T.date.map(U.groupby("date")[tg].mean()))
        G = GT.run_all(lab, U, x, T, tr0, (tr0, TR_[1]), "KR")      # 학습 구간으로만
    except Exception as ex:
        print("오류", x["id"], repr(ex)[:120], flush=True); continue
    va = x["res"]["va"]; s = G["shape"] or {}; m = G["mirror"]; p = G["plateau"]; c = G["cal"] or {}
    tags = {w[:1] for w in G["why"]}
    rows.append(dict(id=x["id"], mode=x["mode"], origin=x.get("origin"), va_mean=va["mean"], va_med=va.get("med"), va_t=va.get("t"), va_n=va["n"],
                     old_pass=(x.get("stage") or 0) >= 2, g9="⑨" in tags, g11="⑪" in tags, g5="⑤" in tags, g4="④" in tags, gate_pass=not tags,
                     trim=s.get("trim"), top10=s.get("top10"), inv=m.get("inv_mean"), inv_ex=m.get("inv_ex"), agree=p.get("agree"), keep=p.get("keep"), pct=c.get("pct")))
    if i % 10 == 0: print("%d/%d %.1f분" % (i, len(X), (time.time() - t0) / 60), flush=True)
R = pd.DataFrame(rows); R.to_csv(Path(lab.__file__).resolve().parent.parent / "reports" / "factory" / "regate2_1114.csv", index=False, encoding="utf-8-sig")
good = lambda g: (g.va_mean >= lab.VA_MIN) & (g.va_med > 0) & (g.va_t >= 1)


def line(nm, g):
    if not len(g): return "| %s | 0 | | | | | |" % nm
    return "| %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %.0f%% | %.0f%% |" % (nm, len(g), g.va_mean.mean(), g.va_med.median(), (g.va_mean > 0).mean() * 100,
                                                            good(g).mean() * 100, g.old_pass.mean() * 100)


P("# 새 관문 4종 — 학습 구간만으로 걸러도 검증이 나아지나 (%s)\n" % time.strftime("%Y-%m-%d %H:%M"))
P("- 대상: 공장에서 학습(G1)을 통과한 명세 %d개(실시간 재료 제외) · 관문은 학습 구간(2016~22, 수급 재료면 2018~)으로만 계산 · 검증 값은 등록부 기록\n" % len(R))
HD = "| 묶음 | 명세 | 검증 건당 평균 | 검증 중앙(명세들 가운데) | 검증 플러스 | 지금 기준 합격감(건당 ≥0.5·중앙>0·t≥1) | 옛 G2 통과 |\n|---|---|---|---|---|---|---|"
P(HD)
P(line("전체", R)); P(line("**관문 4개 다 통과**", R[R.gate_pass])); P(line("하나라도 걸림", R[~R.gate_pass]))
for k, nm in (("g9", "⑨ 복권형"), ("g11", "⑪ 거울도 플러스"), ("g5", "⑤ 봉우리"), ("g4", "④ 가짜 달력")):
    P(line(nm + " 걸림", R[R[k]])); P(line(nm + " 안 걸림", R[~R[k]]))
P("\n방식별(관문 통과 / 걸림)\n"); P(HD)
for md, g in R.groupby(R["mode"].str[:2]):
    P(line("%s 통과" % md, g[g.gate_pass])); P(line("%s 걸림" % md, g[~g.gate_pass]))
P("\n상관(명세 단위, 학습 값 → 검증 건당): " + " · ".join("%s %.2f" % (k, R[k].astype(float).corr(R.va_mean)) for k in ("trim", "top10", "inv", "agree", "keep", "pct") if R[k].notna().sum() > 10))
(Path(lab.__file__).resolve().parent.parent / "reports" / "factory" / "regate2_1114.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
