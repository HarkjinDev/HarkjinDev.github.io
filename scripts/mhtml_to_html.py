"""
MHTML → HTML 변환 스크립트
- cid: CSS 참조를 <style> 태그로 인라인 삽입
- 이미지는 base64 그대로 유지
- 사용법: python mhtml_to_html.py <input.mhtml> <output.html>
"""

import email
import re
import sys
import os
from pathlib import Path


def convert(mhtml_path: str, output_path: str) -> bool:
    print(f"[변환 시작] {mhtml_path} → {output_path}")

    try:
        raw = Path(mhtml_path).read_bytes()
    except FileNotFoundError:
        print(f"[ERROR] 파일 없음: {mhtml_path}")
        return False

    msg = email.message_from_bytes(raw)

    css_parts: dict[str, str] = {}
    html_content: str | None = None

    # 모든 파트 수집
    for part in msg.walk():
        ctype = part.get_content_type()
        cid = part.get("Content-ID", "").strip("<>")
        content_location = part.get("Content-Location", "")

        payload_bytes = part.get_payload(decode=True)
        if payload_bytes is None:
            continue

        charset = part.get_content_charset() or "utf-8"

        if ctype == "text/html" and html_content is None:
            try:
                html_content = payload_bytes.decode(charset, errors="replace")
            except Exception as e:
                print(f"[WARN] HTML 디코드 실패: {e}")
                html_content = payload_bytes.decode("utf-8", errors="replace")

        elif ctype == "text/css":
            try:
                css_text = payload_bytes.decode(charset, errors="replace")
            except Exception:
                css_text = payload_bytes.decode("utf-8", errors="replace")

            if cid:
                css_parts[cid] = css_text
            if content_location:
                css_parts[content_location] = css_text

    if not html_content:
        print(f"[ERROR] HTML 파트를 찾지 못했습니다: {mhtml_path}")
        return False

    print(f"[INFO] CSS 파트 {len(css_parts)}개 발견")

    # cid: CSS 링크를 <style> 태그로 교체
    replaced = 0

    def replace_css_link(match):
        nonlocal replaced
        full_tag = match.group(0)
        href_val = match.group(1)

        # cid: 참조 처리
        clean_cid = href_val.replace("cid:", "").strip()
        css_text = css_parts.get(clean_cid) or css_parts.get(href_val)

        if css_text:
            replaced += 1
            return f"<style>\n{css_text}\n</style>"
        else:
            print(f"[WARN] CSS 파트 미발견: {href_val}")
            return full_tag

    html_content = re.sub(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*/?>', 
        replace_css_link, 
        html_content,
        flags=re.IGNORECASE
    )

    print(f"[INFO] CSS 인라인화 완료: {replaced}개")

    # ── 모바일 반응형 CSS 주입 ──────────────────────────────────────
    MOBILE_CSS = """
<style id="mobile-responsive-override">
/* ── 모바일 반응형 오버라이드 ── */

/* viewport 기본 설정 */
:root { box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; }

/* 페이지 컨테이너 최대폭 제거 및 패딩 조정 */
@media screen and (max-width: 768px) {

  /* Notion 페이지 전체 컨테이너 */
  .notion-page,
  .notion-page-content,
  [class*="notion-page"],
  .page-body,
  body > div {
    max-width: 100% !important;
    width: 100% !important;
    padding-left: 12px !important;
    padding-right: 12px !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
  }

  /* 테이블: 가로 스크롤 허용 */
  table {
    display: block !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    max-width: 100% !important;
    font-size: 0.78rem !important;
  }

  /* 테이블 셀 최소폭 제한 */
  td, th {
    min-width: 60px;
    white-space: nowrap;
  }

  /* 이미지 반응형 */
  img {
    max-width: 100% !important;
    height: auto !important;
  }

  /* 코드 블록 가로 스크롤 */
  pre, code {
    overflow-x: auto !important;
    white-space: pre !important;
    font-size: 0.8rem !important;
  }

  /* 폰트 크기 조정 */
  body {
    font-size: 15px !important;
    line-height: 1.6 !important;
  }

  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.25rem !important; }
  h3 { font-size: 1.1rem !important; }

  /* 콜아웃, 토글 블록 */
  [class*="callout"],
  [class*="toggle"] {
    padding: 10px 12px !important;
  }

  /* 좌우 여백이 큰 컬럼 레이아웃 해제 */
  [class*="column"] {
    display: block !important;
    width: 100% !important;
  }

  /* 상단 헤더/타이틀 영역 */
  [class*="page-title"],
  [class*="notion-title"] {
    font-size: 1.4rem !important;
    word-break: keep-all !important;
  }
}
</style>
"""

    # </head> 직전에 모바일 CSS 삽입
    if "</head>" in html_content:
        html_content = html_content.replace("</head>", MOBILE_CSS + "\n</head>", 1)
    else:
        # </head> 없으면 <body> 앞에 삽입
        html_content = MOBILE_CSS + html_content

    print("[INFO] 모바일 반응형 CSS 주입 완료")

    # 출력 디렉토리 생성
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    Path(output_path).write_text(html_content, encoding="utf-8")
    size_kb = Path(output_path).stat().st_size / 1024
    print(f"[완료] {output_path} ({size_kb:.1f} KB)")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("사용법: python mhtml_to_html.py <input.mhtml> <output.html>")
        sys.exit(1)

    success = convert(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
