# -*- coding: utf-8 -*-
"""스윙 규칙 P10 [단기과열 단일가] — 2026-11-17 사용자 "규칙 하나만 더 찾아줄 수 없어?" → "응 해줘"(1주 시험) · research H0425 heat_1117~heat7.

규칙: 어제 저녁 KIND 에 '단기과열종목(3거래일 단일가매매) 지정' 이 뜬 보통주는 오늘부터 3거래일 동안 30분 단일가로만 거래된다(하루 14번).
      **단일가 첫날(오늘) 종가 단일가에 사서 → 셋째 날 종가에 판다**(매도는 자동매매 sell — 사이트 스윙 보유 · 원장 rid P10 · index.html P10 hold 3).
      조건: 어제 종가 1,000원↑ · 지정 전 5거래일 +15%↑(종목 맞춤 확인 겸) · **오늘 거래대금 50억↑**(15:18 까지 쌓인 것 45억↑ — 종가 단일가 몫이 아직 빠져 있어서)
            · 15:18 현재가가 상한가면 안 삼(종가에 못 삼).
근거(비용 뒤): 50억↑ 학습 2016~22 317건 +4.31%(승 66%) · 검증 2023~ 260건 +3.13%(승 67%) · 11개 해 전부 플러스 · 연 약 50건.
       건당 아래 5% -10% · 최악 -35% — 급등주라 건당 흔들림이 크다. 금액은 1주 시험(사전 등록 P10T — 산 건 30건 뒤 판정).
  python day_heat.py buy     15:05 — 후보(어제 지정) → 15:18 거래대금 확인 → 15:21 1주 시장가(종가 단일가) → 15:31 체결 확인 → 스윙 보유에 기록
  python day_heat.py close   16:25 — 후보 전부(조건 밖 포함)를 data/day/heat_hits.csv 에 적고, 이틀 전 후보의 셋째 날 종가를 채움(채점용 · 돈과 무관)
  python day_heat.py pick [YYYYMMDD]   후보만 보여 줌(주문 없음)
"""
import csv, datetime as dt, json, sqlite3, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "day"
LOG = OUT / "heat.log"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

RID, RNAME = "P10", "단기과열 단일가"
TITLE = "단기과열종목(3거래일 단일가매매) 지정"
MIN_PX, MIN_R5 = 1000, 15.0
AMT_FULL, AMT_1518 = 50e8, 45e8        # 연구 문턱 = 하루 50억 · 15:18 엔 마지막 단일가(하루의 약 10%)가 빠져 있어 45억
MAXN = 15                              # 하루 최대(거래대금 큰 순) — 과거 하루 최대 11건
QTY = 1                                # 1주 시험
HITS = OUT / "heat_hits.csv"
COLS = ["date", "t", "name", "c0", "r5", "amt1518", "px1518", "ok", "why", "real", "ap", "c1", "amt1", "c3", "r"]


def log(*a):
    print("%s %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), " ".join(str(x) for x in a)), flush=True)


def designated(prev, today):
    """전 거래일(과 그 뒤 휴일) 저녁에 지정 공시가 뜬 보통주 [(티커, 공시 시각)] — 자료가 없으면 KIND 에서 받아 온다."""
    import day_alert as D
    db = BASE / "data" / "dart" / "kind_time.db"

    def read():
        c = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)
        rows = c.execute("SELECT kcode, dt FROM kind WHERE title = ? AND day >= ? AND day < ? AND market IN ('유가증권','코스닥') ORDER BY dt", (TITLE, prev, today)).fetchall()
        got = c.execute("SELECT at FROM done_day WHERE day = ?", (prev,)).fetchone()
        c.close(); return rows, got
    rows, got = read()
    fresh = bool(got) and str(got[0])[:10].replace("-", "") > prev          # 전 거래일 치를 그 다음 날 뒤에 받았으면 저녁 공시까지 들어 있다
    if not fresh:
        ok = D.kind_prefetch(prev, today)
        if not ok: raise RuntimeError("KIND 공시 못 받음 — 어제 지정 종목을 모름")
        rows, _ = read()
    return [(k + "0", t) for k, t in rows]


def measure(t, today, prev):
    """토스 일봉으로 어제 종가·5일 등락·오늘 쌓인 거래대금(근사: 거래량 × (고+저+현재가)/3)."""
    import autotrade as AT
    L = (AT.tget("/api/v1/candles", symbol=t, interval="1d", count=10) or {}).get("candles") or []
    by = {x["timestamp"][:10].replace("-", ""): x for x in L}
    ds = sorted(d for d in by if d <= prev)
    if prev not in by or len(ds) < 6: return None
    c0 = float(by[prev]["closePrice"]); c5 = float(by[ds[-6]]["closePrice"])
    r = dict(c0=c0, r5=round((c0 / c5 - 1) * 100, 1) if c5 > 0 else None, amt=0.0, px=None)
    x = by.get(today)
    if x:
        px = float(x["closePrice"]); v = float(x.get("volume") or 0)
        r.update(px=px, amt=v * (float(x["highPrice"]) + float(x["lowPrice"]) + px) / 3)
    return r


def judge_row(z):
    if z.get("c0") is None: return "일봉 없음"
    if z["c0"] < MIN_PX: return "1,000원 아래"
    if z.get("r5") is None or z["r5"] < MIN_R5: return "5일 +15% 안 됨"
    if not z.get("px"): return "오늘 거래 없음"
    if z["amt"] < AMT_1518: return "거래대금 %.0f억(45억 아래)" % (z["amt"] / 1e8)
    if z["px"] >= z["c0"] * 1.295: return "상한가"
    return ""


def pick(today, prev):
    import autotrade as AT
    ev = designated(prev, today)
    tks = sorted({t for t, _ in ev})
    nm = AT.names(tks) if tks else {}
    rows = []
    for t in tks:
        n = nm.get(t)
        z = dict(t=t, name=n[0] if n else t)
        if not n: z.update(c0=None, why="토스에 없는 종목"); rows.append(z); continue
        m = None
        try: m = measure(t, today, prev)
        except Exception as ex: log("시세 실패", t, repr(ex)[:120])
        z.update(m or dict(c0=None, r5=None, amt=0.0, px=None))
        z["why"] = "거래정지" if n[2] else judge_row(z)
        rows.append(z)
        time.sleep(0.15)
    rows.sort(key=lambda z: -(z.get("amt") or 0))
    return rows


def buy():
    import autotrade as AT
    import day_alert as D
    S = AT.session("KR")
    today = AT.now().strftime("%Y%m%d")
    if not S or S["date"] != today:
        log("국장 휴장 — 건너뜀"); return
    if AT.now() < S["close_auction"] - dt.timedelta(minutes=40):         # 수능일처럼 장이 늦게 끝나는 날 — 그 시각까지 기다림
        AT.sleep_until(S["close_auction"] - dt.timedelta(minutes=15), "늦게 끝나는 날 — 종가 단일가 15분 전까지 대기")
    if AT.now() >= S["end"] - dt.timedelta(minutes=3):
        log("종가 단일가 지남 — 건너뜀"); return
    ev = designated(S["prev"], today)
    f = OUT / ("heat_%s.json" % today)
    if not ev:
        log("어제 지정 종목 없음"); f.write_text(json.dumps(dict(date=today, cand=[], real=[]), ensure_ascii=False), encoding="utf-8"); return
    log("어제 지정", len(ev), [t for t, _ in ev])
    AT.sleep_until(S["close_auction"] - dt.timedelta(minutes=2), "15:18 거래대금 확인")
    rows = pick(today, S["prev"])
    good = [z for z in rows if not z["why"]][:MAXN]
    J = dict(date=today, prev=S["prev"], cand=rows, real=[], skip=[])
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    log("후보 %d · 조건 통과 %d" % (len(rows), len(good)), [(z["t"], z["why"]) for z in rows if z["why"]])
    if not good: return
    live = D.env().get("DAY_MODE", "notify") == "live" and not (AT.OUT / "STOP").exists()
    if not live:
        log("실매수 꺼짐(DAY_MODE·STOP) — 후보만 기록"); return
    try: held = {p.get("code") for p in (AT.site_state().get("positions") or []) if not p.get("sell") and RID in (p.get("filters") or [])}
    except Exception: held = set()
    AT.sleep_until(S["close_auction"] + dt.timedelta(seconds=60), "종가 단일가(15:21)")
    try: bp = AT.buying_power("KRW")
    except AT.TossErr: bp = None
    Lg = AT.led(); placed = []
    for z in good:
        if z["t"] in held:
            J["skip"].append(dict(t=z["t"], why="이미 보유")); continue
        if bp is not None and bp < z["px"] * QTY * 1.3:                   # 시장가는 상한가까지 돈을 잡는다
            J["skip"].append(dict(t=z["t"], why="돈 모자람")); continue
        cid = "sp10%s%s" % (today, z["t"])
        o = dict(side="BUY", date=today, t=z["t"], name=z["name"], qty=QTY, cid=cid, rid=RID, mk="KR", pc=z["c0"], ref=z["px"], amt=z["amt"], at=AT.now().isoformat())
        body = {"clientOrderId": cid, "symbol": z["t"], "side": "BUY", "orderType": "MARKET", "quantity": str(QTY)}
        try:
            ok = AT.submit(Lg, o, body)
        except AT.TossErr as ex:
            J["skip"].append(dict(t=z["t"], why=ex.code or str(ex)[:60])); log("주문 거부", z["t"], ex.code, str(ex)[:120]); continue
        if not ok:
            log("주문 결과 모름", z["t"]); continue
        placed.append(o)
        if bp is not None: bp -= z["px"] * QTY
        time.sleep(0.4)
    AT.led_save(Lg)
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    log("주문 %d · 못 낸 것 %d" % (len(placed), len(J["skip"])))
    if not placed:
        if J["skip"]: AT.telegram("🌡 [%s] 주문 못 냄 %d건(%s)" % (RNAME, len(J["skip"]), J["skip"][0]["why"]))
        return
    AT.sleep_until(S["end"] + dt.timedelta(seconds=90), "종가 체결 확인")
    AT.wait_fills(placed)
    for o in placed:                                                     # 종가에 안 맺어진 몫은 취소(시간외로 넘어가 기록과 어긋나지 않게)
        if o.get("status") and o["status"] not in AT.FINAL:
            try:
                AT.call("POST", "/api/v1/orders/%s/cancel" % o["oid"], acct=True, body={}); o["canceled"] = True
                AT.apply_detail(o, AT.detail(o["oid"], o["t"], o["qty"]))
            except AT.TossErr as ex:
                log("남은 몫 취소 실패(%s):" % ex.code, o["t"])
    got = []
    for o in placed:
        if (o.get("fq") or 0) > 0 and (o.get("ap") or 0) > 0:
            o["pos"] = {"id": AT.new_id(), "code": o["t"], "name": o["name"], "date": today, "price": o["ap"],
                        "qty": int(o["fq"]) if o["fq"] == int(o["fq"]) else o["fq"], "filters": [RID], "fx": None, "auto": True, "oid": o["oid"]}
            o["pf"] = o["fq"]; got.append(o)
    AT.led_save(Lg)
    if got: AT.site_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "[%s] 매수 %d건" % (RNAME, len(got)))
    J["real"] = [dict(t=o["t"], name=o["name"], fq=o.get("fq"), ap=o.get("ap")) for o in got]
    f.write_text(json.dumps(J, ensure_ascii=False), encoding="utf-8")
    AT.telegram("🌡 [%s] 종가 매수 %d/%d · 모레 종가 매도\n%s" % (RNAME, len(got), len(placed), "\n".join("✅ %s %d주 @ %s원" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}") for o in got)))


def _day_candle(t, day):
    import autotrade as AT
    for x in (AT.tget("/api/v1/candles", symbol=t, interval="1d", count=10) or {}).get("candles") or []:
        if x["timestamp"][:10].replace("-", "") == day: return x
    return None


def close():
    """채점용 기록 — 오늘 후보 전부(조건 밖 포함) 적고, 이틀 전(거래일) 후보의 오늘 종가(c3)·수익(r, 비용 0.23 뒤)을 채운다."""
    import autotrade as AT
    today = dt.datetime.now().strftime("%Y%m%d")
    rows = list(csv.DictReader(open(HITS, encoding="utf-8-sig"))) if HITS.exists() else []
    f = OUT / ("heat_%s.json" % today)
    if f.exists():
        J = json.loads(f.read_text(encoding="utf-8")); real = {z["t"]: z for z in J.get("real") or []}
        have = {(r["date"], r["t"]) for r in rows}
        for z in J.get("cand") or []:
            if (today, z["t"]) in have or z.get("c0") is None: continue
            c1 = amt1 = ""
            try:
                x = _day_candle(z["t"], today)
                if x: c1 = float(x["closePrice"]); amt1 = round(float(x.get("volume") or 0) * (float(x["highPrice"]) + float(x["lowPrice"]) + c1) / 3)
            except Exception as ex: log("종가 실패", z["t"], repr(ex)[:100])
            rows.append(dict(date=today, t=z["t"], name=z.get("name", z["t"]), c0=z["c0"], r5=z.get("r5"), amt1518=round(z.get("amt") or 0), px1518=z.get("px") or "",
                             ok=int(not z["why"]), why=z["why"], real=int(z["t"] in real), ap=(real.get(z["t"]) or {}).get("ap") or "", c1=c1, amt1=amt1, c3="", r=""))
            time.sleep(0.15)
    days = sorted({r["date"] for r in rows}); n = 0
    for r in rows:                                                       # 산 날을 1일째로 세어 3일째 = 오늘인 줄
        if r["c3"] or not r["c1"] or r["date"] >= today: continue
        try:
            L = (AT.tget("/api/v1/candles", symbol=r["t"], interval="1d", count=10) or {}).get("candles") or []
            ds = sorted(x["timestamp"][:10].replace("-", "") for x in L if x["timestamp"][:10].replace("-", "") >= r["date"])
            if len(ds) < 3: continue
            x = [y for y in L if y["timestamp"][:10].replace("-", "") == ds[2]][0]
            r["c3"] = float(x["closePrice"]); r["r"] = round((r["c3"] / float(r["c1"]) - 1) * 100 - 0.23, 2); n += 1
        except Exception as ex: log("셋째 날 종가 실패", r["t"], repr(ex)[:100])
        time.sleep(0.15)
    with open(HITS, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in COLS})
    log("기록 %d줄 · 오늘 채운 셋째 날 종가 %d" % (len(rows), n))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["buy"]: buy()
        elif a[:1] == ["close"]: close()
        elif a[:1] == ["pick"]:
            import autotrade as AT
            S = AT.session("KR")
            d = a[1] if len(a) > 1 else AT.now().strftime("%Y%m%d")
            c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
            prev = c.execute("SELECT max(day) FROM done_day WHERE day < ? AND n > 300", (d,)).fetchone()[0] if len(a) > 1 else S["prev"]
            c.close()
            rows = pick(d, prev); print("오늘", d, "전 거래일", prev)
            for z in rows: print(z)
        else: print("사용법: python day_heat.py buy | close | pick [YYYYMMDD]")
    except Exception as ex:
        log("실패:", repr(ex)[:400])
        try:
            import autotrade as AT; AT.telegram("⚠ [%s] 오류: %s" % (RNAME, str(ex)[:200]))
        except Exception: pass
        raise
