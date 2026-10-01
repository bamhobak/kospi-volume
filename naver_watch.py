# -*- coding: utf-8 -*-
"""보유 국내 종목의 네이버 검색 관심 쏠림 — 보유 경고등 재료 (2026-10-02, 사용자 제안 12번 · 사용자 승인으로 Actions 에 네이버 키 등록).

관심도 att = 최근 28일 검색량 평균 ÷ 그 앞 365일 평균(research/trend_feat.py 와 같은 정의).
실측(H0248): att 시장 상위 10%(문턱 중앙 ≈1.63 · 이 스크립트는 1.7)는 60일 시장 대비 -5.4%p · 11/11해 음수 ·
오른 폭·거래량을 통제해도 -4.0%p. 단 우리 규칙 안 신호를 거르는 데는 무력 → **매수 거르개가 아니라 보유 경고등으로만** 쓴다.
원래 검색이 거의 없는 종목(앞 1년 중 0인 날 20%↑)은 비율이 의미 없어 경고하지 않는다.

  보유 종목: Supabase kospi_state(사이트 기본 PIN) · 국내 6자리 코드 · 아직 안 판 것
  이름: site/data/table.json 의 현재 종목명(키워드)
  한도: 이 작업만 **월 3,000건**(data/naver_watch_quota.json) — 사용자 지시 월 3만 건 안에서 연구용 수집과 나눠 쓴다
→ data/attn_watch.csv (date, ticker, name, att, zfrac) — 오늘 줄만 갈아 끼운다. shadow.py 가 읽어 warn.json 에 넣는다.

    python naver_watch.py
"""
import csv, datetime as dt, json, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
OUT = BASE / "data" / "attn_watch.csv"
QUOTA = BASE / "data" / "naver_watch_quota.json"
CAP = 3000


def env(k):
    v = os.environ.get(k)
    if v: return v.strip()
    f = BASE / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.startswith(k + "="): return l.split("=", 1)[1].strip().strip('"')
    return None


def held():
    import requests
    js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    pin = re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)
    r = requests.post(f"{url}/rest/v1/rpc/kospi_state_get", headers={"apikey": key, "Authorization": f"Bearer {key}",
                      "Content-Type": "application/json"}, json={"p_pin": pin}, timeout=20)
    r.raise_for_status()
    P = (r.json() or {}).get("positions") or []
    return sorted({p["code"] for p in P if p and p.get("code") and not p.get("sell") and re.fullmatch(r"\d{6}", str(p["code"]))})


def fetch(kw, start, end, cid, sec):
    body = {"startDate": start, "endDate": end, "timeUnit": "date", "keywordGroups": [{"groupName": kw[:50], "keywords": [kw]}]}
    req = urllib.request.Request(URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec, "Content-Type": "application/json"})
    for att in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())["results"][0]["data"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(10 * (att + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (att + 1))
    return None


def main():
    cid, sec = env("NAVER_HUB_CLIENT_ID"), env("NAVER_HUB_CLIENT_SECRET")
    if not cid or not sec:
        print("네이버 키 없음 — 건너뜀"); return
    T = json.loads((BASE / "site" / "data" / "table.json").read_text(encoding="utf-8"))
    names = {r["t"]: r.get("n") for r in T["rows"]}
    last = T["dates"][-1]
    codes = [c for c in held() if names.get(c)]
    m = dt.date.today().strftime("%Y%m")
    q = json.loads(QUOTA.read_text(encoding="utf-8")) if QUOTA.exists() else {}
    if q.get(m, 0) + len(codes) > CAP:
        print("이번 달 한도(%d건) — 건너뜀 (사용 %d)" % (CAP, q.get(m, 0))); return
    end = dt.datetime.strptime(last, "%Y%m%d").date()
    start = end - dt.timedelta(days=28 + 365 + 7)
    rows, used = [], 0
    for c in codes:
        d = fetch(names[c], start.isoformat(), end.isoformat(), cid, sec); used += 1
        if not d:
            continue
        v = {x["period"].replace("-", ""): float(x["ratio"]) for x in d}
        days = [(start + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range((end - start).days + 1)]
        s = [v.get(x, 0.0) for x in days]                      # 빠진 날 = 검색 0
        recent, base = s[-28:], s[-28 - 365:-28]
        bm = sum(base) / len(base) if base else 0
        att = (sum(recent) / 28) / bm if bm > 0 else None
        zf = sum(1 for x in base if x <= 0) / len(base) if base else 1
        rows.append(dict(date=last, ticker=c, name=names[c], att=round(att, 3) if att else "", zfrac=round(zf, 3)))
        time.sleep(0.2)
    q[m] = q.get(m, 0) + used
    QUOTA.write_text(json.dumps(q), encoding="utf-8")
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "ticker", "name", "att", "zfrac"]); w.writeheader(); w.writerows(rows)
    hot = [r for r in rows if r["att"] != "" and r["att"] >= 1.7 and r["zfrac"] <= 0.2]
    print("보유 국내 %d종목 관심도 · 쏠림(1.7배↑) %d종목 %s · 이번 달 %d건" % (len(rows), len(hot), ", ".join("%s %.1f배" % (r["name"], r["att"]) for r in hot), q[m]))


if __name__ == "__main__":
    main()
