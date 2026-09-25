# -*- coding: utf-8 -*-
"""**수집이 실제로 됐는지 확인한다** — 안 됐으면 워크플로를 빨갛게 만든다 (2026-09-18).

왜 필요한가: 지금까지 수집이 빠져도 아무도 몰랐다. 수집 단계는 대부분 `continue-on-error`
라서 실패해도 초록불이고, 표가 하루 묵었는지는 **사람이 화면을 봐야** 알 수 있었다.
실제 사고:
  · 2026-09-11 미장 표가 하루 묵어 [상승장 신고가]가 조용히 0 이 됐다([[us-table-stale]])
  · 2026-09-16 야후가 일봉을 5%만 올린 상태로 수집돼 표가 어제 신호를 보여 줬다
  · 2026-09-17 푸시가 몰려 대기 중이던 수집이 **취소**되고 국내·미장이 하루 통째로 빠졌다
세 번 다 **사용자가 먼저 발견했다**. 그건 감시가 아니다.

여기서는 배포 직전에 두 가지만 본다 — 둘 다 "있어야 할 날짜가 있나" 이다.
  국내  site/data/table.json 의 마지막 거래일 ≥ 코스피 지수의 마지막 거래일
  미장  site/data/table_us.json 의 asof ≥ uscal.json 달력의 마지막 거래일

지수 달력을 잣대로 쓰는 이유: 우리 수집과 **다른 경로**라서 "우리가 못 받았다" 와
"그날은 장이 없었다" 를 가를 수 있다. 우리 파일끼리 견주면 둘 다 틀렸을 때 못 잡는다.

⚠ 장 마감 전에 도는 실행(아침 보충 등)은 오늘치가 없는 게 정상이다. 그때는 지수에도
   오늘이 없으므로 이 검사는 저절로 통과한다 — 시각으로 예외를 두지 않는다.

    python check_fresh.py          # 문제가 있으면 exit 1
    python check_fresh.py --warn   # 알리기만 하고 통과(초기 관찰용)
"""
import json
import sys
from pathlib import Path

# 로컬 콘솔이 cp949 면 ✅·⚠ 를 찍다 UnicodeEncodeError 로 죽는다 —
# 하필 '표가 최신이다' 를 찍는 성공 경로에서 터져 멀쩡한 날에 exit 1 이 났다(2026-09-21 확인).
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = Path(__file__).parent
SITE = BASE / "site" / "data"
WARN_ONLY = "--warn" in sys.argv
BAD = []


def say(m):
    print(m, flush=True)


def load(name):
    p = SITE / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        BAD.append("%s 를 못 읽었다: %r" % (name, e))
        return None


def last_index_day():
    """코스피 지수의 마지막 거래일 — 우리 수집과 다른 경로라 잣대가 된다.

    잣대가 한 소스뿐이면, 그 소스가 밀릴 때 잣대도 같이 물러나 **표가 묵어도 통과한다**.
    2026-09-21 에 FDR 이 09-17 까지만 주는 동안 네이버에는 09-18 이 있었다.
    그래서 index_cal 이 두 경로 중 더 앞선 날짜를 준다.
    """
    try:
        from index_cal import last_index_day as _cal
        return _cal(say=say)
    except Exception as e:
        say("  ⚠ 지수를 못 받아 국내 검사는 건너뛴다: %r" % (e,))
        return None


say("── 수집 확인 ──")

# ── 국내 ──────────────────────────────────────────────────────────────
T = load("table.json")
if T is None:
    BAD.append("table.json 이 없다")
else:
    dates = T.get("dates") or []
    ours = dates[-1] if dates else None
    want = last_index_day()
    say("  국내  표 %s · 지수 %s" % (ours, want))
    if want and ours and ours < want:
        BAD.append("국내 표가 묵었다 — 표 %s 인데 지수는 %s 까지 있다" % (ours, want))
    elif not ours:
        BAD.append("국내 표에 거래일이 없다")

# ── 미장 ──────────────────────────────────────────────────────────────
U = load("table_us.json")
C = load("uscal.json")
if U is None:
    say("  미장  table_us.json 없음 — 이 실행에서 미장을 안 받았으면 정상이다")
else:
    asof = U.get("asof") or ((U.get("dates") or [None])[-1])
    cal = (C or {}).get("dates") or U.get("usdates") or []
    last = cal[-1] if cal else None
    say("  미장  표 %s · 달력 %s" % (asof, last))
    if last and asof and asof < last:
        msg = ("미장 표가 묵었다 — 기준일 %s 인데 달력은 %s 까지 있다"
               " (그날 난 진입 이벤트가 빠져 미장 규칙이 덜 잡힌다)" % (asof, last))
        # 미장 공급처 Stooq 는 전날 장 자료를 **한국 시각 오전 늦게** 올린다 — 2026-09-22 09:19 엔
        # 5,660종목 중 304개(5%)뿐이었고 13:41 엔 다 있었다. 그래서 아침 실행(08:30·09:19)은
        # 평일마다 이 검사에 걸려 빨간불·텔레그램이 났다. 미장 매수는 밤 22:30 장 시작에 하고
        # 20:20 저녁 수집이 그 전에 채우므로 **이른 시각의 미장 묵음은 경고만** 한다.
        # 저녁 실행에서도 묵어 있으면 그건 진짜 사고라 그대로 실패시킨다.
        # 2026-09-25: 아침 수집을 08:30 → 14:30 으로 옮겼다(Massive 가 전날 장을 미 동부 자정 직후 —
        #   한국 13:05(서머타임)·14:05(겨울) — 에 올린다). 그 실행이 끝나는 14:50 무렵까지는 경고로 둔다.
        import datetime as _dt
        kst_hour = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).hour
        if kst_hour < 15:
            say("::warning::%s — 공급처가 아직 안 올렸을 수 있다(14:30·저녁 수집이 채운다)" % msg)
        else:
            BAD.append(msg)
    elif not asof:
        BAD.append("미장 표에 기준일이 없다")

# ── 시장별 최신성 ─────────────────────────────────────────────────────
# ⚠ 표의 **날짜**만 보면 못 잡는 사고가 있다(2026-09-18). 코스닥 DB 는 리포에 없고
#   Actions 캐시에만 사는데, 낡은 로컬 DB 로 표를 다시 만들어 배포하면 날짜는 최신인데
#   **코스닥 값만 열흘 전 것**이 된다. 실제로 종가가 09-07 에 멈춘 채 배포됐고,
#   보유 종목(쎄노텍) 평가손익과 코스닥 규칙 판정이 조용히 틀렸다.
#   그래서 **마지막 날에 값이 들어찼는지를 시장별로** 본다.
if T is not None and (T.get("rows") or []):
    rows = T["rows"]
    L = len(T.get("dates") or [])
    for mk in ("KOSPI", "KOSDAQ"):
        z = [r for r in rows if r.get("mk") == mk]
        if len(z) < 50:
            continue
        got = sum(1 for r in z
                  if (r.get("v") or [None] * L)[-1] is not None) / len(z) * 100
        say("  %-6s %s종목 · 마지막 날 거래량 %.0f%%" % (mk, f"{len(z):,}", got))
        if got < 50:
            BAD.append("%s 의 마지막 날 값이 비었다(거래량 %.0f%%) — 그 시장 규칙이 낡은"
                       " 값으로 판정된다" % (mk, got))

if not BAD:
    say("  ✅ 표가 최신이다")
    sys.exit(0)

for b in BAD:
    say("::warning::%s" % b)
say("")
say("  ❌ " + " / ".join(BAD))
say("  수집 로그를 확인할 것. 되돌리려면: python pipeline.py --no-site  ·  python collect_us_daily.py")
sys.exit(0 if WARN_ONLY else 1)
