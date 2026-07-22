from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any


WEEKDAYS = "월화수목금토일"


def report_date_label(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        return f"{parsed.year}. {parsed.month}. {parsed.day}. ({WEEKDAYS[parsed.weekday()]})"
    except ValueError:
        return value[:10]


def period_label(metadata: dict[str, Any]) -> str:
    start = str(metadata.get("windowStart") or "")
    end = str(metadata.get("windowEnd") or "")
    if not start or not end:
        return ""
    try:
        start_at = datetime.fromisoformat(start)
        end_at = datetime.fromisoformat(end)
        return (
            f"{start_at.year}. {start_at.month}. {start_at.day}. {start_at:%H:%M} ~ "
            f"{end_at.year}. {end_at.month}. {end_at.day}. {end_at:%H:%M}"
        )
    except ValueError:
        return f"{start.replace('T', ' ')} ~ {end.replace('T', ' ')}"


def importance_stars(value: Any) -> str:
    score = value if isinstance(value, int) and not isinstance(value, bool) else 1
    score = max(1, min(5, score))
    return f"{'★' * score}{'☆' * (5 - score)}"


def _points_html(points: list[str], empty_text: str | None = None) -> str:
    if not points:
        return f'<p class="empty-note">{html.escape(empty_text or "해당 사항 없음")}</p>'
    return "<ul>" + "".join(f"<li>{html.escape(point)}</li>" for point in points) + "</ul>"


def render_html(report: dict[str, Any]) -> str:
    metadata = report["metadata"]
    items = report.get("items", [])
    toc = "".join(
        f'<li><a href="#item-{index}"><span>{index}.</span> {html.escape(item.get("title", ""))}</a></li>'
        for index, item in enumerate(items, 1)
    )
    articles: list[str] = []
    for index, item in enumerate(items, 1):
        url = html.escape(str(item.get("url", "")), quote=True)
        source_link = (
            f'<a class="source-link" href="{url}" target="_blank" rel="noopener noreferrer">원문 보도자료</a>'
            if url
            else ""
        )
        articles.append(
            f'''<article id="item-{index}">
  <div class="article-number">{index:02d}</div>
  <div class="article-head">
    <p class="eyebrow">{html.escape(str(item.get("source", "")))} · {html.escape(str(item.get("category", "")))}</p>
    <h2>{html.escape(str(item.get("title", "")))}</h2>
    <div class="article-meta">
      <span class="stars" aria-label="중요도 {int(item.get('importance', 1))}점">{importance_stars(item.get("importance"))}</span>
      <span>{html.escape(str(item.get("date", "")))}</span>
      {source_link}
    </div>
  </div>
  <section class="report-section summary">
    <h3>내용 요약</h3>
    {_points_html(item.get("summaryPoints", []))}
  </section>
  <section class="report-section analysis">
    <h3>교육동향 분석</h3>
    {_points_html(item.get("analysisPoints", []))}
  </section>
  <section class="report-section application">
    <h3>전북교육 적용 검토</h3>
    {_points_html(item.get("applicationReviewPoints", []), "직접 적용 검토사항 없음")}
  </section>
</article>'''
        )
    empty_state = "" if items else '<p class="empty-report">검증을 통과한 교육동향이 없습니다.</p>'
    omitted_count = int(metadata.get("omittedCount", 0))
    omission_note = (
        f'<p class="omission-note">AI 근거 검증 또는 원문 품질 검사를 통과하지 못한 {omitted_count}건은 배포본에서 제외되었습니다.</p>'
        if omitted_count
        else ""
    )
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(str(metadata.get("title", "오늘의 교육동향")))} {html.escape(report_date_label(metadata.get("windowEnd")))}</title>
<style>
:root {{ color-scheme: light; --ink:#17202a; --muted:#5d6875; --line:#d7dde3; --teal:#087f73; --teal-soft:#e9f6f3; --amber:#a96800; --amber-soft:#fff6df; --paper:#ffffff; --page:#eef1f3; }}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; background:var(--page); color:var(--ink); font-family:"Pretendard","Noto Sans KR","Malgun Gothic",sans-serif; line-height:1.72; letter-spacing:0; }}
a {{ color:inherit; }}
.report {{ width:min(960px,100%); margin:0 auto; background:var(--paper); min-height:100vh; box-shadow:0 0 28px rgba(18,31,43,.08); }}
header {{ padding:52px 64px 40px; border-top:7px solid var(--teal); border-bottom:1px solid var(--line); }}
.kicker {{ margin:0 0 8px; color:var(--teal); font-weight:700; font-size:14px; }}
h1 {{ margin:0; font-family:"Nanum Myeongjo","Batang",serif; font-size:42px; line-height:1.25; letter-spacing:0; }}
.report-date {{ margin:16px 0 0; font-size:18px; font-weight:700; }}
.period {{ margin:4px 0 0; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
.summary-strip {{ display:flex; gap:24px; padding:18px 64px; border-bottom:1px solid var(--line); font-size:14px; color:var(--muted); }}
.summary-strip strong {{ color:var(--ink); margin-left:5px; }}
nav {{ padding:34px 64px 44px; border-bottom:1px solid var(--line); }}
nav h2 {{ margin:0 0 15px; font-size:18px; }}
nav ol {{ columns:2; column-gap:40px; margin:0; padding:0; list-style:none; }}
nav li {{ break-inside:avoid; margin:0 0 10px; font-size:14px; line-height:1.45; }}
nav a {{ text-decoration:none; }}
nav a:hover {{ color:var(--teal); text-decoration:underline; }}
nav li span {{ color:var(--teal); font-weight:800; margin-right:5px; }}
article {{ position:relative; padding:52px 64px 58px; border-bottom:10px solid var(--page); scroll-margin-top:12px; }}
.article-number {{ position:absolute; top:51px; left:19px; color:#9aa5af; font-size:13px; font-weight:800; }}
.eyebrow {{ margin:0 0 8px; color:var(--teal); font-size:13px; font-weight:800; }}
.article-head h2 {{ margin:0; font-size:25px; line-height:1.45; letter-spacing:0; overflow-wrap:anywhere; }}
.article-meta {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-top:14px; color:var(--muted); font-size:13px; }}
.stars {{ color:var(--amber); letter-spacing:0; font-size:17px; }}
.source-link {{ color:var(--teal); font-weight:700; text-underline-offset:3px; }}
.report-section {{ margin-top:34px; padding-top:22px; border-top:1px solid var(--line); }}
.report-section h3 {{ margin:0 0 12px; font-size:16px; }}
ul {{ margin:0; padding-left:1.35em; }}
li {{ margin:7px 0; padding-left:3px; }}
.application {{ border-top-color:#ead9b3; }}
.application h3 {{ color:#805200; }}
.empty-note {{ margin:0; color:var(--muted); }}
.empty-report {{ padding:70px 64px; text-align:center; color:var(--muted); }}
.omission-note {{ margin:0; padding:18px 64px; background:var(--amber-soft); color:#664408; font-size:13px; }}
footer {{ padding:34px 64px 50px; color:var(--muted); font-size:12px; }}
footer p {{ margin:4px 0; }}
@media (max-width:700px) {{
  header, nav, article, footer {{ padding-left:24px; padding-right:24px; }}
  h1 {{ font-size:34px; }}
  .summary-strip {{ padding-left:24px; padding-right:24px; gap:12px; flex-wrap:wrap; }}
  nav ol {{ columns:1; }}
  .article-number {{ position:static; margin-bottom:10px; }}
  .article-head h2 {{ font-size:21px; }}
  .omission-note {{ padding-left:24px; padding-right:24px; }}
}}
.toolbar {{ position:fixed; top:18px; right:18px; z-index:50; display:flex; gap:8px; }}
.toolbar button {{ display:inline-flex; align-items:center; gap:6px; padding:9px 14px; border:1px solid var(--teal); border-radius:8px; background:var(--teal); color:#fff; font:inherit; font-size:13px; font-weight:700; cursor:pointer; box-shadow:0 2px 8px rgba(18,31,43,.16); }}
.toolbar button.secondary {{ background:#fff; color:var(--teal); }}
.toolbar button:hover {{ opacity:.92; }}
@media (max-width:700px) {{ .toolbar {{ top:10px; right:10px; }} .toolbar button {{ padding:8px 11px; font-size:12px; }} }}
@media print {{
  @page {{ margin:0; }}
  .toolbar {{ display:none !important; }}
  body {{ background:#fff; }} .report {{ width:100%; box-shadow:none; }}
  header {{ padding-top:24mm; }}
  article {{ break-before:page; border-bottom:0; padding-top:18mm; padding-bottom:16mm; }}
  article:first-of-type {{ break-before:auto; }} nav a {{ text-decoration:none; }}
  footer {{ padding-bottom:18mm; }}
}}
</style>
</head>
<body>
<div class="toolbar" role="toolbar" aria-label="문서 도구">
  <button type="button" class="secondary" onclick="window.print()" title="인쇄 대화상자를 엽니다">🖨 인쇄</button>
  <button type="button" onclick="window.print()" title="인쇄 대화상자에서 '대상'을 'PDF로 저장'으로 선택하세요">📄 PDF 저장</button>
</div>
<main class="report">
<header>
  <p class="kicker">전국 교육정책 및 교육행정 동향</p>
  <h1>{html.escape(str(metadata.get("title", "오늘의 교육동향")))}</h1>
  <p class="report-date">{html.escape(report_date_label(metadata.get("windowEnd")))}</p>
  <p class="period">분석 대상: {html.escape(period_label(metadata))}</p>
</header>
<div class="summary-strip">
  <span>교육동향<strong>{len(items)}건</strong></span>
  <span>작성<strong>{html.escape(str(metadata.get("analysisModel", "")))}</strong></span>
  <span>검증<strong>{html.escape(str(metadata.get("validationStatus", report.get('validation', {}).get('status', ''))))}</strong></span>
</div>
{omission_note}
<nav aria-label="목차"><h2>목차</h2><ol>{toc}</ol></nav>
{empty_state}
{''.join(articles)}
<footer>
  <p>이 문서는 공개 보도자료를 AI로 요약·분석한 내부 검토 자료입니다.</p>
  <p>적용 검토안은 확정된 정책이나 업무 지시가 아니며, 원문은 각 항목의 링크에서 확인할 수 있습니다.</p>
</footer>
</main>
</body>
</html>
'''


def write_hwpx(report: dict[str, Any], path: Path) -> dict[str, Any]:
    try:
        from hwpx.builder import Bullet, Document, Heading, Margins, PageBreak, PageSize, Paragraph, Section
    except ImportError as error:  # pragma: no cover - dependency failure is explicit
        raise RuntimeError("python-hwpx가 설치되지 않아 HWPX를 생성할 수 없습니다.") from error

    metadata = report["metadata"]
    items = report.get("items", [])
    children: list[Any] = [
        Heading(level=1, text=str(metadata.get("title", "오늘의 교육동향"))),
        Paragraph(text=report_date_label(metadata.get("windowEnd")), align="center", style="emphasis"),
        Paragraph(text=f"분석 대상: {period_label(metadata)}", align="center"),
        Paragraph(text=f"교육동향 {len(items)}건 · AI 검증 {report.get('validation', {}).get('status', '')}", align="center"),
        Heading(level=2, text="목차"),
    ]
    if items:
        children.append(Bullet(items=tuple(f"{index}. {item.get('title', '')}" for index, item in enumerate(items, 1)), style="square"))
    else:
        children.append(Paragraph(text="검증을 통과한 교육동향이 없습니다."))

    for index, item in enumerate(items, 1):
        children.extend(
            [
                PageBreak(),
                Heading(level=1, text=f"{index}. {item.get('title', '')}"),
                Paragraph(text=f"{item.get('source', '')} · {item.get('category', '')} · {item.get('date', '')}", style="emphasis"),
                Paragraph(text=f"중요도  {importance_stars(item.get('importance'))}"),
                Heading(level=2, text="내용 요약"),
                Bullet(items=tuple(item.get("summaryPoints", [])), style="square"),
                Heading(level=2, text="교육동향 분석"),
                Bullet(items=tuple(item.get("analysisPoints", [])), style="circle"),
                Heading(level=2, text="전북교육 적용 검토"),
            ]
        )
        application = item.get("applicationReviewPoints", [])
        if application:
            children.append(Bullet(items=tuple(application), style="note"))
        else:
            children.append(Paragraph(text="직접 적용 검토사항 없음"))
        if item.get("url"):
            children.append(Paragraph(text=f"원문: {item['url']}"))

    document = Document(
        sections=(
            Section(
                children=tuple(children),
                page=PageSize.A4,
                margins=Margins(top_mm=18, right_mm=20, bottom_mm=18, left_mm=20),
            ),
        ),
        preset="government_report",
        visual_review_required=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    save_report = document.save_to_path(path)
    details = save_report.to_dict()
    failed_gates = [name for name, status in details.get("hard_gates", {}).items() if status != "pass"]
    if failed_gates:
        raise RuntimeError(f"HWPX 안전 검증 실패: {', '.join(failed_gates)}")
    return details