# -*- coding: utf-8 -*-
"""아침 브리핑 한 통 — 2026-11-12 사용자 "⑧ 해줘". 08:35(평일) 텔레그램 하나, 핵심만.
  · 오늘: 휴장이면 그 한 줄만 · 늦은 개장(수능) · 옵션 만기(둘째 목) · 월말
  · 오늘 시가 매도 예정: 데이 원장에서 어제 산 [장후 낙폭]·이월 보유
  · 어제 실전: 감사관(data/audit/live.csv) 끝난 왕복 건수·건당(실전/연구)
  · 매수 가능 금액(토스)
  · 밤 사이 판정·경보: 사전 등록 판정·밤 연구 일꾼 결과는 각자 보낸다 — 여기선 안 되풀이
  · 막은 경보 N: 경보 판독관(tg_gate.py)이 지난 브리핑 뒤로 막은 수(있을 때만)
  · 원격 로그인 D-N: 폰 원격 세션(StockServer) 로그인 만료 5일 전부터(11-20) — 약 30일마다 서버에서 claude auth login
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


def rc_login(limit=5):
    """폰 원격 세션(StockServer) 로그인 만료가 limit 일 안이면 한 줄 — 2026-11-20 사용자 "원격 로그인 알림도 오게".
    로그인은 약 30일 가고 못 늘린다(쓴다고 연장되지 않음). 1년 토큰 변수를 지워야 정식 로그인 쪽 날짜가 보인다."""
    import os, re, subprocess
    exe = Path.home() / ".local" / "bin" / "claude.exe"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
    try:
        r = subprocess.run([str(exe), "auth", "status", "--text"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=30, env=env, creationflags=0x08000000)
    except Exception as ex:
        print("원격 로그인 확인 실패:", type(ex).__name__); return None
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"Sign-in ends:(.*)", out)
    if not m:
        if re.search(r"not logged in|logged out|login expired|time limit", out, re.I): return "원격 로그인 풀림 · claude auth login"
        print("원격 로그인 날짜 못 읽음"); return None
    ds = re.findall(r"(\d{4})-(\d{2})-(\d{2})", m.group(1))
    if not ds: return "원격 로그인 곧 만료 · claude auth login"          # 날짜 없이 'any day now' · 'may have ended'
    left = (dt.date(*map(int, ds[0])) - dt.date.today()).days          # 적힌 날 중 가장 이른 날 기준
    if left > limit: return None
    return ("원격 로그인 D-%d · claude auth login" % left) if left > 0 else "원격 로그인 곧 만료 · claude auth login"


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
    try:                                               # 11-20 폰 원격 세션 로그인 만료 5일 전부터
        x = rc_login()
        if x: lines.append(x)
    except Exception: pass
    try:                                               # 11-16 경보 판독관이 지난 브리핑 뒤로 막은 경보 — 뭐였는지는 점검 현황 페이지
        import tg_gate
        last = json.loads((BASE / "data" / "day" / "brief_last.json").read_text(encoding="utf-8")).get("at", "")
        n = tg_gate.held_since(last)
        if n: lines.append("막은 경보 %d(점검 현황)" % n)
    except Exception: pass
    msg = "\n".join(lines)
    print(msg)
    if not dry:
        D.telegram(msg)
        (BASE / "data" / "day" / "brief_last.json").write_text(json.dumps({"at": AT.now().strftime("%Y-%m-%d %H:%M"), "text": msg}, ensure_ascii=False), encoding="utf-8")   # 자동 현황 페이지가 읽는다


if __name__ == "__main__":
    main(dry=(sys.argv[1:2] == ["dry"]))
