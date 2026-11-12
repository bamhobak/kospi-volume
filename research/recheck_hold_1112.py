# -*- coding: utf-8 -*-
"""스윙 보유 종목 재판정 (2026-11-12 사용자 "지금 보유 중인 것 중 지금 규칙이라면 안 샀을 것").
국장: stats_2016.py 의 RULES(사이트 지금 정의 미러) 조건 cond 를 신호 날(매수 날의 전 거래일 · [외인 매집] P7 은 매수 날 종가 매수라 그날)에 직접 짚는다.
      take() 는 패널 끝까지 못 간 거래(= 지금 보유)를 빼므로 쓰지 않는다. 패널 끝 뒤 신호는 '판단 못 함'.
미장: 연구 패널 us_full_2007.pkl 끝 날짜만 확인(보유 매수 날까지 이어져 있지 않으면 판단 못 함).
    python research/recheck_hold_1112.py → research/reports/recheck_hold_1112.md · .csv
"""
import io, json, os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
P_ = json.load(open(r"C:\temp\hold_pos.json", encoding="utf-8"))
src = (BASE / "stats_2016.py").read_text(encoding="utf-8").split("OUT = {}")[0]
ns = {"__file__": str(BASE / "stats_2016.py"), "__name__": "x"}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src, "stats_2016.py", "exec"), ns)
sys.stdout = real; sys.stdout.reconfigure(encoding="utf-8")
RULES, NAME = ns["RULES"], ns["NAME"]
BUY_CLOSE = {"P7"}
rows = []
for p in P_:
    rid = (p.get("filters") or ["?"])[0]; code = str(p["code"]); b = str(p["date"])
    if rid.startswith("N"): continue
    r = dict(rid=rid, name=NAME.get(rid, rid), code=code, nm=p.get("name"), buy=b, paper=bool(p.get("paper")), price=p.get("price"))
    if rid not in RULES:
        r.update(verdict="규칙 모름"); rows.append(r); continue
    K, hold, stop, pct, mx, cond = RULES[rid]
    cal = np.array(sorted(K.date.unique()))
    if rid in BUY_CLOSE: s = b
    else:
        j = np.searchsorted(cal, b) - 1
        s = cal[j] if j >= 0 else None
    r["signal"] = s; r["panel_end"] = cal[-1]
    if b > cal[-1] and rid not in BUY_CLOSE or (rid in BUY_CLOSE and b > cal[-1]):
        r.update(verdict="판단 못 함(패널 끝 %s)" % cal[-1]); rows.append(r); continue
    m = (K.ticker.values == code) & (K.date.values == s)
    if not m.any():
        r.update(verdict="안 샀을 것 — 그날 규칙 표본(유니버스) 밖"); rows.append(r); continue
    ok = bool(cond.fillna(False).values[m][0])
    r.update(verdict="그대로" if ok else "안 샀을 것 — 지금 조건 미달")
    rows.append(r)
R = pd.DataFrame(rows)
R.to_csv(ROOT / "reports" / "recheck_hold_1112.csv", index=False, encoding="utf-8-sig")
out = ["# 스윙 보유 재판정(국장) · 2026-11-12", "", "| 판정 | 건수 |", "|---|---|"]
for v, z in R.groupby("verdict"): out.append("| %s | %d |" % (v, len(z)))
out += ["", "| 규칙 | 종목 | 매수 날 | 신호 날 | 가상 | 판정 |", "|---|---|---|---|---|---|"]
for r in R.sort_values(["verdict", "rid", "buy"]).itertuples():
    out.append("| %s | %s(%s) | %s | %s | %s | %s |" % (r.name, r.nm, r.code, r.buy, getattr(r, "signal", ""), "가상" if r.paper else "", r.verdict))
print("\n".join(out))
(ROOT / "reports" / "recheck_hold_1112.md").write_text("\n".join(out) + "\n", encoding="utf-8")
try:
    U = pd.read_pickle(BASE / "data" / "us_full_2007.pkl", )
    print("\n미장 연구 패널 끝:", U.date.max())
except Exception as ex:
    print("미장 패널 못 읽음", repr(ex)[:100])
