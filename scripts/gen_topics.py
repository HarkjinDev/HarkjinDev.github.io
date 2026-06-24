#!/usr/bin/env python3
"""
gen_topics.py — 도메인 HTML을 토픽 단위로 분할
- subnote/topics/{domain}/{001..N}.html 생성
- subnote/topics/{domain}/style.css 생성 (공유 CSS)
- subnote/topics.json 생성 (도메인→토픽 목록 매핑)
"""

import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

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

TOPIC_TAGS = ["h2", "h3", "h4"]
MIN_LEN    = 3   # 토픽 제목 최소 글자 수


def is_topic_heading(tag) -> bool:
    if tag.name not in TOPIC_TAGS:
        return False
    return len(tag.get_text(strip=True)) >= MIN_LEN


def extract_css(soup) -> str:
    """style 태그 전체 추출"""
    parts = [s.string for s in soup.find_all("style") if s.string]
    return "\n".join(parts)


def split_html(html_content: str):
    """
    HTML을 토픽 단위로 분할
    반환: [(topic_name, section_html), ...]
    """
    soup = BeautifulSoup(html_content, "html.parser")

    headings = [h for h in soup.find_all(TOPIC_TAGS) if is_topic_heading(h)]
    if not headings:
        return []

    # 임시 인덱스 속성 추가 → str 변환 후 위치 탐색
    for i, h in enumerate(headings):
        h["data-split-idx"] = str(i)

    html_str = str(soup)

    positions = []
    for i in range(len(headings)):
        marker = f'data-split-idx="{i}"'
        pos    = html_str.find(marker)
        tag_start = html_str.rfind("<", 0, pos) if pos >= 0 else -1
        positions.append(tag_start)

    results = []
    for i, h in enumerate(headings):
        if positions[i] < 0:
            continue
        name  = h.get_text(strip=True)
        start = positions[i]
        end   = positions[i + 1] if (i + 1 < len(positions) and positions[i + 1] >= 0) \
                else len(html_str)

        section = html_str[start:end]
        # 임시 속성 제거
        section = re.sub(r'\s*data-split-idx="\d+"', "", section)
        results.append((name, section))

    return results


def make_topic_html(topic_name: str, section_html: str) -> str:
    """토픽 단독 HTML 파일 생성 (CSS는 style.css 링크)"""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{topic_name}</title>
  <link rel="stylesheet" href="style.css">
  <style>
    /* iframe 내부 여백 및 반응형 보정 */
    body {{ margin: 0; padding: 20px 24px 40px; box-sizing: border-box; }}
    img  {{ max-width: 100% !important; height: auto !important; }}
    /* table display:block 금지 — style.css 값 덮어쓰기 방지 */
    table {{ display: table !important; width: 100%; }}
    .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  </style>
</head>
<body>
{section_html}
</body>
</html>"""


def process_domain(fname: str, label: str, subnote_dir: str = "subnote"):
    html_path = Path(subnote_dir) / f"{fname}.html"
    if not html_path.exists():
        print(f"[SKIP] {label} — HTML 없음")
        return None

    print(f"[{label}] 처리 중...")
    content = html_path.read_text(encoding="utf-8")
    soup    = BeautifulSoup(content, "html.parser")
    css     = extract_css(soup)
    topics  = split_html(content)

    if not topics:
        print(f"[{label}] 토픽 없음 (heading 미발견)")
        return None

    # 출력 디렉토리
    out_dir = Path(subnote_dir) / "topics" / fname
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSS 저장
    css_path = out_dir / "style.css"
    css_path.write_text(css, encoding="utf-8")

    # 토픽 파일 저장
    topic_list = []
    for i, (name, section_html) in enumerate(topics, 1):
        file_id   = f"{i:03d}"
        file_name = f"{file_id}.html"
        html      = make_topic_html(name, section_html)
        (out_dir / file_name).write_text(html, encoding="utf-8")
        topic_list.append({"id": file_id, "name": name})

    print(f"[{label}] 토픽 {len(topic_list)}개 → topics/{fname}/")
    return topic_list


def generate(subnote_dir: str = "subnote"):
    topics_json = {}

    for fname, label, desc in DOMAINS:
        topic_list = process_domain(fname, label, subnote_dir)
        if topic_list:
            topics_json[fname] = {
                "label": label,
                "desc":  desc,
                "topics": topic_list
            }

    # topics.json 저장
    json_path = Path(subnote_dir) / "topics.json"
    json_path.write_text(
        json.dumps(topics_json, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    total = sum(len(v["topics"]) for v in topics_json.values())
    print(f"\n[완료] topics.json 생성 — 도메인 {len(topics_json)}개 / 토픽 {total}개")


if __name__ == "__main__":
    generate()
