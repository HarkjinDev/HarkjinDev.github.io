# Atomic Red Team Detection Lab (웹 포트폴리오)

MITRE ATT&CK 기법을 Atomic Red Team으로 실행하고, Sysmon→Wazuh로 수집된
로그를 분석해 탐지 격차를 찾고 Sigma 룰로 메운 결과를 탐색형으로 보여주는
정적 웹 사이트.

## 구조

```
atomic-red-team/
├── index.html              # 메인: 기법 목록(전술별) + 요약 통계 + 핵심 발견
├── coverage.html           # 200개 배치 커버리지 분석 (전술별 탐지율·편향·Sigma대상)
├── detail.html             # 상세: ?id=T1070.004 로 기법별 로드
├── style.css               # 공통 스타일 (SOC 콘솔 테마)
├── data/
│   ├── techniques.json     # 전체 기법 요약 (목록·통계용)
│   ├── coverage.json       # 200개 배치 분석 집계 데이터
│   └── techniques/         # 기법별 상세 (명령·로그·판정·배운점)
│       └── T*.json
└── sigma/                  # Sigma 룰 원본 (상세 페이지에서 로드)
    └── PH1-*.yml
```

## 동작 방식

- 순수 정적(HTML/CSS/JS). 서버 코드 없음 → GitHub Pages에 그대로 배포 가능.
- `index.html`이 `data/techniques.json`을 읽어 전술별 카드 목록을 렌더.
- 카드 클릭 → `detail.html?id=<기법ID>` → 해당 기법 JSON + Sigma 파일을 fetch해 표시.
- 실행 기능 없음(전시 전용). 실제 실행·판정은 로컬 자동화(Phase 2)에서 수행.

## 기법 추가 방법

1. `data/techniques/T####.json` 파일 생성 (기존 파일 형식 참고)
2. `data/techniques.json`의 `techniques` 배열에 요약 항목 추가
3. (Sigma가 있으면) `sigma/`에 .yml 추가하고 상세 JSON의 `sigma_rules`에 파일명 기재

## GitHub Pages 배포

이 폴더는 `HarkjinDev/HarkjinDev.github.io` 저장소의 `/atomic-red-team` 경로에 둔다.
사용자 페이지(`HarkjinDev.github.io`)는 Pages가 기본 활성화되어 있으므로 커밋만 하면
아래 주소로 접근된다.

```
https://harkjindev.github.io/atomic-red-team/
```

주의: 로컬에서 `index.html`을 파일로 직접 열면 fetch가 CORS로 막힌다.
로컬 확인은 폴더에서 `python -m http.server` 후 `http://localhost:8000/` 로 접속.
GitHub Pages(HTTP 서빙)에서는 정상 동작한다.

## 데이터 출처

- 기법별 로그·판정: Phase 1 수동 분석 (Sysmon EID 1/11/13, Wazuh 내장 룰 반응)
- 판정(DETECTED/PARTIAL/NONE/BLOCKED): Phase 2 배치 자동 실행 결과
- Sigma 룰: Phase 1에서 작성 (각 룰에 근거·설계판단 주석 포함)
