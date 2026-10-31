# -*- coding: utf-8 -*-
"""KRX 종가 맞추기(2026-11-01 사용자 '추천대로').

2026-09-14 부터 네이버 종가(closePrice)가 KRX 종가가 아니다 — 종목 80%가 시간외·NXT 값이 섞여 평균 0.7% 다르다(거래량은 그대로).
KIS 일봉도 **그날 값은 같은 숫자**이고 다음 거래일이 되어야 KRX 종가로 돌아간다. 연구는 KRX 종가로 쟀으므로 규칙 입력을 되돌린다.

  ① 당일: 서버 1분봉 파일의 마지막 체결 봉(토스, KRX 정규장) — collect_m1 이 16:1x 에 Supabase '__krx_close__' 로 올린다(publish)
  ② 확정: KIS 공매도 일별 응답의 종가(맨 위 줄=그날은 뺀다) — collect_daily_extra 가 data/krx_close.csv 에 쌓는다
  pipeline.py 가 표를 만들기 전에 apply() 로 kospi.db·kosdaq.db 종가를 덮는다.
네이버 수집이 최근 며칠 종가를 매일 다시 쓰기 때문에 **매 실행** 덮어야 한다. 차이가 GUARD % 넘는 값은 분할·병합일 수 있어 건드리지 않는다.
"""
import csv, datetime as dt, re, sqlite3
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
CSV = DATA / "krx_close.csv"
PIN = "__krx_close__"
KEEP_DAYS = 130                     # data/krx_close.csv 보관(달력 일) — 네이버가 다시 쓰는 창(코스닥 60거래일)보다 길게
GUARD = 12.0                        # 네이버 값과 이만큼(%) 넘게 다르면 분할·병합으로 보고 안 덮는다(시간외 상한 ±10%)


def _sb():
    js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _rpc(fn, b):
    import requests
    url, H = _sb()
    r = requests.post(f"{url}/rest/v1/rpc/{fn}", headers=H, json=b, timeout=30); r.raise_for_status()
    return r.json() if r.text else None


def from_m1(day):
    """1분봉 파일 → {종목: KRX 종가}(거래량 있는 마지막 봉)."""
    import pandas as pd
    f = DATA / "m1" / "KR" / "day" / ("%s.parquet" % day)
    D = pd.read_parquet(f, columns=["t", "ts", "c", "v"])
    D = D[D.v > 0].sort_values(["t", "ts"])
    return {t: float(c) for t, c in D.groupby("t").c.last().items()}


def publish(day, keep=4):
    """서버 — 그날 KRX 종가를 Supabase 에 올린다(최근 keep 일만)."""
    cur = _rpc("kospi_state_get", {"p_pin": PIN}) or {}
    days = cur.get("days") if isinstance(cur.get("days"), dict) else {}
    days[day] = {t: int(c) for t, c in from_m1(day).items()}
    days = {d: days[d] for d in sorted(days)[-keep:]}
    _rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"days": days, "updated": dt.datetime.now().isoformat(timespec="seconds")}})
    print("KRX 종가 올림", day, len(days[day]))


def load_csv():
    out = {}
    if CSV.exists():
        with open(CSV, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try: out[(r["date"], r["ticker"])] = int(float(r["close"]))
                except (KeyError, TypeError, ValueError): pass
    return out


def save_csv(M):
    lo = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    tmp = CSV.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator=chr(10)); w.writerow(["date", "ticker", "close"])
        w.writerows(sorted((d, t, c) for (d, t), c in M.items() if d >= lo))
    tmp.replace(CSV)


def merge_kis(rows):
    """collect_daily_extra — [(날짜, 종목, 종가)] 를 파일에 합친다. 확정값이라 덮어쓴다."""
    M = load_csv()
    n = 0
    for d, t, c in rows:
        try: c = int(float(c))
        except (TypeError, ValueError): continue
        if c > 0:
            M[(d, t)] = c; n += 1
    save_csv(M)
    print("KRX 종가 파일: %d줄 합침 · 전체 %d줄" % (n, len(M)))


def closes():
    """쓸 값 — 확정(파일)이 우선, 없으면 당일 값(Supabase)."""
    M = load_csv(); kis = len(M)
    try:
        cur = _rpc("kospi_state_get", {"p_pin": PIN}) or {}
        for d, m in (cur.get("days") or {}).items():
            for t, c in m.items(): M.setdefault((d, t), int(c))
    except Exception as ex:
        print("⚠ 당일 KRX 종가 못 받음:", str(ex)[:120])
    print("KRX 종가 재료: 확정 %d · 당일 %d" % (kis, len(M) - kis))
    return M


def apply(dbs, M=None):
    """DB 의 종가를 KRX 값으로 덮고 그 뒤 전일 대비(change)도 다시 계산한다. dbs = 경로 목록(없는 파일은 건너뜀)."""
    M = closes() if M is None else M
    if not M: return
    days = sorted({d for d, _ in M})
    for db in dbs:
        if not Path(db).exists(): continue
        con = sqlite3.connect(str(db), timeout=300)
        cur = con.execute("SELECT date,ticker,close FROM daily WHERE date>=? AND close>0", (days[0],)).fetchall()
        up, skip, tick = [], 0, set()
        for d, t, c in cur:
            k = M.get((d, t))
            if k is None or k == c: continue
            if abs(k / c - 1) * 100 > GUARD:
                skip += 1; continue
            up.append((k, d, t)); tick.add(t)
        con.executemany("UPDATE daily SET close=? WHERE date=? AND ticker=?", up)
        ch = []
        for t in tick:
            rows = con.execute("SELECT date,close FROM daily WHERE ticker=? AND date>=(SELECT COALESCE(MAX(date),'') FROM daily WHERE ticker=? AND date<?) ORDER BY date", (t, t, days[0])).fetchall()
            ch += [(rows[i][1] - rows[i - 1][1], rows[i][0], t) for i in range(1, len(rows))]
        con.executemany("UPDATE daily SET change=? WHERE date=? AND ticker=?", ch)
        con.commit(); con.close()
        print("KRX 종가 적용 %s: %d줄 바꿈(%d종목) · 차이 %.0f%% 넘어 건너뜀 %d줄 · 대상 %d줄" % (Path(db).name, len(up), len(tick), GUARD, skip, len(cur)))
