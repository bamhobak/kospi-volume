# -*- coding: utf-8 -*-
"""덧 수집 (2026-11-23 사용자 "1 2 3 8 10 하자" — 데이 규칙 테스트용 자료 넓히기). 전부 읽기만 하는 수집이고 매매와 무관하다.
계기: 11-22 실측 — [갭하락] 날 성적은 그날 지수 장중과 상관 +0.70, [장후 낙폭] 은 그날 밤 나스닥과 +0.33 인데 '살 때 아는 시장 방향' 자료가 없었다.

  fut    코스피200·코스닥150 선물 1분봉 — 주간(08:45~15:45, 늦은 개장 날은 그날 시간대로)·야간(18:00~다음 날 06:00).
         KIS FHKIF03020200(한 번에 102봉, 시각을 뒤로 넘기며 받음 · 주간 시장 구분 F · 야간 CM). 근월물만
         (만기 = 3·6·9·12월 둘째 목요일, 만기 날 낮까지 그 월물 · 만기 날 밤부터 다음 월물).
         과거는 KIS 에 2026-03 월물부터 남아 있음(2025-12 월물은 0행) → backfill 은 그 월물이 근월물이 된 2025-12-12~.
         야간 봉 시각은 KIS 그대로 24시 넘김 표기(2809 = 다음 날 04:09), 날짜 d 는 야간장이 시작한 날.
         → data/factory/fut/KR_YYYYMMDD.parquet (sym K200·KQ150 · code · sess D·N · d · hm · o·h·l·c·v)
  flow   종목별 외국인·기관 장중 추정 순매수(KIS HHPTJ04160200) — 장 끝난 뒤 한 번 부르면 그날 5개 시각이 다 나온다
         (gb 1~5 = KIS 문서 기준 09:30·10:00·11:20·13:20·14:30 · 수량은 주, 천 주 단위로 떨어지는 추정값). 과거는 안 준다 → 매일 쌓기.
         응답에 날짜가 없다 — 그래서 '오늘이 거래일이고 15:35 지난 뒤 같은 날'에만 받는다.
         → data/factory/flowest/KR_YYYYMMDD.parquet (ticker · gb · frgn · orgn · tot)
  theme  네이버 테마 명단 그날 스냅샷(m.stock.naver.com/api/stocks/theme) — 과거 명단이 없어 '오늘 명단을 과거에 씌우는' 편향
         (research/theme_gap_1116.py)을 없애려고 매일 한 장. → data/factory/theme/YYYYMMDD.parquet (no · theme · ticker · name)
  cal    개장·휴장 달력 — KIS 국내휴장일조회(CTCA0903R)로 앞으로 약 400일 + 늦은 개장 날
         (새해 첫 거래일 10:00~15:30 · 수능일 10:00~16:30 은 '11월 셋째 목요일' 추정 — 공지 확인 필요).
         → data/factory/calendar/kr_cal.json (7일에 한 번 새로). 미리 보는 참고용일 뿐 — 실제 매매·수집은 그날 토스 달력의 개장·마감 시각을 직접 따른다
         (collect_m1.note_today · autotrade.session). 2026-11-23 사용자 "알림 필요 없지 않아? 알아서 맞게" → 텔레그램 알림 없앰.
  daily  = 위 넷을 차례로(예약 \\BamhobakFactory\\Extra 16:50). 하나가 실패해도 나머지는 계속, 실패한 것만 텔레그램 한 줄.
  미장 지수 ETF(QQQ·SPY·SOXX) 한국 시각 05:41~09:00·16:41~20:00 1분봉은 밤 과거 받기(research/backfill/night_fill.py us_idx)가 받는다
  → research/cache/bf_us_idx/ ([장후 낙폭] 19:50 · [갭하락] 08:50 에 아는 미장 방향).

    python research/factory/extra.py daily
    python research/factory/extra.py fut backfill [시작 YYYYMMDD]
    python research/factory/extra.py fut|flow|theme|cal [YYYYMMDD]
"""
import sys, re, time, glob, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

FUTD = C.DATA / "fut"; FLOWD = C.DATA / "flowest"; THD = C.DATA / "theme"; CALD = C.DATA / "calendar"
for _d in (FUTD, FLOWD, THD, CALD): _d.mkdir(parents=True, exist_ok=True)
FUT_FIRST = "20251212"                       # KIS 에 남아 있는 가장 오래된 근월물(2026-03 월물)이 근월물이 된 날
PROD = {"K200": "A01", "KQ150": "A06"}
FP = "/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice"
_last = [0.0]


def kcall(path, tr, params, gap=0.25):
    """KIS 조회 한 번 — 초당 1/gap 번 넘지 않게, 한도 초과·오류는 3번까지 다시. 실패면 None."""
    import kis
    for k in range(3):
        w = gap - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            st, js, _ = kis.call(path, tr, params)
            if st == 200 and str(js.get("rt_cd")) == "0": return js
            if k == 2: C.log("KIS 실패 %s http %s %s" % (tr, st, str(js.get("msg1") or js.get("raw") or "")[:80]))
        except Exception as ex:
            if k == 2: C.log("KIS 오류 %s %s" % (tr, repr(ex)[:120]))
        time.sleep(1.0 + k)
    return None


def _save(path, rows, cols, keys):
    if not rows: return 0
    import pandas as pd
    D = pd.DataFrame(rows, columns=cols)
    if path.exists(): D = pd.concat([pd.read_parquet(path), D], ignore_index=True)
    D = D.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
    tmp = path.with_suffix(".tmp"); D.to_parquet(tmp, index=False); tmp.replace(path)
    return len(D)


# ── ① 지수 선물 1분봉 ────────────────────────────────────────────────
def expiry(y, m):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(3 - d.weekday()) % 7 + 7)          # 둘째 목요일


def front(prod, day, night=False):
    """그 날 근월물 단축코드(A01 + 연도 끝자리 + 월 두 자리). 만기 날 밤(야간장)부터는 다음 월물."""
    d = dt.date(int(day[:4]), int(day[4:6]), int(day[6:]))
    if night: d += dt.timedelta(days=1)
    for yy, mm in ((d.year, 3), (d.year, 6), (d.year, 9), (d.year, 12), (d.year + 1, 3)):
        if d <= expiry(yy, mm): return "%s%d%02d" % (PROD[prod], yy % 10, mm)


def fut_sess(code, day, sess):
    """한 월물·한 날·한 장(D 주간 · N 야간) 1분봉 전부 — [(hm, o, h, l, c, v)]"""
    div, hour, lo = ("F", "170000", 8 * 60) if sess == "D" else ("CM", "300000", 17 * 60 + 30)
    rows, seen = [], set()
    for _ in range(14):
        js = kcall(FP, "FHKIF03020200", {"FID_COND_MRKT_DIV_CODE": div, "FID_INPUT_ISCD": code, "FID_HOUR_CLS_CODE": "60", "FID_PW_DATA_INCU_YN": "Y",
                                         "FID_FAKE_TICK_INCU_YN": "N", "FID_INPUT_DATE_1": day, "FID_INPUT_HOUR_1": hour})
        o = [x for x in ((js or {}).get("output2") or []) if x.get("stck_bsop_date") and x.get("stck_cntg_hour")]
        if not o: break
        new = 0
        for x in o:
            if x["stck_bsop_date"] != day: continue
            hm = int(x["stck_cntg_hour"][:4])
            if hm in seen: continue
            try: rows.append((hm, float(x["futs_oprc"]), float(x["futs_hgpr"]), float(x["futs_lwpr"]), float(x["futs_prpr"]), float(x["cntg_vol"] or 0)))
            except Exception: continue
            seen.add(hm); new += 1
        e = o[-1]                                                     # 가장 이른 봉
        if e["stck_bsop_date"] != day or len(o) < 100 or not new: break
        t = int(e["stck_cntg_hour"][:2]) * 60 + int(e["stck_cntg_hour"][2:4]) - 1
        if t < lo: break
        hour = "%02d%02d00" % (t // 60, t % 60)
    return rows


def fut_day(day, sessions=("D", "N")):
    """그 날 파일에 없는 (상품, 장)만 받아 넣는다. 돌려주는 값 = 새로 받은 봉 수."""
    import pandas as pd
    f = FUTD / ("KR_%s.parquet" % day)
    have = set()
    if f.exists():                                                     # 끝까지 받은 장만 '있음' — 장중·야간장 도중에 받은 반쪽은 다음에 다시 받는다
        z = pd.read_parquet(f, columns=["sym", "sess", "hm"]).groupby(["sym", "sess"]).hm.max()
        have = {k for k, m in z.items() if m >= (1520 if k[1] == "D" else 2950)}
    rows = []
    for prod in PROD:
        for s in sessions:
            if (prod, s) in have: continue
            code = front(prod, day, night=(s == "N"))
            rows += [(prod, code, s, day) + r for r in fut_sess(code, day, s)]
    _save(f, rows, ["sym", "code", "sess", "d", "hm", "o", "h", "l", "c", "v"], ["sym", "sess", "hm"])
    return len(rows)


def kr_days(first):
    ds = {Path(p).stem for p in glob.glob(str(C.BASE / "data" / "m1" / "KR" / "day" / "*.parquet"))}
    try:
        import pandas as pd
        ds |= set(pd.read_parquet(C.CACHE / "m1_daysum.parquet", columns=["d"]).d.astype(str).unique())
    except Exception: pass
    return sorted(d for d in ds if re.fullmatch(r"\d{8}", d) and d >= first)


def fut(day, prev=None):
    """매일: 오늘 주간 + 지난 5거래일 중 빠진 장(야간장은 다음 날 06:00 에 끝나므로 어제 것까지)."""
    n = fut_day(day, ("D",))
    back = [d for d in kr_days(FUT_FIRST) if d < day][-5:]
    if prev and prev not in back: back.append(prev)
    for d in back: n += fut_day(d)
    C.log("선물 1분봉 %s — 새 봉 %d (지난 날 %d일 확인)" % (day, n, len(back)))


def fut_backfill(first=FUT_FIRST):
    today = C.now().strftime("%Y%m%d")
    days = [d for d in kr_days(first) if d < today]
    t0, n = time.time(), 0
    for i, d in enumerate(days):
        n += fut_day(d)
        if i % 20 == 0: C.log("선물 과거 받기 %d/%d %s · 봉 %d · %.0f분" % (i + 1, len(days), d, n, (time.time() - t0) / 60))
    C.log("선물 과거 받기 끝 — %d일 · 봉 %d · %.0f분" % (len(days), n, (time.time() - t0) / 60))


# ── ③ 종목별 외국인·기관 장중 추정 ───────────────────────────────────
def universe():
    try:
        J = C.jload(C.CACHE / "toss_nxt_kr.json", {}) or {}
        U = sorted(k for k in J if re.fullmatch(r"[0-9A-Z]{6}", k))
        if len(U) >= 1000: return U
    except Exception: pass
    import auction
    return auction.uni_today()[0]


def flow(day, limit=None):
    now = C.now()
    if now.strftime("%Y%m%d") != day or now.hour * 100 + now.minute < 1535:
        C.log("장중 추정 수급 — 오늘 %s 15:35 뒤가 아니라 안 받음(응답에 날짜가 없어 다른 날 값이 섞일 수 있음)" % day); return
    U = universe()[: limit or None]
    rows, bad, t0 = [], 0, time.time()
    for s in U:
        js = kcall("/uapi/domestic-stock/v1/quotations/investor-trend-estimate", "HHPTJ04160200", {"MKSC_SHRN_ISCD": s}, gap=0.125)
        if js is None: bad += 1; continue
        for x in js.get("output2") or []:
            try: rows.append((s, int(x["bsop_hour_gb"]), int(x["frgn_fake_ntby_qty"]), int(x["orgn_fake_ntby_qty"]), int(x["sum_fake_ntby_qty"])))
            except Exception: pass
    n = _save(FLOWD / ("KR_%s.parquet" % day), rows, ["ticker", "gb", "frgn", "orgn", "tot"], ["ticker", "gb"])
    C.log("장중 추정 수급 %s — %d종목 중 실패 %d · 줄 %d · %.0f초" % (day, len(U), bad, n, time.time() - t0))
    if len(U) and bad > len(U) * 0.2: raise RuntimeError("장중 추정 수급 실패 %d/%d" % (bad, len(U)))


# ── ⑧ 테마 명단 스냅샷 ───────────────────────────────────────────────
def theme(day):
    import requests
    S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"})
    API = "https://m.stock.naver.com/api/stocks/theme"

    def get(u):
        for k in range(3):
            try:
                r = S.get(u, timeout=20)
                if r.status_code == 200: return r.json()
            except Exception: pass
            time.sleep(1 + 2 * k)
        return {}
    groups, p = [], 1
    while p <= 20:
        g = get("%s?page=%d&pageSize=100" % (API, p)).get("groups") or []
        groups += g
        if len(g) < 100: break
        p += 1; time.sleep(0.3)
    rows, empty = [], 0
    for g in groups:
        p, got = 1, 0
        while p <= 10:
            st = get("%s/%s?page=%d&pageSize=100" % (API, g["no"], p)).get("stocks") or []
            for x in st:
                code = x.get("itemCode") or x.get("itemcode") or x.get("reutersCode") or ""
                if code: rows.append((int(g["no"]), str(g.get("name") or ""), str(code)[:6], str(x.get("stockName") or ""))); got += 1
            if len(st) < 100: break
            p += 1
        empty += (got == 0); time.sleep(0.3)
    n = _save(THD / ("%s.parquet" % day), rows, ["no", "theme", "ticker", "name"], ["no", "ticker"])
    C.log("테마 명단 %s — 테마 %d(빈 것 %d) · 줄 %d" % (day, len(groups), empty, n))
    if len(groups) < 50 or n < 1000: raise RuntimeError("테마 명단이 너무 적음(테마 %d · 줄 %d)" % (len(groups), n))


# ── ⑩ 개장·휴장 달력 ────────────────────────────────────────────────
def late_known():
    """지금까지 실제로 늦게 열린 날(collect_m1.late_hours — 알려진 날 + 그날 달력에서 적힌 날)."""
    try:
        import collect_m1 as M
        return {d: list(v) for d, v in sorted(M.late_hours().items())}
    except Exception: return {}


def cal(force=False):
    f = CALD / "kr_cal.json"
    J = C.jload(f, {}) or {}
    today = C.now().strftime("%Y%m%d")
    age = 99
    try: age = (C.now().date() - dt.date.fromisoformat(J["asof"][:10])).days
    except Exception: pass
    if force or age >= 7 or not J.get("open"):
        days, base = {}, today
        limit = (C.now().date() + dt.timedelta(days=400)).strftime("%Y%m%d")
        for _ in range(30):
            js = kcall("/uapi/domestic-stock/v1/quotations/chk-holiday", "CTCA0903R", {"BASS_DT": base, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}, gap=1.0)
            o = (js or {}).get("output") or []
            if isinstance(o, dict): o = [o]
            before = len(days)
            for x in o:
                if x.get("bass_dt"): days[x["bass_dt"]] = (x.get("opnd_yn") == "Y")
            if len(days) == before or max(days) >= limit: break
            base = (dt.datetime.strptime(max(days), "%Y%m%d") + dt.timedelta(days=1)).strftime("%Y%m%d")
        if len(days) < 30: raise RuntimeError("휴장일 조회가 %d일뿐" % len(days))
        op = sorted(d for d, v in days.items() if v)
        closed = sorted(d for d, v in days.items() if not v and dt.datetime.strptime(d, "%Y%m%d").weekday() < 5)
        late = {}
        for y in sorted({d[:4] for d in days}):
            jan = [d for d in op if d[:4] == y]
            if jan and min(days) <= y + "0101" and jan[0][4:6] == "01":
                late[jan[0]] = {"open": "1000", "close": "1530", "why": "새해 첫 거래일"}
            n1 = dt.date(int(y), 11, 1); su = (n1 + dt.timedelta(days=(3 - n1.weekday()) % 7 + 14)).strftime("%Y%m%d")
            if su in days and days[su]:
                late[su] = {"open": "1000", "close": "1630", "why": "수능일(11월 셋째 목요일 추정 — 공지 확인)"}
        J = {"asof": C.now().isoformat(timespec="seconds"), "from": min(days), "to": max(days), "open": op, "closed_weekday": closed,
             "late": late}
        C.log("개장 달력 %s~%s — 개장 %d일 · 평일 휴장 %d일 · 늦은 개장 %s" % (J["from"], J["to"], len(op), len(closed), sorted(late)))
    J.pop("warned", None); J.pop("late_in_code", None)
    J["late_known"] = late_known()
    C.jsave(f, J)
    return J


def daily():
    day, prev = C.kr_session()
    if not day:
        C.log("국장 휴장 — 덧 수집 쉼"); return
    fails = []
    for name, fn in (("선물 1분봉", lambda: fut(day, prev)), ("장중 추정 수급", lambda: flow(day)), ("개장 달력", cal), ("테마 명단", lambda: theme(day))):
        try: fn()
        except Exception as ex:
            C.log("덧 수집 %s 실패:" % name, repr(ex)[:300]); fails.append(name)
    if fails: C.tg("⚠ 덧 수집 실패: " + ", ".join(fails))
    C.log("덧 수집 끝 %s%s" % (day, " (실패: %s)" % ", ".join(fails) if fails else ""))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        today = C.now().strftime("%Y%m%d")
        if a[:1] == ["daily"]: daily()
        elif a[:2] == ["fut", "backfill"]: fut_backfill(a[2] if len(a) > 2 else FUT_FIRST)
        elif a[:1] == ["fut"]: fut(a[1] if len(a) > 1 else today)
        elif a[:1] == ["flow"]: flow(a[1] if len(a) > 1 else today, int(a[2]) if len(a) > 2 else None)
        elif a[:1] == ["theme"]: theme(a[1] if len(a) > 1 else today)
        elif a[:1] == ["cal"]: cal(force=True)
        else: print(__doc__)
    except Exception as ex:
        import traceback
        C.log("덧 수집 오류:", repr(ex)[:300]); C.log(traceback.format_exc()[-600:])
        C.tg("⚠ 덧 수집 오류: %s" % str(ex)[:200])
