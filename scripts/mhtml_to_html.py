"""
MHTML → HTML 변환 스크립트
- cid: CSS 참조를 <style> 태그로 인라인 삽입
- 이미지 매칭 전략 (순서대로):
    1. 정확한 URL 매칭 (content-location)
    2. URL 디코딩 후 매칭 (%3A → : 등)
    3. UUID 추출 후 매칭 (URL 형식이 달라도 동일 UUID면 매칭)
- 모바일 반응형 CSS 주입
- 사용법: python mhtml_to_html.py <input.mhtml> <output.html>
"""

import base64
import email
import re
import sys
import os
import urllib.parse
from pathlib import Path


# UUID 패턴
UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE
)


def extract_uuid(url: str):
    """URL에서 첫 번째 UUID 추출. 없으면 None."""
    m = UUID_RE.search(url)
    return m.group(0).lower() if m else None


def convert(mhtml_path: str, output_path: str) -> bool:
    print(f"[변환 시작] {mhtml_path} → {output_path}")

    try:
        raw = Path(mhtml_path).read_bytes()
    except FileNotFoundError:
        print(f"[ERROR] 파일 없음: {mhtml_path}")
        return False

    msg = email.message_from_bytes(raw)

    css_parts = {}
    img_parts = {}          # exact URL → (mime, bytes)
    img_parts_decoded = {}  # URL-decoded key → (mime, bytes)
    img_parts_by_uuid = {}  # UUID → (mime, bytes)
    html_content = None

    # ── STEP 1: 모든 파트 수집 ──────────────────────────────────────
    for part in msg.walk():
        ctype = part.get_content_type()
        cid = part.get("Content-ID", "").strip("<>")
        content_location = part.get("Content-Location", "").strip()

        payload_bytes = part.get_payload(decode=True)
        if payload_bytes is None:
            continue

        charset = part.get_content_charset() or "utf-8"

        if ctype == "text/html" and html_content is None:
            try:
                html_content = payload_bytes.decode(charset, errors="replace")
            except Exception:
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

        elif ctype.startswith("image/"):
            val = (ctype, payload_bytes)
            for key in filter(None, [cid, content_location]):
                # 정확한 URL
                img_parts[key] = val
                # URL 디코딩 버전
                decoded = urllib.parse.unquote(key)
                img_parts_decoded[decoded] = val
                # UUID 버전
                uuid = extract_uuid(key)
                if uuid and uuid not in img_parts_by_uuid:
                    img_parts_by_uuid[uuid] = val

    if not html_content:
        print(f"[ERROR] HTML 파트를 찾지 못했습니다: {mhtml_path}")
        return False

    print(f"[INFO] CSS {len(css_parts)}개 / 이미지 {len(img_parts)}개 파트 발견")
    print(f"[INFO] UUID 인덱스: {len(img_parts_by_uuid)}개")

    # ── STEP 2: CSS cid: → <style> 인라인화 ─────────────────────────
    css_replaced = 0

    def replace_css_link(match):
        nonlocal css_replaced
        full_tag = match.group(0)
        href_val = match.group(1)
        clean = href_val.replace("cid:", "").strip()
        css = css_parts.get(clean) or css_parts.get(href_val)
        if css:
            css_replaced += 1
            return f"<style>\n{css}\n</style>"
        return full_tag

    html_content = re.sub(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*/?>', 
        replace_css_link,
        html_content,
        flags=re.IGNORECASE
    )
    print(f"[INFO] CSS 인라인화 완료: {css_replaced}개")

    # ── STEP 3: 이미지 src → 3단계 매칭 후 base64 변환 ─────────────
    matched_exact = 0
    matched_decoded = 0
    matched_uuid = 0
    unmatched = 0

    def lookup_img(src_val):
        """이미지 파트를 3단계로 찾아서 (mime, bytes) 반환. 없으면 None."""
        # 1. 정확한 URL
        r = img_parts.get(src_val)
        if r:
            return r, "exact"
        # 2. URL 디코딩
        decoded = urllib.parse.unquote(src_val)
        r = img_parts_decoded.get(decoded) or img_parts.get(decoded)
        if r:
            return r, "decoded"
        # 3. UUID 매칭
        uuid = extract_uuid(src_val)
        if uuid:
            r = img_parts_by_uuid.get(uuid)
            if r:
                return r, "uuid"
        return None, None

    def replace_img_src(match):
        nonlocal matched_exact, matched_decoded, matched_uuid, unmatched
        full_attr = match.group(0)
        src_val = match.group(1)

        if src_val.startswith("data:"):
            return full_attr

        # cid: 처리
        if src_val.startswith("cid:"):
            clean_cid = src_val[4:].strip()
            result, _ = lookup_img(clean_cid)
            if result:
                mime_type, img_bytes = result
                b64 = base64.b64encode(img_bytes).decode("ascii")
                matched_exact += 1
                return f'src="data:{mime_type};base64,{b64}"'
            return full_attr

        # URL 매칭 (3단계)
        result, method = lookup_img(src_val)
        if result:
            mime_type, img_bytes = result
            b64 = base64.b64encode(img_bytes).decode("ascii")
            if method == "exact":
                matched_exact += 1
            elif method == "decoded":
                matched_decoded += 1
            elif method == "uuid":
                matched_uuid += 1
            return f'src="data:{mime_type};base64,{b64}"'

        # 매칭 실패
        if src_val.startswith("http"):
            unmatched += 1
            print(f"[WARN] 매칭 실패: {src_val[:80]}...")

        return full_attr

    html_content = re.sub(
        r'src=["\']([^"\']+)["\']',
        replace_img_src,
        html_content,
        flags=re.IGNORECASE
    )

    print(f"[INFO] 이미지 인라인화 완료: "
          f"정확매칭 {matched_exact}개 / "
          f"URL디코딩 {matched_decoded}개 / "
          f"UUID매칭 {matched_uuid}개 / "
          f"실패 {unmatched}개")

    # ── STEP 4: 모바일 반응형 CSS 주입 ──────────────────────────────
    MOBILE_CSS = """
<style id="mobile-responsive-override">
:root { box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; }

@media screen and (max-width: 768px) {
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
  table {
    display: block !important;
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    max-width: 100% !important;
    font-size: 0.78rem !important;
  }
  td, th { min-width: 60px; white-space: nowrap; }
  img { max-width: 100% !important; height: auto !important; }
  pre, code {
    overflow-x: auto !important;
    white-space: pre !important;
    font-size: 0.8rem !important;
  }
  body { font-size: 15px !important; line-height: 1.6 !important; }
  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.25rem !important; }
  h3 { font-size: 1.1rem !important; }
  [class*="callout"],
  [class*="toggle"] { padding: 10px 12px !important; }
  [class*="column"] { display: block !important; width: 100% !important; }
  [class*="page-title"],
  [class*="notion-title"] {
    font-size: 1.4rem !important;
    word-break: keep-all !important;
  }
}
</style>
"""

    if "</head>" in html_content:
        html_content = html_content.replace("</head>", MOBILE_CSS + "\n</head>", 1)
    else:
        html_content = MOBILE_CSS + html_content

    print("[INFO] 모바일 반응형 CSS 주입 완료")

    # ── STEP 5: 출력 ─────────────────────────────────────────────────
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
