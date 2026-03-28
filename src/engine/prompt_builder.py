"""
AI 프롬프트 빌더 모듈.

게임 상황에 맞는 프롬프트를 생성한다:
- 새 게임 시작 시스템 프롬프트
- 플레이어 행동 전달 프롬프트
- 세션 재개 프롬프트 (세이브 로드 / 컨텍스트 압축 후)
- 히스토리 요약 요청 프롬프트
"""

from __future__ import annotations

import json

from .models import Character, WorldSetting


class PromptBuilder:
    """게임 상황별 AI 프롬프트를 생성한다."""

    # 응답 형식 안내문 (모든 프롬프트에 공통 포함)
    _FORMAT_GUIDE: str = """
## 응답 형식 (매 응답마다 반드시 이 형식을 정확히 지켜주세요)

[서사]
현재 상황을 생생하게 묘사합니다. 2~4문단으로 작성합니다.
플레이어의 오감을 자극하는 묘사를 포함합니다.
NPC의 대사는 따옴표로 감싸서 표현합니다.

[상태]
```json
{
    "hp": 숫자, "max_hp": 숫자,
    "mp": 숫자, "max_mp": 숫자,
    "level": 숫자, "exp": 숫자,
    "gold": 숫자,
    "location": "현재 위치",
    "inventory": ["아이템1", "아이템2"],
    "effects": ["상태효과"],
    "quest": "현재 퀘스트"
}
```

[선택지]
1. 선택지1
2. 선택지2
3. 선택지3
(2~4개의 선택지를 제시합니다. 플레이어는 이 외에 자유 행동도 가능합니다.)

※ 게임 오버 시에만 마지막에 [GAME_OVER] 태그를 추가합니다.
※ 전투 진입 시 [COMBAT] 태그를 추가합니다.
"""

    def build_system_prompt(
        self, world: WorldSetting, character: Character
    ) -> str:
        """새 게임 시작 시 첫 번째 메시지를 생성한다.

        게임마스터 역할, 세계관, 캐릭터, 응답 형식, 시작 시나리오를 모두 포함한다.

        Args:
            world: 선택된 세계관 설정
            character: 플레이어 캐릭터 정보

        Returns:
            완성된 시스템 프롬프트 문자열
        """
        return f"""당신은 텍스트 RPG 게임의 게임마스터(GM)입니다. 아래 규칙을 반드시 따라주세요.

## 세계관
- 이름: {world.name}
- 장르: {world.genre}
- 분위기: {world.tone}
- 설명: {world.description.strip()}

## 플레이어 캐릭터
- 이름: {character.name}
- 클래스: {character.char_class}

## 게임 규칙
{world.system_rules.strip()}
{self._FORMAT_GUIDE}
## 시작
{world.starting_scenario}

위 설정으로 게임을 시작합니다. 첫 장면을 묘사해주세요.
캐릭터의 초기 스탯을 설정하고 (HP 100, MP 50, 레벨 1, 경험치 0, 골드 50) [상태]에 포함해주세요."""

    def build_action_prompt(self, player_input: str) -> str:
        """플레이어 행동을 AI에게 전달하는 프롬프트를 생성한다.

        Args:
            player_input: 플레이어가 입력한 행동 텍스트

        Returns:
            행동 전달 프롬프트
        """
        return (
            f"{player_input}\n\n"
            "(응답 형식: [서사], [상태](JSON), [선택지]를 반드시 유지해주세요)"
        )

    def build_session_resume_prompt(
        self,
        world: WorldSetting,
        character: Character,
        summary: str,
        current_state: dict,
    ) -> str:
        """세션 재개 시 프롬프트를 생성한다.

        세이브 로드 또는 컨텍스트 압축 후 새 대화를 시작할 때 사용한다.

        Args:
            world: 세계관 설정
            character: 캐릭터 정보
            summary: 지금까지의 이야기 요약
            current_state: 현재 캐릭터 상태 dict

        Returns:
            세션 재개 프롬프트
        """
        state_json = json.dumps(current_state, ensure_ascii=False, indent=4)

        return f"""당신은 텍스트 RPG 게임의 게임마스터(GM)입니다. 아래 규칙을 반드시 따라주세요.

## 세계관
- 이름: {world.name}
- 장르: {world.genre}
- 분위기: {world.tone}
- 설명: {world.description.strip()}

## 플레이어 캐릭터
- 이름: {character.name}
- 클래스: {character.char_class}

## 게임 규칙
{world.system_rules.strip()}
{self._FORMAT_GUIDE}
## 지금까지의 이야기 요약
{summary.strip() if summary else "(이전 기록 없음)"}

## 현재 캐릭터 상태
```json
{state_json}
```

위 상황에서 이어서 진행해주세요.
현재 상황을 간단히 상기시키며 다음 장면을 묘사해주세요."""

    def build_summary_request(self, exchanges: list[dict]) -> str:
        """히스토리 압축용 요약 요청 프롬프트를 생성한다.

        Args:
            exchanges: 요약할 대화 교환 목록 (각 항목: {role, content, timestamp})

        Returns:
            요약 요청 프롬프트
        """
        # 대화 기록을 읽기 쉬운 텍스트로 변환
        lines: list[str] = []
        for ex in exchanges:
            role = ex.get("role", "unknown")
            content = ex.get("content", "")
            if role == "player":
                lines.append(f"[플레이어] {content}")
            elif role == "assistant":
                lines.append(f"[GM] {content[:500]}{'...' if len(content) > 500 else ''}")
            elif role == "system":
                lines.append(f"[시스템] {content[:200]}{'...' if len(content) > 200 else ''}")

        record_text = "\n\n".join(lines)

        return f"""다음은 텍스트 RPG의 진행 기록입니다.
핵심 사건, 중요한 선택, 그 결과를 중심으로 3~5문단으로 요약해주세요.
중요한 NPC 이름, 획득한 아이템, 퀘스트 진행도는 반드시 포함해주세요.
태그 형식([서사], [상태] 등)은 사용하지 말고 일반 문장으로 요약해주세요.

[진행 기록]
{record_text}

요약:"""
