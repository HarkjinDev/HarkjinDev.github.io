"""
validate_sigma.py  —  Sigma 룰 검증 자동화 (방법 A: 실제 Wazuh 적용)

Phase 1에서 작성한 Sigma 룰이 실제로 작동하는지 증명한다:
  ① Sigma 룰 → Wazuh local_rules.xml 형식으로 변환
  ② 변환된 룰을 Wazuh Manager 컨테이너에 적용
  ③ Wazuh 재시작 (룰 로드)
  ④ 해당 공격 재실행 (ART)
  ⑤ 방금 만든 커스텀 룰(rule_id)이 실제로 탐지했는지 API로 확인

Wazuh는 pySigma 공식 백엔드가 없으므로, 우리 로그 필드를 정확히 아는 상태에서
Sigma의 detection 블록을 Wazuh <field> 매처로 직접 변환한다.

사용법 (호스트에서, Docker Wazuh 제어 가능한 환경):
  py validate_sigma.py --sigma sigma/PH1-T1082-recon-chain.yml --technique T1082 --test 1
  py validate_sigma.py --sigma sigma/PH1-T1059.001-encoded.yml --technique T1059.001 --inline encoded_ps

전제:
  - Docker Wazuh 실행 중 (single-node)
  - VM에 ART, run_detection_test.py 로직 접근 가능
  - py -m pip install pyyaml requests

주의: 이 스크립트는 개념 증명(PoC)이다. Wazuh 룰 문법의 모든 Sigma 기능을
      커버하지 않으며, 지원하는 detection 패턴은 아래 SUPPORTED 참고.
"""
import argparse
import subprocess
import time
import datetime
import re
import yaml
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 설정 ──────────────────────────────────────────────
WAZUH_INDEXER = "https://localhost:9200"
WAZUH_USER = "admin"
WAZUH_PASS = "SecretPassword"
WAZUH_CONTAINER = "single-node-wazuh.manager-1"
LOCAL_RULES_PATH = "/var/ossec/etc/rules/local_rules.xml"
CUSTOM_RULE_ID = "100100"       # 검증용 커스텀 룰 ID (기본 예제 100001과 충돌 회피)
CUSTOM_RULE_LEVEL = "12"

# Sigma 필드 → Wazuh 디코딩 필드 매핑 (Sysmon eventchannel)
FIELD_MAP = {
    "Image": "win.eventdata.image",
    "CommandLine": "win.eventdata.commandLine",
    "ParentImage": "win.eventdata.parentImage",
    "ParentCommandLine": "win.eventdata.parentCommandLine",
    "TargetFilename": "win.eventdata.targetFilename",
    "TargetObject": "win.eventdata.targetObject",
    "Details": "win.eventdata.details",
    "User": "win.eventdata.user",
}

"""
SUPPORTED (PoC 범위):
  - selection 블록의 단순 필드 매칭
  - |contains, |endswith, |all 모디파이어
  - condition: 단일 selection, 'A and B', 'A and not B'
미지원(경고 후 스킵): |re 복잡 정규식, count(), 다중 correlation
"""


def sigma_value_to_regex(field_expr, value):
    """Sigma 필드+모디파이어+값 → Wazuh field regex (PCRE)"""
    parts = field_expr.split("|")
    field = parts[0]
    mods = parts[1:]
    wazuh_field = FIELD_MAP.get(field)
    if not wazuh_field:
        return None, f"필드 미매핑: {field}"

    values = value if isinstance(value, list) else [value]
    is_all = "all" in mods

    regexes = []
    for v in values:
        v = str(v)
        esc = re.escape(v)
        if "endswith" in mods:
            regexes.append(f"{esc}$")
        elif "startswith" in mods:
            regexes.append(f"^{esc}")
        elif "contains" in mods:
            regexes.append(esc)
        elif "re" in mods:
            regexes.append(v)   # 원본 정규식 그대로 (검증 필요)
        else:
            regexes.append(esc)

    return (wazuh_field, regexes, is_all), None


def convert_sigma_to_wazuh(sigma_path):
    """Sigma YAML → Wazuh 룰 XML 문자열. (xml, 경고목록) 반환"""
    with open(sigma_path, encoding="utf-8") as f:
        rule = yaml.safe_load(f)

    detection = rule.get("detection", {})
    condition = detection.get("condition", "")
    title = rule.get("title", "Converted Sigma Rule")
    warnings = []

    # PoC: 단순 condition만 지원
    if "count(" in condition or "|" in condition.replace("|contains", "").replace("|all", ""):
        pass  # 아래에서 개별 처리

    # selection 블록들 수집 (filter 제외 처리)
    selections = {k: v for k, v in detection.items() if k != "condition"}

    field_matches = []   # (wazuh_field, [regex], is_all)
    negate_matches = []  # not 조건
    for sel_name, sel_body in selections.items():
        if not isinstance(sel_body, dict):
            warnings.append(f"복합 selection '{sel_name}' 스킵 (PoC 미지원)")
            continue
        is_negated = ("not " + sel_name) in condition or sel_name.startswith("filter")
        for field_expr, value in sel_body.items():
            conv, err = sigma_value_to_regex(field_expr, value)
            if err:
                warnings.append(err)
                continue
            if is_negated:
                negate_matches.append(conv)
            else:
                field_matches.append(conv)

    # Wazuh 룰 XML 생성
    lines = [f'<group name="sigma_validation,">']
    lines.append(f'  <rule id="{CUSTOM_RULE_ID}" level="{CUSTOM_RULE_LEVEL}">')
    lines.append(f'    <if_group>sysmon</if_group>')
    for wfield, regexes, is_all in field_matches:
        # is_all 이면 각 regex를 개별 field로 (AND), 아니면 | 로 묶어 OR
        if is_all:
            for rgx in regexes:
                lines.append(f'    <field name="{wfield}" type="pcre2">{rgx}</field>')
        else:
            joined = "|".join(f"(?:{r})" for r in regexes)
            lines.append(f'    <field name="{wfield}" type="pcre2">{joined}</field>')
    lines.append(f'    <description>[SIGMA-VALIDATION] {title}</description>')
    lines.append(f'  </rule>')
    lines.append(f'</group>')
    xml = "\n".join(lines)

    if negate_matches:
        warnings.append("not/filter 조건은 PoC에서 룰에 반영 안 됨 (Wazuh는 별도 처리 필요)")

    return xml, warnings


def apply_rule_to_wazuh(xml):
    """변환된 룰을 컨테이너의 local_rules.xml에 추가하고 재시작"""
    # 기존 local_rules.xml 백업 후, 검증 룰 append
    # (기존 내용 유지를 위해 </group> 앞이 아니라 파일 끝에 새 group 추가)
    cmd_read = ["docker", "exec", WAZUH_CONTAINER, "cat", LOCAL_RULES_PATH]
    existing = subprocess.run(cmd_read, capture_output=True, text=True).stdout

    # 이전 검증 룰 제거 (CUSTOM_RULE_ID 포함 group)
    cleaned = re.sub(r'<group name="sigma_validation,">.*?</group>', "",
                     existing, flags=re.DOTALL).strip()
    new_content = (cleaned + "\n" + xml).strip() + "\n"

    # 컨테이너에 쓰기 (stdin으로 전달)
    write = subprocess.run(
        ["docker", "exec", "-i", WAZUH_CONTAINER, "sh", "-c",
         f"cat > {LOCAL_RULES_PATH}"],
        input=new_content, text=True, capture_output=True,
    )
    if write.returncode != 0:
        return False, write.stderr

    # Wazuh Manager 재시작
    print("[*] Wazuh Manager 재시작 (룰 로드)...")
    restart = subprocess.run(
        ["docker", "exec", WAZUH_CONTAINER, "/var/ossec/bin/wazuh-control", "restart"],
        capture_output=True, text=True, timeout=120,
    )
    return restart.returncode == 0, restart.stdout + restart.stderr


def check_custom_rule_fired(start_time, window=120):
    """커스텀 룰(CUSTOM_RULE_ID)이 실제 발동했는지 API 확인"""
    gte = (start_time - datetime.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S")
    lte = (start_time + datetime.timedelta(seconds=window)).strftime("%Y-%m-%dT%H:%M:%S")
    query = {
        "size": 10,
        "query": {"bool": {"must": [
            {"range": {"timestamp": {"gte": gte, "lte": lte}}},
            {"match": {"rule.id": CUSTOM_RULE_ID}},
        ]}},
    }
    resp = requests.get(f"{WAZUH_INDEXER}/wazuh-alerts-*/_search",
                        auth=(WAZUH_USER, WAZUH_PASS), json=query,
                        verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json().get("hits", {}).get("hits", [])


def main():
    ap = argparse.ArgumentParser(description="Sigma 룰 검증 (방법 A: 실제 Wazuh 적용, 반자동)")
    ap.add_argument("--sigma", help="검증할 Sigma 룰 파일 (apply 단계)")
    ap.add_argument("--technique", help="확인할 기법 ID (check 단계 표시용)")
    ap.add_argument("--wait", type=int, default=20)
    ap.add_argument("--window", type=int, default=300, help="check 시 조회 시간창(초)")

    # 반자동 3모드
    ap.add_argument("--dry-run", action="store_true", help="변환만 출력, 적용 안 함")
    ap.add_argument("--apply-only", action="store_true",
                    help="[호스트] Sigma 변환 → Wazuh 적용·재시작 후 종료 (공격은 VM에서 수동)")
    ap.add_argument("--check-only", action="store_true",
                    help="[호스트] 커스텀 룰 발동 여부만 확인 (공격 수동 실행 후)")
    ap.add_argument("--since", type=int, default=10,
                    help="check 시 '몇 분 전부터' 조회 (기본 10분)")
    args = ap.parse_args()

    # ── 확인 전용 모드 ────────────────────────────────
    if args.check_only:
        start = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) \
                - datetime.timedelta(minutes=args.since)
        print(f"[check] 최근 {args.since}분 내 커스텀 룰({CUSTOM_RULE_ID}) 발동 확인")
        try:
            hits = check_custom_rule_fired(start, args.since * 60)
            if hits:
                print(f"\n  ✅ 검증 성공 — 커스텀 Sigma 룰이 {len(hits)}건 탐지")
                for h in hits[:5]:
                    r = h["_source"].get("rule", {})
                    ed = h["_source"].get("data", {}).get("win", {}).get("eventdata", {})
                    ctx = ed.get("commandLine") or ed.get("targetObject") or ed.get("targetFilename") or ""
                    print(f"     rule{r.get('id')} level{r.get('level')} :: {str(ctx)[:70]}")
                print(f"\n  → 이 Sigma 룰은 실제 Wazuh 환경에서 작동함이 증명됨.")
            else:
                print(f"\n  ❌ 미발동 — 커스텀 룰이 잡지 못함")
                print(f"     점검: (1) 공격을 실행했는가 (2) 필드 매핑 (3) 정규식 (4) --since 시간")
        except Exception as e:
            print(f"[!] 확인 실패: {e}")
        return

    # ── 변환은 apply/dry-run 공통 ─────────────────────
    if not args.sigma:
        print("[!] --sigma 파일이 필요합니다 (apply/dry-run)")
        return

    print(f"{'='*55}\n[변환] Sigma → Wazuh: {args.sigma}")
    xml, warnings = convert_sigma_to_wazuh(args.sigma)
    print(xml)
    for w in warnings:
        print(f"  [warn] {w}")

    if args.dry_run:
        print("\n[dry-run] 변환만 수행. 종료.")
        return

    # ── 적용 전용 모드 (반자동) ───────────────────────
    print(f"\n[적용] Wazuh local_rules.xml 갱신 + 재시작")
    ok, msg = apply_rule_to_wazuh(xml)
    if not ok:
        print(f"[!] 적용 실패: {msg}")
        return
    print("[*] 적용 완료. 룰 로드 대기 15초...")
    time.sleep(15)

    print(f"\n{'='*55}")
    print(f"  다음 단계 (수동):")
    print(f"  1) VM에서 공격 실행:")
    if args.technique:
        print(f"       Invoke-AtomicTest {args.technique} -TestNumbers <N>")
    print(f"  2) 잠시 후 호스트에서 발동 확인:")
    print(f"       py validate_sigma.py --check-only --technique {args.technique or '<TID>'}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
