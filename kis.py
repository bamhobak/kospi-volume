# -*- coding: utf-8 -*-
"""한국투자증권 KIS Open API 공통 모듈 — 토큰 캐시 + 호출 헬퍼
   토큰은 1일 1회 발급 원칙(한투 안내). 유효기간 24h.
   캐시 순서: ① 로컬 파일 → ② Supabase(__kis_token__, GitHub Actions 간 공유) → ③ 신규 발급
   GitHub Actions 는 매 실행이 새 환경이라 ②가 없으면 매번 발급하게 됨 → 이용 제한 위험.
"""
import json, os, re, time, datetime as dt
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent
ENV = {}
_envf = BASE_DIR / ".env"
if _envf.exists():
    ENV = dict(l.split("=", 1) for l in _envf.read_text(encoding="utf-8").strip().splitlines() if "=" in l)
APP_KEY = (os.environ.get("KIS_APP_KEY") or ENV.get("KIS_APP_KEY", "")).strip()
APP_SECRET = (os.environ.get("KIS_APP_SECRET") or ENV.get("KIS_APP_SECRET", "")).strip()
HOST = "https://openapi.koreainvestment.com:9443"
TOKEN_FILE = BASE_DIR / "data" / ".kis_token.json"
KST = dt.timezone(dt.timedelta(hours=9))

# ── Supabase (prices.py 와 동일한 방식으로 assets/sb.js 에서 읽음)
_SB = None
def _sb():
    global _SB
    if _SB is None:
        try:
            js = (BASE_DIR / "assets" / "sb.js").read_text(encoding="utf-8")
            url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
            _SB = (url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except Exception:
            _SB = (None, None)
    return _SB
def _sb_get():
    url, h = _sb()
    if not url: return None
    try:
        r = requests.post(f"{url}/rest/v1/rpc/kospi_state_get", headers=h, json={"p_pin": "__kis_token__"}, timeout=15)
        return r.json() if r.ok and r.text else None
    except Exception:
        return None
def _sb_set(tok):
    url, h = _sb()
    if not url: return
    try:
        requests.post(f"{url}/rest/v1/rpc/kospi_state_set", headers=h,
                      json={"p_pin": "__kis_token__", "p_data": tok}, timeout=15)
    except Exception:
        pass

def _valid(t):
    try:
        exp = dt.datetime.strptime(t["access_token_token_expired"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        return (exp - dt.datetime.now(KST)) > dt.timedelta(minutes=30)
    except Exception:
        return False

def get_token(force=False):
    if not force:
        # ① 로컬 파일
        if TOKEN_FILE.exists():
            try:
                t = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
                if _valid(t): return t["access_token"]
            except Exception:
                pass
        # ② Supabase 공유 캐시 (Actions 실행 간 재사용)
        t = _sb_get()
        if t and _valid(t):
            try:
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(json.dumps(t), encoding="utf-8")
            except Exception:
                pass
            return t["access_token"]
    # ③ 신규 발급 (1일 1회 원칙 — 위 캐시가 없을 때만)
    for attempt in range(3):
        r = requests.post(f"{HOST}/oauth2/tokenP",
                          json={"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET},
                          headers={"content-type": "application/json; charset=utf-8"}, timeout=30)
        d = r.json()
        if "access_token" in d:
            d["issued_at"] = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            try:
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(json.dumps(d), encoding="utf-8")
            except Exception:
                pass
            _sb_set(d)
            print(f"KIS 토큰 신규 발급 ({d['issued_at']} KST, 만료 {d.get('access_token_token_expired')})")
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
