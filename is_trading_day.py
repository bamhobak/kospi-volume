# -*- coding: utf-8 -*-
"""수집할 새 거래일이 있는지 판정 → stdout 에 true/false

옛 판정은 "코스피 지수에 **오늘** 봉이 있는가" 였다. 이 방식은 GitHub Actions 의
예약 실행이 지연돼 자정을 넘겨 도착하면(실측: 최대 7시간 41분 지연) '오늘'이 다음날로
바뀌어 버려서, 정작 받아야 할 전날 데이터를 "휴장일" 로 오판하고 건너뛰었다.
(2026-08-31 월요일치가 이 때문에 통째로 유실됨)

새 판정: **코스피 지수의 최신 거래일 > 우리가 이미 가진 최신 거래일** 이면 수집한다.
 - 언제 실행되든(정시·지연·새벽) 못 받은 날이 있으면 받는다.
 - 주말·공휴일에 돌아도 새 봉이 없으면 false 라 헛돌지 않는다.
 - 이미 오늘치를 받았으면 false → 하루 여러 번 걸어둬도 중복 수집하지 않는다.
보유분은 리포지토리에 커밋되는 월별 CSV(data/YYYY-MM.csv)로 판단한다(러너에 DB 가 없으므로).
조회 자체가 실패하면 true 로 답한다(하루를 통째로 잃는 것보다 한 번 더 도는 편이 낫다).
"""
import csv, sys, datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data"

def have_latest():
    """커밋된 월별 CSV 중 가장 최신 거래일 (없으면 None)"""
    files = sorted(DATA.glob("20??-??.csv"))
    for f in reversed(files[-3:]):          # 최근 3개 파일이면 충분
        try:
            best = ""
            with open(f, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    d = r.get("date") or ""
                    if d > best: best = d
            if best: return best
        except Exception:
            continue
    return None

def main():
    now = dt.datetime.now()
    try:
        import FinanceDataReader as fdr
        k = fdr.DataReader("KS11", (now - dt.timedelta(days=20)).strftime("%Y-%m-%d"))
        k = k[k["Close"] > 0]
        latest = k.index[-1].strftime("%Y%m%d")
    except Exception as e:
        print("true", end="")
        print(f"지수 조회 실패({str(e)[:60]}) → 수집 진행", file=sys.stderr)
        return

    have = have_latest()
    if have is None:
        print("true", end="")
        print(f"보유 CSV 없음 → 전체 수집 (지수 최신 {latest})", file=sys.stderr)
        return

    ok = latest > have
    print("true" if ok else "false", end="")
    print(f"{'수집 필요' if ok else '이미 최신'} — 지수 최신 {latest} / 보유 최신 {have} "
          f"(실행 {now:%Y-%m-%d %H:%M})", file=sys.stderr)

main()
