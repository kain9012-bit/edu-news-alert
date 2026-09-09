// 방문 수(오늘·누적)를 GoatCounter API에서 읽어 60초 캐시로 돌려줍니다.
// 공개 카운터(counter/*.json)는 최대 4시간 캐시라 오늘 수치가 늦게 반영되므로,
// 토큰을 쓰는 서버 함수로 읽습니다. 토큰이 없으면 화면이 공개 카운터로 대체합니다.
const SITE = (process.env.GOATCOUNTER_SITE || "https://jbe-edu-trends.goatcounter.com").replace(/\/+$/, "");
const TOKEN = process.env.GOATCOUNTER_API_TOKEN;
const SINCE = "2026-01-01T00:00:00Z"; // 누적의 시작(사이트 개설 전이면 됨)
const CACHE_MS = 60_000;

let cached = null;
let cachedAt = 0;

// 오늘 0시(한국 시간)를 UTC로. 예: 9/9 00:00 KST = 9/8 15:00 UTC
function todayUtc(now = new Date()) {
  const kst = new Date(now.getTime() + 9 * 3600_000);
  const midnight = Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate());
  return new Date(midnight - 9 * 3600_000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function total(start) {
  const url = new URL(`${SITE}/api/v0/stats/total`);
  url.searchParams.set("start", start);
  url.searchParams.set("include_paths", "/"); // '/' 경로 = 사람 수
  url.searchParams.set("path_by_name", "true");
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
  });
  if (!response.ok) throw new Error(`goatcounter ${response.status}`);
  return Number((await response.json()).total ?? 0);
}

function json(body, status = 200, cacheSeconds = 0) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": cacheSeconds
        ? `public, s-maxage=${cacheSeconds}, stale-while-revalidate=300`
        : "no-store",
    },
  });
}

export async function GET() {
  if (!TOKEN) return json({ error: "GOATCOUNTER_API_TOKEN이 없습니다." }, 503);
  if (cached && Date.now() - cachedAt < CACHE_MS) return json(cached, 200, 60);
  try {
    const [all, today] = await Promise.all([total(SINCE), total(todayUtc())]);
    cached = { total: all, today, updatedAt: new Date().toISOString() };
    cachedAt = Date.now();
    return json(cached, 200, 60);
  } catch (error) {
    return json({ error: error.message }, 502);
  }
}
