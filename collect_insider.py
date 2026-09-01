# -*- coding: utf-8 -*-
"""임원·주요주주 특정증권등 소유상황보고서 본문에서 실제 매매내역을 뽑는다.

공시 메타데이터에는 '누가 언제 신고했나' 만 있다. 방향(장내매수/장내매도)과 수량·단가는
문서 안에 있다. 문서의 마지막 표(보고사유·변동일·증감·단가)를 파싱해 DB 에 쌓는다.

보고사유가 중요하다 — 신규선임·증여·상속·스톡옵션행사는 실제 매수가 아니다.
장내매수/장내매도만 골라야 신호가 된다.

재개 가능: 이미 받은 rcept_no 는 done 테이블에 남기고 건너뛴다.
DART 일일 한도 20,000콜 → 10.9만건이면 약 6일. 하루치를 다 쓰면 스스로 멈춘다.
"""
import io, os, re, sqlite3, sys, time, zipfile, logging
from pathlib import Path
import requests

BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(BASE/"insider_collect.log", encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger()
ENV = dict(l.split("=",1) for l in (BASE/".env").read_text(encoding="utf-8").strip().splitlines() if "=" in l)
KEY = ENV["DART_API_KEY"].strip()
SRC = BASE/"data"/"dart"/"disclosures.db"
DST = BASE/"data"/"dart"/"insider.db"
DAILY_CAP = int(os.environ.get("DART_CAP", "18000"))     # 여유 두고 18,000

def setup():
    c = sqlite3.connect(DST)
    c.executescript("""
    create table if not exists tx(
      rcept_no text, ticker text, corp_name text, rcept_dt text, reporter text,
      reason text, reason_cd text, chg_dt text, kind text, before_qty integer, delta integer,
      after_qty integer, price integer);
    create index if not exists ix_tx_tk on tx(ticker, chg_dt);
    create table if not exists done(rcept_no text primary key, status text, n integer);
    """); c.commit(); return c

def NUM(s):
    """숫자만 남겨 정수로. '1-2' 같은 변칙 표기나 자릿수 폭주는 None 으로 흘린다
       (예외를 던지면 문서 전체가 실패 처리돼 재시도 없이 유실된다)."""
    if not s or not re.search(r"[0-9]", s): return None
    t = re.sub(r"[^0-9-]", "", s)
    t = ("-" if t.startswith("-") else "") + t.replace("-", "")
    try:
        v = int(t)
        return v if abs(v) < 10**15 else None
    except (ValueError, OverflowError):
        return None
CELL = re.compile(r"<T[UE]([^>]*)>(.*?)</T[UE]>", re.S)
ATTR = lambda a, k: (re.search(k + r'="([^"]*)"', a) or [None, None])[1]
TXT  = lambda v: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", v).replace("&cr;", " ")).strip()

def parse(rcept_no, xml):
    """행마다 ACODE/AUNIT 속성으로 값을 뽑는다.
       위치(몇 번째 칸)가 아니라 속성 이름으로 읽으므로 연도별 서식 변화에 안전하다.
         AUNIT=RPT_RSN 보고사유(AUNITVALUE=코드) · MDF_DM 변동일(AUNITVALUE=YYYYMMDD)
         ACODE=BFR_STK_CNT 변동전 · MDF_STK_CNT 증감 · AFR_STK_CNT 변동후 · ACI_AMT2 단가"""
    rows = []
    for tr in re.findall(r"<TR.*?</TR>", xml, re.S):
        f = {}
        for a, v in CELL.findall(tr):
            code = ATTR(a, "ACODE") or ATTR(a, "AUNIT")
            if not code: continue
            f[code] = (TXT(v), ATTR(a, "AUNITVALUE"))
        if "MDF_STK_CNT" not in f or "RPT_RSN" not in f: continue
        dt = (f.get("MDF_DM") or ("", None))[1] or ""
        if not re.fullmatch(r"\d{8}", dt):
            m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", (f.get("MDF_DM") or ("",))[0])
            dt = f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else None
        rows.append(dict(reason=f["RPT_RSN"][0], reason_cd=f["RPT_RSN"][1], chg_dt=dt,
                         kind=(f.get("STR_KND") or ("",))[0],
                         before_qty=NUM((f.get("BFR_STK_CNT") or ("",))[0]),
                         delta=NUM(f["MDF_STK_CNT"][0]),
                         after_qty=NUM((f.get("AFR_STK_CNT") or ("",))[0]),
                         price=NUM((f.get("ACI_AMT2") or ("",))[0])))
    return rows

def main():
    c = setup()
    done = {r[0] for r in c.execute("select rcept_no from done")}
    src = sqlite3.connect(SRC)
    todo = [r for r in src.execute(
        """select rcept_no, stock_code, corp_name, rcept_dt, flr_nm from disclosure
           where report_nm like '%임원%소유상황%' and length(stock_code)=6
           order by rcept_dt""") if r[0] not in done]
    log.info(f"남은 문서 {len(todo):,}건 (완료 {len(done):,}건) · 이번 실행 상한 {DAILY_CAP:,}")
    s = requests.Session(); n_ok = n_row = n_err = 0
    for i, (rno, tk, nm, dt, who) in enumerate(todo[:DAILY_CAP]):
        try:
            r = s.get("https://opendart.fss.or.kr/api/document.xml",
                      params={"crtfc_key": KEY, "rcept_no": rno}, timeout=30)
            if r.content[:2] != b"PK":
                c.execute("insert or replace into done values(?,?,?)", (rno, "nozip", 0)); n_err += 1
                if b"limit" in r.content.lower() or b"020" in r.content[:200]:
                    log.warning(f"한도 도달로 보임 — 중단: {r.text[:120]}"); break
            else:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                raw = z.read(z.namelist()[0])
                try: xml = raw.decode("euc-kr")
                except UnicodeDecodeError: xml = raw.decode("utf-8", "ignore")
                rows = parse(rno, xml)
                c.executemany("insert into tx values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              [(rno, tk, nm, dt, who, x["reason"], x["reason_cd"], x["chg_dt"], x["kind"],
                                x["before_qty"], x["delta"], x["after_qty"], x["price"]) for x in rows])
                c.execute("insert or replace into done values(?,?,?)", (rno, "ok", len(rows)))
                n_ok += 1; n_row += len(rows)
        except Exception as e:
            n_err += 1   # done 에 안 남긴다 → 다음 실행에서 재시도
        if i % 200 == 0:
            c.commit(); log.info(f"  {i:,}/{min(len(todo),DAILY_CAP):,} · 성공 {n_ok:,} · 행 {n_row:,} · 실패 {n_err}")
        time.sleep(0.06)
    c.commit()
    log.info(f"종료 — 성공 {n_ok:,} · 추출 {n_row:,}행 · 실패 {n_err} · 누적완료 {len(done)+n_ok:,}/{len(done)+len(todo):,}")
main()
