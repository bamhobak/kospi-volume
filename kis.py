# -*- coding: utf-8 -*-
"""한국투자증권 KIS Open API 공통 모듈 — 토큰 캐시(24h) + 호출 헬퍼
   토큰 발급은 1분당 1회 제한이므로 반드시 캐시를 재사용한다.
"""
import json, time, datetime as dt
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent
import os
ENV = {}
_envf = BASE_DIR / ".env"
if _envf.exists():
    ENV = dict(l.split("=", 1) for l in _envf.read_text(encoding="utf-8").strip().splitlines() if "=" in l)
APP_KEY = (os.environ.get("KIS_APP_KEY") or ENV.get("KIS_APP_KEY", "")).strip()
APP_SECRET = (os.environ.get("KIS_APP_SECRET") or ENV.get("KIS_APP_SECRET", "")).strip()
HOST = "https://openapi.koreainvestment.com:9443"
TOKEN_FILE = BASE_DIR / "data" / ".kis_token.json"

def get_token(force=False):
    if not force and TOKEN_FILE.exists():
        try:
            t = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            exp = dt.datetime.strptime(t["access_token_token_expired"], "%Y-%m-%d %H:%M:%S")
            if exp - dt.datetime.now() > dt.timedelta(minutes=10):
                return t["access_token"]
        except Exception:
            pass
    for attempt in range(3):
        r = requests.post(f"{HOST}/oauth2/tokenP",
                          json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET},
                          headers={"content-type": "application/json; charset=utf-8"}, timeout=30)
        d = r.json()
        if "access_token" in d:
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(json.dumps(d), encoding="utf-8")
            return d["access_token"]
        if d.get("error_code") == "EGW00133":          # 1분당 1회 제한
            time.sleep(62); continue
        raise RuntimeError(f"토큰 발급 실패: {d}")
    raise RuntimeError("토큰 발급 실패(재시도 초과)")

def call(path, tr_id, params, token=None, tr_cont=""):
    h = {"content-type": "application/json; charset=utf-8",
         "authorization": f"Bearer {token or get_token()}",
         "appkey": APP_KEY, "appsecret": APP_SECRET, "tr_id": tr_id,
         "custtype": "P", "tr_cont": tr_cont}
    r = requests.get(HOST + path, headers=h, params=params, timeout=30)
    try: return r.status_code, r.json(), r.headers.get("tr_cont", "")
    except Exception: return r.status_code, {"raw": r.text[:300]}, ""
