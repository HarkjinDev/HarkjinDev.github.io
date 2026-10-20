# Atomic Red Team Detection Lab

MITRE ATT&CK 기법을 Atomic Red Team으로 실행하고, Sysmon→Wazuh로 수집된
로그를 분석해 탐지 격차를 찾고 Sigma 룰로 메운 결과를 탐색형으로 보여주는
정적 웹 사이트.

## 구조

```
atomic-red-team/
├── index.html              # 메인
├── coverage.html           # 200개 배치 커버리지 분석 (전술별 탐지율·편향·Sigma대상)
├── soc.html                # Slack AI SOC (L1/L2/L3 에이전트 아키텍처)
├── style.css               # 공통 스타일 (SOC 콘솔 테마)
├── data/
│   ├── techniques.json     # 전체 기법 요약 (목록·통계용)
│   ├── coverage.json       # 200개 배치 분석 집계 데이터
│   ├── soc.json            # AI SOC 아키텍처 데이터
│   └── techniques/         # 기법별 상세 (명령·로그·판정·배운점)
│       └── T*.json
└── sigma/                  # Sigma 룰 원본
```

## 데이터 출처

- 기법별 로그·판정: Phase 1 수동 분석 (Sysmon EID 1/11/13, Wazuh 내장 룰 반응)
- 판정(DETECTED/PARTIAL/NONE/BLOCKED): Phase 2 배치 자동 실행 결과
- Sigma 룰: Phase 1에서 작성 (각 룰에 근거·설계판단 주석 포함)
