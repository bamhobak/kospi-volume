# -*- coding: utf-8 -*-
"""수집 DB 매일 백업 — PC 가 죽어 SQLite 가 깨져도 하루치만 잃게 (2026-09-23).

왜: 2026-09-20~22 사흘간 PC 가 7번 비정상 종료됐고(블루스크린 1번은 덤프상 NVIDIA 드라이버
nvlddmkm 의 DPC 시간 초과), 그 여파로 data/toss.db(1.3GB)가 통째로 깨졌다("database disk image
is malformed" — 모든 테이블 읽기 실패). 9월 초에도 같은 일로 kis/market.db 인덱스가 깨졌었다
([[bsod-inca-driver]]). 백업이 없어서 매번 복구를 '시도' 해야 했다.

어떻게:
  · SQLite **백업 API**(sqlite3.Connection.backup)로 복사한다 — 파일 복사와 달리 쓰는 도중이어도
    일관된 사본이 나온다. 원본이 깨져 있으면 여기서 오류가 나므로 **손상 감지기** 역할도 한다.
  · D:\\kospi_backup\\YYYYMMDD\\ 에 두고 **최근 2일치**만 남긴다 — 깨진 날의 사본이 멀쩡한
    사본을 덮어쓰지 않게.
  · 원본과 다른 드라이브(D:)에 둔다.

    python backup_dbs.py            # 전부
    python backup_dbs.py --keep 3
종료코드: 0 전부 성공 · 1 하나라도 실패(깨졌을 수 있다)
"""
import io, os, shutil, sqlite3, sys, time
from pathlib import Path

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):                      # pythonw(예약 작업)에서는 None 이다
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
KEEP = int(arg("--keep", "2"))
DEST = Path(arg("--to", r"D:\kospi_backup"))
# 다시 받기 어렵거나 오래 걸리는 것만. 패널 pkl·캐시는 원본에서 다시 만들 수 있어 뺀다.
DBS = ["data/kospi.db", "data/kosdaq.db", "data/kis/market.db", "data/krx_daily.db", "data/investor.db",
       "data/toss.db", "data/index_members.db", "data/feargreed.db", "data/delisted.db", "data/delisted_kd.db",
       "data/dart/disclosures.db", "data/dart/insider.db", "data/dart/financials.db", "data/dart/shares.db",
       "data/us/tiingo_dead.db"]


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def main():
    day = DEST / time.strftime("%Y%m%d")
    day.mkdir(parents=True, exist_ok=True)
    fail, t0, tot = [], time.time(), 0
    for rel in DBS:
        src = BASE / rel
        if not src.exists():
            continue
        dst = day / rel.replace("/", "__")
        tmp = dst.with_suffix(".tmp")
        t = time.time()
        try:
            s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=600)
            d = sqlite3.connect(tmp)
            s.backup(d, pages=20000)
            d.close(); s.close()
            os.replace(tmp, dst)
            sz = dst.stat().st_size / 1e9
            tot += sz
            log(f"  ✓ {rel} {sz:.2f}GB ({time.time() - t:.0f}초)")
        except Exception as e:
            fail.append(rel)
            log(f"  ✗ {rel} 실패 — {str(e)[:80]}  (원본이 깨졌을 수 있다)")
            try: tmp.unlink()
            except Exception: pass
    # 오래된 세대 지우기 — 날짜 폴더만, 최근 KEEP 개 남김
    olds = sorted([p for p in DEST.iterdir() if p.is_dir() and p.name.isdigit()])[:-KEEP]
    for p in olds:
        shutil.rmtree(p, ignore_errors=True)
    log(f"백업 끝 → {day} · {tot:.1f}GB · {(time.time() - t0) / 60:.1f}분 · 실패 {len(fail)}"
        + (f" ({', '.join(fail)})" if fail else "") + (f" · 옛 세대 {len(olds)}개 정리" if olds else ""))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
