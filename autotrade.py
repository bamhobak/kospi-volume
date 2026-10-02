# -*- coding: utf-8 -*-
"""토스 자동매매 — 1단계 **알림만**(실제 주문 없음) · 2026-10-03 시작.

사용자 결정(2026-10-03): 규칙마다 300만원씩 · 총 한도 3억 · 하루 최대 국장 5건·미장 5건.
단계: ① 알림만(이 파일) → ② 텔레그램 확인 후 주문 → ③ 자동 주문. AUTOTRADE_MODE(.env)로 바꾼다 — 지금은 notify 만 있다.

무엇을 사나: 사이트 '매수 대기'와 같은 목록 — notify_new.py 가 매 수집 뒤 Supabase '__filters__' 에 저장하는
  규칙별 신호(그 규칙으로 아직 안 산 종목). 우선순위는 사이트와 같은 '하루당 기대수익'(index.html stats.avg ÷ hold).
언제:
  국장  python autotrade.py plan kr   — 장 열리는 날 08:35 (09:00 시가 단일가 = 백테스트 '다음날 시가')
  미장  python autotrade.py plan us   — 21:50·22:50 둘 다 걸어 두면 **개장 60분 전 안**일 때만 돈다(서머타임 자동)
  점검  python autotrade.py check     — 토큰·계좌·매수가능금액·장 운영 시간만 본다
나중 주문 방식(문서 확인 2026-10-03):
  국장 매수 MARKET+OPG(장전 사전접수 → 시가 단일가) · 국장 매도 15:20~15:30 MARKET(종가 단일가)
  미장 매수 개장 직후 MARKET+orderAmount(달러) · 미장 매도 LIMIT+CLS(LOC, 낮은 지정가 → 종가)
⚠ 토큰은 키당 1개만 산다 — collect_toss.py 와 같은 캐시(toss.token)를 쓴다. 따로 받으면 서로를 끊는다.
⚠ 허용 IP 밖에서 부르면 403 — 그때는 지금 공인 IP 를 텔레그램으로 알린다.
⚠ 예약작업(pythonw)은 sys.stdout 이 None — print 대신 log() 로 파일에 쓴다.
"""
import csv, datetime as dt, json, math, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "data" / "autotrade"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:                     # 콘솔(cp949)에서 한글이 깨지지 않게 — pythonw 면 None 이라 건드리지 않는다
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

BUDGET = 300_000_000          # 총 한도(원) — 보유 중 매수금액 합 + 오늘 살 것
PER = 3_000_000               # 규칙 하나당
MAXDAY = {"KR": 5, "US": 5}   # 하루 최대 건수
KST = dt.timezone(dt.timedelta(hours=9))


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass
    if sys.stdout is not None:
        try:
            print(s, flush=True)
        except Exception:
            pass


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
    tok, chat = E.get("TELEGRAM_BOT_TOKEN"), E.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        log("텔레그램 미설정:", text.replace("\n", " | ")); return
    try:
        body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
        rq = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(rq, timeout=30).read()
    except Exception as ex:
        log("텔레그램 실패:", repr(ex)[:200])


# ── 토스 ───────────────────────────────────────────────────────────────
import toss


class TossErr(Exception):
    pass


def tget(path, acct=False, **q):
    u = toss.B + path + ("?" + urllib.parse.urlencode(q) if q else "")
    for att in range(2):
        h = {"Authorization": "Bearer " + toss.token(), "Accept": "application/json"}
        if acct:
            h["X-Tossinvest-Account"] = ACCT()
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=20).read().decode())
            return d.get("result", d)
        except urllib.error.HTTPError as ex:
            body = ex.read().decode(errors="replace")[:300]
            if ex.code == 401 and att == 0:              # 다른 프로세스가 새 토큰을 받아 이전 것이 죽은 경우
                toss._TOK.update(v=None, exp=0)
                try: (BASE / "data" / ".toss_token.json").unlink()
                except Exception: pass
                continue
            if ex.code == 403:
                ip = "?"
                try: ip = urllib.request.urlopen("https://ifconfig.me/ip", timeout=10).read().decode().strip()
                except Exception: pass
                raise TossErr("403 차단 — 허용 IP 밖일 수 있다(지금 공인 IP %s). 토스 웹 설정 > Open API > 허용 IP 관리에 추가할 것" % ip)
            raise TossErr("HTTP %d %s %s" % (ex.code, path, body))
    raise TossErr("토큰 재발급 뒤에도 401")


_acct = {}
def ACCT():
    if "v" not in _acct:
        h = {"Authorization": "Bearer " + toss.token(), "Accept": "application/json"}
        d = json.loads(urllib.request.urlopen(urllib.request.Request(toss.B + "/api/v1/accounts", headers=h), timeout=20).read().decode())
        L = [a for a in d.get("result", []) if a.get("accountType") == "BROKERAGE"] or d.get("result", [])
        if not L:
            raise TossErr("계좌가 없다")
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


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ── 사이트 쪽(규칙 신호·보유·우선순위) ─────────────────────────────────
def supa():
    import requests
    js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    H = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    pin = re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)
    rpc = lambda fn, b: requests.post(f"{url}/rest/v1/rpc/{fn}", headers=H, json=b, timeout=20).json() or {}
    return rpc("kospi_state_get", {"p_pin": "__filters__"}), rpc("kospi_state_get", {"p_pin": pin})


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
    return "KR" if re.fullmatch(r"[0-9A-Z]{6}", t) and any(c.isdigit() for c in t[:2]) else "US"


# ── 계획 ───────────────────────────────────────────────────────────────
def plan(mk):
    now = dt.datetime.now(KST)
    cal = tget("/api/v1/market-calendar/" + mk)
    if mk == "KR":
        today = (cal.get("today") or {}).get("integrated")
        if not today:
            log("국장 휴장 — 건너뜀"); return
        open_at = ts(today["regularMarket"]["startTime"])
        want = cal["previousBusinessDay"]["date"].replace("-", "")
    else:
        rm = (cal.get("today") or {}).get("regularMarket")
        if not rm:
            log("미장 휴장 — 건너뜀"); return
        open_at = ts(rm["startTime"])
        want = cal["previousBusinessDay"]["date"].replace("-", "")
        if not (open_at - dt.timedelta(minutes=60) <= now < open_at):
            log("미장 개장 %s 60분 전 구간 아님 — 건너뜀" % open_at.strftime("%H:%M")); return
    F, ST = supa()
    have = F.get("date") if mk == "KR" else F.get("usasof")
    stale = None
    if not have:
        stale = "신호 기준일을 모른다(__filters__ 에 %s 없음)" % ("date" if mk == "KR" else "usasof")
    elif have < want:
        stale = "신호가 묵었다 — 신호 %s · 직전 거래일 %s (수집 실패?)" % (have, want)
    R = rules()
    rank = {rid: i + 1 for i, rid in enumerate(sorted([r for r in R if (r[0] == "N") == (mk == "US")], key=lambda r: -R[r][2]))}
    pos = [p for p in (ST.get("positions") or []) if p and p.get("code") and not p.get("sell")]
    held_by = {}
    for p in pos:
        held_by.setdefault(p["code"], set()).update(str(f) for f in (p.get("filters") or []))
    try:
        fx = usdkrw()
    except TossErr:
        fx = 1400.0
    tied = sum(float(p.get("price") or 0) * float(p.get("qty") or 0) * (fx if mk_of(p["code"]) == "US" else 1) for p in pos)
    streak = F.get("streaks") or {}
    cand = []
    for rid, ts_ in (F.get("filters") or {}).items():
        for t in ts_:
            if mk_of(t) != mk or rid not in R or rid in held_by.get(t, set()):
                continue
            cand.append((rank.get(rid, 99), streak.get(f"{rid}:{t}", 1), rid, t))
    cand.sort()
    syms = sorted({c[3] for c in cand})
    px = prices(syms) if syms else {}
    nm = names(syms) if syms else {}
    left = BUDGET - tied
    buy, skip = [], []
    for rk, stk, rid, t in cand:
        why = None
        info = nm.get(t, (t, None, None))
        if t not in px:
            why = "현재가 없음"
        elif info[1] not in (None, "ACTIVE") or info[2]:
            why = "거래 정지·비활성"
        elif len(buy) >= MAXDAY[mk]:
            why = "하루 %d건 초과" % MAXDAY[mk]
        elif left < PER:
            why = "총 한도 3억 도달"
        if mk == "KR" and not why:
            q = math.floor(PER / px[t])
            if q < 1:
                why = "1주 가격이 300만원 초과"
        if why:
            skip.append((rid, t, info[0], why)); continue
        if mk == "KR":
            q = math.floor(PER / px[t]); amt = q * px[t]
            buy.append(dict(rid=rid, t=t, name=info[0], qty=q, px=px[t], krw=amt, usd=None, rank=rk, streak=stk))
        else:
            usd = math.floor(PER / fx * 100) / 100
            buy.append(dict(rid=rid, t=t, name=info[0], qty=round(usd / px[t], 4), px=px[t], krw=usd * fx, usd=usd, rank=rk, streak=stk))
        left -= PER
    try:
        bp = buying_power("KRW" if mk == "KR" else "USD")
    except TossErr as ex:
        bp = None; log("매수가능금액 실패:", ex)
    need = sum(b["usd"] if mk == "US" else b["krw"] for b in buy)
    # 기록
    f = OUT / "plan.csv"; new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["실행시각", "모드", "시장", "장시작", "결과", "규칙", "종목", "이름", "수량", "기준가", "원화", "달러", "우선", "연속일", "사유"])
        for b in buy:
            w.writerow([now.strftime("%Y-%m-%d %H:%M"), MODE, mk, open_at.strftime("%Y-%m-%d %H:%M"), "살 것", b["rid"], b["t"], b["name"], b["qty"], b["px"], round(b["krw"]), b["usd"], b["rank"], b["streak"], ""])
        for rid, t, n, why in skip:
            w.writerow([now.strftime("%Y-%m-%d %H:%M"), MODE, mk, open_at.strftime("%Y-%m-%d %H:%M"), "넘김", rid, t, n, "", px.get(t), "", "", rank.get(rid), "", why])
    log("%s 계획: 살 것 %d · 넘김 %d · 한도 남음 %s원 · 보유 매수금 %s원 · 신호일 %s%s" % (
        mk, len(buy), len(skip), f"{left:,.0f}", f"{tied:,.0f}", have, (" · ⚠ " + stale) if stale else ""))
    # 알림 — 살 것·넘긴 것·경고가 있을 때만
    if not (buy or skip or stale):
        return
    def won(v):
        v = round(v / 1e4)                       # 만원 단위
        return (f"{v // 10000}억" + (f" {v % 10000:,}만" if v % 10000 else "")) if v >= 10000 else f"{v:,}만"
    head = "🧪 <b>자동매매 [알림만 · 실제 주문 없음]</b>"
    when = ("국장 %s 09:00 시가" % open_at.strftime("%m/%d")) if mk == "KR" else ("미장 %s 개장(%s) 직후 시장가" % (open_at.strftime("%m/%d"), open_at.strftime("%H:%M")))
    L = [head, "%s 매수 예정 <b>%d건</b>" % (when, len(buy))]
    for i, b in enumerate(buy, 1):
        rn = R[b["rid"]][0]
        if mk == "KR":
            L.append("%d. [%s] %s(%s) %d주 ≈ %s" % (i, rn, b["name"], b["t"], b["qty"], won(b["krw"])))
        else:
            L.append("%d. [%s] %s(%s) $%s ≈ %s (약 %.2f주)" % (i, rn, b["name"], b["t"], f"{b['usd']:,.2f}", won(b["krw"]), b["qty"]))
    if skip:
        L.append("넘김 %d건: " % len(skip) + " · ".join("[%s] %s(%s)" % (R[r][0] if r in R else r, n, why) for r, t, n, why in skip[:8]) + (" …" if len(skip) > 8 else ""))
    L.append("한도: 보유 %s + 오늘 %s / 3억 · 남음 %s" % (won(tied), won(sum(b['krw'] for b in buy)), won(max(left, 0))))
    if bp is not None:
        ok = bp >= need
        L.append("토스 매수가능 %s %s" % ((won(bp) if mk == "KR" else "$" + f"{bp:,.0f}"), "✅" if ok else "⚠ 부족(필요 %s)" % (won(need) if mk == "KR" else "$" + f"{need:,.0f}")))
    if stale:
        L.append("⚠ " + stale + " — 실제 주문 단계였다면 오늘은 사지 않는다")
    telegram("\n".join(L))


def check():
    log("모드", MODE)
    log("계좌 seq", ACCT())
    for c in ("KRW", "USD"):
        log("매수가능", c, f"{buying_power(c):,.2f}")
    log("환율", usdkrw())
    for mk in ("KR", "US"):
        c = tget("/api/v1/market-calendar/" + mk)
        log(mk, "오늘", json.dumps(c.get("today"), ensure_ascii=False)[:200])
    F, ST = supa()
    log("신호 기준일", F.get("date"), "미장", F.get("usasof"), "· 대기", {k: len(v) for k, v in (F.get("filters") or {}).items() if v})
    log("보유", len([p for p in ST.get("positions") or [] if not p.get("sell")]))
    log("우선순위", {k: round(v[2], 3) for k, v in sorted(rules().items(), key=lambda x: -x[1][2])})


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["check"]:
            check()
        elif a[:1] == ["plan"] and len(a) > 1 and a[1].lower() in ("kr", "us"):
            if MODE != "notify":
                raise SystemExit("AUTOTRADE_MODE=%s — 아직 알림만(notify) 단계만 있다" % MODE)
            plan(a[1].upper())
        else:
            log("사용법: python autotrade.py check | plan kr | plan us")
    except Exception as ex:
        log("실패:", repr(ex)[:500])
        telegram("⚠ 자동매매 [알림만] 실패: %s" % (str(ex)[:300]))
        raise
