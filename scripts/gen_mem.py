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

        # 도메인별 요약 표 생성: 토픽명 | 두음 | 보기
        rows_html = ""
        for topic, mnemonics in topic_map.items():
            for mnemonic, _ in mnemonics:
                safe_topic    = topic.replace('"', '&quot;')
                safe_mnemonic = mnemonic.replace('"', '&quot;')
                rows_html += f"""
          <tr>
            <td class="col-topic">{topic}</td>
            <td class="col-mnemonic">
              <span class="mnemonic">{mnemonic}</span>
              <button class="view-btn"
                data-domain="{label}"
                data-fname="{fname}"
                data-topic="{safe_topic}"
                title="내용 보기">↓</button>
            </td>
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

    /* ── 보기 버튼 ── */
    .view-btn {{
      background: #e8f4fd; border: 1px solid #93c7e7;
      color: #2563a8; border-radius: 5px;
      padding: 2px 8px; font-size: .75rem;
      cursor: pointer; margin-left: 8px;
      vertical-align: middle; transition: all .15s;
      white-space: nowrap;
    }}
    .view-btn:hover {{ background: #bde3f5; }}
    .view-btn.active {{ background: #93c7e7; color: #fff; border-color: #5aacd4; }}

    /* ── 하단 패널 오버레이 ── */
    .bp-overlay {{
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,.3); z-index: 100;
    }}
    .bp-overlay.show {{ display: block; }}

    /* ── 하단 패널 ── */
    .bottom-panel {{
      position: fixed; bottom: 0; left: 0; right: 0;
      height: 0;
      background: #fff;
      border-radius: 14px 14px 0 0;
      border-top: 2px solid #e0e0e0;
      box-shadow: 0 -4px 24px rgba(0,0,0,.13);
      z-index: 101;
      transition: height .3s cubic-bezier(.4,0,.2,1);
      overflow: hidden;
      display: flex; flex-direction: column;
    }}
    .bottom-panel.open {{ height: 55vh; }}

    .bp-header {{
      display: flex; align-items: center; gap: 10px;
      padding: 12px 16px; border-bottom: 1px solid #eee;
      background: #f7f9fc; flex-shrink: 0;
    }}
    .bp-domain-tag {{
      background: #2d3748; color: #fff;
      font-size: .7rem; font-weight: 700;
      padding: 2px 8px; border-radius: 4px; flex-shrink: 0;
    }}
    .bp-title {{
      flex: 1; font-size: .88rem; font-weight: 600;
      color: #333; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap;
    }}
    .bp-close {{
      background: none; border: none; font-size: 1.1rem;
      color: #999; cursor: pointer; padding: 4px 8px;
      border-radius: 6px; flex-shrink: 0; line-height: 1;
    }}
    .bp-close:hover {{ background: #eee; color: #333; }}

    .bp-body {{ flex: 1; position: relative; overflow: hidden; }}
    .bp-loading {{
      display: none; position: absolute; inset: 0;
      align-items: center; justify-content: center; background: #fff; z-index: 1;
    }}
    .bp-loading.show {{ display: flex; }}
    .bp-spinner {{
      width: 24px; height: 24px; border: 3px solid #eee;
      border-top-color: #93c7e7; border-radius: 50%;
      animation: bpspin .7s linear infinite;
    }}
    @keyframes bpspin {{ to {{ transform: rotate(360deg); }} }}
    #bpFrame {{ width: 100%; height: 100%; border: none; }}

    /* ── 본문 패딩 보정 (패널 열릴 때 가림 방지) ── */
    body.panel-open {{ padding-bottom: 55vh; }}

    @media (max-width: 640px) {{
      body {{ padding: 12px; }}
      h1 {{ font-size: 1.3rem; }}
      .domain-title {{ font-size: 1.1rem; }}
      .domain-table {{ font-size: 0.82rem; }}
      .domain-table td, .domain-table th {{ padding: 6px 10px; }}
      span.mnemonic {{ font-size: 0.88rem; padding: 2px 8px; }}
      .bottom-panel.open {{ height: 65vh; }}
      body.panel-open {{ padding-bottom: 65vh; }}
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
</div>

<!-- ── 하단 패널 ── -->
<div class="bp-overlay" id="bpOverlay"></div>
<div class="bottom-panel" id="bottomPanel">
  <div class="bp-header">
    <span class="bp-domain-tag" id="bpDomainTag">-</span>
    <span class="bp-title" id="bpTitle">-</span>
    <button class="bp-close" id="bpClose">✕</button>
  </div>
  <div class="bp-body">
    <div class="bp-loading" id="bpLoading"><div class="bp-spinner"></div></div>
    <iframe id="bpFrame" title="토픽 내용"></iframe>
  </div>
</div>

<script>
let topicsData  = null;
let activeBtn   = null;

/* topics.json 로드 */
async function loadTopics() {{
  try {{
    const res = await fetch('topics.json', {{ cache: 'no-cache' }});
    topicsData = await res.json();
  }} catch(e) {{ console.warn('topics.json 로드 실패', e); }}
}}

/* 토픽명 → 파일 경로 매핑 */
function findFile(fname, topicName) {{
  if (!topicsData || !topicsData[fname]) return null;
  const topics = topicsData[fname].topics;

  // 1. 완전 일치
  let t = topics.find(t => t.name === topicName);
  // 2. 포함 관계
  if (!t) t = topics.find(t => t.name.includes(topicName) || topicName.includes(t.name));
  // 3. 앞 10자 비교
  if (!t) t = topics.find(t => t.name.slice(0,10) === topicName.slice(0,10));

  return t ? `topics/${{fname}}/${{t.id}}.html` : null;
}}

/* 패널 열기 */
function openPanel(btn) {{
  const domain = btn.dataset.domain;
  const fname  = btn.dataset.fname;
  const topic  = btn.dataset.topic;
  const file   = findFile(fname, topic);

  // 이전 활성 버튼 해제
  if (activeBtn && activeBtn !== btn) activeBtn.classList.remove('active');
  btn.classList.toggle('active');

  // 같은 버튼 재클릭 → 패널 닫기
  if (activeBtn === btn && !document.getElementById('bottomPanel').classList.contains('open')) {{
    activeBtn = btn;
  }} else if (activeBtn === btn) {{
    closePanel(); return;
  }}
  activeBtn = btn;

  const panel   = document.getElementById('bottomPanel');
  const overlay = document.getElementById('bpOverlay');
  const frame   = document.getElementById('bpFrame');
  const loading = document.getElementById('bpLoading');

  document.getElementById('bpDomainTag').textContent = domain;
  document.getElementById('bpTitle').textContent     = topic;
  document.body.classList.add('panel-open');
  panel.classList.add('open');
  overlay.classList.add('show');

  if (!file) {{
    loading.classList.remove('show');
    frame.srcdoc = '<div style="padding:24px;color:#999;text-align:center;font-family:sans-serif">토픽 파일을 찾을 수 없습니다</div>';
    return;
  }}

  loading.classList.add('show');
  frame.onload = () => loading.classList.remove('show');
  frame.src = file + '?v=' + Date.now();
}}

/* 패널 닫기 */
function closePanel() {{
  document.getElementById('bottomPanel').classList.remove('open');
  document.getElementById('bpOverlay').classList.remove('show');
  document.body.classList.remove('panel-open');
  if (activeBtn) {{ activeBtn.classList.remove('active'); activeBtn = null; }}
}}

document.getElementById('bpClose').addEventListener('click', closePanel);
document.getElementById('bpOverlay').addEventListener('click', closePanel);

/* 보기 버튼 이벤트 */
document.querySelectorAll('.view-btn').forEach(btn => {{
  btn.addEventListener('click', e => {{ e.stopPropagation(); openPanel(btn); }});
}});

/* 초기화 */
loadTopics();
</script>
</body>
</html>"""

    output_path = f"{subnote_dir}/mem.html"
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"[완료] {output_path} 생성 (총 {total_count}개 두음)")


if __name__ == "__main__":
    generate_mem_html()
