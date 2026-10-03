# -*- coding: utf-8 -*-
"""데이 첫 규칙 후보 [갭 하락 조용주] — **알림만**(실제 주문 없음) · 2026-10-03 (research H0285).

규칙(일봉 2005~2026 실측, 비용 0.22% 뒤 하루 평균: 학습 16~22 +0.37% 7/7해 · 검증 23~ +0.39% 4/4해 · 05~15 +0.67% 11/11해):
  유니버스 = 국장 보통주 중 20일 평균 거래대금 상위 40%
  ① 그중 거래대금 아래 2/3(중소형)         — 위 1/3(대형)은 효과 없음
  ② 오늘 갭(시가 ÷ 어제 종가)이 유니버스 하위 10%
  ③ 어제 거래량 ÷ 그 전 20일 평균이 유니버스 하위 30%(조용했던 종목)
  → **시가 단일가에 사서 같은 날 종가 단일가에 판다.** 1분봉으로 보면 09:05 에만 사도 효과가 사라진다 → 장전에 골라야 한다.
⚠ 오늘 시가는 장 전에 모른다. 토스 API 에 '예상 체결가' 칸이 없어 두 가지로 미리 짐작하고, 장 끝나고 실제 시가와 맞춰 어느 쪽이 맞는지 잰다.
   NXT = 넥스트레이드 장전(08:00~08:50) 마지막 체결가 · 호가 = 08:50 이후 장전 단일가 호가 1단계 가운데값

  python day_alert.py morning   08:40 — 전 종목 일봉 25개(약 6분) → 08:52 예상 시가 → 후보 텔레그램 · 사이트(__day__)
  python day_alert.py review    16:25 — 오늘 실제 시가·종가로 후보 성적 + 예상 시가가 맞았는지 → data/day/log.csv · 텔레그램
"""
import csv, datetime as dt, json, math, os, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "day"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
import collect_m1 as M          # 토스 호출(속도 조절·재시도·토큰 공용), 국장 종목 목록
import autotrade as AT          # 주문·체결 확인·장 시각·사이트 상태(같은 토큰을 쓴다)

KST = M.KST
DAY_PER = 500_000                                 # 2026-10-04 사용자: 데이는 건당 50만원으로 실매수 시작(.env DAY_MODE=live)
DAY_MAX = 10                                      # 하루 최대 종목 수(후보 순서 = 시장 대비 더 빠진 순)
COST = 0.23                                     # 토스 실제 왕복: 수수료 0.015×2 + 거래세 0.20 (index.html DEFFEE)
RULE = "갭 하락 조용주"


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def env():
    e = {}
    f = BASE / ".env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); e[k.strip()] = v.strip()
    return e


def telegram(text):
    e = env(); tok, chat = e.get("TELEGRAM_BOT_TOKEN"), e.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        log("텔레그램 미설정:", text.replace("\n", " | ")); return
    try:
        body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body,
                                                      headers={"Content-Type": "application/json"}), timeout=30).read()
    except Exception as ex:
        log("텔레그램 실패:", repr(ex)[:200])


def supa_set(pin, data):
    import requests
    js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    H = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    requests.post(f"{url}/rest/v1/rpc/kospi_state_set", headers=H, json={"p_pin": pin, "p_data": data}, timeout=30).raise_for_status()


def today_session():
    cal = M.get("/api/v1/market-calendar/KR")
    it = (cal.get("today") or {}).get("integrated")
    return (cal["today"]["date"].replace("-", ""), it, cal["previousBusinessDay"]["date"].replace("-", "")) if it else (None, None, None)


def pct_rank(vals):
    """{키: 값} → {키: 0~1 백분위}(작을수록 0)."""
    ks = sorted(vals, key=lambda k: vals[k]); n = len(ks)
    return {k: (i + 1) / n for i, k in enumerate(ks)}


def prep(today):
    """전 종목 일봉 25개 → 어제 종가·20일 평균 거래대금·어제 거래량 배수."""
    U = M.universe("KR"); R = {}; t0 = time.time()
    for s in U:
        c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=25) or {}).get("candles") or []
        c = sorted([x for x in c if x["timestamp"][:10].replace("-", "") < today], key=lambda x: x["timestamp"])
        if len(c) < 22: continue
        v = [float(x["volume"]) for x in c]; cl = [float(x["closePrice"]) for x in c]
        amt20 = sum(a * b for a, b in zip(cl[-20:], v[-20:])) / 20
        base = sum(v[-21:-1]) / 20
        if base <= 0 or cl[-1] <= 0: continue
        R[s] = dict(pc=cl[-1], amt20=amt20, vm=v[-1] / base, pdate=c[-1]["timestamp"][:10].replace("-", ""),
                    d5=(cl[-1] / (sum(cl[-5:]) / 5) - 1) * 100)          # 어제 종가의 5일선 대비 — 낮을수록 기대 큼(day2.py)
    log("준비: %d종목 · %.1f분" % (len(R), (time.time() - t0) / 60))
    return R


def morning():
    today, it, prev = today_session()
    if not today:
        log("국장 휴장 — 건너뜀"); return
    R = prep(today)
    names = {}
    # 유니버스: 20일 평균 거래대금 상위 40% (1,000원 미만 제외 — 연구와 같게)
    R = {k: v for k, v in R.items() if v["pc"] >= 1000 and v["pdate"] == prev}
    liq = pct_rank({k: v["amt20"] for k, v in R.items()})
    uni = [k for k in R if liq[k] >= 0.60]
    uliq = pct_rank({k: R[k]["amt20"] for k in uni})
    small = [k for k in uni if uliq[k] <= 2 / 3]
    vmq = pct_rank({k: R[k]["vm"] for k in uni})
    pre = [k for k in small if vmq[k] <= 0.30]                 # ①③ 은 장 전에 확정 — 갭만 남는다
    # 2026-10-04 좁힘(사용자 '2번' · research H0291): 중소형 중 **더 작은 쪽(유니버스 거래대금 아래 1/3)** + 시장보다 2%p 이상 더 빠짐
    #   승률 55% → 학습 63.5% · 검증 63.9% · 건당 +1.19/+1.41% · 하루 1.4~1.8종목(신호 없는 날 약 40%)
    tiny = {k for k in uni if uliq[k] <= 1 / 3}
    log("유니버스 %d · 중소형 %d · 조용(거래량 하위30%%) %d" % (len(uni), len(small), len(pre)))
    # 08:52 까지 기다렸다 예상 시가 — NXT 장전 체결가(08:50 마감) + 장전 단일가 호가
    at = dt.datetime.now(KST).replace(hour=8, minute=52, second=0, microsecond=0)
    w = (at - dt.datetime.now(KST)).total_seconds()
    if w > 0:
        log("08:52 까지 기다림 %.0f초" % w); time.sleep(w)
    nxt = {}
    for i in range(0, len(uni), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(uni[i:i + 200])) or []:
            ts = x.get("timestamp") or ""
            if ts[:10].replace("-", "") == today:
                nxt[x["symbol"]] = float(x["lastPrice"])
    ob = {}
    for s in uni:                                              # 갭 순위는 유니버스 전체에서 매긴다 → 전부 본다
        r = M.get("/api/v1/orderbook", symbol=s) or {}
        a = (r.get("asks") or [{}])[0].get("price"); b = (r.get("bids") or [{}])[0].get("price")
        if a and b: ob[s] = (float(a) + float(b)) / 2
        elif a or b: ob[s] = float(a or b)
    exp = {s: nxt.get(s, ob.get(s)) for s in uni}
    src = {s: ("NXT" if s in nxt else ("호가" if s in ob else None)) for s in uni}
    gap = {s: (exp[s] / R[s]["pc"] - 1) * 100 for s in uni if exp[s]}
    gq = pct_rank(gap)
    # 순서(2026-10-03 day2.py): 시장보다 더 빠진 순 — 시장 대비 -3%p 이상이면 하루 +0.9~1.0%(학습·검증), 그 안은 +0.3%
    mg = sorted(gap.values())[len(gap) // 2] if gap else 0.0           # 오늘 유니버스 갭 중앙 = 시장 갭
    d5q = pct_rank({k: R[k]["d5"] for k in uni})
    base_c = [s for s in pre if s in gq and gq[s] <= 0.10]                       # 예전 T1(넓은 조건) — 결과 비교용으로 남긴다
    cand = sorted([s for s in base_c if s in tiny and gap[s] - mg <= -2], key=lambda s: gap[s] - mg)
    nm = {}
    for i in range(0, len(cand), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(cand[i:i + 100])) or []:
            nm[x["symbol"]] = x.get("name") or x["symbol"]
    L = [dict(t=s, name=nm.get(s, s), gap=round(gap[s], 2), rel=round(gap[s] - mg, 2), vm=round(R[s]["vm"], 2), d5=round(R[s]["d5"], 2),
              d5low=d5q[s] <= 0.30, exp=exp[s], pc=R[s]["pc"], src=src[s]) for s in cand]
    snap = dict(date=today, prev=prev, made=dt.datetime.now(KST).strftime("%H:%M"), rule=RULE, n_uni=len(uni), n_gap=len(gap), mgap=round(mg, 2),
                cut=round(sorted(gap.values())[max(int(len(gap) * 0.10) - 1, 0)], 2) if gap else None,
                src_n={"NXT": sum(1 for s in src.values() if s == "NXT"), "호가": sum(1 for s in src.values() if s == "호가")}, cand=L,
                n_base=len(base_c), all={s: dict(gap=round(gap[s], 3), src=src[s], pre=s in pre, tiny=s in tiny) for s in gap})
    (OUT / ("snap_%s.json" % today)).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    try:
        supa_set("__day__", {k: v for k, v in snap.items() if k != "all"})
    except Exception as ex:
        log("사이트 기록 실패:", ex)
    log("후보 %d · 예상가 NXT %d · 호가 %d · 갭 10%% 선 %s%%" % (len(L), snap["src_n"]["NXT"], snap["src_n"]["호가"], snap["cut"]))
    live = env().get("DAY_MODE", "notify") == "live"
    head = "🌅 <b>데이 [%s] %s</b> %s/%s 08:52" % (RULE, "실매수" if live else "알림만", today[4:6], today[6:])
    body = [("후보 %d종목 — 위에서 %d종목 %s원씩 시가 단일가 매수 → 오늘 종가 매도" % (len(L), min(len(L), DAY_MAX), f"{DAY_PER:,}")) if live
            else ("후보 %d종목 — 시가 단일가 매수 → 종가 매도 (실제 주문 없음 · 검증 중)" % len(L)),
            "오늘 시장 갭 %+.1f%%%s" % (mg, " — 다 같이 빠진 날(과거 기대 큼)" if mg <= -1 else "")]
    for x in L[:15]:
        body.append("· %s(%s) 예상 갭 %+.1f%%(시장 대비 %+.1f) · 거래량 %.1f배%s [%s]" % (
            x["name"], x["t"], x["gap"], x["rel"], x["vm"], " · 5일선 아래" if x["d5low"] else "", x["src"]))
    if len(L) > 15: body.append("… 외 %d" % (len(L) - 15))
    body.append("넓은 조건(예전 T1) %d개 중 좁힘(더 작은 종목 · 시장보다 2%%p↑ 더 빠짐) 통과 %d%s" % (len(base_c), len(L), " — 오늘은 안 산다" if not L else ""))
    body.append("갭 하위 10%% 선 %s%% · 예상가 NXT %d·호가 %d / 유니버스 %d" % (snap["cut"], snap["src_n"]["NXT"], snap["src_n"]["호가"], len(uni)))
    telegram("\n".join([head] + body))
    try: M.BUSY.unlink()                                       # 고르는 건 끝났다 — 1분봉 과거 채우기를 다시 돌게 둔다
    except Exception: pass
    if live and L:
        trade(L[:DAY_MAX], today)


# ── 실매수(2026-10-04) — 시가 단일가(OPG) 매수 → 같은 날 종가 단일가 매도 · 사이트 데이 보유(positions_scalp)에 기록 ──
LEDGER = OUT / "ledger.json"


def _led():
    try: return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception: return {"orders": []}


def _led_save(L):
    if AT.DRY: return
    tmp = LEDGER.with_suffix(".tmp"); tmp.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(LEDGER)


def scalp_update(mutate, why):
    """사이트 데이 보유 목록(positions_scalp)을 읽고 고쳐 쓴다 — 스윙 목록(positions)은 건드리지 않는다."""
    for att in range(3):
        d = AT.site_state()
        pos = d.get("positions_scalp") if isinstance(d.get("positions_scalp"), list) else []
        if not mutate(pos): return
        d["positions_scalp"] = pos; d["updated"] = int(time.time() * 1000)
        if AT.DRY:
            log("사이트 쓰기(보내지 않음):", why); return
        AT.rpc("kospi_state_set", {"p_pin": AT._sb["pin"], "p_data": d})
        if AT.site_state().get("updated") == d["updated"]:
            log("사이트 기록:", why); return
        time.sleep(1)
    log("⚠ 사이트 기록 실패:", why)


def trade(L, today):
    if (AT.OUT / "STOP").exists():
        telegram("⛔ 데이 실매수 멈춤(data/autotrade/STOP)"); return
    S = AT.session("KR")
    if not S or S["date"] != today or AT.now() >= S["start"]:
        log("데이 매수 시각 지남 — 건너뜀"); return
    Lg = _led(); done = {o["t"] for o in Lg["orders"] if o.get("date") == today and o.get("side") == "BUY"}
    placed, skip = [], []
    for x in L:
        if x["t"] in done: continue
        px = float(x["exp"] or x["pc"])
        q = math.floor(DAY_PER / px)
        if q < 1 and px <= DAY_PER * 2: q = 1
        if q < 1:
            skip.append((x["name"], "1주가 너무 비쌈")); continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", f"db{today}{x['t']}")[:36]
        o = dict(side="BUY", date=today, t=x["t"], name=x["name"], qty=q, cid=cid, rid="T1", at=AT.now().isoformat())
        try:
            o["oid"] = AT.place({"clientOrderId": cid, "symbol": x["t"], "side": "BUY", "orderType": "MARKET", "timeInForce": "OPG", "quantity": str(q)})
        except AT.TossErr as ex:
            o["oid"] = None; o["err"] = ex.code or str(ex)[:100]
            skip.append((x["name"], "주문 거부 " + str(o["err"])))
            Lg["orders"].append(o); _led_save(Lg)
            if ex.code == "insufficient-buying-power": break
            continue                                          # 시가 단일가를 놓치면 사지 않는다(09:05 만 늦어도 효과가 사라진다)
        Lg["orders"].append(o); _led_save(Lg); placed.append(o)
        time.sleep(0.3)
    if not placed:
        if skip: telegram("⚠ 데이 매수 0건 — " + " · ".join("%s(%s)" % s_ for s_ in skip[:6]))
        return
    AT.sleep_until(S["start"] + dt.timedelta(seconds=90), "데이 시가 체결 확인")
    AT.wait_fills(placed)
    got = [o for o in placed if o["fq"] > 0 and o["ap"] > 0]
    for i, o in enumerate(got):
        o["pos"] = {"id": int(time.time() * 1000) + i, "code": o["t"], "name": o["name"], "date": today, "price": o["ap"],
                    "qty": int(o["fq"]), "filters": ["T1"], "auto": True, "day": True, "oid": o["oid"]}
    _led_save(Lg)
    if got:
        scalp_update(lambda P: (P.extend(dict(o["pos"]) for o in got) or True), "데이 매수 %d건" % len(got))
    lines = ["🌅 <b>데이 매수</b> %s/%s 시가" % (today[4:6], today[6:])]
    lines += ["✅ %s %d주 @ %s원 = %s원" % (o["name"], int(o["fq"]), f"{o['ap']:,.0f}", f"{o['fq'] * o['ap']:,.0f}") for o in got]
    lines += ["❌ %s 미체결(%s)" % (o["name"], o.get("status")) for o in placed if o not in got]
    if skip: lines.append("못 산 것: " + " · ".join("%s(%s)" % s_ for s_ in skip[:6]))
    telegram("\n".join(lines))
    if not got: return
    # 같은 날 종가 단일가(15:20~15:30)에 판다
    AT.sleep_until(S["close_auction"] + dt.timedelta(seconds=60), "데이 종가 매도")
    sold = []
    for o in got:
        try:
            have = AT.sellable(o["t"]) if not AT.DRY else o["fq"]
        except AT.TossErr:
            have = None
        q = int(o["fq"]) if have is None else int(min(o["fq"], have))
        if q < 1: continue
        so = dict(side="SELL", date=today, t=o["t"], name=o["name"], qty=q, posId=o["pos"]["id"], cid=("ds" + o["cid"][2:])[:36])
        try:
            so["oid"] = AT.place({"clientOrderId": so["cid"], "symbol": o["t"], "side": "SELL", "orderType": "MARKET", "quantity": str(q)})
            sold.append((so, o))
        except AT.TossErr as ex:
            so["err"] = ex.code or str(ex)[:100]
        Lg["orders"].append(so); _led_save(Lg)
        time.sleep(0.3)
    AT.sleep_until(S["end"] + dt.timedelta(seconds=90), "데이 종가 체결 확인")
    AT.wait_fills([so for so, _ in sold])
    fin = [(so, o) for so, o in sold if so["fq"] > 0 and so["ap"] > 0]
    _led_save(Lg)
    if fin:
        ids = {o["pos"]["id"]: so["ap"] for so, o in fin}

        def mark(P):
            ch = False
            for p_ in P:
                if p_.get("id") in ids and not p_.get("sell"):
                    p_["sell"] = ids[p_["id"]]; p_["sellDate"] = today; ch = True
            return ch
        scalp_update(mark, "데이 매도 %d건" % len(fin))
    lines = ["🌇 <b>데이 매도</b> %s/%s 종가" % (today[4:6], today[6:])]
    tot, rs = 0.0, []
    for so, o in fin:
        r = (so["ap"] / o["ap"] - 1) * 100 - COST
        won_ = so["fq"] * (so["ap"] - o["ap"]) - so["fq"] * (so["ap"] * 0.00215 + o["ap"] * 0.00015)
        tot += won_; rs.append(r)
        lines.append("%s %s %+.2f%% (%s원)" % ("🔺" if r > 0 else "🔻", o["name"], r, f"{won_:+,.0f}"))
    if rs:
        lines.append("합계 %s원 · 평균 %+.2f%% · 오른 종목 %d/%d (수수료·세금 뒤)" % (f"{tot:+,.0f}", sum(rs) / len(rs), sum(r > 0 for r in rs), len(rs)))
    fin_ids = {o["pos"]["id"] for _, o in fin}
    left = [o["name"] for o in got if o["pos"]["id"] not in fin_ids]
    if left: lines.append("⚠ 못 판 것: " + ", ".join(left) + " — 직접 확인")
    telegram("\n".join(lines))


def review():
    today, it, prev = today_session()
    if not today:
        log("국장 휴장 — 건너뜀"); return
    f = OUT / ("snap_%s.json" % today)
    if not f.exists():
        log("오늘 아침 기록 없음 — 건너뜀"); return
    snap = json.loads(f.read_text(encoding="utf-8"))
    syms = list(snap["all"].keys())
    act, prevc = {}, {}                                    # 오늘 (시가, 종가) · 어제 종가
    for s in syms:
        c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=3) or {}).get("candles") or []
        c = sorted(c, key=lambda x: x["timestamp"])
        t = [x for x in c if x["timestamp"][:10].replace("-", "") == today]
        b = [x for x in c if x["timestamp"][:10].replace("-", "") < today]
        if t: act[s] = (float(t[0]["openPrice"]), float(t[0]["closePrice"]))
        if b: prevc[s] = float(b[-1]["closePrice"])
    # 예상 시가가 맞았나 — 예상 갭 vs 실제 갭(같은 어제 종가 기준) · 실제 갭으로 다시 고르면 후보가 얼마나 겹치나
    real_gap = {s: (act[s][0] / prevc[s] - 1) * 100 for s in syms if s in act and s in prevc}
    errs = {"NXT": [], "호가": []}
    for s, g in real_gap.items():
        a = snap["all"].get(s)
        if a and a.get("src") in errs: errs[a["src"]].append(a["gap"] - g)
    rq = pct_rank(real_gap)
    rmg = sorted(real_gap.values())[len(real_gap) // 2] if real_gap else 0.0
    real_cand = {s for s in real_gap if rq[s] <= 0.10 and snap["all"].get(s, {}).get("pre") and snap["all"].get(s, {}).get("tiny")
                 and real_gap[s] - rmg <= -2}
    mine = {x["t"] for x in snap["cand"]}
    rets = []
    for x in snap["cand"]:
        if x["t"] in act:
            o, c = act[x["t"]]; r = (c / o - 1) * 100 - COST; rets.append(r)
            x["open"], x["close"], x["ret"] = o, c, round(r, 3)
    real_rets = [(act[s][1] / act[s][0] - 1) * 100 - COST for s in real_cand if s in act]
    avg = lambda L: sum(L) / len(L) if L else float("nan")
    mae = lambda L: sum(abs(v) for v in L) / len(L) if L else float("nan")
    lf = OUT / "log.csv"; new = not lf.exists()
    with open(lf, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new: w.writerow(["날짜", "후보수", "후보 평균(비용 뒤)", "실제 갭 기준 후보수", "그 평균", "겹친 수", "NXT 갭 오차(평균 절대 %p)", "호가 갭 오차", "NXT 수", "호가 수"])
        w.writerow([today, len(rets), round(avg(rets), 3), len(real_rets), round(avg(real_rets), 3), len(mine & real_cand),
                    round(mae(errs["NXT"]), 3), round(mae(errs["호가"]), 3), len(errs["NXT"]), len(errs["호가"])])
    snap["review"] = dict(rets=rets, real_n=len(real_cand), overlap=len(mine & real_cand))
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    try:
        supa_set("__day__", {k: v for k, v in snap.items() if k != "all"})
    except Exception as ex:
        log("사이트 기록 실패:", ex)
    L = ["📊 <b>데이 [%s] 오늘 결과</b> %s/%s (후보 전체 기준 · 예상 시가 점검)" % (RULE, today[4:6], today[6:]),
         "아침 후보 %d종목 시가→종가 평균 <b>%+.2f%%</b>(비용 뒤) · 오른 종목 %d/%d" % (len(rets), avg(rets), sum(r > 0 for r in rets), len(rets)),
         "실제 시가로 골랐다면 %d종목 평균 %+.2f%% · 아침 후보와 겹침 %d" % (len(real_rets), avg(real_rets), len(mine & real_cand)),
         "예상 시가 오차(갭 %%p): NXT %.2f(%d종목) · 호가 %.2f(%d종목)" % (mae(errs["NXT"]), len(errs["NXT"]), mae(errs["호가"]), len(errs["호가"]))]
    telegram("\n".join(L))
    log("리뷰:", L[1], "|", L[2], "|", L[3])


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] in (["morning"], ["review"]):
            # 도는 동안 1분봉 과거 채우기를 쉬게 한다 — 토스 시세 호출은 초당 10회를 같이 쓴다(아침은 08:56 전에 끝나야 한다)
            M.BUSY.write_text("day")
            try:
                morning() if a[0] == "morning" else review()
            finally:
                try: M.BUSY.unlink()
                except Exception: pass
        else: log("사용법: python day_alert.py morning | review")
    except Exception as ex:
        log("실패:", repr(ex)[:500])
        telegram("⚠ 데이 알림 실패: %s" % str(ex)[:300]); raise
