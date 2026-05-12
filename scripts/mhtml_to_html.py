"""
MHTML → HTML 변환 스크립트
- cid: CSS 참조를 <style> 태그로 인라인 삽입
- cid: 이미지 참조를 data: URL로 변환 (base64 인라인)
- 외부 URL 이미지(S3, Notion CDN)를 다운로드 후 base64 인라인화
- 모바일 반응형 CSS 주입
- 사용법: python mhtml_to_html.py <input.mhtml> <output.html>
"""

import base64
import email
import re
import sys
import os
import urllib.request
import urllib.error
from pathlib import Path


# 다운로드 대상 외부 이미지 도메인
EXTERNAL_IMG_DOMAINS = (
    "prod-files-secure.s3",
    "s3.us-west-2.amazonaws.com",
    "s3.amazonaws.com",
    "notion.so/image",
    "notion-static.com",
)


def fetch_image_as_base64(url: str) -> tuple | None:
    """외부 이미지 URL을 다운로드해서 (mime_type, base64_str) 반환. 실패 시 None."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get_content_type() or "image/png"
            data = resp.read()
            b64 = base64.b64encode(data).decode("ascii")
            return content_type, b64
    except Exception as e:
        print(f"[WARN] 이미지 다운로드 실패: {url[:80]}... → {e}")
        return None


def convert(mhtml_path: str, output_path: str) -> bool:
    print(f"[변환 시작] {mhtml_path} → {output_path}")

    try:
        raw = Path(mhtml_path).read_bytes()
    except FileNotFoundError:
        print(f"[ERROR] 파일 없음: {mhtml_path}")
        return False

    msg = email.message_from_bytes(raw)

    css_parts = {}
    img_parts = {}  # key → (mime_type, raw_bytes)
    html_content = None

    # ── STEP 1: 모든 파트 수집 ──────────────────────────────────────
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

        elif ctype.startswith("image/"):
            if cid:
                img_parts[cid] = (ctype, payload_bytes)
            if content_location:
                img_parts[content_location] = (ctype, payload_bytes)

    if not html_content:
        print(f"[ERROR] HTML 파트를 찾지 못했습니다: {mhtml_path}")
        return False

    print(f"[INFO] CSS {len(css_parts)}개 / 이미지 {len(img_parts)}개 파트 발견")

    # ── STEP 2: CSS cid: → <style> 인라인화 ─────────────────────────
    css_replaced = 0

    def replace_css_link(match):
        nonlocal css_replaced
        full_tag = match.group(0)
        href_val = match.group(1)
        clean_cid = href_val.replace("cid:", "").strip()
        css_text = css_parts.get(clean_cid) or css_parts.get(href_val)
        if css_text:
            css_replaced += 1
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
    print(f"[INFO] CSS 인라인화 완료: {css_replaced}개")

    # ── STEP 3: 이미지 cid: → data: URL 인라인화 ────────────────────
    img_cid_replaced = 0

    def replace_img_cid(match):
        nonlocal img_cid_replaced
        full_attr = match.group(0)
        src_val = match.group(1)

        if not src_val.startswith("cid:"):
            return full_attr

        clean_cid = src_val[4:].strip()
        result = img_parts.get(clean_cid)
        if result:
            mime_type, img_bytes = result
            b64 = base64.b64encode(img_bytes).decode("ascii")
            img_cid_replaced += 1
            return f'src="data:{mime_type};base64,{b64}"'
        else:
            print(f"[WARN] 이미지 cid 파트 미발견: {clean_cid}")
            return full_attr

    html_content = re.sub(
        r'src=["\']([^"\']+)["\']',
        replace_img_cid,
        html_content,
        flags=re.IGNORECASE
    )
    print(f"[INFO] 이미지 cid 인라인화 완료: {img_cid_replaced}개")

    # ── STEP 4: 외부 URL 이미지 → 다운로드 후 data: URL 인라인화 ────
    ext_replaced = 0
    ext_failed = 0

    def replace_external_img(match):
        nonlocal ext_replaced, ext_failed
        full_attr = match.group(0)
        src_val = match.group(1)

        if src_val.startswith("data:") or src_val.startswith("cid:"):
            return full_attr

        if not any(domain in src_val for domain in EXTERNAL_IMG_DOMAINS):
            return full_attr

        result = fetch_image_as_base64(src_val)
        if result:
            mime_type, b64 = result
            ext_replaced += 1
            return f'src="data:{mime_type};base64,{b64}"'
        else:
            ext_failed += 1
            return 'src=""'

    html_content = re.sub(
        r'src=["\']([^"\']+)["\']',
        replace_external_img,
        html_content,
        flags=re.IGNORECASE
    )
    print(f"[INFO] 외부 이미지 인라인화: 성공 {ext_replaced}개 / 실패 {ext_failed}개")

    # ── STEP 5: 모바일 반응형 CSS 주입 ──────────────────────────────
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

    # ── STEP 6: 출력 ─────────────────────────────────────────────────
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
