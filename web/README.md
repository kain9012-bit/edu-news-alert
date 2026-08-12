# 오늘의 교육동향 · 교육 보도자료 아카이브 (웹)

'오늘의 교육동향' 지난 호와 전국 시도교육청·교육부의 전체 수집 보도자료를 한곳에서 보는 웹앱입니다.
데이터는 별도 저장소(`edu-news-alert`)가 GitHub Pages로 공개하는 JSON을 그대로 사용하며(별도 DB·서버 없음), UI는 KRDS(대한민국 디지털 정부 디자인시스템)를 따릅니다.

## 스택
- Vite + React 19 + TypeScript
- Tailwind CSS v4 + KRDS 색 토큰 / Pretendard 서체

## 로컬 실행
```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # 정적 산출물 dist/
```

## 데이터 소스
`src/lib/data.ts`가 아래 파일들을 불러옵니다(기본 주소는 `VITE_DATA_BASE`, 미설정 시 코드 기본값).
- `reports/index.json`, `reports/<날짜>.json` — 오늘의 교육동향 지난 호
- `news.json` — 전체 수집 보도자료
- `briefings/<날짜>.json` — 교육동향 선정 여부

주소를 바꾸려면 `.env` 에 `VITE_DATA_BASE`를 지정하세요(`.env.example` 참고).

## Vercel 배포
1. 이 폴더를 새 GitHub 저장소로 push
2. Vercel에서 該 저장소를 Import → 프레임워크는 **Vite** 자동 감지
   - Build Command: `npm run build`, Output Directory: `dist`
3. (선택) 환경변수 `VITE_DATA_BASE` 설정
