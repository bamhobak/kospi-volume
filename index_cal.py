# -*- coding: utf-8 -*-
"""코스피 지수의 '마지막 거래일' 을 두 경로에서 받아 더 앞선 쪽을 쓴다 (2026-09-21 신설).

왜 필요한가: `check_fresh.py` 와 `is_trading_day.py` 는 지수 달력을 **잣대**로 삼는다.
"우리가 못 받았다" 와 "그날은 장이 없었다" 를 가르려면 우리 수집과 다른 경로가 필요해서다.
그런데 그 잣대가 **한 소스(FinanceDataReader)뿐**이었고, 그 소스가 밀리면
잣대도 같이 뒤로 물러나 **표가 묵어도 통과한다** — 감시가 조용히 느슨해진다.

실제로 2026-09-21 에 FDR 의 KS11 은 09-17 까지만 줬다(09-18 금요일 봉이 없었다).
같은 시각 네이버 `siseJson` 에는 09-18 이 있었다. 그날 표가 09-17 에 멈춰 있었더라도
검사는 통과했을 것이다.

그래서 **둘 중 더 앞선 날짜**를 쓴다. 한 소스가 밀려도 잣대는 안 물러난다.
두 소스 다 장 마감 뒤 몇 시간 늦게 올라오는 성질은 같으므로, "장 마감 전 실행은
지수에도 오늘이 없어 저절로 통과한다" 는 기존 설계는 그대로다.
"""
import sys


def naver_days(back=30):
    """네이버 금융 지수 일별(siseJson)이 주는 **거래일 목록** — 휴장일은 애초에 안 들어 있다.
       우리 종목 수집과 다른 엔드포인트라 잣대로 쓸 수 있다."""
    import re, time, requests
    end = time.strftime("%Y%m%d")
    start = time.strftime("%Y%m%d", time.localtime(time.time() - back * 86400))
    u = ("https://api.finance.naver.com/siseJson.naver?symbol=KOSPI&requestType=1"
         "&startTime=%s&endTime=%s&timeframe=day" % (start, end))
    r = requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0",
                                             "Referer": "https://finance.naver.com/"})
    return sorted(set(re.findall(r'"(\d{8})"', r.text)))


def _naver():
    days = naver_days()
    return days[-1] if days else None


def _fdr():
    import FinanceDataReader as fdr
    ix = fdr.DataReader("KS11", "2026-01-01")
    ix = ix[ix.Close > 0]
    return ix.index[-1].strftime("%Y%m%d") if len(ix) else None


def last_index_day(say=None):
    """두 경로 중 더 앞선 마지막 거래일. 둘 다 실패하면 None."""
    got, errs = [], []
    for name, fn in (("naver", _naver), ("fdr", _fdr)):
        try:
            d = fn()
            if d:
                got.append((name, d))
        except Exception as e:
            errs.append("%s: %s" % (name, str(e)[:60]))
    if not got:
        if say:
            say("  지수를 못 받았다 — %s" % " · ".join(errs))
        return None
    best = max(d for _, d in got)
    if say and len(got) > 1 and len({d for _, d in got}) > 1:
        say("  지수 달력 %s → %s 채택" % (", ".join("%s %s" % g for g in got), best))
    return best


if __name__ == "__main__":
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print(last_index_day(say=print))
