# -*- coding: utf-8 -*-
"""공시 감시 — 그림자 규칙·보유 경고등 재료 (2026-10-02, 사용자 제안 11·12번).

찾는 공시(정정·해제·예고·자회사 공시는 뺀다):
  양수도   최대주주변경을수반하는주식양수도계약체결   → 보유 경고등(실측 60일 중앙 -13.9%, H0246)
  밸류업   기업가치제고계획                         → 그림자 규칙(H0245)
  신탁     자기주식취득신탁계약체결결정               → 그림자 규칙(자사주 신탁 + 20일 -10%)
  대량보유 주식등의대량보유상황보고서 — 보고자가 행동주의·가치 운용사일 때만 → 그림자 규칙
→ data/disc_watch.csv (rcept_no, rcept_dt, ticker, kind, report_nm, flr_nm) · 최근 400일만 남긴다.

    python collect_disc_watch.py           # Actions: DART list.json 으로 최근 7일을 받아 덧붙인다
    python collect_disc_watch.py --seed    # 로컬: data/dart/disclosures.db 에서 최근 400일로 채운다(처음 한 번)
"""
import csv, os, re, sqlite3, sys, time, datetime as dt
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "data" / "disc_watch.csv"
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

ACT = re.compile(r"얼라인|케이씨지아이|KCGI|트러스톤|안다자산|플래쉬라이트|차파트너스|머스트자산|라이프자산|밸류파트너스|"
                 r"시티오브런던|City of London|브이아이피자산|VIP자산|돌핀|에셋플러스")


def kind(nm, flr):
    n = (nm or "").replace(" ", "")
    if re.search(r"정정|해제|취소|예고|자회사|종속회사", n):
        return None
    if "최대주주변경을수반하는주식양수도계약체결" in n: return "양수도"
    if "기업가치제고계획" in n: return "밸류업"
    if "자기주식취득신탁계약체결결정" in n: return "신탁"
    if "주식등의대량보유상황보고서" in n and ACT.search(flr or ""): return "대량보유"
    return None


def env(k):
    v = os.environ.get(k)
    if v: return v.strip()
    f = BASE / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.startswith(k + "="): return l.split("=", 1)[1].strip().strip('"')
    return None


def load():
    if not OUT.exists():
        return {}
    with open(OUT, encoding="utf-8") as fh:
        return {r["rcept_no"]: r for r in csv.DictReader(fh)}


def save(rows):
    cut = (dt.date.today() - dt.timedelta(days=400)).strftime("%Y%m%d")
    rows = sorted((r for r in rows.values() if r["rcept_dt"] >= cut), key=lambda r: (r["rcept_dt"], r["rcept_no"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["rcept_no", "rcept_dt", "ticker", "kind", "report_nm", "flr_nm"])
        w.writeheader(); w.writerows(rows)
    print("공시 감시 저장 %d건 → %s" % (len(rows), OUT.name))


def seed(rows):
    cut = (dt.date.today() - dt.timedelta(days=400)).strftime("%Y%m%d")
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    for rn, d, t, nm, flr in c.execute("select rcept_no, rcept_dt, stock_code, report_nm, flr_nm from disclosure "
                                         "where rcept_dt >= ? and stock_code != ''", (cut,)):
        k = kind(nm, flr)
        if k:
            rows[rn] = dict(rcept_no=rn, rcept_dt=d, ticker=t, kind=k, report_nm=nm[:80], flr_nm=flr or "")


def fetch(rows, days=7):
    import requests
    K = env("DART_API_KEY")
    if not K:
        print("DART 키 없음 — 건너뜀"); return
    b = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d"); e = dt.date.today().strftime("%Y%m%d")
    n0 = len(rows)
    for ty in ("I", "B", "D"):                       # 거래소공시 · 주요사항보고 · 지분공시
        for cls in ("Y", "K"):
            page = 1
            while page <= 80:
                try:
                    d = requests.get("https://opendart.fss.or.kr/api/list.json",
                                     params={"crtfc_key": K, "bgn_de": b, "end_de": e, "corp_cls": cls, "pblntf_ty": ty,
                                             "page_no": page, "page_count": 100}, timeout=30).json()
                except Exception as ex:
                    print("DART %s %s p%d 실패: %s" % (ty, cls, page, str(ex)[:60])); break
                if d.get("status") != "000":
                    break
                for x in d.get("list") or []:
                    k = kind(x.get("report_nm"), x.get("flr_nm"))
                    if k and x.get("stock_code"):
                        rows[x["rcept_no"]] = dict(rcept_no=x["rcept_no"], rcept_dt=x["rcept_dt"], ticker=x["stock_code"], kind=k,
                                                   report_nm=(x.get("report_nm") or "")[:80], flr_nm=x.get("flr_nm") or "")
                if page >= int(d.get("total_page") or 1):
                    break
                page += 1; time.sleep(0.1)
    print("새로 찾은 공시 %d건" % (len(rows) - n0))


if __name__ == "__main__":
    rows = load()
    if "--seed" in sys.argv:
        seed(rows)
    else:
        fetch(rows)
    save(rows)
