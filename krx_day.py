# -*- coding: utf-8 -*-
"""네이버 수급이 늦는 날 KRX 자료로 그날 줄 채우기(2026-11-05 사용자 "만들어봐").

2026-11-05: 11-04 장은 열렸는데 네이버 trend(개인·기관·외인)가 다음 날 아침에도 11-03 이 마지막 → 저녁 트리거가 안 쏘고
05:00 보충 수집도 11-03 까지라 표가 묵었다(국장 스윙 매수 건너뜀). 서버에는 KRX 자료가 있다.
  ① publish(서버, 평일 18:40): 그날 KRX 공식 시고저종·거래량 + 종목별 순매수 수량(둘 다 pykrx — 개인 · 기관합계 ·
     외국인+기타외국인 = 네이버 값과 같음, 11-03 삼성전자·SK하이닉스로 맞춤) → Supabase '__krx_day__'(최근 3일)
  ② apply(파이프라인, 표 만들기 전): 네이버가 그날 줄을 안 준 종목만 KRX 값으로 넣는다(INSERT OR IGNORE — 네이버가 나중에 주면
     collect 가 그 값으로 덮는다). 보유 비중(foreign_ratio)은 전날 값.
  트리거(supabase/functions/trigger)는 20:20 넘어도 네이버가 안 오면 '__krx_day__' 가 오늘이면 수집을 쏜다.
    python krx_day.py publish [YYYYMMDD]
"""
import datetime as dt, os, sqlite3, sys, time
from pathlib import Path
import krx_close as KC

BASE = Path(__file__).parent
DATA = BASE / "data"
PIN = "__krx_day__"
if sys.stdout is None or sys.stderr is None:                             # pythonw(예약 작업)는 stdout 이 없다 — print 가 죽는다
    sys.stdout = sys.stderr = open(DATA / "krx_day.log", "a", encoding="utf-8", buffering=1)
    print("──", dt.datetime.now().isoformat(timespec="seconds"), sys.argv[1:])
INV = (("indiv", ("개인",)), ("organ", ("기관합계",)), ("frgn", ("외국인", "기타외국인")))


def collect(day):
    import pandas as pd
    for l in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    from pykrx import stock
    rows = {}
    for mk in ("KOSPI", "KOSDAQ"):
        X = stock.get_market_ohlcv(day, market=mk); time.sleep(2)         # KRX 공식 시고저종·거래량(1분봉 파일은 NXT 가 섞여 11-04 삼성 종가 218,000 vs 공식 221,500)
        px = X.rename(columns={"시가": "o", "고가": "h", "저가": "l", "종가": "c", "거래량": "v"})
        px = px[px.v > 0]
        F = {}
        for col, names in INV:
            s = None
            for nm in names:
                x = stock.get_market_net_purchases_of_equities(day, day, mk, nm)["순매수거래량"]
                s = x if s is None else s.add(x, fill_value=0)
                time.sleep(2)                                            # KRX 는 저속·순차
            F[col] = s
        for t in F["indiv"].index:
            if t not in px.index: continue
            p = px.loc[t]
            rows[t] = ["P" if mk == "KOSPI" else "K", int(p.o), int(p.h), int(p.l), int(p.c), int(p.v)] + [int(F[c].get(t, 0)) for c, _ in INV]
    return rows


def publish(day=None, keep=3):
    day = day or dt.datetime.now().strftime("%Y%m%d")
    rows = collect(day)
    if len(rows) < 1500: raise RuntimeError("KRX 하루 자료가 너무 적다: %d종목" % len(rows))
    cur = KC._rpc("kospi_state_get", {"p_pin": PIN}) or {}
    days = cur.get("days") if isinstance(cur.get("days"), dict) else {}
    days[day] = rows
    days = {d: days[d] for d in sorted(days)[-keep:]}
    KC._rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"days": days, "cols": "mk(P/K),open,high,low,close,volume,indiv,organ,frgn",
                                                         "updated": dt.datetime.now().isoformat(timespec="seconds")}})
    print("KRX 하루 자료 올림", day, len(rows))


def apply(kospi_db, kosdaq_db):
    """네이버가 비운 날·종목만 채운다. 반환 {db: 넣은 줄 수}."""
    try:
        cur = KC._rpc("kospi_state_get", {"p_pin": PIN}) or {}
    except Exception as ex:
        print("⚠ KRX 하루 자료 못 받음:", str(ex)[:120]); return {}
    out = {}
    for db, mk in ((kospi_db, "P"), (kosdaq_db, "K")):
        if not Path(db).exists(): continue
        con = sqlite3.connect(str(db), timeout=300)
        try:
            n = 0
            for day, rows in sorted((cur.get("days") or {}).items()):
                want = {t: r for t, r in rows.items() if r[0] == mk}
                have = {r[0] for r in con.execute("SELECT ticker FROM daily WHERE date=?", (day,))}
                miss = [t for t in want if t not in have]
                if not miss: continue
                ins = []
                for t in miss:
                    p = con.execute("SELECT name, close, foreign_ratio FROM daily WHERE ticker=? AND date<? ORDER BY date DESC LIMIT 1", (t, day)).fetchone()
                    if not p: continue                                   # 처음 보는 종목은 네이버를 기다린다
                    _, o, h, l, c, v, iv, og, fr = want[t]
                    ins.append((day, t, p[0], c, c - (p[1] or c), v, iv, og, fr, p[2], o, h, l))
                cols = "date,ticker,name,close,change,volume,indiv,organ,frgn,foreign_ratio,open,high,low"
                if mk == "K": cols += ",market"; ins = [x + ("KOSDAQ",) for x in ins]
                con.executemany("INSERT OR IGNORE INTO daily (%s) VALUES (%s)" % (cols, ",".join("?" * len(cols.split(",")))), ins)
                con.commit(); n += len(ins)
                print("KRX 하루 자료로 채움 %s %s: %d종목(네이버에 그날 줄 없음)" % (Path(db).name, day, len(ins)))
            out[str(db)] = n
        finally:
            con.close()
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["publish"]: publish(a[1] if len(a) > 1 else None)
    else: print("사용법: python krx_day.py publish [YYYYMMDD]")
