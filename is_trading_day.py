# -*- coding: utf-8 -*-
"""오늘이 증시 영업일인지 판정 → stdout 에 true/false
   주말·공휴일(설날·추석·광복절 등)에는 수집을 돌리지 않기 위한 게이트.
   판정 근거: 코스피 지수(KS11)에 '오늘' 봉이 있는가 — 휴장일엔 생기지 않는다.
   조회 자체가 실패하면 true 로 답한다(수집을 건너뛰어 하루를 통째로 잃는 것보다,
   불필요하게 한 번 더 도는 편이 낫다).
"""
import sys, datetime as dt

def main():
    today = dt.datetime.now().strftime("%Y%m%d")
    if dt.datetime.now().weekday() >= 5:            # 토·일
        print("false", end=""); print(f"주말 ({today})", file=sys.stderr); return
    try:
        import FinanceDataReader as fdr
        k = fdr.DataReader("KS11", (dt.datetime.now() - dt.timedelta(days=12)).strftime("%Y-%m-%d"))
        k = k[k["Close"] > 0]
        last = k.index[-1].strftime("%Y%m%d")
        ok = last == today
        print("true" if ok else "false", end="")
        print(f"{'영업일' if ok else '휴장일'} — 코스피 최신 봉 {last}, 오늘 {today}", file=sys.stderr)
    except Exception as e:
        print("true", end="")
        print(f"판정 실패({str(e)[:60]}) → 영업일로 간주하고 진행", file=sys.stderr)

main()
