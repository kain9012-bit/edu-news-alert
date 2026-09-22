// 해외 IP를 막는 게시판을 대신 받아 주는 중계.
//
// 세종교육청은 GitHub Actions(미국)에서 접속이 아예 안 된다(2026-09-07부터 매일 실패).
// 이 함수는 vercel.json의 regions=["icn1"] 설정으로 서울에서 실행되므로 한국 IP를 쓴다.
// 수집기가 세종만 이 주소를 거쳐 받아 가면 차단을 피할 수 있다.
//
// 아무 주소나 받아 주면 공개 프록시가 되어 악용될 수 있으므로,
// 허용한 호스트와 경로로만 요청을 보낸다.

const ALLOWED = [
  { host: "www.sje.go.kr", prefix: "/sje/na/ntt/" }, // 세종 보도자료 목록·상세
];
const FETCH_TIMEOUT_MS = 20_000;
const MAX_BYTES = 3_000_000;

export const config = { maxDuration: 30 };

function allowed(target) {
  return ALLOWED.some(
    (rule) => target.hostname === rule.host && target.pathname.startsWith(rule.prefix),
  );
}

function text(body, status, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

export async function GET(request) {
  const url = new URL(request.url);
  const raw = url.searchParams.get("url");
  if (!raw) return text("url 쿼리 값이 필요합니다.", 400);

  let target;
  try {
    target = new URL(raw);
  } catch {
    return text("주소 형식이 올바르지 않습니다.", 400);
  }
  if (target.protocol !== "https:") return text("https만 허용합니다.", 400);
  if (!allowed(target)) return text(`허용되지 않은 주소입니다: ${target.hostname}`, 403);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const upstream = await fetch(target, {
      signal: controller.signal,
      redirect: "follow",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
      },
    });
    const body = await upstream.text();
    if (body.length > MAX_BYTES) return text("응답이 너무 큽니다.", 502);
    return new Response(body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Proxy-Region": process.env.VERCEL_REGION || "unknown",
      },
    });
  } catch (error) {
    return text(`가져오기 실패: ${error.name} ${error.message}`, 502);
  } finally {
    clearTimeout(timer);
  }
}
