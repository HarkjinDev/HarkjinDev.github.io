#!/usr/bin/env python3
"""
mem.html 생성기
각 도메인 HTML에서 두음(<xxx> 형식)을 추출하여 mem.html로 정리
"""

from bs4 import BeautifulSoup
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 두음 패턴: <xxx> 형식 (한글/영문/특수문자 1~20자)
MNEMONIC_RE = re.compile(r'[<＜〈]([가-힣A-Za-z·,\s]{1,20})[>＞〉]')

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
    """table 태그를 HTML 문자열로 변환 (스타일 제거)"""
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


def extract_mnemonics(html_path: str, domain_label: str):
    """
    HTML에서 두음 항목 추출
    반환: [(topic_name, mnemonic_text, table_html), ...]
    """
    try:
        content = Path(html_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[WARN] 파일 없음: {html_path}")
        return []

    soup = BeautifulSoup(content, "html.parser")
    results = []
    seen = set()

    # 두음 패턴을 포함하는 텍스트 노드 탐색
    for text_node in soup.find_all(string=lambda t: t and MNEMONIC_RE.search(t)):
        match = MNEMONIC_RE.search(str(text_node))
        if not match:
            continue

        mnemonic = f"<{match.group(1).strip()}>"
        parent = text_node.parent

        # ── 직전 heading 찾기 ───────────────────────────────────────
        topic = domain_label
        # 실제 h 태그 시도
        prev_h = parent.find_previous(["h1", "h2", "h3", "h4"])
        if prev_h:
            topic = prev_h.get_text(strip=True)
        else:
            # Notion 클래스 기반 heading 시도
            prev_h = parent.find_previous(
                class_=re.compile(r"notion-h[1-4]|notion-header|header-block")
            )
            if prev_h:
                topic = prev_h.get_text(strip=True)

        # ── 직후 table 찾기 ─────────────────────────────────────────
        table_html = ""
        next_table = parent.find_next("table")
        if next_table:
            # 다음 heading 보다 table이 먼저 나오는지 확인
            next_heading = parent.find_next(["h1", "h2", "h3", "h4"])
            if next_heading is None or (
                next_table.find_previous() and
                str(next_table) in str(next_heading.find_next())
            ) or next_heading is None:
                table_html = table_to_html(next_table)
            else:
                # table이 heading 이전에 있으면 사용
                try:
                    if list(next_table.parents).__len__() <= list(next_heading.parents).__len__():
                        table_html = table_to_html(next_table)
                except Exception:
                    table_html = table_to_html(next_table)

        # 중복 제거
        key = (topic, mnemonic)
        if key not in seen:
            seen.add(key)
            results.append((topic, mnemonic, table_html))

    return results


def generate_mem_html(subnote_dir: str = "subnote"):
    """전체 도메인을 순회하며 mem.html 생성"""
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    sections_html = ""
    total_count = 0

    for fname, label, desc in DOMAINS:
        html_path = f"{subnote_dir}/{fname}.html"
        items = extract_mnemonics(html_path, label)

        if not items:
            print(f"[{label}] 두음 없음 또는 파일 없음")
            continue

        print(f"[{label}] 두음 {len(items)}개 추출")
        total_count += len(items)

        # 토픽별로 그룹핑
        topic_map = {}
        for topic, mnemonic, table_html in items:
            if topic not in topic_map:
                topic_map[topic] = []
            topic_map[topic].append((mnemonic, table_html))

        items_html = ""
        for topic, mnemonics in topic_map.items():
            items_html += f'<h3 class="topic">{topic}</h3>\n'
            for mnemonic, table_html in mnemonics:
                items_html += f'<p class="mnemonic">{mnemonic}</p>\n'
                if table_html:
                    items_html += f'<div class="table-wrap">{table_html}</div>\n'

        sections_html += f"""
<section class="domain">
  <h2 class="domain-title">
    <span class="domain-label">{label}</span>
    <span class="domain-desc">{desc}</span>
  </h2>
  {items_html}
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
    /* ── 기본 ── */
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      max-width: 860px;
      margin: 0 auto;
      padding: 20px;
      color: #333;
      background: #fafafa;
    }}
    h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
    .meta {{ color: #999; font-size: 0.85rem; margin-bottom: 32px; }}
    .meta a {{ color: #999; text-decoration: none; }}
    .meta a:hover {{ text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid #e5e5e5; margin: 32px 0; }}

    /* ── 도메인 섹션 ── */
    .domain {{ margin-bottom: 8px; }}
    .domain-title {{
      font-size: 1.3rem;
      margin: 24px 0 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .domain-label {{
      background: #2d3748;
      color: #fff;
      padding: 3px 10px;
      border-radius: 4px;
      font-size: 0.95rem;
    }}
    .domain-desc {{ color: #666; font-size: 0.95rem; font-weight: normal; }}

    /* ── 토픽명 ── */
    h3.topic {{
      font-size: 1rem;
      color: #444;
      margin: 20px 0 6px;
      padding-left: 8px;
      border-left: 3px solid #93c7e7;
    }}

    /* ── 두음 ── */
    p.mnemonic {{
      display: inline-block;
      background-color: #93c7e7;
      color: #d44c47;
      font-weight: 700;
      font-size: 1.1rem;
      padding: 4px 14px;
      border-radius: 4px;
      margin: 4px 0 10px;
      letter-spacing: 0.05em;
    }}

    /* ── 테이블 ── */
    .table-wrap {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      margin-bottom: 12px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 0.88rem;
      background: #fff;
    }}
    th {{
      background: #f0f4f8;
      padding: 8px 12px;
      border: 1px solid #ddd;
      text-align: left;
      white-space: nowrap;
    }}
    td {{
      padding: 7px 12px;
      border: 1px solid #ddd;
      vertical-align: top;
    }}
    tr:hover td {{ background: #f9f9f9; }}

    /* ── 모바일 ── */
    @media (max-width: 640px) {{
      body {{ padding: 12px; }}
      h1 {{ font-size: 1.3rem; }}
      .domain-title {{ font-size: 1.1rem; }}
      p.mnemonic {{ font-size: 1rem; }}
      th, td {{ font-size: 0.8rem; padding: 6px 8px; }}
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
