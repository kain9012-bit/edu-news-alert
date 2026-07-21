# 교육동향 보도자료 선별 AI Agent 하네스

교육부와 16개 시도교육청 본청 보도자료를 평일 오전 6시 5분에 수집하고, Gemini가 교육행정 담당자에게 의미 있는 교육동향을 선별·분류하는 AI Agent 하네스입니다. 최근 자료는 Chrome·Edge 사이드바에서 확인할 수 있으며, 선별 결과는 별도의 비공개 하네스에서 요약·분석·전북교육 적용 검토를 거쳐 HTML·HWPX 내부 보고서로 생성할 수 있습니다.

## 하네스 주제와 목적

교육청 보도자료에는 광역 정책 변화뿐 아니라 개별 학교 행사, 기관 방문, 수상 소식처럼 교육동향으로 보기 어려운 자료도 섞여 있습니다. 이 프로젝트는 먼저 업무에 참고할 자료만 선별하고, 공개 대시보드와 비공개 내부 보고서가 동일한 선별 결과를 각 목적에 맞게 사용하도록 구성합니다.

수집기는 게시글 본문 영역만 추출하고, 실제 보도자료가 첨부파일에만 있는 경우 HWP·HWPX·PDF·DOCX 문서에서 본문을 읽습니다. 메뉴·첨부 안내 같은 페이지 문구와 제목 중복을 제거한 뒤 HTML 본문과 첨부 본문 중 품질이 더 높은 내용을 사용합니다.

- 주제: 전국 교육청 보도자료 기반 평일 교육동향 선별
- 목적: 반복적인 보도자료 확인을 줄이고 정책·제도·사업 변화를 빠르게 찾기
- AI: 선별·사실정리·검증은 `gemini-3.1-flash-lite`, 내부 동향분석·적용 검토는 `gemini-3.5-flash`
- 원칙: 원문과 AI 판정을 분리하고 모든 판정에 원문 `newsId` 연결
- 자동화: GitHub Actions가 수집부터 AI 선별, 검증, Pages 배포까지 실행

## 전체 구조

```mermaid
flowchart LR
    A[입력: 해당 분석 기간 보도자료] --> B[적합성 판별 Agent]
    B -->|KEEP| C[유형 분류 Agent]
    B -->|DROP + 사유| D[제외 목록]
    C --> E[선별 결과 검증 Agent]
    D --> E
    E -->|PASS| F[공개 교육동향 목록]
    E -->|REVISE| G[검토 필요 상태와 오류 기록]
    F --> H[GitHub Pages·브라우저 사이드바]
    F --> I[전북·교육지원청 자료 사전 제외]
    I --> J[사실정리 Agent]
    J --> K[동향분석·적용검토 Agent]
    K --> L[근거 검증 Agent]
    L -->|PASS| M[기준 JSON]
    M --> N[HTML·HWPX]
    N --> O[비공개 Actions 결과 파일 14일 보관]
```

## 에이전트 역할

1. **적합성 판별 Agent**: 각 보도자료를 `KEEP` 또는 `DROP`으로 판정합니다. 특정 교육지원청이 작성 주체로 드러나는 자료는 LLM 판단 전에 규칙으로 모두 제외합니다. 본청 정책, 여러 학교에 적용되는 사업, 광역적 파급력이 있는 변화는 남기고 개별 직속기관·학교의 일회성 행사·방문·수상과 개인의 인사발령·정기인사 명단 등은 제외합니다. 인사제도나 인사정책 자체의 변경은 선별 대상입니다.
2. **유형 분류 Agent**: `KEEP` 자료만 정책·행정, 교육과정·수업, 디지털·AI, 학생지원·복지, 교원·인사, 안전·시설, 진로·직업교육, 지역협력·행사, 기타로 분류합니다. 중요도는 사업 규모가 아니라 `통상 운영 → 사업 변화 → 정책 변화 → 제도 변화`를 먼저 판정한 뒤 1~5점으로 평가합니다. 통상적인 시설공사·예산 집행은 금액과 대상 학교 수가 커도 최대 2점이며, 사업 변화는 최대 3점, 정책 변화는 최대 4점입니다.
3. **선별 결과 검증 Agent**: 모든 후보가 판정됐는지, `KEEP` 자료만 분류됐는지, 교육지원청 자료가 최종 목록에 남지 않았는지, 중요도가 변화 수준별 상한과 1~5점 범위를 지켰는지, 중요도 근거가 기록됐는지, 중복·누락과 잘못된 근거 ID가 없는지 검사합니다.
4. **사실정리 Agent**: 전북교육청 자료를 제외한 선정 원문에서 내용 요약 1~5개와 후속 분석에 필요한 근거 사실을 추출합니다. 원문에 없는 정보나 긴 복사는 허용하지 않습니다.
5. **동향분석 Agent**: 검증된 사실만 받아 교육동향 분석 1~5개와 전북교육 적용 검토 0~5개를 작성합니다. 부서를 지정하거나 확정된 업무 지시처럼 표현하지 않습니다.
6. **내부 보고서 검증 Agent**: 원문과 요약·분석·적용 검토를 대조해 근거 없는 숫자·기관·성과, 반복, 과장, 부서 지정, 장문 복사를 검사합니다. 통과하지 못한 항목은 배포본에서 제외합니다.

Gemini 응답은 단계별 JSON 계약으로 검사합니다. 계약을 어기면 재시도하고 계속 실패하면 규칙 기반 대체 판정을 사용합니다. 대체 처리 건수, 검증 결과, 단계별 실행 시간과 Gemini 토큰 사용량은 최종 결과에 기록됩니다.

## 입력과 출력

입력은 수집기가 만든 `public/latest.json`입니다.

```json
{
  "windowStart": "2026-07-14T08:00:00+09:00",
  "windowEnd": "2026-07-15T08:00:00+09:00",
  "items": [
    {
      "id": "policy-1",
      "source": "전북특별자치도교육청",
      "title": "AI 기반 수업 지원 정책 전면 시행",
      "summary": "도내 전체 학교를 대상으로 지원한다.",
      "url": "https://example.com/policy-1"
    }
  ]
}
```

최종 JSON의 주요 결과는 다음과 같습니다.

```json
{
  "metadata": {
    "candidateCount": 2,
    "relevantCount": 1,
    "filteredOutCount": 1,
    "validationStatus": "PASS"
  },
  "categorySummary": [{ "category": "디지털·AI", "count": 1 }],
  "selectedItems": [
    {
      "newsId": "policy-1",
      "category": "디지털·AI",
      "changeLevel": "system_change",
      "importance": 5,
      "importanceReason": "전체 학교에 의무 적용되는 제도 변화다.",
      "selectionReason": "전체 학교에 적용되는 정책 변화다."
    }
  ],
  "excludedItems": [
    {
      "newsId": "event-1",
      "reason": "개별 학교의 일회성 행사다."
    }
  ]
}
```

사이드바는 중요도를 `★★★★★` 형식으로 표시하며 5점부터 내림차순으로 정렬합니다. 같은 점수에서는 최신 보도자료가 먼저 표시됩니다.

해당 분석 기간에 자료가 없는 날도 오류로 중단하지 않고 0건짜리 정상 브리핑을 발행합니다.

생성 파일:

- `public/briefings/latest.json`: 사이드바가 읽는 최신 AI 선별 결과
- `public/briefings/latest.md`: 사람이 읽을 수 있는 카테고리별 목록
- `public/briefings/YYYY-MM-DD.json`: 날짜별 구조화 결과
- `public/briefings/runs/<runId>.json`: 판별·분류·검증·실행 기록

내부 보고서는 `public`에 저장하거나 Git 기록에 커밋하지 않습니다. 비공개 저장소 [`kain9012-bit/edu-news-alert-private-reports`](https://github.com/kain9012-bit/edu-news-alert-private-reports)가 최신 공개 선별 결과를 받아 다음 세 파일을 동일한 기준 JSON에서 생성합니다.

- `오늘의 교육동향 (YYYYMMDD).json`: 검증된 기준 데이터와 모델·토큰·예상 비용 기록
- `오늘의 교육동향 (YYYYMMDD).html`: 기본 배포본
- `오늘의 교육동향 (YYYYMMDD).hwpx`: 한글 문서 배포본

세 파일은 비공개 GitHub Actions 결과 파일 `daily-education-trend-report`로 묶어 14일간만 보관하며, 동시에 HTML·HWPX를 텔레그램으로 발송해 PC를 켜지 않아도 휴대폰에서 확인하고 배포할 수 있습니다. Gmail은 사용하지 않습니다. Windows 자동 수신기가 GitHub의 결과 목록과 JSON 검증 상태를 확인한 뒤 지정 폴더에 내려받으며, 보관 기한이 지나면 GitHub에서 자동으로 삭제됩니다.
## 텔레그램 발송

내부 보고서 생성이 끝나면 `harness/notify_telegram.py`가 HTML과 HWPX를 텔레그램 문서로 보냅니다. HTML에는 기준일, 교육동향 건수, 검증 상태와 제목 목록이 설명으로 붙습니다. 휴대폰에서 내용을 확인한 뒤 HTML 파일을 그대로 메신저로 전달해 배포할 수 있습니다.

비공개 저장소 `Settings` → `Secrets and variables` → `Actions`에 다음 두 Secret을 등록합니다.

- `TELEGRAM_BOT_TOKEN`: BotFather에서 `/newbot`으로 만든 봇 토큰
- `TELEGRAM_CHAT_ID`: 봇과 대화를 시작한 뒤 `https://api.telegram.org/bot<토큰>/getUpdates`의 `message.chat.id` 값

두 Secret이 없으면 발송 단계는 건너뛰고 나머지 절차는 그대로 진행합니다. 토큰과 대화 ID는 저장소 파일과 로그에 남지 않습니다.

## Gemini API 설정

GitHub 저장소의 `Settings` → `Secrets and variables` → `Actions`에 다음 Repository secret을 등록합니다.

- 이름: `GEMINI_API_KEY`
- 값: Google AI Studio에서 발급받은 API 키

API 키는 저장소 파일, 로그, 브라우저 확장 프로그램에 포함되지 않습니다. GitHub Actions 환경변수로만 전달됩니다. 내부 보고서용 비공개 저장소에도 같은 이름의 Secret을 별도로 한 번 등록해야 합니다. GitHub는 다른 저장소의 Secret 값을 복사하거나 공개하지 않습니다.

## Windows 자동 수신기

`local_downloader`는 Gmail이나 브라우저를 거치지 않고 비공개 GitHub Actions 결과 파일을 내려받는 Windows 전용 도구입니다. GitHub 토큰은 Windows 현재 사용자만 복호화할 수 있도록 DPAPI로 보호해 `%LOCALAPPDATA%\EduNewsAlertDownloader`에 저장합니다.

기본 저장 위치:

```text
C:\Users\kain9\Documents\오늘의 교육동향\YYYY-MM-DD\
  오늘의 교육동향 (YYYYMMDD).json
  오늘의 교육동향 (YYYYMMDD).html
  오늘의 교육동향 (YYYYMMDD).hwpx
```

자동 수신 규칙:

- 배포는 텔레그램으로 끝나므로 수신기는 원본 보관용이며, 출근 시각에 맞춰 평일 오전 9시 10분부터 9시 50분까지 5분 간격으로 확인
- 받지 못했으면 오전 10시부터 11시까지 10분 간격으로 다시 확인
- 예약 작업에 놓친 실행 따라잡기를 적용해 부팅·절전 해제가 늦어도 복귀 즉시 실행
- Windows 로그인 시 최근 14일 동안 받지 못한 평일 보고서 확인
- 토·일요일에는 자동 확인 중단
- GitHub 결과 파일 ID와 보고서 JSON의 날짜·고유번호·검증 상태 확인
- 검증된 JSON·HTML·HWPX가 모두 있을 때만 날짜별 폴더에 저장
- 이미 받은 결과는 다시 내려받지 않고, 로컬 파일이 삭제된 경우에는 복구
- Gmail, SMTP, IMAP과 Gmail 앱 비밀번호를 사용하지 않음

로컬 수신기에는 비공개 저장소의 Actions 결과를 읽을 수 있는 GitHub fine-grained personal access token을 한 번 등록합니다.

1. GitHub `Settings → Developer settings → Personal access tokens → Fine-grained tokens`에서 새 토큰을 만듭니다.
2. `Repository access`에서 `Only select repositories`를 선택하고 `edu-news-alert-private-reports`만 지정합니다.
3. `Repository permissions`의 `Actions`를 `Read-only`로 지정합니다.
4. 생성된 토큰을 자동 수신기의 `Actions 읽기 토큰`에 입력합니다.

실행 파일은 다음 명령으로 빌드합니다.

```powershell
python local_downloader\build_exe.py
```

빌드 결과인 `local_downloader\dist\오늘의 교육동향 자동 수신기.exe`를 열고 저장소, Actions 읽기 토큰, 저장 위치를 확인합니다. `연결 확인` 후 `설정 저장`을 누르면 실행 파일을 `%LOCALAPPDATA%\Programs\EduNewsAlertDownloader`에 복사하고 오전 9시 10분·10시 반복 예약 작업과 현재 사용자 로그인 시작 항목을 등록합니다. `지금 확인`은 요일과 시간에 관계없이 최근 보고서를 즉시 확인합니다.
## 로컬 실행

Python 3.11 이상에서 다음 명령으로 실행합니다. 로컬 PowerShell에도 `GEMINI_API_KEY` 환경변수가 있어야 합니다.

```powershell
python -m pip install -r requirements.txt
$env:GEMINI_API_KEY = "발급받은 키"
.\run_harness.ps1
```

소량으로 구조를 시험할 수 있습니다.

```powershell
.\run_harness.ps1 -MaxItems 6
python -m unittest discover -s tests -v
```

이미 선별된 최신 자료로 내부 보고서를 로컬에서 생성하려면 다음 명령을 사용합니다. 결과는 공개 경로가 아닌 `.artifacts/daily-report`에 생성됩니다.

```powershell
python -m harness.report_run
```
비공개 저장소의 `Run workflow`에서 `report_date`에 `2026-07-17`처럼 기준일을 입력하면 최근 14일 안의 날짜별 선별 결과와 원문으로 보고서를 다시 생성할 수 있습니다. 날짜가 비어 있으면 기존 평일 자동 실행 규칙을 사용합니다.

Ollama를 비상용 로컬 제공자로 실행하려면 다음처럼 지정합니다.

```powershell
.\run_harness.ps1 -Provider ollama -Model exaone3.5:7.8b
```

## 수집과 저장

GitHub Actions는 한국시간 월요일부터 금요일까지 오전 6시 5분에 실행됩니다. 수집 기준 시각은 오전 6시이며, 월요일에는 금요일 오전 6시부터 월요일 오전 6시까지 72시간, 화요일부터 금요일에는 전날 오전 6시부터 당일 오전 6시까지 24시간의 보도자료를 수집·선별합니다. 토요일과 일요일에는 자동 실행하지 않습니다. 중복 자료는 저장하지 않고 `public/news.json`에는 최근 14일 자료만 유지합니다.

`crawler/sources.json`에는 교육부와 16개 시도교육청의 본청 게시판 17개가 등록되어 있습니다.

- 전북특별자치도교육청: [`BBS_0000222`](https://news.jbe.go.kr/board/list.jbe?boardId=BBS_0000222&menuCd=DOM_000001201001000000&contentsSid=2105&cpath=)만 수집
- 전남광주통합특별시교육청: [`S1N1`](https://www.jngjedu.kr/news/articleList.html?sc_section_code=S1N1&view_type=sm)만 수집
- 두 기관의 직속기관·교육지원청·학교 게시판은 수집하지 않음
- 인천광역시교육청의 묶음 보도자료는 개별 보도자료로 분리 저장

수동 실행은 저장소의 `Actions` → `Collect education press releases` → `Run workflow`에서 시작합니다. 수동 실행도 가장 최근 오전 6시를 종료 시점으로 삼아 월요일 72시간, 그 밖의 평일 24시간 규칙을 적용합니다. 워크플로가 결과를 저장하려면 `Workflow permissions`가 `Read and write permissions`여야 합니다.

## 확장 프로그램

1. Chrome의 `chrome://extensions` 또는 Edge의 `edge://extensions`를 엽니다.
2. 개발자 모드를 켭니다.
3. `extension` 폴더를 압축해제된 확장 프로그램으로 불러옵니다.
4. 확장 프로그램 아이콘 또는 `Ctrl+Shift+Y`로 사이드바를 엽니다.

AI 선별 결과가 있으면 사이드바는 `KEEP` 자료만 목록의 기반으로 사용합니다. 저장된 관심 키워드가 있으면 그 목록을 먼저 관심 자료로 추리고, 검색창은 관심 자료 목록 안에서 제목과 내용을 다시 검색합니다. 관심 키워드를 모두 지우면 AI가 선별한 전체 교육동향을 검색합니다. AI 실행 결과가 없으면 해당 분석 기간의 수집 자료를 그대로 사용하는 안전한 대체 동작을 합니다.

`이전 보도자료 기간 조회`에서는 최근 14일 자료를 날짜·기관·검색어·관심 키워드로 조회할 수 있습니다. 단축키는 `chrome://extensions/shortcuts` 또는 `edge://extensions/shortcuts`에서 바꿀 수 있습니다.

## 저장소 구성

```text
crawler/                 보도자료 수집·정제
harness/                 AI Agent와 오케스트레이터
  agents/                적합성·분류·검증 Agent
  reporting/             내부 보고서 사실정리·분석·검증·출력
  contracts/             단계별 JSON 계약
  prompts/               Gemini 역할 프롬프트
extension/               Chrome·Edge 사이드바
local_downloader/        GitHub Actions 결과 Windows 자동 수신기
public/                  GitHub Pages 데이터
tests/                   하네스 자동 테스트와 예시 입력
.github/workflows/       평일 수집·AI 선별·Pages 배포
```

프로그램의 동작, 수집 대상, 저장 정책 또는 하네스 구조가 바뀌면 이 README도 같은 변경에서 함께 갱신합니다.
