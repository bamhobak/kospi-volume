# -*- coding: utf-8 -*-
"""토스증권 Open API 얇은 클라이언트.

KRX 는 저속(gap 2초)으로만 때릴 수 있는데 토스는 매매동향 그룹이 초당 10회다.
과거를 얼마나 주는지에 따라 KRX 백필을 상당 부분 대체할 수 있다.
토큰은 24시간짜리라 파일에 캐시해 두고 재사용한다.
"""
import io, os, sys, json, time, urllib.request, urllib.parse
from pathlib import Path
BASE = Path(__file__).parent
B = "https://openapi.tossinvest.com"
_TOK = {"v": None, "exp": 0}

def _env():
    """로컬은 .env, GitHub Actions 는 환경변수(secrets)에서 읽는다."""
    e = {}
    f = BASE/".env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); e[k.strip()] = v.strip()
    for k in ("TOSS_CLIENT_KEY", "TOSS_SECRET_KEY"):
        if os.environ.get(k): e[k] = os.environ[k]
        if k not in e: raise SystemExit(f"{k} 가 없습니다(.env 또는 환경변수)")
    return e

def token():
    if _TOK["v"] and time.time() < _TOK["exp"] - 60: return _TOK["v"]
    c = BASE/"data"/".toss_token.json"
    if c.exists():
        try:
            j = json.loads(c.read_text())
            if time.time() < j["exp"] - 60:
                _TOK.update(v=j["v"], exp=j["exp"]); return j["v"]
        except Exception: pass
    e = _env()
    body = urllib.parse.urlencode({"grant_type": "client_credentials",
        "client_id": e["TOSS_CLIENT_KEY"], "client_secret": e["TOSS_SECRET_KEY"]}).encode()
    r = urllib.request.Request(B+"/oauth2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    t = json.loads(urllib.request.urlopen(r, timeout=30).read().decode())
    _TOK.update(v=t["access_token"], exp=time.time()+int(t.get("expires_in", 3600)))
    try: c.write_text(json.dumps(_TOK))
    except Exception: pass
    return _TOK["v"]

def get(path, **q):
    """응답은 {'result': ...} 로 한 겹 싸여 온다 — 벗겨서 돌려준다."""
    u = path + ("?" + urllib.parse.urlencode({k: v for k, v in q.items() if v is not None}) if q else "")
    for i in range(4):
        rq = urllib.request.Request(B+u, headers={"Authorization": f"Bearer {token()}"})
        try:
            d = json.loads(urllib.request.urlopen(rq, timeout=12).read().decode())
            return d.get("result", d)
        except Exception as ex:
            code = getattr(ex, "code", None)
            msg = ex.read().decode()[:200] if hasattr(ex, "read") else str(ex)
            # 400·404 는 그 종목에 데이터가 없다는 뜻이라 다시 물어도 같다. 즉시 포기해야
            # 전체 수집이 느려지지 않는다(2,767종목 중 상당수가 여기 해당한다).
            if code in (400, 404) or i == 3: return {"_err": msg}
            time.sleep(2.0*(i+1) if code == 429 else 0.4*(i+1))
