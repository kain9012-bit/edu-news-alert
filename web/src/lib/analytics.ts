// GoatCounter 이벤트 전송.
//
// 페이지뷰는 index.html에서 경로를 '/' 하나로 통일해 보낸다(= 사람 수).
// 탭별로 얼마나 보는지는 여기서 '이벤트'로 따로 보낸다. 이벤트는 대시보드
// Pages 목록에 별도 줄로 쌓이고 방문자 수와 섞이지 않으므로, 사람 수를
// 부풀리지 않으면서 탭 인기도를 볼 수 있다.

type GoatCounter = {
  count?: (vars: { path: string; title?: string; event?: boolean }) => void;
};

declare global {
  interface Window {
    goatcounter?: GoatCounter;
  }
}

const TAB_TITLES: Record<string, string> = {
  reports: "오늘의 교육동향",
  archive: "전국 보도자료",
  coverage: "전북 언론 게재현황",
};

// 같은 방문에서 같은 탭을 여러 번 오가도 한 번만 보낸다.
const sent = new Set<string>();

export function countTabEvent(tab: string): void {
  if (!tab || sent.has(tab)) return;
  sent.add(tab);

  let tries = 0;
  const send = () => {
    if (typeof window.goatcounter?.count === "function") {
      window.goatcounter.count({
        path: `tab-${tab}`,
        title: TAB_TITLES[tab] || tab,
        event: true,
      });
      return;
    }
    // count.js가 async라 늦게 올 수 있어 최대 10초까지 기다린다.
    if (tries++ < 40) setTimeout(send, 250);
  };
  send();
}
