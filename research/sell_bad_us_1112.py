# -*- coding: utf-8 -*-
"""2026-11-12 사용자 "지금 다 매도 처리하고, 사이트 기록에서도 빼줘" → "지금 팔 수 없나? 아니면 사이트에서만이라도 안 보이게"
지금 규칙이면 안 샀을 미장 보유 16개(research/recheck_us_1112): [실적 서프라이즈] N6 8 · [상승장 신고가] N1 8. WESCO·TSMC 는 그대로.
① 지금: 사이트 positions 에서 16개를 지우고 data/autotrade/site_hidden.json 에 id(heal 이 되살리지 않게) — 백업 positions_backup_20261112_us16.json
② 미장 마감 45분 전(11-13 05:15 KST): autotrade.sell("US") 를 부르되 site_state 는 백업의 16개만 돌려주고 held_days 는 매도일 도래로
   → 평소와 같은 LOC 종가 매도 · 원장에 매도 기록(사이트엔 이미 없어 표시는 안 바뀜). 토스 API 장외 주문은 써 본 적 없어 정규장 종가로.
"""
import json, sys, time, datetime as dt
from pathlib import Path
BASE = Path(r"C:\vscode\kospi-volume"); sys.path.insert(0, str(BASE))
import autotrade as AT
LOG = BASE / "data" / "autotrade" / "sell_bad_us_1112.log"
BK = BASE / "data" / "autotrade" / "positions_backup_20261112_us16.json"
def log(*a):
    s = "%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a))
    with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
TARGET = "GTLB NTSK DELL SNOW CHPT AVAV TCOM FEIM MRNA EMBJ BAP ZBRA CAI KEYS CNK JCI".split()
try:
    if AT.MODE != "live":
        log("AUTOTRADE_MODE=%s — 주문 안 함" % AT.MODE); sys.exit(0)
    allpos = json.loads(BK.read_text(encoding="utf-8"))                    # ① 의 첫 실행 때 만든 백업(그 뒤로 안 덮어씀)
    tpos = [p for p in allpos if p.get("code") in TARGET and not p.get("sell") and p.get("auto")]
    ids = {p["id"] for p in tpos}
    log("대상", len(tpos), sorted(p["code"] for p in tpos))
    # ① 사이트에서 지금 빼기
    def drop(P):
        n0 = len(P); P[:] = [p for p in P if p.get("id") not in ids]; return len(P) != n0
    AT.site_update(drop, "미장 정리 16건 사이트에서 빼기(매도는 05:15 종가)")
    h = json.loads(AT.HIDDEN.read_text(encoding="utf-8")) if AT.HIDDEN.exists() else {"ids": []}
    h["ids"] = sorted(set(h.get("ids") or []) | ids)
    AT.HIDDEN.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    left = [p["code"] for p in AT.site_state().get("positions") or [] if p.get("id") in ids]
    log("사이트에서 뺌 · 남은 것", left)
    AT.telegram("🧹 <b>미장 정리</b> 지금 규칙이면 안 샀을 %d개 사이트에서 뺌%s · 매도는 오늘 밤 미장 종가(LOC, 05:15 접수)" % (len(ids), (" ⚠ 남음 " + ",".join(left)) if left else ""))
    # ② 마감 45분 전 매도
    S = AT.session("US")
    t_go = S["end"] - dt.timedelta(minutes=45)
    log("미장 마감", S["end"], "· 매도 시작", t_go)
    AT.sleep_until(t_go, "미장 마감 45분 전")
    keys = {(p["code"], str(p["date"])) for p in tpos}
    real_hd, real_ss = AT.held_days, AT.site_state
    AT.held_days = lambda sym, bd, sd: 9999 if (sym, str(bd)) in keys else 0
    AT.site_state = lambda: {"positions": [dict(p) for p in tpos]}
    try:
        AT.sell("US")
    finally:
        AT.held_days, AT.site_state = real_hd, real_ss
    L = AT.led()
    sold = {o["posId"] for o in L["orders"] if o.get("side") == "SELL" and o.get("posId") in ids and o.get("sold")}
    miss = sorted(p["code"] for p in tpos if p["id"] not in sold)
    log("매도 기록", len(sold), "· 안 팔림", miss)
    AT.telegram("🧹 <b>미장 정리 매도</b> %d/%d 팔림%s" % (len(sold), len(ids), (" · ⚠ 안 팔림 " + ", ".join(miss) + " — 토스에서 확인") if miss else ""))
except SystemExit:
    raise
except Exception as ex:
    log("실패", repr(ex)[:400]); AT.telegram("⚠ 미장 정리 실패: %s" % str(ex)[:200]); raise
