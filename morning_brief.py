# -*- coding: utf-8 -*-
"""아침 브리핑 한 통 — 2026-11-12 사용자 "⑧ 해줘". 08:35(평일) 텔레그램 하나, 핵심만.
  · 오늘: 휴장이면 그 한 줄만 · 늦은 개장(수능) · 옵션 만기(둘째 목) · 월말
  · 오늘 시가 매도 예정: 데이 원장에서 어제 산 [장후 낙폭]·이월 보유
  · 어제 실전: 감사관(data/audit/live.csv) 끝난 왕복 건수·건당(실전/연구)
  · 매수 가능 금액(토스)
  · 밤 사이 판정·경보: 사전 등록 판정·밤 연구 일꾼 결과는 각자 보낸다 — 여기선 안 되풀이
    python morning_brief.py [dry]
"""
import datetime as dt, json, sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
LOG = BASE / "data" / "day" / "brief.log"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import pandas as pd

WD = "월화수목금토일"
RNAME = {"T1": "갭하락", "T2": "갭하락+", "T3": "갭하락++", "T4": "미장 폭락", "T5": "장전 되돌림", "T6": "장후 낙폭"}


def special(day, prev):
    d = dt.date(int(day[:4]), int(day[4:6]), int(day[6:]))
    out = []
    try:
        import collect_m1 as M
        if day in getattr(M, "LATE_OPEN", set()): out.append("늦은 개장 10:00(수능)")
    except Exception: pass
    if d.weekday() == 3 and 8 <= d.day <= 14: out.append("옵션 만기")
    nxt = d + dt.timedelta(days=1)
    while nxt.weekday() >= 5: nxt += dt.timedelta(days=1)
    if nxt.month != d.month: out.append("월말")
    return out


def holds(today):
    """오늘 시가에 팔 데이 보유 — 원장에서 매수 체결됐고 아직 매도 체결 없는 것(오늘 산 것 빼고)."""
    X = json.loads((BASE / "data" / "day" / "ledger.json").read_text(encoding="utf-8"))["orders"]
    sold = {o.get("posId") for o in X if o.get("side") == "SELL" and o.get("status") == "FILLED"}
    h = {}
    old = (dt.datetime.strptime(today, "%Y%m%d") - dt.timedelta(days=7)).strftime("%Y%m%d")   # 10-06 첫날 매도와 안 이어진 찌꺼기 3건 같은 옛 줄은 뺀다
    for o in X:
        if o.get("side") == "BUY" and o.get("status") == "FILLED" and (o.get("fq") or 0) > 0 and old <= o.get("date") < today:
            pid = (o.get("pos") or {}).get("id")
            if pid and pid not in sold: h.setdefault(o.get("rid"), []).append(o.get("name") or o.get("t"))
    return h


def yesterday(prev):
    f = BASE / "data" / "audit" / "live.csv"
    if not f.exists() or not prev: return None
    A = pd.read_csv(f, dtype={"sell_day": str})
    z = A[A.sell_day == prev]
    if not len(z): return None
    parts = ["%s %d건 %+.2f%%" % (RNAME.get(r, r), len(g), g.live.mean()) for r, g in z.groupby("rid")]
    return "어제 실전 %d건 %+.2f%% (연구 %+.2f%%) · %s" % (len(z), z.live.mean(), z.research.mean(), " · ".join(parts))


def main(dry=False):
    import autotrade as AT
    import day_alert as D
    today = AT.now().strftime("%Y%m%d")
    S = AT.session("KR")
    if not S or S["date"] != today:
        print(today, "휴장 — 안 보냄"); return
    lines = ["☀️ <b>%s/%s(%s)</b>%s" % (today[4:6], today[6:], WD[AT.now().weekday()], (" · " + " · ".join(special(today, S.get("prev")))) if special(today, S.get("prev")) else "")]
    h = holds(today)
    if h: lines.append("시가 매도 예정: " + " · ".join("[%s] %d" % (RNAME.get(r, r), len(v)) for r, v in sorted(h.items(), key=lambda kv: str(kv[0]))))
    y = yesterday(S.get("prev"))
    if y: lines.append(y)
    try: lines.append("매수 가능 %.0f만" % (AT.buying_power("KRW") / 1e4))
    except Exception as ex: lines.append("매수 가능 금액 못 읽음")
    if (AT.OUT / "STOP").exists(): lines.append("⛔ 자동매매 STOP 켜짐")
    msg = "\n".join(lines)
    print(msg)
    if not dry: D.telegram(msg)


if __name__ == "__main__":
    main(dry=(sys.argv[1:2] == ["dry"]))
