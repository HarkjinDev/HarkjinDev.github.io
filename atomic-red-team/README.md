# Phase 3 (일부) — Sigma 룰 검증 자동화 (방법 A: 실제 Wazuh 적용)

> 작성한 Sigma 룰이 "실제로 작동하는가"를 증명하는 반자동 검증 파이프라인.
> Sigma → Wazuh 룰 변환 → 실제 적용 → 공격 재실행 → 커스텀 룰 발동 확인.

## 왜 직접 변환하는가

Wazuh는 pySigma의 공식 백엔드가 없다(2026 기준). 서드파티 변환기
(sigma_to_wazuh, SigWaz)는 완성도·의존성 리스크가 있어, 우리 로그 필드를
정확히 아는 상태에서 Sigma의 detection 블록을 Wazuh `<field>` 매처로
직접 변환했다. 이 방식이 서드파티 의존 없이 "검증 가능함"을 증명한다.

## 검증 흐름 (반자동)

```
[호스트]  ① Sigma → Wazuh 룰 XML 변환
          ② local_rules.xml 적용 + Manager 재시작       ← validate_sigma.py --apply-only 계열
[VM]      ③ 공격 수동 재실행 (Invoke-AtomicTest)
[호스트]  ④ 커스텀 룰(100001) 발동 여부 API 확인          ← validate_sigma.py --check-only
```

호스트는 docker로 Wazuh를 제어하고, 공격은 VM에서 실행되므로 적용/확인을
분리한 반자동 구조가 가장 안정적이다. (완전 자동화는 art_agent 원격 연동 시)

## 사용법

```powershell
py -m pip install pyyaml requests

# 1) 변환 미리보기 (Wazuh 불필요)
py validate_sigma.py --sigma sigma/PH1-T1082-recon-chain.yml --technique T1082 --dry-run

# 2) [호스트] 룰 적용 + 재시작
py validate_sigma.py --sigma sigma/PH1-T1082-recon-chain.yml --technique T1082

# 3) [VM] 공격 수동 실행
#    Invoke-AtomicTest T1082 -TestNumbers 1

# 4) [호스트] 발동 확인
py validate_sigma.py --check-only --technique T1082 --since 5
```

## 변환 규칙 (PoC 범위)

Sigma detection 블록 → Wazuh 룰:

| Sigma | Wazuh |
|---|---|
| `Image\|endswith: '\svc.exe'` | `<field name="win.eventdata.image" type="pcre2">\\svc\.exe$</field>` |
| `\|contains\|all: [A, B]` | 각각 별도 `<field>` (AND 조건) |
| 리스트 값 (모디파이어 하나) | `(?:A)\|(?:B)` (OR) |
| `condition: sel and not filter` | filter는 PoC 미반영(경고) |

필드 매핑: Image→win.eventdata.image, CommandLine→win.eventdata.commandLine,
ParentImage/ParentCommandLine/TargetFilename/TargetObject/Details/User 동일 패턴.

## 검증 적합도 (룰별)

| 검증 잘 됨 | 이유 |
|---|---|
| PH1-T1082-recon-chain | `\|all` → field AND 로 깔끔히 변환 |
| PH1-T1547.001-runkey | 단순 selection, EID13 명확 |
| PH1-T1053.005-target | schtasks 명령행 매칭 |

| 검증 제약 | 이유 |
|---|---|
| PH1-T1059.001-encoded | 복잡 정규식 — pcre2 변환 후 별도 확인 필요 |
| PH1-T1105-tuned | `not filter` 제외조건 — Wazuh는 처리 방식이 달라 PoC 미지원 |
| PH1-DiscoveryChain | OR 그룹/다중 selection 복잡 |

→ 데모는 검증 잘 되는 룰(T1082, T1547.001) 위주로 "검증 성공" 사례를 확보.

## 결론 (포트폴리오 기입용)

- **Sigma 룰 검증 자동화가 구현 가능함을 증명**했다. Wazuh 공식 백엔드가 없는
  제약 하에서, detection 블록을 Wazuh 룰로 직접 변환하고 실제 적용→재실행→
  발동 확인까지의 루프를 반자동으로 구성했다.
- 단순~중간 복잡도의 Sigma 룰은 이 방식으로 실제 SIEM 작동을 검증할 수 있다.
- 복잡한 정규식·제외조건·상관 룰은 변환 한계가 있어, 이후 AI Agent 기반
  검증(대량 배치 결과 대상)으로 확장 예정.

## 한계와 다음 단계

- PoC 변환기라 Sigma 전 기능을 커버하지 않음 (not/count/correlation 미지원)
- 완전 자동화하려면 art_agent 원격 실행 연동 필요
- 대량 검증은 AI Agent 단계에서: 배치로 나온 미탐/오분류 기법에 대해
  AI가 Sigma 생성 → 본 검증 루프로 자동 확인 → 사람 승인

---

## 검증 성공 기록 (2026-09-15)

### 결과
```
대상 Sigma: PH1-T1082-recon-chain.yml
변환 → Wazuh 룰(id 100100, level 12) → 적용 → 공격 재실행 → 확인
결과: ✅ rule100100 level12 :: systeminfo  (1건 탐지)
```

**작성한 Sigma 룰이 실제 Wazuh 환경에서 작동함이 증명됨.**
Sigma 검증 자동화가 개념 증명을 넘어 실동작함을 확인.

### 검증 과정에서 발견·해결한 이슈

**rule ID 충돌**: Wazuh 기본 local_rules.xml에 예제 룰이 이미 id 100001을
사용 중이었다. 커스텀 룰을 같은 100001로 추가하니 ID 중복으로 룰이 발동하지
않았다. 커스텀 룰 ID를 100100으로 변경하여 해결.
→ 교훈: 커스텀 룰 삽입 시 기본 예제 룰의 ID 대역을 피해야 한다.

### 검증된 파이프라인
1. Sigma YAML 파싱 → Wazuh `<field type=pcre2>` 매처로 변환 (|all은 field AND)
2. docker exec로 local_rules.xml 갱신 + wazuh-control restart
3. VM에서 Invoke-AtomicTest 재실행
4. Indexer API로 rule.id=100100 발동 조회 → 탐지 확인
