#!/usr/bin/env python3
"""
mem.html 생성기
각 도메인 HTML에서 두음(<xxx> 형식)을 추출하여 mem.html로 정리

콘텐츠 탐색 전략:
  케이스 1 (리스트): 두음이 들어있는 <li> 안에 중첩 <ul>/<ol> 있으면 사용
  케이스 2 (표):    없으면 같은 섹션(heading 범위) 안의 <table> 탐색
"""

from bs4 import BeautifulSoup
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

MNEMONIC_RE  = re.compile(r'[<＜〈]([가-힣A-Za-z0-9·,/\-~\s]{1,40})[>＞〉]')
HEADING_TAGS = ["h1", "h2", "h3", "h4"]

DOMAINS = [
    ("db",    "DB",     "데이터베이스"),
    ("ai",    "AI",     "인공지능"),
    ("sec",   "SEC",    "정보보안"),
    ("nw",    "NW",     "네트워크"),
    ("sw",    "SW",     "소프트웨어공학"),
    ("al",    "AL",     "알고리즘"),
    ("st",    "ST",     "통계/수학"),
    ("caos",  "CA/OS",  "컴퓨터구조/운영체제"),
    ("bizpm", "BIZ/PM", "경영/프로젝트관리"),
    ("ds",    "DS",     "디지털서비스"),
    ("gr",    "GR",     "가이드/법제도/표준"),
]


def table_to_html(table_tag) -> str:
    rows = table_tag.find_all("tr")
    if not rows:
        return ""
    html_rows = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        cells_html = []
        for cell in cells:
            tag = "th" if (i == 0 or cell.name == "th") else "td"
            cells_html.append(f"<{tag}>{cell.get_text(strip=True)}</{tag}>")
        html_rows.append(f"<tr>{''.join(cells_html)}</tr>")
    return "<table>" + "".join(html_rows) + "</table>"


def list_to_html(list_tag) -> str:
    items = []
    # 직접 자식 li 우선
    direct_lis = list_tag.find_all("li", recursive=False)
    target_lis = direct_lis if direct_lis else list_tag.find_all("li")
    for li in target_lis:
        parts = []
        for child in li.children:
            if getattr(child, "name", None) in ["ul", "ol"]:
                continue  # 중첩 리스트 텍스트 중복 제외
            text = child.get_text(strip=True) if hasattr(child, "get_text") else str(child).strip()
            if text:
                parts.append(text)
        text = " ".join(parts).strip()
        if text:
            items.append(f"<li>{text}</li>")
    return f"<ul>{''.join(items)}</ul>" if items else ""


def find_ancestor_li(element):
    """element의 가장 가까운 조상 <li> 반환"""
    el = element.parent
    while el and el.name not in ["body", "html", None]:
        if el.name == "li":
            return el
        el = el.parent
    return None


def extract_content(parent) -> str:
    """
    두음 parent 이후 콘텐츠(표 또는 리스트) 추출

    전략:
      1. 두음이 <li> 안에 있으면 → 같은 <li>의 중첩 리스트 확인 (서브 불릿)
      2. 없으면 → 같은 섹션(heading 기준) 안의 <table> 탐색
         (다른 불릿의 서브 ul에 속지 않도록 table만 탐색)
    """

    # ── 케이스 1: 같은 <li> 안의 중첩 리스트 ────────────────────────
    mnemonic_li = find_ancestor_li(parent)
    if mnemonic_li:
        nested = mnemonic_li.find(["ul", "ol"])
        if nested:
            result = list_to_html(nested)
            if result:
                return result

    # ── 케이스 2: 섹션 내 table 탐색 ────────────────────────────────
    # 현재 섹션 heading 레벨 파악 (같은/높은 레벨 heading 만나면 중단)
    prev_h = parent.find_previous(HEADING_TAGS)
    prev_level = int(prev_h.name[1]) if prev_h else 6

    for el in parent.find_all_next(HEADING_TAGS + ["table"]):
        if el.name in HEADING_TAGS:
            if int(el.name[1]) <= prev_level:
                break   # 같은/높은 레벨 heading → 섹션 종료
            continue    # 더 낮은 레벨 heading → 계속 탐색
        if el.name == "table":
            result = table_to_html(el)
            if result:
                return result

    return ""


def extract_mnemonics(html_path: str, domain_label: str):
    try:
        content = Path(html_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[WARN] 파일 없음: {html_path}")
        return []

    soup    = BeautifulSoup(content, "html.parser")
    results = []
    seen    = set()

    # &lt;...&gt; 로 이스케이프된 두음도 탐지 (notion_to_html.py 생성 HTML 대응)
    MNEMONIC_ESC = re.compile(r'&lt;([가-힣A-Za-z0-9·,/\-~\s]{1,40})&gt;')
    
    # raw HTML에서 이스케이프 패턴 직접 탐지 후 치환
    raw_html = str(soup)
    if MNEMONIC_ESC.search(raw_html):
        # &lt;두음&gt; → <두음> 로 치환 후 재파싱
        fixed_html = MNEMONIC_ESC.sub(lambda m: f'<{m.group(1)}>', raw_html)
        soup = BeautifulSoup(fixed_html, "html.parser")

    for text_node in soup.find_all(string=lambda t: t and MNEMONIC_RE.search(t)):
        match = MNEMONIC_RE.search(str(text_node))
        if not match:
            continue

        mnemonic = f"<{match.group(1).strip()}>"
        parent   = text_node.parent

        # 직전 heading → 토픽명
        topic  = domain_label
        prev_h = parent.find_previous(HEADING_TAGS)
        if prev_h:
            topic = prev_h.get_text(strip=True)
        else:
            prev_h = parent.find_previous(
                class_=re.compile(r"notion-h[1-4]|notion-header|header-block")
            )
            if prev_h:
                topic = prev_h.get_text(strip=True)

        content_html = extract_content(parent)

        key = (topic, mnemonic)
        if key not in seen:
            seen.add(key)
            results.append((topic, mnemonic, content_html))

    return results


def generate_mem_html(subnote_dir: str = "subnote"):
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    sections_html = ""
    total_count   = 0

    for fname, label, desc in DOMAINS:
        html_path = f"{subnote_dir}/{fname}.html"
        items     = extract_mnemonics(html_path, label)

        if not items:
            print(f"[{label}] 두음 없음 또는 파일 없음")
            continue

        # 표/리스트 있는 항목 / 없는 항목 집계
        with_content    = sum(1 for _, _, c in items if c)
        without_content = len(items) - with_content
        print(f"[{label}] 두음 {len(items)}개 (콘텐츠 있음: {with_content}, 없음: {without_content})")
        if without_content:
            no_content = [m for _, m, c in items if not c]
            print(f"  └ 콘텐츠 없는 두음: {no_content[:5]}")
        total_count += len(items)

        topic_map: dict = {}
        for topic, mnemonic, content_html in items:
            topic_map.setdefault(topic, []).append((mnemonic, content_html))

        # 도메인별 요약 표 생성: 토픽명 | 두음
        rows_html = ""
        for topic, mnemonics in topic_map.items():
            for mnemonic, _ in mnemonics:
                rows_html += f"""
          <tr>
            <td class="col-topic">{topic}</td>
            <td class="col-mnemonic"><span class="mnemonic">{mnemonic}</span></td>
          </tr>"""

        domain_table = f"""
<table class="domain-table">
  <thead>
    <tr>
      <th>토픽명</th>
      <th>두음</th>
    </tr>
  </thead>
  <tbody>{rows_html}
  </tbody>
</table>"""

        sections_html += f"""
<section class="domain">
  <h2 class="domain-title">
    <span class="domain-label">{label}</span>
    <span class="domain-desc">{desc}</span>
  </h2>
  {domain_table}
</section>
<hr>
"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>두음 모음 (mem)</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      max-width: 860px; margin: 0 auto; padding: 20px;
      color: #333; background: #fafafa;
    }}
    h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
    .meta {{ color: #999; font-size: 0.85rem; margin-bottom: 32px; }}
    .meta a {{ color: #999; text-decoration: none; }}
    .meta a:hover {{ text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid #e5e5e5; margin: 32px 0; }}
    .domain {{ margin-bottom: 8px; }}
    .domain-title {{
      font-size: 1.3rem; margin: 24px 0 12px;
      display: flex; align-items: center; gap: 10px;
    }}
    .domain-label {{
      background: #2d3748; color: #fff;
      padding: 3px 10px; border-radius: 4px; font-size: 0.95rem;
    }}
    .domain-desc {{ color: #666; font-size: 0.95rem; font-weight: normal; }}

    /* ── 도메인 요약 표 ── */
    .domain-table {{
      border-collapse: collapse; width: 100%;
      font-size: 0.9rem; background: #fff;
      margin-bottom: 8px;
    }}
    .domain-table th {{
      background: #2d3748; color: #fff;
      padding: 9px 14px; text-align: left;
      font-weight: 600; white-space: nowrap;
    }}
    .domain-table td {{
      padding: 8px 14px; border-bottom: 1px solid #eee;
      vertical-align: middle;
    }}
    .domain-table tr:last-child td {{ border-bottom: none; }}
    .domain-table tr:hover td {{ background: #f7f9fc; }}
    .col-topic {{ color: #444; width: 70%; }}
    .col-mnemonic {{ width: 30%; }}

    /* ── 두음 배지 ── */
    span.mnemonic {{
      display: inline-block;
      background-color: #93c7e7; color: #d44c47;
      font-weight: 700; font-size: 1rem;
      padding: 3px 12px; border-radius: 4px;
      letter-spacing: 0.05em; white-space: nowrap;
    }}

    @media (max-width: 640px) {{
      body {{ padding: 12px; }}
      h1 {{ font-size: 1.3rem; }}
      .domain-title {{ font-size: 1.1rem; }}
      .domain-table {{ font-size: 0.82rem; }}
      .domain-table td, .domain-table th {{ padding: 6px 10px; }}
      span.mnemonic {{ font-size: 0.88rem; padding: 2px 8px; }}
    }}
  </style>
</head>
<body>
  <h1>📝 두음 모음</h1>
  <p class="meta">
    총 {total_count}개 항목 &nbsp;|&nbsp; 마지막 업데이트: {now}
    &nbsp;|&nbsp; <a href="index.html">← 목록으로</a>
  </p>
  {sections_html}
</body>
</html>"""

    output_path = f"{subnote_dir}/mem.html"
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[완료] {output_path} 생성 (총 {total_count}개 두음)")


if __name__ == "__main__":
    generate_mem_html()
