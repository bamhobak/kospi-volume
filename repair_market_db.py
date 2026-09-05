# -*- coding: utf-8 -*-
"""data/kis/market.db 재구축 — 블루스크린으로 깨진 인덱스를 데이터 손실 없이 복구한다.

배경: 2026-09-05 잉카인터넷 필터 드라이버(TKFsFt64.sys)가 대량 파일 입출력에서 블루스크린을
      두 번 내면서 SQLite 쓰기가 중간에 끊겼다. 깨진 곳은 인덱스 ix_credit_t(Tree 9) 하나이고
      credit 테이블 본체는 519만 행 전체 스캔이 통과한다. 그런데 DROP INDEX 도 페이지 검사에
      걸려 실패하므로, 읽을 수 있는 데이터를 새 파일로 옮겨 다시 만든다.
사용: python repair_market_db.py
"""
import shutil, sqlite3, sys, time
from pathlib import Path

BASE = Path(__file__).parent
SRC = BASE / "data" / "kis" / "market.db"
NEW = BASE / "data" / "kis" / "market_rebuilt.db"
sys.stdout.reconfigure(encoding="utf-8")
t0 = time.time()
def log(m): print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

if NEW.exists(): NEW.unlink()
src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=1800)
dst = sqlite3.connect(NEW, timeout=1800)
dst.execute("PRAGMA journal_mode=OFF")      # 재구축 중엔 저널 필요 없다(끝나고 검증한다)
dst.execute("PRAGMA synchronous=OFF")

# 원본 스키마 그대로 (인덱스는 데이터를 다 넣은 뒤에 만든다)
schema = [r for r in src.execute(
    "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")]
tables = [(n, s) for t, n, s in schema if t == "table"]
indexes = [(n, s) for t, n, s in schema if t == "index"]
log(f"테이블 {len(tables)}개 · 인덱스 {len(indexes)}개")

for name, sql in tables:
    dst.execute(sql)
    cols = [r[1] for r in src.execute(f"PRAGMA table_info({name})")]
    ph = ",".join("?" * len(cols))
    n = 0
    cur = src.execute(f"SELECT {','.join(cols)} FROM {name} NOT INDEXED")
    while True:
        rows = cur.fetchmany(50000)
        if not rows: break
        dst.executemany(f"INSERT OR IGNORE INTO {name} VALUES({ph})", rows)
        n += len(rows)
        if n % 500000 == 0: log(f"  {name} {n:,}행"); dst.commit()
    dst.commit()
    log(f"  {name} 완료 {n:,}행")

for name, sql in indexes:
    log(f"인덱스 {name} 생성"); dst.execute(sql); dst.commit()

log("무결성 검사")
r = dst.execute("PRAGMA integrity_check(5)").fetchall()
log(f"  {r}")
ok = (r and r[0][0] == "ok")
summary = {}
for name, _ in tables:
    try:
        a = src.execute(f"SELECT count(*) FROM {name} NOT INDEXED").fetchone()[0]
    except Exception: a = -1
    b = dst.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    summary[name] = (a, b)
    log(f"  {name}: 원본 {a:,} → 새 파일 {b:,}")
src.close(); dst.close()

if not ok:
    log("⚠ 무결성 검사 실패 — 교체하지 않는다. 새 파일은 market_rebuilt.db 로 남겨 둔다.")
    sys.exit(1)
bak = SRC.with_suffix(".db.broken")
if bak.exists(): bak.unlink()
shutil.move(str(SRC), str(bak))
shutil.move(str(NEW), str(SRC))
log(f"교체 완료 · 손상본은 {bak.name} 로 남겨 둠(확인 후 지울 것)")
