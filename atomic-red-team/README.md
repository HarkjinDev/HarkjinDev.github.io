# Atomic Red Team Detection Lab

MITRE ATT&CK 기법을 **Atomic Red Team**으로 실행하고, **Sysmon → Wazuh**의 수집·탐지 결과를 분석하여 오분류, 오탐, 로그 수집 공백을 살펴본 탐지 엔지니어링 프로젝트입니다. GitHub Pages 포트폴리오에서 분석 결과와 Sigma 룰 원문을 확인할 수 있습니다.

**웹 포트폴리오:** https://harkjindev.github.io/atomic-red-team/index.html

## 웹페이지 구성

| 메뉴 / 페이지 | 주요 내용 |
|---|---|
| [접근 방식](https://harkjindev.github.io/atomic-red-team/index.html#approach) | Atomic Test 실행 → Sysmon/Wazuh 수집 → 탐지 평가 → Sigma 설계·검증 |
| [핵심 발견](https://harkjindev.github.io/atomic-red-team/index.html#insights) | T1087 오분류 편향, `__PSScriptPolicyTest` 오탐, 로그 미확인 원인 분석 |
| [심층 분석 사례 3건](https://harkjindev.github.io/atomic-red-team/index.html#cases) | T1082, T1053.005, T1547.001 카드 및 상세 페이지 |
| [Sigma 룰 라이브러리](https://harkjindev.github.io/atomic-red-team/index.html#sigma-library) | 현재 `sigma/`의 YAML 11개를 펼쳐서 열람, GitHub 원문 링크 |
| [커버리지 분석](https://harkjindev.github.io/atomic-red-team/coverage.html) | 200개 기법 배치 실행에 대한 전술별 탐지·오분류 및 공백 집계 |
| [AI SOC](https://harkjindev.github.io/atomic-red-team/soc.html) | 별도 AI SOC Agent 아키텍처 및 Slack ChatOps 예시 |
| [AI SOC (Docker Agent)](https://harkjindev.github.io/art-siem-ai-soc-demo/) | 별도 Docker Agent 기반 AI SOC 데모 프로젝트 포트폴리오 |

## 상세 분석 사례

아래 **세 기법만** 독립 상세 JSON을 갖고 있습니다. 각 페이지는 실행 명령, 관찰된 로그, Wazuh 내장 룰 판단, Sigma 파일과 룰 검증 기록을 보여줍니다.

| 기법 | 연구 주제 | 상세 페이지 | 상세 JSON |
|---|---|---|---|
| T1082 | System Information Discovery — systeminfo 정찰의 ATT&CK 오분류 | [보고서](detail.html?id=T1082) | [T1082.json](data/T1082.json) |
| T1053.005 | Scheduled Task — 예약작업 실행 대상 및 부모 프로세스 분석 | [보고서](detail.html?id=T1053.005) | [T1053.005.json](data/T1053.005.json) |
| T1547.001 | Registry Run Keys — Sysmon EID 13 및 지속성 탐지 | [보고서](detail.html?id=T1547.001) | [T1547.001.json](data/T1547.001.json) |

- `detail.html?id=T1082`는 `data/T1082.json`과 `data/techniques.json`을 함께 읽습니다.
- `data/techniques.json`에는 요약 기법 **10개**가 있으나, 개별 상세 JSON은 **3개만** 존재합니다. 따라서 다른 ID로 직접 이동하면 상세 데이터를 찾지 못할 수 있습니다.
- 세 상세 페이지에 기록된 Sigma/Wazuh 실동작 검증은 해당 사례의 실험 기록입니다. 모든 Sigma 파일의 개별 검증을 뜻하지 않습니다.

## Sigma 룰

현재 `sigma/`에는 YAML 룰 **11개**가 있습니다. 웹 메인의 **Sigma 룰** 섹션에서 개별 파일을 펼쳐 확인하거나 GitHub 원문을 열 수 있습니다.

| 범주 | 파일 |
|---|---|
| 정찰 연쇄 | `PH1-DiscoveryChain.yml`, `PH1-T1082-recon-chain.yml` |
| 예약작업 | `PH1-T1053.005-parent.yml`, `PH1-T1053.005-target.yml` |
| PowerShell | `PH1-T1059.001-encoded.yml` |
| 파일 삭제 | `PH1-T1070.004-delete.yml` |
| 도구 전송 | `PH1-T1105-known-tools.yml`, `PH1-T1105-temp-drop.yml`, `PH1-T1105-tuned.yml` |
| Rundll32 | `PH1-T1218.011-rundll32.yml` |
| Registry Run Keys | `PH1-T1547.001-runkey.yml` |

**유의:** Sigma YAML 파일 보유·구문 적합성·샘플 일치·실제 Wazuh 룰 재실행 검증은 서로 다른 수준입니다. 검증 여부는 상세 분석 기록을 참조하세요.

## 저장소 구조 (현재 GitHub 기준)

```text
atomic-red-team/
├── README.md
├── index.html                # 메인: 접근 방식 / 핵심 발견 / 심층 사례 3건 / Sigma 11개
├── detail.html               # 기법 ID로 data/<ID>.json 동적 조회
├── coverage.html             # 배치 커버리지 분석
├── soc.html                  # AI SOC Agent 소개와 Slack 재현 예시
├── style.css                 # 공통 다크 테마
├── data/
│   ├── techniques.json       # 10개 기법 요약 (상세 탐색용)
│   ├── T1082.json            # 상세 분석
│   ├── T1053.005.json        # 상세 분석
│   ├── T1547.001.json        # 상세 분석
│   ├── coverage.json         # 커버리지 집계
│   └── soc.json              # AI SOC 소개 데이터
├── sigma/                    # Sigma YAML 11개 및 readme.md
├── ai-soc/
│   ├── soc_ai_agent.py       # 별도 에이전트 Python 코드
│   └── readme.md
└── validate_sigma.py         # Sigma/Wazuh 검증용 Python 스크립트
```

## 사용 및 확인

프로젝트 소개 페이지는 **정적 HTML/CSS/JavaScript**로 구성되어 별도 백엔드 없이 GitHub Pages에서 열 수 있습니다. 브라우저에서 JSON과 YAML을 `fetch()`하므로 로컬 `file://`로 HTML을 열면 보안 정책상 데이터 조회가 실패할 수 있습니다. 로컬 확인 시 정적 웹 서버를 사용하세요.

```powershell
git clone https://github.com/HarkjinDev/HarkjinDev.github.io.git
cd HarkjinDev.github.io/atomic-red-team
python -m http.server 8000
```

접속 주소: http://localhost:8000/

## 데이터 출처 및 범위

- **Phase 1:** 개별 Atomic Test 수행 후 Sysmon 이벤트 및 Wazuh 룰 반응을 분석하고 Sigma 탐지 조건을 설계.
- **Phase 2:** 여러 ATT&CK 기법을 배치 실행한 집계 결과를 `coverage.json`에 정리.
- **웹 상세 보고서:** 세 JSON 파일에 기록된 개별 실험 결과를 표시.
- **AI SOC 관련 페이지:** Atomic Red Team 탐지 실험과 별도로 구성된 에이전트·ChatOps 데모 소개. 해당 페이지의 시각적 예시는 자동으로 운영 탐지·배포가 이루어졌음을 증명하지 않습니다.

이 저장소는 **연구·교육 및 포트폴리오 목적**입니다. 실제 환경의 탐지율이나 운영 적용을 보증하지 않습니다.
