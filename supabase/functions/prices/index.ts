// 장중 시세·지수 수집 (Edge Function)
//
// 왜 서버에서 받아야 하나: 네이버 시세 API 는 브라우저 출처를 보고 403 을 준다.
// (polling.finance.naver.com · m.stock.naver.com · api.stock.naver.com 모두 실측 403)
// 그래서 페이지가 직접 못 받고, 이 함수가 대신 받아 __prices__ 에 저장한 뒤 돌려준다.
//
// 호출 경로
//   1) 웹사이트 — 페이지를 열 때와 열어둔 동안 10분마다
//   2) (추후) Supabase 크론 — PC·브라우저가 꺼져 있어도 알림이 나가도록
//
// prices.py 와 저장 형식이 같아야 한다(화면이 그대로 읽는다):
//   { updated, prices: { <코드>: {now,open,high,low,chg,vol,at,status} },
//     index: { kospi|kosdaq: {now,chg,pct,at,status} } }

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const NAVER = { "User-Agent": "Mozilla/5.0" };

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

/** "11,340" → 11340, 빈값/하이픈 → null */
const num = (s: unknown): number | null => {
  if (s === null || s === undefined) return null;
  const t = String(s).replace(/,/g, "").trim();
  if (!t || t === "-") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

async function rpc(fn: string, body: unknown) {
  const r = await fetch(`${SB_URL}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${fn} ${r.status} ${(await r.text()).slice(0, 120)}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

/** 네이버 실시간 — 종목/지수 공용 */
async function naver(path: string) {
  const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/${path}`, {
    headers: NAVER,
  });
  if (!r.ok) throw new Error(`naver ${path} ${r.status}`);
  const j = await r.json();
  const d = j?.datas?.[0];
  if (!d) throw new Error(`naver ${path} 빈 응답`);
  return d;
}

/** KST 'YYYY-MM-DD HH:MM' */
function kstStamp(): string {
  const k = new Date(Date.now() + 9 * 3600 * 1000);
  return k.toISOString().slice(0, 16).replace("T", " ");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const t0 = Date.now();
  try {
    // 1) 보유 종목 코드 (모든 PIN, 미매도)
    const positions = (await rpc("kospi_state_positions", {})) ?? [];
    const codes = [...new Set(positions.map((p: any) => p.code).filter(Boolean))] as string[];

    // 2) 종목 시세 — 동시에, 실패한 종목은 건너뛴다
    const prices: Record<string, unknown> = {};
    await Promise.all(codes.map(async (c) => {
      try {
        const d = await naver(`stock/${c}`);
        prices[c] = {
          now: num(d.closePrice), open: num(d.openPrice), high: num(d.highPrice),
          low: num(d.lowPrice), chg: num(d.compareToPreviousClosePrice),
          vol: num(d.accumulatedTradingVolume),
          at: d.localTradedAt ?? "", status: d.marketStatus ?? "",
        };
      } catch (e) {
        console.error("종목 실패", c, String(e).slice(0, 100));
      }
    }));

    // 3) 코스피·코스닥 지수 (화면 배지용 — 규칙 판정에는 쓰지 않는다. 규칙은 종가 기준)
    const index: Record<string, unknown> = {};
    await Promise.all([["kospi", "KOSPI"], ["kosdaq", "KOSDAQ"]].map(async ([key, code]) => {
      try {
        const d = await naver(`index/${code}`);
        index[key] = {
          now: num(d.closePrice), chg: num(d.compareToPreviousClosePrice),
          pct: num(d.fluctuationsRatio), at: d.localTradedAt ?? "", status: d.marketStatus ?? "",
        };
      } catch (e) {
        console.error("지수 실패", code, String(e).slice(0, 100));
      }
    }));

    // 4) 저장 — 종목도 지수도 다 실패했으면 기존 값을 덮어쓰지 않는다
    const payload = { updated: kstStamp(), prices, index };
    if (Object.keys(prices).length || Object.keys(index).length) {
      await rpc("kospi_state_set", { p_pin: "__prices__", p_data: payload });
    }

    return new Response(JSON.stringify({
      ...payload,
      _meta: { codes: codes.length, ok: Object.keys(prices).length, ms: Date.now() - t0 },
    }), { headers: { ...CORS, "Content-Type": "application/json" } });
  } catch (e) {
    console.error(e);
    return new Response(JSON.stringify({ error: String(e).slice(0, 300) }), {
      status: 500, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
