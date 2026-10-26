# -*- coding: utf-8 -*-
"""토스에서 살 수 있는 미장 종목 목록 → data/us/toss_us.csv (저장소에 커밋 — CI 의 미장 표가 이걸로 거른다).

왜(2026-10-26 사용자 "큰일날 뻔했는데"): 미장 표(collect_us_daily.py, CI)는 나스닥 목록을 통째로 받아서
**토스에 없는 종목 541개**(SPAC 유닛·Tangible Equity Units·우선주·예탁증서 등)가 섞여 있었다.
그중 VSECU(VSE Tangible Equity Units)가 [N4] 매수 대기에 떴고 토스는 "지원하지 않거나 상장 폐지된 주식".
CI 러너는 토스 API 를 못 쓴다(허용 IP 가 서버뿐) → 서버가 목록을 받아 커밋하고, 표 만들 때 이걸로 거른다.

    python toss_us_list.py                       # 목록 새로(그냥 저장)
    python toss_us_list.py --push --max-age 6    # 6일 넘었을 때만 새로 받아 이 파일만 커밋·푸시(run_daily_research 10단계)
"""
import csv, datetime as dt, io, os, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):                      # pythonw(예약 작업)에서는 None
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "us" / "toss_us.csv"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
TODAY = dt.date.today().strftime("%Y%m%d")


def fetch():
    import collect_m1 as M
    rows = {}
    for m in ("NYSE", "NASDAQ", "AMEX"):
        for x in M.get("/api/v1/stocks/all", market=m) or []:
            if x.get("status") not in (None, "ACTIVE"): continue
            rows[x["symbol"]] = (x["symbol"], x.get("securityType") or "", m, TODAY)
        time.sleep(1.5)
    return sorted(rows.values())


def main():
    age = float(arg("--max-age", "-1"))
    if age >= 0 and OUT.exists() and time.time() - OUT.stat().st_mtime < age * 86400:
        print("토스 미장 목록 %.1f일 됨 — 그대로" % ((time.time() - OUT.stat().st_mtime) / 86400)); return 0
    R = fetch()
    if len(R) < 5000:                                 # 반쯤 받다 끊긴 목록으로 표를 깎으면 안 된다
        print("토스 미장 목록 %d개뿐 — 이상해서 저장 안 함" % len(R)); return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["symbol", "type", "market", "asof"]); w.writerows(R)   # asof — CI 체크아웃은 파일 시각이 새로 찍혀 내용에 날짜를 둔다
    print("토스 미장 목록 %d개 → %s" % (len(R), OUT))
    if "--push" in sys.argv:
        g = lambda *a: subprocess.run(["git", *a], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="replace")
        g("add", str(OUT.relative_to(BASE)))
        if not g("diff", "--cached", "--quiet", "--", str(OUT.relative_to(BASE))).returncode:
            print("바뀐 것 없음 — 커밋 안 함"); return 0
        c = g("commit", "-m", "토스 미장 종목 목록 %s (%d개, toss_us_list.py)" % (dt.date.today(), len(R)), "--", str(OUT.relative_to(BASE)))
        p = g("pull", "-q", "--rebase", "--autostash"); u = g("push", "-q")
        print("커밋 %s · pull %s · push %s %s" % (c.returncode, p.returncode, u.returncode, (u.stderr or p.stderr or "")[:200]))
        return 0 if u.returncode == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
