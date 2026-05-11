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
