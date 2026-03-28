# Text RPG Engine

AI 기반 텍스트 RPG 데스크톱 앱.
Genspark(chat.genspark.ai)의 무제한 AI 채팅을 Playwright 브라우저 자동화로 연동하여,
AI 게임마스터와 함께하는 몰입감 있는 텍스트 어드벤처를 즐길 수 있다.

## 요구사항

- Windows 10/11
- Python 3.11+
- Genspark 계정 (무료 또는 유료)
- 인터넷 연결

## 설치 및 실행

### 소스에서 실행

```bash
# 1. 의존 패키지 설치
pip install -r requirements.txt

# 2. Playwright Chromium 브라우저 설치 (필수, 약 150MB, 최초 1회)
playwright install chromium

# 3. 실행
python main.py
```

### 최초 실행 시 로그인

세션 파일이 없으면 브라우저가 자동으로 화면에 표시되며 콘솔에 다음 메시지가 출력된다.

```
===== Genspark 로그인이 필요합니다 =====
브라우저에서 로그인을 완료한 후
이 터미널에서 Enter를 눌러주세요.
```

Genspark에 로그인한 후 터미널에서 Enter를 누르면 세션이 저장되어 이후 재로그인이 필요 없다.

## 게임 조작

| 입력 | 동작 |
|------|------|
| 숫자 (1, 2, 3...) | 해당 번호 선택지 선택 |
| 자유 텍스트 | 원하는 행동 직접 입력 |
| `F1` | 도움말 |
| `F5` | 게임 저장 |
| `F9` | 게임 불러오기 |
| `ESC` | 일시 정지 메뉴 |

## 빌드 (.exe)

```bash
# 가벼운 배포 (첫 실행 시 Chromium 자동 다운로드)
python build.py --mode light

# Chromium 포함 배포 (오프라인 가능)
python build.py --mode full
```

결과물: `dist/TextRPG/TextRPG.exe`

## 프로젝트 구조

```
text-rpg/
├── main.py                       # 엔트리포인트
├── build.py                      # PyInstaller 빌드 스크립트
├── requirements.txt
├── config/
│   ├── settings.toml             # 전체 설정
│   └── worlds/                   # 세계관 설정
│       ├── fantasy.toml          # 중세 판타지
│       ├── cyberpunk.toml        # 사이버펑크
│       └── zombie.toml           # 좀비 서바이벌
├── src/
│   ├── bridge/
│   │   ├── selectors.py          # DOM 셀렉터 ← UI 변경 시 여기만 수정
│   │   ├── session_manager.py    # 쿠키/스토리지 저장·복원
│   │   └── genspark_bridge.py    # Playwright 브릿지 핵심
│   ├── engine/
│   │   ├── models.py             # 데이터 모델
│   │   ├── response_parser.py    # AI 응답 파서
│   │   ├── prompt_builder.py     # 프롬프트 생성기
│   │   ├── history.py            # 히스토리 / 컨텍스트 압축
│   │   ├── state_manager.py      # 상태 관리 / 세이브·로드
│   │   └── game_engine.py        # 게임 루프 조율
│   └── ui/
│       ├── styles.tcss           # 다크 테마 CSS
│       ├── widgets.py            # 커스텀 Textual 위젯
│       ├── screens.py            # 게임 화면들
│       └── tui_app.py            # 메인 앱 클래스
├── saves/                        # 세이브 파일
└── logs/                         # 로그 및 실패 스크린샷
```

## 커스텀 세계관 추가

`config/worlds/` 에 `.toml` 파일을 추가하면 게임 설정 화면에 자동으로 나타난다.

```toml
[world]
name = "세계관 이름"
genre = "장르"
tone = "분위기"
description = """
세계관 설명 (여러 줄 가능)
"""
starting_scenario = "시작 장면 설명"

[rules]
system_rules = """
- 규칙 1
- 규칙 2
"""
```

## 주요 설정 (config/settings.toml)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `genspark.headless` | `true` | `false`로 바꾸면 브라우저가 화면에 표시 (디버깅) |
| `genspark.response_timeout` | `120` | AI 응답 대기 최대 시간 (초) |
| `genspark.response_stable_duration` | `3` | 텍스트 안정화 판정 기준 (초) |
| `game.max_exchanges_before_compaction` | `25` | 컨텍스트 자동 압축 기준 턴 수 |

## 테스트

```bash
# ResponseParser 단위 테스트 (인터넷 불필요)
python tests/test_parser.py

# Bridge 통합 테스트 (Genspark 로그인 필요)
python tests/test_bridge.py
```

## 문제 해결

| 문제 | 해결 방법 |
|------|-----------|
| 셀렉터 오류 | Genspark UI 업데이트 시 `src/bridge/selectors.py` 수정 |
| 응답이 느리거나 timeout | `config/settings.toml`의 `response_timeout` 값 증가 |
| 로그인 실패 | `saves/genspark_session.json` 삭제 후 재실행 |
| 자세한 로그 확인 | `logs/app.log` 파일 확인 |
| 실패 스크린샷 | `logs/*.png` 파일 확인 |
