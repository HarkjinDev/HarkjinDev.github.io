#!/usr/bin/env python3
"""
Notion 공식 API → HTML 변환기
블록 JSON을 재귀적으로 가져와 자체완결 HTML 파일로 저장
"""

import base64
import os
import re
import time
from pathlib import Path
import requests

TOKEN   = os.environ["NOTION_INTEGRATION_TOKEN"]
BASE    = "https://api.notion.com/v1"
HEADS   = {
    "Authorization":  f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type":   "application/json",
}
DOMAINS = [
    ("db",    "DB",     "데이터베이스",        "3336968f-52c4-80d4-be00-c83639a5ee64"),
    ("ai",    "AI",     "인공지능",            "32d6968f-52c4-8064-9b2e-f0be961c3a7c"),
    ("sec",   "SEC",    "정보보안",            "3396968f-52c4-817e-8ecb-dac791ad2d56"),
    ("nw",    "NW",     "네트워크",            "3466968f-52c4-8061-9afe-ecdbcf66c206"),
    ("sw",    "SW",     "소프트웨어공학",       "3466968f-52c4-80fc-9ada-f62344b29fa8"),
    ("al",    "AL",     "알고리즘",            "3466968f-52c4-80b0-a414-c596c619b340"),
    ("st",    "ST",     "통계/수학",           "3436968f-52c4-81af-8f10-f58df4f3a7c5"),
    ("caos",  "CA/OS",  "컴퓨터구조/운영체제",  "3416968f-52c4-8018-9650-ed73a0c41e7d"),
    ("bizpm", "BIZ/PM", "경영/프로젝트관리",    "3466968f-52c4-8024-a060-e2173bd72c24"),
    ("ds",    "DS",     "디지털서비스",        "3466968f-52c4-8061-a7cd-faafe8009fba"),
    ("gr",    "GR",     "가이드/법제도/표준",   "3536968f-52c4-80b7-9401-dcaefe521c71"),
]


# ── API 호출 ─────────────────────────────────────────────────────────
def api_get(path, params=None):
    r = requests.get(f"{BASE}/{path}", headers=HEADS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_all_blocks(block_id):
    """페이지네이션으로 전체 자식 블록 수집"""
    results, cursor = [], None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = api_get(f"blocks/{block_id}/children", params)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.35)
    return results


# ── 텍스트 변환 ──────────────────────────────────────────────────────
def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


COLOR_FG = {
    "gray": "#9b9a97", "brown": "#64473a", "orange": "#d9730d",
    "yellow": "#dfab01", "green": "#0f7b6c", "blue": "#0b6e99",
    "purple": "#6940a5", "pink": "#ad1a72", "red": "#e03e3e",
}
COLOR_BG = {
    "gray_background":   "#ebeced", "brown_background":  "#e9e5e3",
    "orange_background": "#faebdd", "yellow_background": "#fbf3db",
    "green_background":  "#ddedea", "blue_background":   "#ddebf1",
    "purple_background": "#eae4f2", "pink_background":   "#f4dfeb",
    "red_background":    "#fbe4e4",
}


def rt_to_html(rich_texts):
    """rich_text 배열 → HTML 문자열"""
    parts = []
    for rt in rich_texts:
        text = esc(rt.get("plain_text", ""))
        if not text:
            continue
        a = rt.get("annotations", {})
        color = a.get("color", "default")

        if a.get("code"):        text = f"<code>{text}</code>"
        if a.get("bold"):        text = f"<strong>{text}</strong>"
        if a.get("italic"):      text = f"<em>{text}</em>"
        if a.get("strikethrough"): text = f"<del>{text}</del>"
        if a.get("underline"):   text = f"<u>{text}</u>"

        href = ((rt.get("text") or {}).get("link") or {}).get("url") or rt.get("href")
        if href:
            text = f'<a href="{esc(href)}" target="_blank">{text}</a>'

        if color in COLOR_BG:
            text = f'<span style="background:{COLOR_BG[color]};border-radius:3px;padding:1px 3px">{text}</span>'
        elif color in COLOR_FG:
            text = f'<span style="color:{COLOR_FG[color]}">{text}</span>'

        parts.append(text)
    return "".join(parts)


# ── 이미지 ───────────────────────────────────────────────────────────
def img_to_b64(url):
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "image/png").split(";")[0].strip()
            b64 = base64.b64encode(r.content).decode()
            return f"data:{ct};base64,{b64}"
    except Exception as e:
        print(f"    [WARN] 이미지 실패: {e}")
    return url


# ── 블록 변환 ────────────────────────────────────────────────────────
def block_html(b, depth=0):
    """단일 블록 → HTML (None 반환 = 특수 처리 필요)"""
    t = b.get("type", "")
    c = b.get(t, {})
    rt  = c.get("rich_text", [])
    txt = rt_to_html(rt)

    color = c.get("color", "default")
    cs = ""
    if color in COLOR_BG:
        cs = f' style="background:{COLOR_BG[color]};border-radius:4px;padding:2px 6px"'
    elif color in COLOR_FG:
        cs = f' style="color:{COLOR_FG[color]}"'

    if t == "heading_1":     return f"<h2{cs}>{txt}</h2>\n"
    if t == "heading_2":     return f"<h3{cs}>{txt}</h3>\n"
    if t == "heading_3":     return f"<h4{cs}>{txt}</h4>\n"
    if t == "paragraph":
        return (f"<p{cs}>{txt}</p>\n") if txt.strip() else ""  # 빈 단락 무시
    if t in ("bulleted_list_item", "numbered_list_item"):
        return f"<li{cs}>{txt}"          # 닫는 태그는 caller에서
    if t == "to_do":
        chk = "checked" if c.get("checked") else ""
        return f'<li><input type="checkbox" disabled {chk}> {txt}</li>\n'
    if t == "toggle":
        return f"<details><summary>{txt}</summary>"  # </details>는 caller에서
    if t == "quote":
        return f"<blockquote{cs}>{txt}</blockquote>\n"
    if t == "callout":
        icon = c.get("icon", {})
        emoji = icon.get("emoji", "💡") if icon.get("type") == "emoji" else "💡"
        return (f'<div class="callout"{cs}>'
                f'<span class="callout-icon">{emoji}</span>'
                f'<div>{txt}</div></div>\n')
    if t == "code":
        lang = esc(c.get("language", ""))
        code = esc("".join(r.get("plain_text", "") for r in rt))
        return f'<pre><code class="language-{lang}">{code}</code></pre>\n'
    if t == "equation":
        expr = esc(c.get("expression", ""))
        return f'<div class="equation">{expr}</div>\n'
    if t == "divider":
        return "<hr>\n"
    if t == "table_of_contents":
        return ""
    if t == "image":
        url = (c.get("file") or c.get("external") or {}).get("url", "")
        cap = rt_to_html(c.get("caption", []))
        src = img_to_b64(url) if url else ""
        if cap:
            return f'<figure><img src="{src}" alt=""><figcaption>{cap}</figcaption></figure>\n'
        return f'<img src="{src}" alt="">\n'
    if t in ("video", "file", "pdf"):
        url = (c.get("external") or c.get("file") or {}).get("url", "")
        cap = rt_to_html(c.get("caption", [])) or "[미디어]"
        return f'<p><a href="{esc(url)}" target="_blank">{cap}</a></p>\n' if url else ""
    if t == "bookmark":
        url = c.get("url", "")
        cap = rt_to_html(c.get("caption", [])) or esc(url)
        return f'<p><a href="{esc(url)}" target="_blank">{cap}</a></p>\n'
    # 기타 미지원 블록: 텍스트만 출력
    return f"<p>{txt}</p>\n" if txt else ""


def render_table(b):
    """table 블록 → HTML (children을 직접 가져옴)"""
    rows = get_all_blocks(b["id"])
    time.sleep(0.35)
    has_header = b.get("table", {}).get("has_column_header", False)
    rows_html = ""
    for i, row in enumerate(rows):
        if row.get("type") != "table_row":
            continue
        cells = row["table_row"].get("cells", [])
        row_html = "".join(
            f'<{"th" if (i==0 and has_header) else "td"}>{rt_to_html(cell)}</{"th" if (i==0 and has_header) else "td"}>'
            for cell in cells
        )
        rows_html += f"<tr>{row_html}</tr>\n"
    return f'<div class="table-scroll"><table>\n{rows_html}</table></div>\n'


def blocks_to_html(blocks, depth=0):
    """블록 목록 → HTML (list 그룹핑, 재귀 children 포함)"""
    html = ""
    i    = 0
    while i < len(blocks):
        b     = blocks[i]
        btype = b.get("type", "")

        # ── 불릿 리스트 그룹 ──────────────────────────
        if btype == "bulleted_list_item":
            html += "<ul>\n"
            while i < len(blocks) and blocks[i].get("type") == "bulleted_list_item":
                cur  = blocks[i]
                html += block_html(cur, depth)
                if cur.get("has_children"):
                    ch = get_all_blocks(cur["id"])
                    time.sleep(0.35)
                    html += blocks_to_html(ch, depth + 1)
                html += "</li>\n"
                i += 1
            html += "</ul>\n"
            continue

        # ── 번호 리스트 그룹 ──────────────────────────
        if btype == "numbered_list_item":
            html += "<ol>\n"
            while i < len(blocks) and blocks[i].get("type") == "numbered_list_item":
                cur  = blocks[i]
                html += block_html(cur, depth)
                if cur.get("has_children"):
                    ch = get_all_blocks(cur["id"])
                    time.sleep(0.35)
                    html += blocks_to_html(ch, depth + 1)
                html += "</li>\n"
                i += 1
            html += "</ol>\n"
            continue

        # ── 테이블 ────────────────────────────────────
        if btype == "table":
            html += render_table(b)
            i += 1
            continue

        # ── 컬럼 리스트 ──────────────────────────────
        if btype == "column_list":
            cols = get_all_blocks(b["id"])
            time.sleep(0.35)
            html += '<div class="column-list">\n'
            for col in cols:
                if col.get("type") == "column":
                    col_ch = get_all_blocks(col["id"])
                    time.sleep(0.35)
                    html += '<div class="column">\n'
                    html += blocks_to_html(col_ch, depth + 1)
                    html += "</div>\n"
            html += "</div>\n"
            i += 1
            continue

        # ── 토글 ─────────────────────────────────────
        if btype == "toggle":
            html += block_html(b, depth)
            if b.get("has_children"):
                ch = get_all_blocks(b["id"])
                time.sleep(0.35)
                html += blocks_to_html(ch, depth + 1)
            html += "</details>\n"
            i += 1
            continue

        # ── heading의 has_children (드문 케이스) ──────
        frag = block_html(b, depth)
        if frag is None:
            i += 1
            continue
        html += frag
        if b.get("has_children") and btype not in ("table", "column_list", "toggle"):
            ch = get_all_blocks(b["id"])
            time.sleep(0.35)
            html += blocks_to_html(ch, depth + 1)
        i += 1

    return html


# ── 페이지 → HTML ────────────────────────────────────────────────────
CSS = """
  :root {
    --bg: #ffffff; --text: #37352f; --border: #e5e5e5;
    --code-bg: #f0eeec; --pre-bg: #f7f6f3; --callout-bg: #f7f6f3;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif;
    font-size: 16px; line-height: 1.65; color: var(--text);
    max-width: 900px; margin: 0 auto; padding: 24px 32px;
  }
  h2 { font-size: 1.6rem; margin: 2rem 0 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
  h3 { font-size: 1.3rem; margin: 1.5rem 0 0.4rem; }
  h4 { font-size: 1.1rem; margin: 1.1rem 0 0.3rem; }
  p  { margin: 0.35rem 0; }
  ul, ol { padding-left: 1.5em; margin: 0.3rem 0; }
  li { margin: 0.2rem 0; }
  .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 0.8rem 0; }
  table { border-collapse: collapse; width: max-content; min-width: 100%; font-size: 0.9rem; }
  th { background: #f0f0f0; font-weight: 600; }
  th, td { border: 1px solid #ddd; padding: 7px 12px; text-align: left; vertical-align: top; }
  img { max-width: 100%; height: auto; border-radius: 4px; margin: 0.5rem 0; }
  figure { margin: 0.8rem 0; }
  figcaption { font-size: 0.85rem; color: #888; margin-top: 4px; }
  pre { background: var(--pre-bg); border-radius: 6px; padding: 12px 16px; overflow-x: auto; font-size: 0.88rem; margin: 0.6rem 0; }
  code { background: var(--code-bg); padding: 2px 5px; border-radius: 3px; font-size: 0.88em; font-family: 'Fira Code', monospace; }
  pre code { background: none; padding: 0; }
  blockquote { border-left: 3px solid var(--border); margin: 0.5rem 0; padding: 4px 16px; color: #666; }
  .callout { display: flex; gap: 10px; background: var(--callout-bg); border-radius: 6px; padding: 12px 16px; margin: 0.5rem 0; align-items: flex-start; }
  .callout-icon { font-size: 1.2rem; flex-shrink: 0; line-height: 1.5; }
  details { margin: 0.3rem 0; }
  summary { cursor: pointer; font-weight: 500; padding: 4px 0; }
  hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
  .equation { font-family: monospace; background: var(--pre-bg); padding: 8px 12px; border-radius: 4px; margin: 0.5rem 0; }
  .column-list { display: flex; gap: 16px; margin: 0.5rem 0; }
  .column { flex: 1; min-width: 0; }
  a { color: #0b6e99; text-decoration: none; }
  a:hover { text-decoration: underline; }
  strong { font-weight: 600; }
  @media (max-width: 600px) {
    body { padding: 16px; }
    .column-list { flex-direction: column; }
    h2 { font-size: 1.3rem; }
  }
"""


def make_html(page_id, label, desc):
    print(f"[{label}] 블록 로드 중...")
    blocks = get_all_blocks(page_id)
    print(f"[{label}] 블록 {len(blocks)}개 변환 중...")
    body = blocks_to_html(blocks)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>서브노트({label})</title>
  <style>{CSS}</style>
</head>
<body>
<h1>서브노트 — {label} <small style="font-size:.6em;color:#888">{desc}</small></h1>
{body}
</body>
</html>"""


# ── 메인 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    out_dir = Path("subnote")
    out_dir.mkdir(exist_ok=True)

    for fname, label, desc, page_id in DOMAINS:
        try:
            html = make_html(page_id, label, desc)
            out  = out_dir / f"{fname}.html"
            out.write_text(html, encoding="utf-8")
            size = out.stat().st_size / 1024
            print(f"[{label}] 완료 → {out} ({size:.0f} KB)")
        except Exception as e:
            print(f"[{label}] 실패: {e}")
        time.sleep(1)   # 도메인 간 딜레이
