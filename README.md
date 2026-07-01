# 교육청 보도자료 키워드 알리미

교육부와 시도교육청 보도자료를 GitHub Actions로 수집하고, GitHub Pages의 JSON을 크롬 확장 프로그램이 확인해 사용자가 등록한 키워드에 맞는 새 보도자료를 알려주는 1차 버전입니다.

## 1차 범위

- 수집 대상: 교육부, 전북특별자치도교육청, 서울특별시교육청, 경기도교육청, 부산광역시교육청
- 저장 방식: `public/news.json` 최근 7일 보존
- 배포 방식: GitHub Pages
- 알림 방식: 크롬 확장 프로그램 알림

## 데이터 파일

- `public/news.json`: 최근 보도자료 목록
- `public/latest.json`: 최근 수집 요약
- `public/sources.json`: 수집 대상 기관 목록
- `public/status.json`: 마지막 수집 상태

## 자동 수집

`.github/workflows/collect-news.yml`이 매시간 실행됩니다. GitHub Pages는 Actions 배포 방식으로 `public/` 폴더를 게시합니다.
