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
RULES = {"S1": ("자사주 신탁 + 20일 -10%", 20), "S2": ("행동주의 5% 신규", 120), "S3": ("밸류업 공시", 60)}


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


if __name__ == "__main__":
    main()
