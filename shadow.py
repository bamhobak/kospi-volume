# -*- coding: utf-8 -*-
"""그림자 규칙 기록기 + 보유 경고등 (2026-10-02, 사용자 제안 11·12번).

그림자 규칙 = 아직 판정할 수 없는(표본·기간이 모자란) 후보를 **사지 않고 매일 기록만** 한다. 1년쯤 뒤
research/shadow_eval.py 로 기록된 신호의 실제 성적을 일괄 판정한다. 기록은 data/shadow/log.csv(덧붙이기, 중복 없음).

  S1 자사주 신탁 + 낙폭   자사주취득 신탁계약 체결 공시 & 신호일 20일 등락 ≤ -10%  · 20일 보유 (buyback_size.py)
  S2 행동주의 5% 신규     행동주의·가치 운용사의 그 종목 첫 대량보유 보고 · 120일 보유 (event_lab 8번)
  S3 밸류업 공시          기업가치제고계획 공시 · 60일 보유 (H0245)
재료: data/disc_watch.csv(collect_disc_watch.py) · site/data/table.json(국내 표 — ret20·종가)

보유 경고등 → site/data/warn.json {종목코드: {d, why}} — 화면이 보유 종목 이름 옆에 ⚠ 를 띄운다(판단은 사용자).
  · 경영권 양수도 계약 공시 후 90일 안(실측 60일 중앙 -13.9%·세 구간 모두 크게 음수, H0246)
  · 네이버 검색 관심 쏠림 1.7배↑(naver_watch.py → data/attn_watch.csv · H0248)

    python shadow.py
"""
import csv, json, os, sys, datetime as dt
from pathlib import Path

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

W = BASE / "data" / "disc_watch.csv"
LOG = BASE / "data" / "shadow" / "log.csv"
SEEN = BASE / "data" / "shadow" / "activist_seen.csv"
FIELDS = ["date", "rule", "ticker", "name", "close", "hold", "rcept_no", "note"]
RULES = {"S1": ("자사주 신탁 + 20일 -10%", 20), "S2": ("행동주의 5% 신규", 120), "S3": ("밸류업 공시", 60),
         # 10-25 사용자 "기록해줘" — 등록부에 '그림자'로만 있던 미장 H0258. CI 에서 미장 표가 생긴 뒤 `python shadow.py us` 로 기록
         "S4": ("미장 [저PBR 낙폭] + 고가 낮아지는 음봉 3개 (H0258)", 60), "S4x": ("(대조) 미장 [저PBR 낙폭] 음봉 3개 아님", 60)}
US_RULES = ("S4", "S4x")
USX = BASE / "data" / "shadow" / "us_exit.json"      # 미장 그림자 만기 종가(야후) — 한 번 받으면 다시 안 받는다


def yahoo(sym, rng="1mo"):
    """야후 일봉 [(뉴욕 날짜, 시가, 고가, 종가)] — 브라우저 머리글이 없으면 막힌다"""
    import urllib.request
    u = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d" % (sym.replace(".", "-"), rng)
    j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode())
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]; off = (r.get("meta") or {}).get("gmtoffset", 0)
    out = []
    for ts, o, h, c in zip(r.get("timestamp") or [], q["open"], q["high"], q["close"]):
        if None in (o, h, c): continue
        out.append((dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).strftime("%Y%m%d"), o, h, c))
    return out


def n3(r, gate_dn):
    """사이트 N3 [저PBR 낙폭] 판정과 같은 식(index.html FILTERS N3 fn)"""
    g = lambda k: r.get(k)
    return (gate_dn and not g("pref") and g("pbrd") is not None and 0 < g("pbrd") <= 0.8 and g("ret20") is not None and g("ret20") <= -10
            and g("su1") is not None and g("su1") >= 2 and g("sr60") is not None and g("sr60") <= -10 and (g("amt20") or 0) >= 2 and (g("c") or 0) >= 3)


def us_main():
    """미장 그림자 H0258 기록 — N3 신호 종목 중 직전 3일이 '고가가 낮아지는 음봉 3개'면 S4, 아니면 대조 S4x."""
    p = BASE / "site" / "data" / "table_us.json"
    if not p.exists():
        print("미장 표 없음 — 미장 그림자 건너뜀"); return
    U = json.loads(p.read_text(encoding="utf-8"))
    asof = U.get("asof") or (U.get("dates") or [""])[-1]
    gate_dn = (U.get("us") or {}).get("up60") is False
    sig = [r for r in U.get("rows") or [] if n3(r, gate_dn)]
    log = read(LOG)
    have = {(r["rule"], r["ticker"], r["rcept_no"]) for r in log}
    new = []
    for r in sig:
        key = "N3-" + asof
        if ("S4", r["t"], key) in have or ("S4x", r["t"], key) in have: continue
        try:
            B = [x for x in yahoo(r["t"]) if x[0] <= asof][-3:]
        except Exception as ex:
            print("야후 실패", r["t"], repr(ex)[:80]); continue
        if len(B) < 3: continue
        bear3 = all(c < o for _, o, h, c in B) and B[0][2] > B[1][2] > B[2][2]
        rule = "S4" if bear3 else "S4x"
        new.append(dict(date=asof, rule=rule, ticker=r["t"], name=r.get("n", ""), close=r.get("c"), hold=RULES[rule][1], rcept_no=key,
                        note="음봉3 %s · 고가 %s" % ("O" if bear3 else "X", "→".join("%.2f" % x[2] for x in B))))
    if new:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        exists = LOG.exists()
        with open(LOG, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if not exists: w.writeheader()
            w.writerows(new)
    print("미장 그림자 %s: S&P500 60일선 %s · N3 %d · 새로 S4 %d · S4x %d" % (asof, "아래" if gate_dn else "위(N3 닫힘)", len(sig),
          sum(1 for n in new if n["rule"] == "S4"), sum(1 for n in new if n["rule"] == "S4x")))


def read(p):
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    T = json.loads((BASE / "site" / "data" / "table.json").read_text(encoding="utf-8"))
    dates = T.get("dates") or []
    if not dates:
        print("국내 표 없음 — 건너뜀"); return
    last = dates[-1]
    rows = {r["t"]: r for r in T["rows"]}
    disc = read(W)
    # ── 보유 경고등 ──
    cut = (dt.datetime.strptime(last, "%Y%m%d") - dt.timedelta(days=90)).strftime("%Y%m%d")
    warn = {}
    for x in disc:
        if x["kind"] == "양수도" and x["rcept_dt"] >= cut:
            if x["ticker"] not in warn or warn[x["ticker"]]["d"] < x["rcept_dt"]:
                warn[x["ticker"]] = {"d": x["rcept_dt"], "why": "경영권 양수도 계약 공시(%s) — 실측 60일 중앙 -13.9%%" % x["rcept_dt"]}
    # 네이버 검색 관심 쏠림(naver_watch.py — 보유 국내 종목만, 최근 5일 안에 잰 값)
    for x in read(BASE / "data" / "attn_watch.csv"):
        try:
            att, zf = float(x["att"]), float(x["zfrac"])
        except (TypeError, ValueError):
            continue
        if x["date"] >= dates[max(0, len(dates) - 5)] and att >= 1.7 and zf <= 0.2:
            why = "네이버 검색 관심 쏠림 — 최근 28일이 1년 평균의 %.1f배(%s) · 실측 시장 상위 10%%는 60일 시장 대비 -5%%p" % (att, x["date"])
            if x["ticker"] in warn:
                warn[x["ticker"]]["why"] += " / " + why
            else:
                warn[x["ticker"]] = {"d": x["date"], "why": why}
    (BASE / "site" / "data").mkdir(parents=True, exist_ok=True)
    (BASE / "site" / "data" / "warn.json").write_text(json.dumps({"asof": last, "w": warn}, ensure_ascii=False), encoding="utf-8")
    print("경고등 %d종목 (경영권 양수도 90일 안 · 네이버 관심 쏠림)" % len(warn))
    # ── 그림자 규칙 ──
    log = read(LOG)
    have = {(r["rule"], r["ticker"], r["rcept_no"]) for r in log}
    seen = {(r["flr_nm"], r["ticker"]) for r in read(SEEN)}
    # 표의 거래일 중 공시일 이후 첫날 = 신호일. 표에 아직 그날이 없으면 다음 실행에서 잡는다.
    def sig_day(d):
        for x in dates:
            if x >= d:
                return x
        return None
    new = []
    lookback = dates[-6] if len(dates) >= 6 else dates[0]          # 최근 5거래일 공시만(늦은 수집 흡수)
    for x in disc:
        if x["rcept_dt"] < lookback:
            continue
        sd = sig_day(x["rcept_dt"])
        if sd is None or sd < dates[max(0, len(dates) - 3)]:      # 최근 3거래일 신호까지(실행을 하루 놓쳐도 잡는다)
            continue                                               # ⚠ 늦게 잡으면 종가·20일 등락은 오늘 값(근사) — note 에 적는다
        r = rows.get(x["ticker"])
        if not r:
            continue
        rule = None
        if x["kind"] == "신탁" and r.get("ret20") is not None and r["ret20"] <= -10:
            rule = "S1"
        elif x["kind"] == "대량보유":
            k = (x["flr_nm"], x["ticker"])
            if k not in seen:
                rule = "S2"; seen.add(k)
        elif x["kind"] == "밸류업":
            rule = "S3"
        if not rule or (rule, x["ticker"], x["rcept_no"]) in have:
            continue
        new.append(dict(date=sd, rule=rule, ticker=x["ticker"], name=r.get("n", ""), close=r.get("c"),
                        hold=RULES[rule][1], rcept_no=x["rcept_no"],
                        note=(x["flr_nm"] if rule == "S2" else "") + ("" if sd == last else " · 늦게 기록(%s 값)" % last)))
        have.add((rule, x["ticker"], x["rcept_no"]))
    if new:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        exists = LOG.exists()
        with open(LOG, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if not exists: w.writeheader()
            w.writerows(new)
        with open(SEEN, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh); w.writerow(["flr_nm", "ticker"]); w.writerows(sorted(seen))
    print("그림자 기록 %s: 새 신호 %d건 (%s)" % (last, len(new), ", ".join("%s %s" % (n["rule"], n["name"]) for n in new) or "없음"))
    try:
        page(last, rows)
    except Exception as ex:
        print("그림자 페이지 자료 실패:", repr(ex)[:200])


def page(last, rows):
    """10-25 사용자 "기존 그림자 테스트도 웹페이지(규칙 후보)에서 보이게" → site/data/shadow.json.
    신호마다 산 값 = 신호일 종가 → 보유 만기가 지났으면 만기일 종가, 아니면 오늘 종가 · 비용 0.23 뒤.
    가설 목록 = research/hypotheses.jsonl 중 상태 '그림자'·'후보'."""
    COST = 0.23
    cache = {}

    def series(t):
        if t not in cache:
            try:
                d = json.loads((BASE / "site" / "data" / "stock" / (t + ".json")).read_text(encoding="utf-8"))
                cache[t] = (d["dates"], {d["dates"][x[0]]: x[1] for x in d["rows"] if x[1]})
            except Exception:
                cache[t] = None
        return cache[t]

    # 미장 그림자(S4·S4x) — 미장 표 종가·거래일 달력, 만기 종가는 야후(한 번 받으면 us_exit.json 에 남김)
    U = {}
    try: U = json.loads((BASE / "site" / "data" / "table_us.json").read_text(encoding="utf-8"))
    except Exception: pass
    urows = {x["t"]: x for x in U.get("rows") or []}
    try: ucal = json.loads((BASE / "site" / "data" / "uscal.json").read_text(encoding="utf-8")).get("dates") or []
    except Exception: ucal = []
    ucal = sorted(set(ucal) | set(U.get("usdates") or []))
    try: ux = json.loads(USX.read_text(encoding="utf-8"))
    except Exception: ux = {}
    by = {}
    for r in read(LOG):
        try: entry, hold = float(r["close"]), int(r["hold"])
        except (TypeError, ValueError): continue
        px, held, done, xd = None, None, False, None
        if r["rule"] in US_RULES:
            after = [d for d in ucal if d > r["date"]]
            held = len(after)
            if held >= hold:
                xd = after[hold - 1]; done = True
                k = r["ticker"] + ":" + xd
                if k not in ux:
                    try: ux[k] = next((c for d, o, h, c in yahoo(r["ticker"], "1y") if d == xd), None)
                    except Exception: ux[k] = None
                px = ux.get(k)
            else:
                px = (urows.get(r["ticker"]) or {}).get("c")
            ret = round((px / entry - 1) * 100 - COST, 2) if px and entry else None
            by.setdefault(r["rule"], []).append({"d": r["date"], "t": r["ticker"], "n": r.get("name", ""), "in": entry, "px": px, "ret": ret,
                                                 "held": held, "hold": hold, "done": done, "xd": xd, "note": (r.get("note") or "").strip()})
            continue
        s = series(r["ticker"])
        if s:
            ds, cl = s
            after = [d for d in ds if d > r["date"]]
            held = len(after)
            if held >= hold:
                xd = after[hold - 1]; px = cl.get(xd); done = True
            else:
                px = (rows.get(r["ticker"]) or {}).get("c") or (cl.get(ds[-1]) if ds else None)
        ret = round((px / entry - 1) * 100 - COST, 2) if px and entry else None
        by.setdefault(r["rule"], []).append({"d": r["date"], "t": r["ticker"], "n": r.get("name", ""), "in": entry, "px": px, "ret": ret,
                                             "held": held, "hold": hold, "done": done, "xd": xd, "note": (r.get("note") or "").strip()})
    out = []
    for rid, (nm, hold) in RULES.items():
        L = sorted(by.get(rid, []), key=lambda x: x["d"], reverse=True)
        D = [x["ret"] for x in L if x["done"] and x["ret"] is not None]
        A = [x["ret"] for x in L if x["ret"] is not None]
        out.append({"id": rid, "name": nm, "hold": hold, "n": len(L), "done": len(D), "open": len(L) - len(D),
                    "avg_done": round(sum(D) / len(D), 2) if D else None, "win_done": round(sum(1 for x in D if x > 0) / len(D) * 100) if D else None,
                    "avg_all": round(sum(A) / len(A), 2) if A else None, "items": L[:80]})
    hyps = []
    hp = BASE / "research" / "hypotheses.jsonl"
    if hp.exists():
        for ln in open(hp, encoding="utf-8"):
            try: e = json.loads(ln)
            except ValueError: continue
            if e.get("status") in ("그림자", "후보"):
                hyps.append({"id": e["id"], "st": e["status"], "name": e.get("name", ""), "date": e.get("date", ""), "reason": (e.get("reason") or "")[:160]})
    try: USX.parent.mkdir(parents=True, exist_ok=True); USX.write_text(json.dumps(ux), encoding="utf-8")
    except Exception: pass
    (BASE / "site" / "data" / "shadow.json").write_text(json.dumps({"asof": last, "us_asof": U.get("asof"), "us_gate_dn": (U.get("us") or {}).get("up60") is False,
                                                                    "rules": out, "hyps": hyps}, ensure_ascii=False), encoding="utf-8")
    print("그림자 페이지 자료: " + " · ".join("%s %d건(만기 %d)" % (x["id"], x["n"], x["done"]) for x in out) + " · 가설 %d" % len(hyps))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "us":
        us_main()
        try:
            T = json.loads((BASE / "site" / "data" / "table.json").read_text(encoding="utf-8"))
            page((T.get("dates") or [""])[-1], {r["t"]: r for r in T.get("rows") or []})
        except Exception as ex:
            print("그림자 페이지 자료 실패:", repr(ex)[:200])
    else:
        main()
