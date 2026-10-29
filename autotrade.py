# -*- coding: utf-8 -*-
"""토스 자동매매 — 규칙 신호대로 **실제로 사고 판다** (2026-10-03 사용자: "바로 자동", "완전 자동을 직접 허용").

사용자 결정(2026-10-03): 시드 국장 5천만·미장 5천만(원화 기준, 미장은 달러로 직접 환전해 둔다) · 한 건에 국장 150만·미장 100만
  · 하루 최대 국장 5건·미장 5건. 시드가 차거나 토스 매수가능 금액이 모자라면 우선순위 낮은 것부터 못 사고 알린다.
무엇을 사나: 사이트 '매수 대기'와 같은 목록 — notify_new.py 가 매 수집 뒤 Supabase '__filters__' 에 저장하는
  규칙별 신호(그 규칙으로 아직 안 산 종목). 순서는 사이트 우선순위(하루당 기대수익 = stats.avg ÷ hold).
무엇을 파나: **자동매매가 산 포지션(auto=true)만**. 손으로 기록한 것·토스 계좌의 다른 보유분(스페이스X 등)은 절대 안 건드린다.
  보유일은 사이트·매도일 알림과 같은 셈법(매수일 = 1일째, 거래일로 센다) — 보유일 ≥ 규칙 hold 인 날 **종가**에 판다.

예약작업(이 PC — 토스 허용 IP 가 이 PC 다):
  plan kr  08:35  → 08:51 장전 시가 단일가에 시장가(OPG) · 09:01 체결 확인 · 사이트 보유 목록에 기록
  plan us  21:50·22:50 → 개장 70분 전 안이면 개장+1분까지 기다렸다 시장가(정수 주) · 체결 확인 · 기록
  sell kr  15:15  → 15:21 종가 단일가에 시장가 매도 · 15:32 체결 확인 · 사이트에 매도 기록
  sell us  04:15·05:15 → 마감 50~12분 전이면 LOC(종가 지정가, 낮은 지정가 = 사실상 종가) · 마감 뒤 체결 확인 · 기록
  check            → 토큰·계좌·매수가능·장 시간·신호만 본다(주문 없음)
멈추기: .env 에 AUTOTRADE_MODE=off (live 일 때만 주문) · 또는 data/autotrade/STOP 파일을 만든다.
시험: --dry → 주문·사이트 쓰기·텔레그램 대신 기록만(체결은 현재가로 가정) · --wait0 → 기다리지 않는다 · AUTOTRADE_PIN 으로 다른 PIN.

⚠ 토큰은 키당 1개만 산다 — collect_toss.py 와 같은 캐시(toss.token)를 쓴다. 따로 받으면 서로를 끊는다.
⚠ 허용 IP 밖이면 403 — 지금 공인 IP 를 텔레그램으로 알린다.
⚠ 예약작업(pythonw)은 sys.stdout 이 None — print 대신 log().
⚠ 미장 소수점 주문은 정규장 마감 1시간 전까지만 팔 수 있어 종가 매도(LOC)가 안 된다 → **정수 주로만 산다**.
⚠ 사이트는 보유 목록을 통째로 덮어쓴다(updated 가 늦은 쪽이 이김). 열린 탭이 옛 목록을 올리면 자동 기록이 지워질 수 있어
   매 실행 처음에 원장(ledger.json)과 맞춰 **빠진 자동 포지션을 되살린다**.
"""
import datetime as dt, gzip, http.client, json, math, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "autotrade"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"; LEDGER = OUT / "ledger.json"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

PER = {"KR": 1_500_000, "US": 1_000_000}      # 규칙 하나당(원) — 2026-10-03 사용자: 국장 150만·미장 100만
SEED = {"KR": 50_000_000, "US": 50_000_000}   # 시장별 시드(원) — 자동매매가 들고 있는 매수금(미장은 그때 환율) + 오늘 살 것 ≤ 시드
MAXDAY = {"KR": 5, "US": 5}   # 하루 최대 매수 건수
# 2026-10-15 사용자 "스윙도 일단 1주씩": 테스트 동안 신호마다 1주만(PER 금액 무시). 돈 제대로 넣을 때 None 으로 되돌린다.
SWING_QTY = 1
# 2026-10-18 [지수 덮개] IX1(사용자 '둘 다 적용' · research H0360): 코스피200 종가가 60일선 +3% 위로 마감 → 다음날 시가에 KODEX 200 매수,
#   60일선 -3% 아래로 마감 → 다음날 시가에 매도(띠 안에서는 그대로). 금액 = 시드에서 자동 보유를 뺀 남은 돈의 50%(10-18 사용자, 처음 30%) · 테스트 동안은 SWING_QTY 주.
#   계좌(2005~): 연 +15.4% → +18.2% · 낙폭 -12.4% → -14.3% · 수익 난 해 21/22 그대로. 스윙 매도(보유일)는 이 포지션을 건드리지 않는다(overlay=True).
OVL_ID, OVL_SYM, OVL_NAME, OVL_MA, OVL_BAND, OVL_W = "IX1", "069500", "KODEX 200", 60, 3.0, 0.50   # 10-18 사용자: 30% → 50%
KST = dt.timezone(dt.timedelta(hours=9))
DRY = "--dry" in sys.argv
WAIT0 = "--wait0" in sys.argv
FINAL = ("FILLED", "CANCELED", "REJECTED", "CANCEL_REJECTED", "REPLACE_REJECTED", "REPLACED")


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + ("[DRY] " if DRY else "") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def env():
    e = {}
    f = BASE / ".env"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1); e[k.strip()] = v.strip()
    e.update({k: v for k, v in os.environ.items() if k.startswith(("TOSS_", "TELEGRAM_", "AUTOTRADE_"))})
    return e


E = env()
MODE = E.get("AUTOTRADE_MODE", "notify")


def telegram(text):
    if DRY:
        log("텔레그램(보내지 않음):\n" + text); return
    tg_send(E.get("TELEGRAM_BOT_TOKEN"), E.get("TELEGRAM_CHAT_ID"), text)


TG_PEND = BASE / "data" / "autotrade" / "tg_pending.jsonl"
_TGC = []


def _tg_ctx():
    """텔레그램 TLS 검증 — certifi 묶음 우선. 2026-10-26 서버 첫 실전날: 윈도우 루트 목록에 GoDaddy 루트가 아직 없어서
    (윈도우는 처음 쓸 때 받아 오지만 파이썬은 안 받아 옴) 'self-signed certificate in chain' 으로 아침 알림이 전부 막혔다."""
    if not _TGC:
        try:
            import ssl, certifi
            _TGC.append(ssl.create_default_context(cafile=certifi.where()))
        except Exception:
            _TGC.append(None)
    return _TGC[0]


def tg_send(tok, chat, text):
    """텔레그램 — 몇 번 다시 하고, 그래도 안 되면 파일에 쌓아 두었다가 다음 알림 때 같이 보낸다(10-06 매도 실패 알림도 같이 사라졌다)."""
    if not (tok and chat):
        log("텔레그램 미설정:", text.replace("\n", " | ")); return
    msgs = []
    try:
        if TG_PEND.exists():
            msgs = [json.loads(l) for l in TG_PEND.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception: msgs = []
    msgs.append(text)
    left = []
    for m in msgs:
        ok, html = False, True
        for i in range(4):
            try:
                d = {"chat_id": chat, "text": m, "disable_web_page_preview": True}
                if html: d["parse_mode"] = "HTML"
                else: d["text"] = re.sub(r"</?(b|i|u|s|code|pre)>", "", m)          # 서식 없이 — 굵은 글씨 꼬리표만 떼고 나머지 글자는 그대로
                rq = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
                urllib.request.urlopen(rq, timeout=30, context=_tg_ctx()).read(); ok = True; break
            except urllib.error.HTTPError as ex:
                # 2026-10-27: 실패 알림에 '<HTTPError 403: ...>' 같은 글자가 들어가 HTML 서식이 깨져 400 으로 거절 → 04:15 미장 매도 실패 알림이 사라졌다.
                #   400 이면 서식 없이 한 번 더 보낸다. 그래도 거절이면 형식 문제라 다시 해도 같다 — 쌓지 않는다.
                if ex.code == 400 and html:
                    log("텔레그램 서식 거절(400) — 서식 없이 다시"); html = False; continue
                log("텔레그램 거절:", ex.code); ok = True; break
            except Exception as ex:
                log("텔레그램 실패(%d):" % (i + 1), repr(ex)[:120]); time.sleep(5 * (i + 1))
        if not ok: left.append(m)
    try:
        TG_PEND.parent.mkdir(parents=True, exist_ok=True)
        if left: TG_PEND.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in left), encoding="utf-8")
        elif TG_PEND.exists(): TG_PEND.unlink()
    except Exception: pass


def now():
    return dt.datetime.now(KST)


def sleep_until(t, why=""):
    s = (t - now()).total_seconds()
    if s > 0:
        log("%s까지 기다림(%s) %.0f초" % (t.strftime("%H:%M:%S"), why, s))
        if not WAIT0:
            time.sleep(s)


def won(v):
    v = round(v / 1e4)
    return (f"{v // 10000}억" + (f" {v % 10000:,}만" if v % 10000 else "")) if v >= 10000 else f"{v:,}만"


# ── 토스 ───────────────────────────────────────────────────────────────
import toss


GZ = bytes([0x1F, 0x8B])


class TossErr(Exception):
    def __init__(self, msg, code=None, status=None):
        super().__init__(msg); self.code = code; self.status = status


_acct = {}


def _blocked(path, code=None):
    """토스 403 — 허용 IP 밖. 지금 공인 IP 를 같이 알려 준다(서버 공유기·회선이 바뀌면 생긴다)."""
    ip = "?"
    try: ip = urllib.request.urlopen("https://ifconfig.me/ip", timeout=10).read().decode().strip()
    except Exception: pass
    return TossErr("토스 403 차단 %s — 허용 IP 밖일 수 있다(지금 공인 IP %s). 토스 웹 설정 > Open API > 허용 IP 관리에 추가" % (path, ip), code or "forbidden", 403)


NET_WAIT = 300      # 네트워크가 끊겨도 이만큼(초)은 다시 해 본다 — 종가 단일가(15:20~30) 안에 붙어야 한다


def call(method, path, acct=False, body=None, **q):
    """2026-10-06: 15:21 데이 종가 매도가 DNS 실패(getaddrinfo) 한 번에 통째로 죽었다 → 3주가 안 팔렸다.
    이제 네트워크 오류(DNS·연결 끊김·시간 초과)는 NET_WAIT 동안 5→30초 간격으로 다시 한다.
    clientOrderId 가 10분 멱등키라 주문을 다시 보내도 두 번 체결되지 않는다."""
    t0 = time.time(); k = 0
    while True:
        try:
            return _call(method, path, acct, body, **q)
        except TossErr:
            raise
        except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException) as ex:
            # 2026-10-27: 서버 공유기 교체로 공인 IP 가 바뀌자 토큰 발급·계좌번호 조회(_call 의 try 밖)가 403 → 여기서 '네트워크 오류'로
            #   5분 넘게 다시 했다(04:15 미장 매도). 403 은 다시 해도 같다 — 바로 '허용 IP 밖' 으로 끝낸다.
            if isinstance(ex, urllib.error.HTTPError) and ex.code == 403:
                raise _blocked(path)
            k += 1
            if time.time() - t0 > NET_WAIT:
                raise TossErr("네트워크 %d번 실패(%.0f초) %s: %s" % (k, time.time() - t0, path, repr(ex)[:120]), "network")
            w = min(30, 5 * k); log("네트워크 오류 — %d초 뒤 다시(%d번째):" % (w, k), path, repr(ex)[:120])
            time.sleep(w)


_TH = []


def _pace():
    """2026-10-26 사용자 "후보 많아질 걸 미리 대비" — 주문·조회 호출도 collect_m1 시세 호출과 **같은 자물쇠**로 초당 ~14회(토스 한도 20/초) 안에.
    전엔 주문 쪽엔 속도 조절이 없어 데이 09:00 시가 확인(8갈래 동시)에서 HTTP 429 가 4건 났다. 한 프로세스 안에서만 맞춘다."""
    if not _TH:
        try:
            import collect_m1 as _M
            _TH.append(_M._throttle)
        except Exception:
            _TH.append(None)
    if _TH[0]: _TH[0]()


def _call(method, path, acct=False, body=None, **q):
    u = toss.B + path + ("?" + urllib.parse.urlencode(q) if q else "")
    for att in range(6):
        _pace()
        h = {"Authorization": "Bearer " + toss.token(), "Accept": "application/json"}
        if acct: h["X-Tossinvest-Account"] = ACCT()
        data = None
        if body is not None:
            data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, data=data, headers=h, method=method), timeout=30)
            b = r.read()
            if b.startswith(GZ):
                b = gzip.decompress(b)
            d = json.loads(b.decode() or "{}")
            return d.get("result", d)
        except urllib.error.HTTPError as ex:
            raw = ex.read()
            if raw.startswith(GZ):              # 토스 오류 본문이 gzip 으로 올 때가 있다(10-06 데이 매수 422 원인을 못 읽음)
                try: raw = gzip.decompress(raw)
                except Exception: pass
            raw = raw.decode(errors="replace")[:500]
            try: code = json.loads(raw).get("error", {}).get("code")
            except Exception: code = None
            if ex.code == 401 and att == 0:              # 다른 프로세스가 새 토큰을 받아 이 토큰이 죽은 경우
                toss._TOK.update(v=None, exp=0)
                try: (BASE / "data" / ".toss_token.json").unlink()
                except Exception: pass
                continue
            if ex.code == 429 and att < 5:                 # 10-26: 2번 → 5번 · 0.5→1→2→4→5초(토스가 Retry-After 를 주면 그 값)
                try: w = float(ex.headers.get("Retry-After"))
                except Exception: w = min(5.0, 0.5 * 2 ** att)
                time.sleep(w); continue
            if ex.code == 403:
                raise _blocked(path, code)
            raise TossErr("HTTP %d %s %s" % (ex.code, path, raw), code, ex.code)
    raise TossErr("재시도 뒤에도 실패 %s" % path)


def tget(path, acct=False, **q):
    return call("GET", path, acct, None, **q)


def ACCT():
    if "v" not in _acct:
        h = {"Authorization": "Bearer " + toss.token(), "Accept": "application/json"}
        d = json.loads(urllib.request.urlopen(urllib.request.Request(toss.B + "/api/v1/accounts", headers=h), timeout=20).read().decode())
        L = [a for a in d.get("result", []) if a.get("accountType") == "BROKERAGE"] or d.get("result", [])
        if not L: raise TossErr("계좌가 없다")
        _acct["v"] = str(L[0]["accountSeq"])
    return _acct["v"]


def prices(symbols):
    out = {}
    for i in range(0, len(symbols), 200):
        for x in tget("/api/v1/prices", symbols=",".join(symbols[i:i + 200])) or []:
            out[x["symbol"]] = float(x["lastPrice"])
    return out


def names(symbols):
    out = {}
    for i in range(0, len(symbols), 100):
        try:
            for x in tget("/api/v1/stocks", symbols=",".join(symbols[i:i + 100])) or []:
                out[x["symbol"]] = (x.get("name") or x["symbol"], x.get("status"), (x.get("koreanMarketDetail") or {}).get("krxTradingSuspended"))
        except TossErr as ex:
            log("종목 정보 실패:", ex)
    return out


def usdkrw():
    return float(tget("/api/v1/exchange-rate", baseCurrency="USD", quoteCurrency="KRW")["rate"])


def buying_power(cur):
    return float(tget("/api/v1/buying-power", acct=True, currency=cur)["cashBuyingPower"])


def sellable(sym):
    return float(tget("/api/v1/sellable-quantity", acct=True, symbol=sym)["sellableQuantity"])


_dry_px = {}


def place(body):
    """주문 → orderId. DRY 면 가짜 id."""
    if DRY:
        log("주문(보내지 않음):", json.dumps(body, ensure_ascii=False))
        return "DRY-" + body["clientOrderId"]
    r = call("POST", "/api/v1/orders", acct=True, body=body)
    return r["orderId"]


def detail(oid, sym=None, qty=None):
    if DRY:
        p = _dry_px.get(sym) or prices([sym])[sym]
        return {"status": "FILLED", "execution": {"filledQuantity": str(qty), "averageFilledPrice": str(p), "commission": "0"}}
    return tget("/api/v1/orders/%s" % oid, acct=True)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def session(mk):
    """지금과 관련된 정규장 하나 → dict(date, start, end, ...) 또는 None(오늘 장 없음).
    미장은 한국 시각으로 하루를 넘기므로 '직전 영업일'·'오늘' 중 아직 안 끝난 쪽을 고른다."""
    cal = tget("/api/v1/market-calendar/" + mk)
    n = now()
    if mk == "KR":
        it = (cal.get("today") or {}).get("integrated")
        if not it: return None
        rm = it["regularMarket"]; pm = it.get("preMarket") or {}
        return dict(date=cal["today"]["date"].replace("-", ""), start=ts(rm["startTime"]), end=ts(rm["endTime"]),
                    close_auction=ts(rm["singlePriceAuctionStartTime"]) if rm.get("singlePriceAuctionStartTime") else ts(rm["endTime"]) - dt.timedelta(minutes=10),
                    open_auction=ts(pm["singlePriceAuctionStartTime"]) if pm.get("singlePriceAuctionStartTime") else ts(rm["startTime"]) - dt.timedelta(minutes=10),
                    prev=cal["previousBusinessDay"]["date"].replace("-", ""))
    for key in ("previousBusinessDay", "today", "nextBusinessDay"):
        x = cal.get(key) or {}
        rm = x.get("regularMarket")
        if rm and n < ts(rm["endTime"]):
            prev = cal["previousBusinessDay"]["date"].replace("-", "") if key == "today" else None
            return dict(date=x["date"].replace("-", ""), start=ts(rm["startTime"]), end=ts(rm["endTime"]), prev=prev)
    return None


# ── 사이트(Supabase) ────────────────────────────────────────────────────
_sb = {}


def _sbinit():
    if not _sb:
        js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
        _sb["url"] = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
        _sb["H"] = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        _sb["pin"] = E.get("AUTOTRADE_PIN") or re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)


def rpc(fn, b):
    import requests
    _sbinit()
    r = requests.post(f"{_sb['url']}/rest/v1/rpc/{fn}", headers=_sb["H"], json=b, timeout=30); r.raise_for_status()
    return r.json() if r.text else None


def filters_state():
    return rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}


def site_state():
    _sbinit()
    return rpc("kospi_state_get", {"p_pin": _sb["pin"]}) or {}


def site_update(mutate, why):
    """보유 목록을 읽고 고쳐서 다시 쓴다(다른 칸은 그대로). 사이트와 같은 방식으로 updated = ms."""
    _sbinit()
    for att in range(3):
        d = site_state()
        pos = d.get("positions") if isinstance(d.get("positions"), list) else []
        if not mutate(pos):
            return False
        d["positions"] = pos; d["updated"] = int(time.time() * 1000)
        if DRY:
            log("사이트 쓰기(보내지 않음):", why, "· 보유", len([p for p in pos if not p.get("sell")])); return True
        rpc("kospi_state_set", {"p_pin": _sb["pin"], "p_data": d})
        if site_state().get("updated") == d["updated"]:
            log("사이트 기록:", why); return True
        time.sleep(1)
    raise RuntimeError("사이트 기록 실패: " + why)


def rules():
    """index.html FILTERS → {id: (이름, 보유일, 하루당 기대수익)} — 사이트 priMap 과 같은 계산."""
    s = (BASE / "index.html").read_text(encoding="utf-8")
    R = {}
    for m in re.finditer(r"\{id:'([NPD]\d)'(.*?)stats:\{(.*?)\}", s, re.S):
        rid, body, st = m.groups()
        h = re.search(r"hold:(\d+)", body); a = re.search(r"avg:([-\d.]+)", st); nm = re.search(r"name:'([^']*)'", body)
        if h and a and rid not in R:
            R[rid] = ((nm.group(1).split(" · ")[-1] if nm else rid), int(h.group(1)), float(a.group(1)) / int(h.group(1)))
    return R


def mk_of(t):
    return "KR" if re.fullmatch(r"[0-9A-Z]{6}", t or "") and any(c.isdigit() for c in t[:2]) else "US"


# ── 원장 ───────────────────────────────────────────────────────────────
def led():
    try: return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception: return {"orders": []}


def led_save(L):
    if DRY: return
    tmp = LEDGER.with_suffix(".tmp"); tmp.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(LEDGER)


def heal():
    """원장에 체결로 남은 자동 포지션이 사이트에서 빠졌거나 매도 기록이 없으면 되살린다."""
    L = led()
    buys = {o["pos"]["id"]: o for o in L["orders"] if o.get("side") == "BUY" and o.get("pos")}
    sells = {o["posId"]: o for o in L["orders"] if o.get("side") == "SELL" and o.get("sold")}
    if not buys: return

    def fix(pos):
        ch = False; ids = {p.get("id") for p in pos}
        for pid, o in buys.items():
            if pid not in ids:
                pos.append(dict(o["pos"])); ch = True; log("되살림:", o["pos"]["code"], o["pos"]["filters"])
        for p in pos:
            s = sells.get(p.get("id"))
            if s and not p.get("sell"):
                p.update(s["sold"]); ch = True; log("매도 기록 되살림:", p["code"])
        return ch
    site_update(fix, "원장 맞춤")


def guard():
    if (OUT / "STOP").exists():
        log("STOP 파일 — 멈춤"); telegram("⛔ 자동매매 멈춤(STOP)"); return False
    return True


def wait_fills(orders):
    for o in orders:
        dtl = None
        for k in range(20):
            try: dtl = detail(o["oid"], o["t"], o["qty"])
            except TossErr as ex: log("주문 조회 실패", ex); time.sleep(3); continue
            if dtl.get("status") in FINAL: break
            time.sleep(6)
        ex_ = (dtl or {}).get("execution") or {}
        o["status"] = (dtl or {}).get("status")
        o["fq"] = float(ex_.get("filledQuantity") or 0); o["ap"] = float(ex_.get("averageFilledPrice") or 0); o["fee"] = ex_.get("commission")


# ── 매수 ───────────────────────────────────────────────────────────────
def candidates(mk, F, ST, R, rank, today_keys):
    pos = [p for p in (ST.get("positions") or []) if p and p.get("code") and not p.get("sell")]
    held_by = {}
    for p in pos: held_by.setdefault(p["code"], set()).update(str(f) for f in (p.get("filters") or []))
    streak = F.get("streaks") or {}
    toss_us = _toss_us() if mk == "US" else None
    C = []
    for rid, L in (F.get("filters") or {}).items():
        for t in L:
            if mk_of(t) != mk or rid not in R or rid in held_by.get(t, set()) or f"{rid}:{t}" in today_keys:
                continue
            if toss_us and t not in toss_us:
                log("토스에 없는 미장 종목이라 건너뜀:", rid, t); continue
            C.append((rank.get(rid, 99), streak.get(f"{rid}:{t}", 1), rid, t))
    return sorted(C)


def _toss_us():
    """토스에서 살 수 있는 미장 종목(toss_us_list.py → data/us/toss_us.csv). 10-26 VSECU(유닛)가 [N4] 에 걸린 사고 —
    사이트 표는 다음 CI 부터 걸러지지만 그 사이·목록 밖 종목을 여기서도 막는다. 파일이 없거나 이상하면 None(거르지 않음)."""
    try:
        import csv
        with open(BASE / "data" / "us" / "toss_us.csv", encoding="utf-8") as fh:
            s = {r["symbol"] for r in csv.DictReader(fh)}
        return s if len(s) >= 5000 else None
    except Exception:
        return None


def ovl_state():
    """코스피200 ±3% 띠 상태 — (들어가 있어야 하나, 마지막 종가일, 종가, 60일선). 띠는 이력에 따라 달라서 처음부터 다시 돌린다."""
    import index_cal as IC
    k = IC.naver_closes("KPI200", 700)
    ds = sorted(k); c = [k[d] for d in ds]
    if len(c) < OVL_MA + 20: raise RuntimeError("코스피200 종가 부족 %d" % len(c))
    inpos = False; ma = None
    for i in range(OVL_MA - 1, len(c)):
        ma = sum(c[i - OVL_MA + 1:i + 1]) / OVL_MA
        if not inpos and c[i] > ma * (1 + OVL_BAND / 100): inpos = True
        elif inpos and c[i] < ma * (1 - OVL_BAND / 100): inpos = False
    return inpos, ds[-1], c[-1], ma


def ovl_plan(S, ST):
    """오늘 아침 할 일 — None / ("BUY", 주수) / ("SELL", 포지션). 판정은 어제(직전 거래일) 종가까지."""
    inpos, d, c, ma = ovl_state()
    if S.get("prev") and d < S["prev"]:
        log("지수 덮개: 코스피200 종가가 묵음(%s < %s) — 오늘은 안 건드림" % (d, S["prev"])); return None, (inpos, d, c, ma)
    held = [p for p in (ST.get("positions") or []) if p.get("overlay") and not p.get("sell")]
    log("지수 덮개: 코스피200 %s 종가 %.2f · 60일선 %.2f(%+.1f%%) → %s · 보유 %d" % (d, c, ma, (c / ma - 1) * 100, "들어감" if inpos else "나옴", len(held)))
    if inpos and not held:
        return ("BUY", None), (inpos, d, c, ma)
    if not inpos and held:
        return ("SELL", held[0]), (inpos, d, c, ma)
    return None, (inpos, d, c, ma)


def ovl_place(plan, S, ST):
    """덮개 주문(시가 단일가 시장가) — 원장에 남기고 주문 dict 를 돌려준다. 체결 확인·사이트 기록은 ovl_record."""
    act, x = plan
    cid = re.sub(r"[^A-Za-z0-9_-]", "", f"ov{S['date']}{act[0]}")[:36]
    if act == "BUY":
        px = prices([OVL_SYM]).get(OVL_SYM)
        if not px: log("지수 덮개: 현재가 없음 — 안 삼"); return None
        tied = sum(float(p.get("price") or 0) * float(p.get("qty") or 0) for p in (ST.get("positions") or [])
                   if p.get("auto") and not p.get("sell") and mk_of(p.get("code")) == "KR")
        q = SWING_QTY or math.floor(OVL_W * max(SEED["KR"] - tied, 0) / px)
        if q < 1: log("지수 덮개: 살 돈 없음"); return None
    else:
        q = x["qty"]
    body = {"clientOrderId": cid, "symbol": OVL_SYM, "side": act, "orderType": "MARKET", "quantity": str(q), "timeInForce": "OPG"}
    o = dict(side=act, mk="KR", date=S["date"], rid=OVL_ID, t=OVL_SYM, name=OVL_NAME, qty=q, cid=cid, at=now().isoformat(), overlay=True)
    if act == "SELL": o["posId"] = x["id"]
    Lg = led()
    if any(z.get("cid") == cid and z.get("oid") for z in Lg["orders"]):
        log("지수 덮개: 오늘 주문 이미 나감"); return None
    try:
        o["oid"] = place(body)
    except TossErr as ex:
        o["oid"] = None; o["err"] = ex.code or str(ex)[:120]
        telegram("⚠ <b>[지수 덮개]</b> %s 주문 거부: %s" % ("매수" if act == "BUY" else "매도", o["err"]))
    Lg["orders"].append(o); led_save(Lg)
    log("지수 덮개 주문:", act, q, "주", o.get("oid"))
    return o if o.get("oid") else None


def ovl_record(o, S, info):
    if not o: return
    wait_fills([o])
    Lg = led()
    for z in Lg["orders"]:
        if z.get("cid") == o["cid"]: z.update({k: o[k] for k in ("fq", "ap", "status") if k in o})
    inpos, d, c, ma = info
    why = "코스피200 %s 종가 %s · 60일선 %s(%+.1f%%)" % (d[4:], f"{c:,.2f}", f"{ma:,.2f}", (c / ma - 1) * 100)
    if not (o.get("fq", 0) > 0 and o.get("ap", 0) > 0):
        led_save(Lg); telegram("❌ <b>[지수 덮개]</b> %s 미체결(%s) — %s" % ("매수" if o["side"] == "BUY" else "매도", o.get("status"), why)); return
    if o["side"] == "BUY":
        pos = {"id": int(time.time() * 1000), "code": OVL_SYM, "name": OVL_NAME, "date": S["date"], "price": o["ap"], "qty": int(o["fq"]),
               "filters": [OVL_ID], "auto": True, "overlay": True, "oid": o["oid"]}
        for z in Lg["orders"]:
            if z.get("cid") == o["cid"]: z["pos"] = pos                  # heal() 이 사이트에서 빠지면 되살린다
        led_save(Lg)
        site_update(lambda P: (P.append(dict(pos)) or True), "지수 덮개 매수")
        telegram("📈 <b>[지수 덮개] 매수</b> %s %d주 @ %s원 = %s\n%s" % (
            OVL_NAME, int(o["fq"]), f"{o['ap']:,.0f}", won(o["fq"] * o["ap"]), why))
    else:
        sold = {"sell": o["ap"], "sellDate": S["date"]}
        for z in Lg["orders"]:
            if z.get("cid") == o["cid"]: z["sold"] = sold
        led_save(Lg)

        def mark(P):
            for x in P:
                if x.get("id") == o["posId"] and not x.get("sell"): x.update(sold); return True
            return False
        site_update(mark, "지수 덮개 매도")
        bp_ = next((float(p["price"]) for p in (site_state().get("positions") or []) if p.get("id") == o["posId"]), None)
        r = (o["ap"] / bp_ - 1) * 100 if bp_ else float("nan")
        telegram("📉 <b>[지수 덮개] 매도</b> %s %d주 @ %s원 (%+.1f%%)\n%s" % (OVL_NAME, int(o["fq"]), f"{o['ap']:,.0f}", r, why))


def buy(mk):
    if not guard(): return
    S = session(mk)
    if not S:
        log(mk, "오늘 장 없음 — 건너뜀"); return
    n = now()
    if mk == "KR":
        if n >= S["start"]:
            log("국장 이미 개장 — 시가 매수 시각 지남, 건너뜀"); return
        at = max(n, S["open_auction"] + dt.timedelta(seconds=60))        # 장전 시가 단일가 접수 중(08:51)
    else:
        if S["start"] - dt.timedelta(minutes=70) <= n < S["start"]:
            at = S["start"] + dt.timedelta(seconds=60)
        elif S["start"] <= n < S["start"] + dt.timedelta(minutes=20):
            at = n
        else:
            log("미장 개장 %s 근처 아님 — 건너뜀" % S["start"].strftime("%m/%d %H:%M")); return
    heal()
    ovp = ovi = None                                                  # [지수 덮개] — 국장 아침마다 판정(스윙 신호와 무관)
    if mk == "KR":
        try: ovp, ovi = ovl_plan(S, site_state())
        except Exception as ex:
            log("지수 덮개 판정 실패:", repr(ex)[:200]); telegram("⚠ <b>[지수 덮개]</b> 판정 실패: %s" % str(ex)[:150])

    def ovl_alone():
        if not ovp: return
        sleep_until(at, "국장 장전 시가 단일가(지수 덮개)")
        o = ovl_place(ovp, S, site_state())
        if o:
            sleep_until(S["start"] + dt.timedelta(seconds=90), "지수 덮개 체결 확인"); ovl_record(o, S, ovi)
    F = filters_state()
    have = F.get("date") if mk == "KR" else F.get("usasof")
    stale = None
    if not have:
        stale = "신호 기준일을 모른다"
    elif S.get("prev") and have < S["prev"]:
        stale = "신호가 묵었다 — 신호 %s · 직전 거래일 %s" % (have, S["prev"])
    if stale:
        log(mk, "매수 안 함:", stale)
        telegram("⚠ <b>자동매매 %s 매수 안 함</b>\n%s — 묵은 신호" % ("국장" if mk == "KR" else "미장", stale))
        ovl_alone(); return
    R = rules()
    rank = {rid: i + 1 for i, rid in enumerate(sorted([r for r in R if (r[0] == "N") == (mk == "US")], key=lambda r: -R[r][2]))}
    Lg = led()
    today_keys = {f"{o['rid']}:{o['t']}" for o in Lg["orders"] if o.get("side") == "BUY" and o.get("date") == S["date"]}
    ST = site_state()
    C = candidates(mk, F, ST, R, rank, today_keys)
    if not C:
        log(mk, "살 것 없음 · 신호일", have); ovl_alone(); return
    syms = sorted({c[3] for c in C})
    nm = names(syms)
    fx = usdkrw() if mk == "US" else None
    # 시드: 자동매매가 이 시장에서 들고 있는 매수금(원) — 손으로 기록한 것·토스의 다른 보유분은 안 센다
    tied = sum(float(p.get("price") or 0) * float(p.get("qty") or 0) * ((float(p.get("fx") or fx or 0)) if mk == "US" else 1)
               for p in (ST.get("positions") or []) if p.get("auto") and not p.get("sell") and mk_of(p.get("code")) == mk)
    room = SEED[mk] - tied
    sleep_until(at, "국장 장전 시가 단일가" if mk == "KR" else "미장 개장+1분")
    px = prices(syms)
    if DRY: _dry_px.update(px)
    # 2026-10-06 사용자: 돈이 모자라면 1주씩만 산다(규칙이 제대로 도는지 보는 게 먼저) — 매수가능(그 시장 통화)을 들고 깎아 간다
    try: cash = buying_power("KRW" if mk == "KR" else "USD") if not DRY else float("inf")
    except TossErr as ex: cash = None; log("매수가능 조회 실패", ex)
    placed, skip, stop_reason = [], [], None
    for rk, stk, rid, t in C:
        info = nm.get(t, (t, None, None))
        if stop_reason:
            skip.append((rid, t, info[0], stop_reason)); continue
        if len(placed) >= MAXDAY[mk]:
            skip.append((rid, t, info[0], "하루 %d건 초과" % MAXDAY[mk])); continue
        if t not in px:
            skip.append((rid, t, info[0], "현재가 없음")); continue
        if info[1] not in (None, "ACTIVE") or info[2]:
            skip.append((rid, t, info[0], "거래 정지·비활성")); continue
        one = px[t] * (fx if mk == "US" else 1)                       # 1주 원화 값
        if SWING_QTY:
            q = SWING_QTY                                             # 테스트: 금액 상관없이 정해진 주수
        else:
            q = math.floor(PER[mk] / one)
            if q < 1 and one <= PER[mk] * 2:                         # 2026-10-03 사용자: 한 건 금액의 2배까지는 1주 산다
                q = 1
            if q < 1:
                skip.append((rid, t, info[0], "1주가 %s원 초과" % won(PER[mk] * 2))); continue
        if cash is not None and q * px[t] > cash:
            if px[t] > cash:
                skip.append((rid, t, info[0], "매수가능 부족(1주도 못 삼)")); continue
            log("매수가능 부족 — 1주만:", rid, t, "%d→1주" % q); q = 1
        cost = q * px[t] * (fx if mk == "US" else 1)
        if cost > room:
            skip.append((rid, t, info[0], "시드 %s 다 참" % won(SEED[mk]))); continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", f"ab{S['date']}{rid}{t}")[:36]
        body = {"clientOrderId": cid, "symbol": t, "side": "BUY", "orderType": "MARKET", "quantity": str(q)}
        if mk == "KR": body["timeInForce"] = "OPG"
        o = dict(side="BUY", mk=mk, date=S["date"], rid=rid, t=t, name=info[0], qty=q, cid=cid, at=now().isoformat(), ref=px[t])
        err = None
        try:
            o["oid"] = place(body)
        except TossErr as ex:
            err = ex
            if mk == "KR" and ex.code in ("order-hours-closed", "order-type-not-allowed"):
                # 장전 사전접수가 막히면 개장 직후 시장가로 — 시가 근처
                log("OPG 거절(%s) — 개장 직후 시장가로" % ex.code)
                sleep_until(S["start"] + dt.timedelta(seconds=20), "국장 개장 직후")
                body.pop("timeInForce", None); body["clientOrderId"] = (cid + "m")[:36]; o["cid"] = body["clientOrderId"]
                try:
                    o["oid"] = place(body); err = None
                except TossErr as ex2:
                    err = ex2
        if err is not None and err.code == "insufficient-buying-power" and q > 1:
            # 시장가는 토스가 현재가보다 넉넉히 잡아 둬서 미리 본 매수가능으론 모자랄 수 있다 → 1주로 한 번 더
            log("매수가능 부족 거절 — 1주로 다시:", rid, t)
            q = 1; body["quantity"] = "1"; body["clientOrderId"] = (body["clientOrderId"] + "o")[:36]
            o.update(qty=1, cid=body["clientOrderId"]); cost = px[t] * (fx if mk == "US" else 1)
            try:
                o["oid"] = place(body); err = None
            except TossErr as ex3:
                err = ex3
        if err is not None:
            o["oid"] = None; o["err"] = err.code or str(err)[:120]
            Lg["orders"].append(o); led_save(Lg)
            if err.code == "insufficient-buying-power" and cash is None:
                stop_reason = "매수가능 금액 부족"     # 남은 돈을 모를 때만 멈춘다 — 알면 더 싼 종목 1주는 계속 시도
            elif err.code == "insufficient-buying-power":
                cash = min(cash, px[t] * 0.999)             # 이 값 1주도 안 됐으니 이보다 비싼 건 건너뛴다
            skip.append((rid, t, info[0], "주문 거부 " + (err.code or str(err)[:60]))); continue
        Lg["orders"].append(o); led_save(Lg); placed.append(o); room -= cost
        if cash is not None: cash -= q * px[t]
        log("매수 주문:", mk, rid, t, q, "주")
        time.sleep(0.3)
    ov_o = None
    if ovp:
        try: ov_o = ovl_place(ovp, S, ST)
        except Exception as ex: log("지수 덮개 주문 실패:", repr(ex)[:200])
    if placed or ov_o:
        sleep_until((S["start"] + dt.timedelta(seconds=90)) if mk == "KR" else now() + dt.timedelta(seconds=15), "체결 확인")
    wait_fills(placed)
    if ov_o:
        try: ovl_record(ov_o, S, ovi)
        except Exception as ex: log("지수 덮개 기록 실패:", repr(ex)[:200])
    filled = []
    for o in placed:
        if o["fq"] > 0 and o["ap"] > 0:
            o["pos"] = {"id": int(time.time() * 1000) + len(filled), "code": o["t"], "name": o["name"], "date": S["date"], "price": o["ap"],
                        "qty": int(o["fq"]) if o["fq"] == int(o["fq"]) else o["fq"], "filters": [o["rid"]],
                        "fx": fx if mk == "US" else None, "auto": True, "oid": o["oid"]}
            filled.append(o)
    led_save(Lg)
    if filled:
        site_update(lambda P: (P.extend(dict(o["pos"]) for o in filled) or True), "%s 매수 %d건" % (mk, len(filled)))
    L = ["🤖 <b>자동매매 %s 매수</b> %s/%s" % ("국장" if mk == "KR" else "미장", S["date"][4:6], S["date"][6:])]
    for o in filled:
        if mk == "KR":
            L.append("✅ [%s] %s %d주 @ %s원 = %s" % (R[o["rid"]][0], o["name"], int(o["fq"]), f"{o['ap']:,.0f}", won(o["fq"] * o["ap"])))
        else:
            L.append("✅ [%s] %s(%s) %d주 @ $%s = $%s (≈%s)" % (R[o["rid"]][0], o["name"], o["t"], int(o["fq"]), f"{o['ap']:,.2f}", f"{o['fq']*o['ap']:,.0f}", won(o["fq"] * o["ap"] * fx)))
    for o in placed:
        if o not in filled:
            L.append("❌ [%s] %s 미체결(%s)" % (R[o["rid"]][0], o["name"], o.get("status")))
    if skip:
        L.append("못 산 것 %d건: " % len(skip) + " · ".join("[%s] %s(%s)" % (R[r][0] if r in R else r, n_, w) for r, t, n_, w in skip[:8]) + (" …" if len(skip) > 8 else ""))
    L.append("시드 %s 중 남은 %s" % (won(SEED[mk]), won(max(room, 0))))
    try:
        L.append("토스 매수가능 %s" % (won(buying_power("KRW")) if mk == "KR" else "$" + f"{buying_power('USD'):,.0f}"))
    except TossErr: pass
    telegram("\n".join(L))


# ── 매도 ───────────────────────────────────────────────────────────────
def held_days(sym, buy_date, sess_date):
    c = tget("/api/v1/candles", symbol=sym, interval="1d", count=200) or {}
    ds = {x["timestamp"][:10].replace("-", "") for x in c.get("candles", [])}
    ds.add(sess_date)
    return len([d for d in ds if buy_date <= d <= sess_date])


def sell(mk):
    if not guard(): return
    S = session(mk)
    if not S:
        log(mk, "오늘 장 없음 — 건너뜀"); return
    n = now()
    if mk == "KR":
        if not (S["close_auction"] - dt.timedelta(minutes=30) <= n < S["end"] - dt.timedelta(minutes=2)):
            log("국장 종가 단일가 근처 아님 — 건너뜀"); return
        at = max(n, S["close_auction"] + dt.timedelta(seconds=60))
    else:
        if not (S["end"] - dt.timedelta(minutes=50) <= n < S["end"] - dt.timedelta(minutes=12)):
            log("미장 마감 %s 50~12분 전 아님 — 건너뜀" % S["end"].strftime("%H:%M")); return
        at = n
    heal()
    R = rules()
    ST = site_state()
    mine = [p for p in (ST.get("positions") or []) if p.get("auto") and not p.get("sell") and not p.get("overlay") and mk_of(p.get("code")) == mk]   # 지수 덮개는 띠로 판다(ovl_*)
    due = []
    for p in mine:
        rid = (p.get("filters") or [None])[0]
        if rid not in R:
            log("규칙 모름 — 매도 판단 못함:", p["code"], rid); continue
        try: d = held_days(p["code"], str(p["date"]), S["date"])
        except TossErr as ex: log("보유일 계산 실패", p["code"], ex); continue
        log("보유", p["code"], rid, "%d/%d일" % (d, R[rid][1]) + (" (가상)" if p.get("paper") else ""))
        if d >= R[rid][1]: due.append((p, rid, d))
    if not due:
        log(mk, "오늘 팔 것 없음 (자동 보유 %d)" % len(mine)); return
    # 2026-10-16 사용자: 돈 없어 못 산 것을 '산 걸로' 넣은 가상 보유(paper)는 토스 주문 없이 그날 종가로 매도 기록만
    paper = [x for x in due if x[0].get("paper")]
    due = [x for x in due if not x[0].get("paper")]
    sleep_until(at, "국장 종가 단일가" if mk == "KR" else "미장 LOC 접수")
    Lg = led()
    done_ids = {o["posId"] for o in Lg["orders"] if o.get("side") == "SELL" and o.get("oid") and o.get("date") == S["date"]}
    due = [x for x in due if x[0]["id"] not in done_ids]
    if not due and not paper:          # 두 번째(지킴이) 실행 — 앞 실행이 이미 다 냈다
        log(mk, "매도 주문 이미 다 나감 — 지킴이 할 일 없음"); return
    px = prices(sorted({p["code"] for p, _, _ in due}))
    if DRY: _dry_px.update(px)
    placed, fail = [], []
    for p, rid, d in due:
        if p["id"] in done_ids: continue
        q = p["qty"]
        try:
            have = sellable(p["code"]) if not DRY else float(q)
        except TossErr as ex:
            have = None; log("매도가능 조회 실패", ex)
        if have is not None and have < float(q):
            fail.append((p, "매도가능 %s주 < 기록 %s주" % (have, q))); continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "", f"as{S['date']}{p['id']}")[:36]
        body = {"clientOrderId": cid, "symbol": p["code"], "side": "SELL", "quantity": str(q)}
        if mk == "KR":
            body["orderType"] = "MARKET"
        else:
            ref = px.get(p["code"], float(p["price"]))
            body.update(orderType="LIMIT", timeInForce="CLS", price="%.2f" % (math.floor(ref * 80) / 100))   # 현재가의 80% — 종가가 그 위면 종가 체결
        o = dict(side="SELL", mk=mk, date=S["date"], posId=p["id"], t=p["code"], name=p.get("name"), rid=rid, qty=q, cid=cid, at=now().isoformat(), days=d)
        try:
            o["oid"] = place(body)
        except TossErr as ex:
            o["oid"] = None; o["err"] = ex.code or str(ex)[:120]
            if mk == "US" and ex.code in ("order-type-not-allowed", "price-out-of-range", "invalid-request"):
                log("LOC 거절(%s) — 시장가로" % ex.code)
                body = {"clientOrderId": (cid + "m")[:36], "symbol": p["code"], "side": "SELL", "orderType": "MARKET", "quantity": str(q)}
                o["cid"] = body["clientOrderId"]
                try:
                    o["oid"] = place(body); o.pop("err", None)
                except TossErr as ex2:
                    o["err"] = ex2.code or str(ex2)[:120]
        Lg["orders"].append(o); led_save(Lg)
        if o.get("oid"): placed.append((o, p))
        else: fail.append((p, "주문 거부 " + str(o.get("err"))))
        time.sleep(0.3)
    if placed:
        sleep_until(S["end"] + dt.timedelta(seconds=90 if mk == "KR" else 150), "종가 체결 확인")
    wait_fills([o for o, _ in placed])
    fx = usdkrw() if mk == "US" else None
    sold = []
    for o, p in placed:
        if o["fq"] > 0 and o["ap"] > 0:
            o["sold"] = {"sell": o["ap"], "sellDate": S["date"]}
            if mk == "US": o["sold"]["sellFx"] = fx
            sold.append((o, p))
    led_save(Lg)
    if sold:
        ids = {o["posId"]: o["sold"] for o, _ in sold}

        def mark(P):
            ch = False
            for x in P:
                if x.get("id") in ids and not x.get("sell"):
                    x.update(ids[x["id"]]); ch = True
            return ch
        site_update(mark, "%s 매도 %d건" % (mk, len(sold)))
    L = ["🤖 <b>자동매매 %s 매도</b> %s/%s" % ("국장" if mk == "KR" else "미장", S["date"][4:6], S["date"][6:])]
    for o, p in sold:
        r = (o["ap"] / float(p["price"]) - 1) * 100
        bp_, sp_ = (f"{float(p['price']):,.0f}", f"{o['ap']:,.0f}") if mk == "KR" else ("$%.2f" % float(p["price"]), "$%.2f" % o["ap"])
        L.append("%s [%s] %s %d주 %s → %s (%+.1f%%, %d일)" % ("🔺" if r > 0 else "🔻", R[o["rid"]][0], p.get("name"), int(o["fq"]), bp_, sp_, r, o["days"]))
    sold_ids = {id(o) for o, _ in sold}
    for o, p in placed:
        if id(o) not in sold_ids:
            L.append("❌ %s 매도 미체결(%s)" % (p.get("name"), o.get("status")))
    for p, why in fail:
        L.append("⚠ %s 매도 실패: %s" % (p.get("name"), why))
    if paper:
        sleep_until(S["end"] + dt.timedelta(seconds=90 if mk == "KR" else 150), "가상 보유 종가 확인")
        ppx = prices(sorted({p["code"] for p, _, _ in paper}))
        upd = {p["id"]: ppx[p["code"]] for p, _, _ in paper if ppx.get(p["code"])}

        def pmark(P):
            ch = False
            for x in P:
                if x.get("id") in upd and not x.get("sell"):
                    x.update(sell=upd[x["id"]], sellDate=S["date"])
                    if mk == "US": x["sellFx"] = usdkrw()
                    ch = True
            return ch
        if upd and site_update(pmark, "%s 가상 매도 %d건" % (mk, len(upd))):     # 지킴이 두 번째 실행은 이미 팔려 있어 False → 알림 안 겹침
            for p, rid, d in paper:
                if p["id"] not in upd: continue
                r = (upd[p["id"]] / float(p["price"]) - 1) * 100
                L.append("🧾 [%s] %s %s주 %s → %s (%+.1f%%, %d일) 가상" % (
                    R[rid][0], p.get("name"), p["qty"], f"{float(p['price']):,.0f}", f"{upd[p['id']]:,.0f}", r, d))
        if len(L) == 1: return
    telegram("\n".join(L))


def paper_buy(mk, code, rid, day):
    """돈 없어 못 산 스윙 신호를 '그날 시가에 1주 산 걸로' 사이트에 넣는다(토스 주문 없음). 국장만 — 시가 = 1분봉 첫 체결 봉 시가(시가 단일가)."""
    import collect_m1 as M
    rows = sorted((r for r in M.fetch_day(mk, code, day) if r[6] > 0), key=lambda r: r[1])
    if not rows: raise RuntimeError("시가 못 찾음 %s %s" % (code, day))
    op = rows[0][2]
    nm = names([code]).get(code, (code,))[0]

    def add(P):
        if any(p.get("code") == code and str(p.get("date")) == day and p.get("paper") for p in P): return False
        P.append({"id": int(time.time() * 1000), "code": code, "name": nm, "date": day, "price": op, "qty": SWING_QTY or 1,
                  "filters": [rid], "auto": True, "paper": True})
        return True
    site_update(add, "가상 매수 %s %s [%s] %s원" % (nm, code, rid, f"{op:,.0f}"))
    log("가상 매수:", nm, code, rid, day, op)


# ── 점검 ───────────────────────────────────────────────────────────────
def check():
    log("모드", MODE, "· STOP" if (OUT / "STOP").exists() else "")
    log("계좌 seq", ACCT())
    for c in ("KRW", "USD"): log("매수가능", c, f"{buying_power(c):,.2f}")
    log("환율", usdkrw())
    for mk in ("KR", "US"):
        s = session(mk); log(mk, "세션", {k: (v.strftime("%m/%d %H:%M") if hasattr(v, "strftime") else v) for k, v in (s or {}).items()})
    F = filters_state()
    log("신호 기준일", F.get("date"), "미장", F.get("usasof"), "· 대기", {k: len(v) for k, v in (F.get("filters") or {}).items() if v})
    ST = site_state()
    log("보유", len([p for p in ST.get("positions") or [] if not p.get("sell")]), "· 자동", len([p for p in ST.get("positions") or [] if p.get("auto") and not p.get("sell")]))
    log("우선순위", {k: round(v[2], 3) for k, v in sorted(rules().items(), key=lambda x: -x[1][2])})


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    try:
        if a[:1] == ["check"]:
            check()
        elif a[:1] == ["paper"] and len(a) >= 5:          # python autotrade.py paper kr 298040 P6 20261016
            paper_buy(a[1].upper(), a[2], a[3], a[4])
        elif a[:1] in (["plan"], ["buy"], ["sell"]) and len(a) > 1 and a[1].lower() in ("kr", "us"):
            if MODE != "live" and not DRY:
                log("AUTOTRADE_MODE=%s — 주문하지 않는다(live 일 때만)" % MODE)
            elif a[0] == "sell":
                sell(a[1].upper())
            else:
                buy(a[1].upper())
        else:
            log("사용법: python autotrade.py check | plan kr|us | sell kr|us  [--dry] [--wait0]")
    except Exception as ex:
        log("실패:", repr(ex)[:500])
        telegram("⚠ <b>자동매매 실패</b>: %s" % (str(ex)[:300]))
        raise
