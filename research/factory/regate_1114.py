# -*- coding: utf-8 -*-
"""2026-11-14 새 관문 4종(gates.py) 다시 거르기 — 공장에서 G2 를 통과했던 명세 전부 + 기준 규칙(T1 [갭하락] 명세판)을
옛 판정(GATES False)과 새 판정(GATES True)으로 같이 잰다. 등록부(specs.jsonl)는 안 고친다(보고만).
    python research/factory/regate_1114.py   → research/reports/factory/regate_1114.md"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
import lab, gates as GT
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
L = lab.load()
X = [x for x in L if ((x.get("stage") or 0) >= 2) and not lab.uses_live(x)]
LIVE = [x["id"] for x in L if ((x.get("stage") or 0) >= 2) and lab.uses_live(x)]
REF = [dict(id="기준 T1", name="[갭하락] 명세판", mode="oc", conds=[{"f": "rgap", "op": "<=", "v": -1.5}, {"f": "gap", "q": True, "op": "<=", "v": 0.40},
            {"f": "vm", "q": True, "op": "<=", "v": 0.30}, {"f": "liq", "op": "<=", "v": 0.4444}], status="기준")]
U = lab.hist(); t0 = time.time()
P("# 새 관문 4종 다시 거르기 (%s)\n" % time.strftime("%Y-%m-%d %H:%M"))
P("- 대상: 공장에서 검증(G2)까지 통과했던 명세 %d개 + 기준 규칙 1개 · 실시간 재료라 과거가 없는 %s 는 못 잼" % (len(X), ", ".join(LIVE) or "없음"))
P("- 관문: ⑨ 분포(상위 5%% 뺀 건당 > 0 · 좋은 날 10개 < %.0f%%) · ⑪ 거울(뒤집은 짝 비용 뒤 ≤ 0) · ⑤ 이웃(같은 부호 ≥ %.0f%% · 이웃 평균 ≥ 원래의 %.0f%%) · ④ 가짜 달력(무작위 %d판 중 상위 %.0f%%)\n" % (
    GT.SHAPE_TOP, GT.NEI_AGREE * 100, GT.NEI_KEEP * 100, GT.CAL_N, (1 - GT.CAL_P) * 100))
P("| 명세 | 지금 상태 | 방식·조건 | 검증 건당·중앙 | 옛 판정 | 새 판정 | 관문 숫자 | 걸린 이유 |"); P("|---|---|---|---|---|---|---|---|")
res = []
for x in REF + X:
    lab.GATES = False; R0 = lab.judge(x, U)
    lab.GATES = True; R1 = lab.judge(x, U)
    v = R1.get("va") or R0.get("va") or {}
    G = R1.get("gates")
    new = "통과" if R1["stage"] >= 2 else "탈락"
    why = " / ".join(w for w in (R1["why"] or "").split(" · ") if w[:1] in "⑨⑪⑤④") or ("" if new == "통과" else R1["why"][:80])
    P("| %s | %s | %s | %s | %s | **%s** | %s | %s |" % (x["id"], x.get("status"), lab.desc(x)[:70], ("%+.2f / %+.2f" % (v["mean"], v["med"])) if v else "-",
      "통과" if R0["stage"] >= 2 else "탈락", new, GT.fmt(G) if G else "-", why))
    res.append(dict(id=x["id"], old=R0["stage"], new=R1["stage"], why=R1["why"], gates=G))
    print("  %.1f분" % ((time.time() - t0) / 60), flush=True)
n_old = sum(r["old"] >= 2 for r in res[1:]); n_new = sum(r["new"] >= 2 for r in res[1:])
P("\n공장 통과 명세: 옛 판정 %d개 → 새 판정 %d개 · 기준 [갭하락] 명세판: %s" % (n_old, n_new, "통과" if res[0]["new"] >= 2 else "탈락 — " + res[0]["why"]))
from collections import Counter
P("걸린 관문 수: " + str(dict(Counter(w[:1] for r in res[1:] for w in (r["why"] or "").split(" · ") if w[:1] in "⑨⑪⑤④"))))
Path(lab.__file__).resolve().parent.parent.joinpath("reports", "factory").mkdir(parents=True, exist_ok=True)
Path(lab.__file__).resolve().parent.parent.joinpath("reports", "factory", "regate_1114.md").write_text("\n".join(OUT), encoding="utf-8")
json.dump(res, open(r"C:\temp\kp\regate_1114.json", "w", encoding="utf-8"), ensure_ascii=False, default=float)
