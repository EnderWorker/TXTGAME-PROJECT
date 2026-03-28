"""
게임 엔진 모듈.

브릿지, 파서, 프롬프트 빌더, 히스토리, 상태 관리자를 조율하여
게임 루프의 핵심 로직을 제공한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import toml
from loguru import logger

from .history import NarrativeHistory
from .models import Character, GamePhase, GameState, WorldSetting
from .prompt_builder import PromptBuilder
from .response_parser import GameResponse, ResponseParser
from .state_manager import StateManager

if TYPE_CHECKING:
    from ..bridge.genspark_bridge import GensparkBridge


def load_worlds(config_dir: str = "config") -> list[WorldSetting]:
    """config/worlds/*.toml 파일들을 읽어 WorldSetting 목록을 반환한다.

    게임 엔진 인스턴스 없이도 세계관 목록을 불러올 수 있다.

    Args:
        config_dir: 설정 파일이 있는 디렉터리 경로

    Returns:
        로드된 WorldSetting 목록
    """
    worlds: list[WorldSetting] = []
    worlds_dir = Path(config_dir) / "worlds"

    if not worlds_dir.exists():
        logger.warning("worlds 디렉터리를 찾을 수 없습니다: {}", worlds_dir)
        return []

    for toml_file in sorted(worlds_dir.glob("*.toml")):
        try:
            data = toml.loads(toml_file.read_text(encoding="utf-8"))
            w_data = data.get("world", {})
            r_data = data.get("rules", {})
            world = WorldSetting(
                name=w_data.get("name", toml_file.stem),
                genre=w_data.get("genre", ""),
                description=w_data.get("description", "").strip(),
                tone=w_data.get("tone", ""),
                system_rules=r_data.get("system_rules", "").strip(),
                starting_scenario=w_data.get("starting_scenario", ""),
            )
            worlds.append(world)
            logger.debug("세계관 로드: '{}'", world.name)
        except Exception as exc:
            logger.warning("세계관 파일 로드 실패: {} — {}", toml_file, exc)

    return worlds


class GameEngine:
    """게임 루프의 핵심 로직을 조율하는 엔진."""

    def __init__(self, bridge: "GensparkBridge", config: dict) -> None:
        """
        Args:
            bridge: 초기화된 GensparkBridge 인스턴스
            config: settings.toml 전체 dict
        """
        self.bridge = bridge
        self.config = config
        self.parser = ResponseParser()
        self.prompt_builder = PromptBuilder()
        self.history = NarrativeHistory(
            max_exchanges=config.get("game", {}).get(
                "max_exchanges_before_compaction", 25
            )
        )
        self.state_manager = StateManager(
            save_dir=config.get("game", {}).get("save_dir", "saves")
        )

    # ── 게임 흐름 ────────────────────────────────────────────────────────────

    async def start_new_game(
        self, world: WorldSetting, character: Character
    ) -> GameResponse:
        """새 게임을 시작하고 첫 장면 응답을 반환한다.

        1. state_manager에 world, character 설정
        2. phase = PLAYING
        3. 새 대화 시작 및 모델 선택
        4. 시스템 프롬프트 전송
        5. 응답 파싱 및 상태 업데이트

        Args:
            world: 선택된 세계관
            character: 플레이어 캐릭터

        Returns:
            파싱된 첫 장면 GameResponse
        """
        logger.info(
            "새 게임 시작 — 세계관: '{}', 캐릭터: '{}' ({})",
            world.name,
            character.name,
            character.char_class,
        )

        # 상태 초기화
        self.state_manager.game_state = GameState(
            phase=GamePhase.PLAYING,
            character=character,
            world=world,
        )
        self.history = NarrativeHistory(
            max_exchanges=self.config.get("game", {}).get(
                "max_exchanges_before_compaction", 25
            )
        )

        # 새 대화 시작
        await self.bridge.start_new_conversation()

        # 모델 선택
        default_model = self.config.get("genspark", {}).get("default_model", "")
        if default_model:
            await self.bridge.select_model(default_model)

        # 시스템 프롬프트 전송
        system_prompt = self.prompt_builder.build_system_prompt(world, character)
        raw_response = await self.bridge.send_message(system_prompt)

        # 응답 파싱
        game_response = self.parser.parse(raw_response)
        self.state_manager.update_from_response(game_response)

        # 히스토리 기록
        self.history.add_exchange("system", system_prompt)
        self.history.add_exchange("assistant", raw_response)

        logger.info("새 게임 시작 완료 (서사 {}자)", len(game_response.narrative))
        return game_response

    async def process_player_action(self, player_input: str) -> GameResponse:
        """플레이어 행동을 처리하고 AI 응답을 반환한다.

        1. 컨텍스트 압축 필요 여부 확인
        2. 행동 프롬프트 생성 및 전송
        3. 응답 파싱
        4. 상태 업데이트, turn_count 증가
        5. 히스토리 기록

        Args:
            player_input: 플레이어 입력 텍스트 또는 선택지 번호

        Returns:
            파싱된 GameResponse
        """
        logger.info("플레이어 행동 처리: '{}'", player_input[:50])

        # 선택지 번호를 텍스트로 변환
        resolved_input = self._resolve_choice(player_input)

        # 컨텍스트 압축 필요 시 실행
        if self.history.needs_compaction():
            logger.info("컨텍스트 압축 필요 — compact 실행")
            resume_text = await self.history.compact(
                self.bridge, self.prompt_builder, self.state_manager
            )
            resume_response = self.parser.parse(resume_text)
            self.state_manager.update_from_response(resume_response)
            # 압축 후 플레이어 행동 즉시 처리
            # (재개 응답을 먼저 표시하려면 이 부분을 수정)

        # 행동 프롬프트 전송
        action_prompt = self.prompt_builder.build_action_prompt(resolved_input)
        raw_response = await self.bridge.send_message(action_prompt)

        # 파싱
        game_response = self.parser.parse(raw_response)
        self.state_manager.update_from_response(game_response)

        # 턴 카운트 증가
        self.state_manager.game_state.turn_count += 1

        # 히스토리 기록
        self.history.add_exchange("player", resolved_input)
        self.history.add_exchange("assistant", raw_response)

        logger.info(
            "턴 {} 완료 — 서사 {}자, 선택지 {}개",
            self.state_manager.game_state.turn_count,
            len(game_response.narrative),
            len(game_response.choices),
        )
        return game_response

    async def save_game(self, slot_name: str) -> str:
        """현재 게임을 세이브 파일로 저장한다.

        Args:
            slot_name: 세이브 슬롯 이름

        Returns:
            저장된 파일 경로
        """
        return self.state_manager.save_game(self.history, slot_name)

    async def load_game(self, slot_name: str) -> GameResponse:
        """세이브 파일에서 게임을 불러오고 재개 응답을 반환한다.

        1. 세이브 데이터 로드
        2. 히스토리 복원
        3. 새 대화에서 세션 재개 프롬프트 전송

        Args:
            slot_name: 로드할 세이브 슬롯 이름

        Returns:
            파싱된 재개 GameResponse
        """
        logger.info("게임 로드: '{}'", slot_name)

        save_data = self.state_manager.load_game(slot_name)

        # 히스토리 복원
        from .history import NarrativeHistory  # noqa: PLC0415
        self.history = NarrativeHistory.from_serializable({
            "summary": save_data.history_summary,
            "active_exchanges": save_data.recent_exchanges,
            "max_exchanges": self.history.max_exchanges,
        })

        # 새 대화에서 세션 재개
        await self.bridge.start_new_conversation()
        default_model = self.config.get("genspark", {}).get("default_model", "")
        if default_model:
            await self.bridge.select_model(default_model)

        gs = self.state_manager.game_state
        resume_prompt = self.prompt_builder.build_session_resume_prompt(
            world=gs.world,
            character=gs.character,
            summary=save_data.history_summary,
            current_state=gs.current_state,
        )
        raw_response = await self.bridge.send_message(resume_prompt)

        game_response = self.parser.parse(raw_response)
        self.state_manager.update_from_response(game_response)

        self.history.add_exchange("system", resume_prompt)
        self.history.add_exchange("assistant", raw_response)

        logger.info("게임 로드 완료 — 세계관: '{}'", gs.world.name)
        return game_response

    def get_available_worlds(self) -> list[WorldSetting]:
        """config/worlds/*.toml에서 세계관 목록을 반환한다."""
        return load_worlds()

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────────

    def _resolve_choice(self, player_input: str) -> str:
        """입력이 선택지 번호면 해당 선택지 텍스트로 변환한다.

        Args:
            player_input: 플레이어 입력 (숫자 또는 텍스트)

        Returns:
            해결된 입력 텍스트
        """
        stripped = player_input.strip()

        # 숫자 입력인지 확인
        if stripped.isdigit():
            idx = int(stripped) - 1
            last_response = self._get_last_choices()
            if 0 <= idx < len(last_response):
                resolved = last_response[idx]
                logger.debug("선택지 {} → '{}'", stripped, resolved)
                return resolved

        return stripped

    def _get_last_choices(self) -> list[str]:
        """히스토리에서 마지막 AI 응답의 선택지 목록을 반환한다."""
        for entry in reversed(self.history.active_exchanges):
            if entry.get("role") == "assistant":
                response = self.parser.parse(entry.get("content", ""))
                if response.choices:
                    return response.choices
        return []
