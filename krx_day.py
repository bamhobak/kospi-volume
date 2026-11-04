# -*- coding: utf-8 -*-
"""국장 일별 자료는 KRX 가 기본, 네이버는 예비(2026-11-05 사용자 "만들어봐" → "거래소 자료를 기본값으로 바꿔줘").

2026-11-05: 11-04 장은 열렸는데 네이버 trend(개인·기관·외인)가 다음 날 아침에도 11-03 이 마지막 → 저녁 트리거가 안 쏘고
05:00 보충 수집도 11-03 까지라 표가 묵었다(국장 스윙 매수 건너뜀). 네이버 종가는 09-14 부터 NXT 섞인 통합 종가이기도 하다.
  ① publish(서버, 평일 18:40): 그날 KRX 공식 정규장 시고저종·거래량 + 종목별 순매수 수량 + 외국인 지분율(전부 pykrx —
     개인 · 기관합계 · 외국인+기타외국인 = 네이버 값과 같음, 11-03 삼성전자·SK하이닉스로 맞춤) → Supabase '__krx_day__'(최근 3일)
     refresh(서버, 평일 14:10): '__krx_day__' 의 지난 날들을 다시 받는다 — 저녁 수급은 잠정치, 다음 날이면 확정(14:30 재수집이 씀)
  ② apply(파이프라인, 표 만들기 전, 수집 뒤): '__krx_day__' 에 있는 날은 **KRX 값으로 덮는다**(네이버가 넣은 줄도) · 처음 보는 종목은
     이름이 없어 네이버를 기다린다 · 전일 대비(change)는 다시 계산. 서버 자료가 없는 날(서버 꺼짐·KRX 실패)은 네이버 값 그대로.
  트리거(supabase/functions/trigger)는 '__krx_day__' 에 오늘이 올라오면 네이버를 기다리지 않고 바로 수집을 쏜다(krx_day=true → 대기 없음).
    python krx_day.py publish [YYYYMMDD] | refresh
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
COLS = "mk(P/K),open,high,low,close,volume,indiv,organ,frgn,foreign_ratio"


def collect(day):
    for l in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    from pykrx import stock
    rows = {}
    for mk in ("KOSPI", "KOSDAQ"):
        X = stock.get_market_ohlcv(day, market=mk); time.sleep(2)         # KRX 정규장 공식값(11-04 삼성 종가 218,000 — 네이버·종목별 추이의 221,500 은 NXT 통합)
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
        try:
            fr = stock.get_exhaustion_rates_of_foreign_investment(day, mk)["지분율"]; time.sleep(2)
        except Exception:
            fr = {}
        for t in px.index:
            p = px.loc[t]
            f = fr.get(t) if hasattr(fr, "get") else None
            rows[t] = ["P" if mk == "KOSPI" else "K", int(p.o), int(p.h), int(p.l), int(p.c), int(p.v)] + \
                      [int(F[c].get(t, 0)) for c, _ in INV] + [round(float(f), 2) if f is not None and f == f else None]
    return rows


def publish(day=None, keep=3):
    day = day or dt.datetime.now().strftime("%Y%m%d")
    rows = collect(day)
    if len(rows) < 1500: raise RuntimeError("KRX 하루 자료가 너무 적다: %d종목(휴장?)" % len(rows))
    cur = KC._rpc("kospi_state_get", {"p_pin": PIN}) or {}
    days = cur.get("days") if isinstance(cur.get("days"), dict) else {}
    days[day] = rows
    days = {d: days[d] for d in sorted(days)[-keep:]}
    KC._rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"days": days, "cols": COLS, "updated": dt.datetime.now().isoformat(timespec="seconds")}})
    print("KRX 하루 자료 올림", day, len(rows))


def refresh():
    """지난 날들(오늘 뺀)을 확정치로 다시 — 다음 날 14:10."""
    cur = KC._rpc("kospi_state_get", {"p_pin": PIN}) or {}
    today = dt.datetime.now().strftime("%Y%m%d")
    for d in sorted(cur.get("days") or {}):
        if d < today: publish(d)


def apply(kospi_db, kosdaq_db):
    """'__krx_day__' 에 있는 날은 KRX 값으로 덮는다. 반환 {db: 줄 수}."""
    try:
        cur = KC._rpc("kospi_state_get", {"p_pin": PIN}) or {}
    except Exception as ex:
        print("⚠ KRX 하루 자료 못 받음 — 네이버 값 그대로:", str(ex)[:120]); return {}
    out = {}
    for db, mk in ((kospi_db, "P"), (kosdaq_db, "K")):
        if not Path(db).exists(): continue
        con = sqlite3.connect(str(db), timeout=300)
        try:
            n = 0
            for day, rows in sorted((cur.get("days") or {}).items()):
                want = {t: r for t, r in rows.items() if r[0] == mk}
                if not want: continue
                have = {r[0] for r in con.execute("SELECT ticker FROM daily WHERE date=?", (day,))}
                up, new, ch = [], 0, []
                for t, r in want.items():
                    p = con.execute("SELECT name, close, foreign_ratio FROM daily WHERE ticker=? AND date<? ORDER BY date DESC LIMIT 1", (t, day)).fetchone()
                    if not p and t not in have: continue                 # 처음 보는 종목 — 이름이 없어 네이버를 기다린다
                    _, o, h, l, c, v, iv, og, fr = r[:9]
                    frr = r[9] if len(r) > 9 and r[9] is not None else (p[2] if p else None)
                    name = p[0] if p else None
                    up.append((day, t, name, c, v, iv, og, fr, frr, o, h, l) + (("KOSDAQ",) if mk == "K" else ()))
                    if p and p[1]: ch.append((c - p[1], day, t))
                    new += t not in have
                cols = "date,ticker,name,close,volume,indiv,organ,frgn,foreign_ratio,open,high,low" + (",market" if mk == "K" else "")
                sets = "close=excluded.close, volume=excluded.volume, indiv=excluded.indiv, organ=excluded.organ, frgn=excluded.frgn, " \
                       "foreign_ratio=COALESCE(excluded.foreign_ratio, daily.foreign_ratio), open=excluded.open, high=excluded.high, low=excluded.low, " \
                       "name=COALESCE(daily.name, excluded.name)"
                con.executemany("INSERT INTO daily (%s) VALUES (%s) ON CONFLICT(date, ticker) DO UPDATE SET %s" % (cols, ",".join("?" * len(cols.split(","))), sets), up)
                con.executemany("UPDATE daily SET change=? WHERE date=? AND ticker=?", ch)
                con.commit(); n += len(up)
                print("KRX 하루 자료 적용 %s %s: %d종목(네이버에 없던 것 %d)" % (Path(db).name, day, len(up), new))
            out[str(db)] = n
        finally:
            con.close()
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["publish"]: publish(a[1] if len(a) > 1 else None)
    elif a[:1] == ["refresh"]: refresh()
    else: print("사용법: python krx_day.py publish [YYYYMMDD] | refresh")
