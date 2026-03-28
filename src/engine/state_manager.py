"""
게임 상태 관리 및 세이브/로드 모듈.

게임 상태(GameState)를 업데이트하고 JSON 파일로 저장/복원한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from .models import Character, GamePhase, GameState, SaveData, WorldSetting
from .response_parser import GameResponse

if TYPE_CHECKING:
    from .history import NarrativeHistory


class StateManager:
    """게임 상태를 관리하고 세이브/로드를 담당한다."""

    def __init__(self, save_dir: str = "saves") -> None:
        """
        Args:
            save_dir: 세이브 파일을 저장할 디렉터리
        """
        self.game_state: GameState = GameState()
        self.save_dir: Path = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    # ── 상태 업데이트 ────────────────────────────────────────────────────────

    def update_from_response(self, game_response: GameResponse) -> None:
        """AI 응답에서 파싱된 상태로 game_state.current_state를 업데이트한다.

        빈 dict이거나 None이면 무시한다.

        Args:
            game_response: 파싱된 게임 응답
        """
        if not game_response.state:
            logger.debug("업데이트할 상태 없음 — 스킵")
            return

        self.game_state.current_state.update(game_response.state)

        if game_response.is_game_over:
            self.game_state.phase = GamePhase.GAME_OVER
        elif game_response.is_combat:
            self.game_state.phase = GamePhase.COMBAT
        else:
            if self.game_state.phase in (GamePhase.COMBAT,):
                self.game_state.phase = GamePhase.PLAYING

        logger.debug(
            "상태 업데이트 — phase={}, hp={}/{}",
            self.game_state.phase.value,
            self.game_state.current_state.get("hp", "?"),
            self.game_state.current_state.get("max_hp", "?"),
        )

    # ── 세이브 / 로드 ────────────────────────────────────────────────────────

    def save_game(self, history: "NarrativeHistory", slot_name: str) -> str:
        """현재 게임 상태를 JSON 파일로 저장한다.

        Args:
            history: NarrativeHistory 인스턴스
            slot_name: 세이브 슬롯 이름 (파일명 접두사)

        Returns:
            저장된 파일 경로
        """
        # 파일명에 사용할 수 없는 문자 제거
        safe_name = "".join(c for c in slot_name if c.isalnum() or c in "-_ ")
        safe_name = safe_name.strip() or "save"

        file_path = self.save_dir / f"{safe_name}.json"

        save_data = SaveData(
            game_state=self.game_state,
            history_summary=history.summary,
            recent_exchanges=history.active_exchanges,
            timestamp=datetime.now().isoformat(),
            save_name=slot_name,
        )

        data_dict = {
            "save_name": save_data.save_name,
            "timestamp": save_data.timestamp,
            "history_summary": save_data.history_summary,
            "recent_exchanges": save_data.recent_exchanges,
            "game_state": {
                "phase": save_data.game_state.phase.value,
                "turn_count": save_data.game_state.turn_count,
                "current_state": save_data.game_state.current_state,
                "character": {
                    "name": save_data.game_state.character.name,
                    "char_class": save_data.game_state.character.char_class,
                    "description": save_data.game_state.character.description,
                },
                "world": {
                    "name": save_data.game_state.world.name,
                    "genre": save_data.game_state.world.genre,
                    "description": save_data.game_state.world.description,
                    "tone": save_data.game_state.world.tone,
                    "system_rules": save_data.game_state.world.system_rules,
                    "starting_scenario": save_data.game_state.world.starting_scenario,
                },
            },
        }

        file_path.write_text(
            json.dumps(data_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("게임 저장 완료: {}", file_path)
        return str(file_path)

    def load_game(self, slot_name: str) -> SaveData:
        """세이브 파일을 로드하여 SaveData를 반환한다.

        Args:
            slot_name: 세이브 슬롯 이름

        Returns:
            로드된 SaveData

        Raises:
            FileNotFoundError: 세이브 파일이 없는 경우
            ValueError: 파일 형식이 잘못된 경우
        """
        safe_name = "".join(c for c in slot_name if c.isalnum() or c in "-_ ").strip()
        file_path = self.save_dir / f"{safe_name}.json"

        if not file_path.exists():
            raise FileNotFoundError(f"세이브 파일 없음: {file_path}")

        try:
            data_dict = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"세이브 파일 파싱 실패: {e}") from e

        gs_dict = data_dict.get("game_state", {})
        char_dict = gs_dict.get("character", {})
        world_dict = gs_dict.get("world", {})

        character = Character(
            name=char_dict.get("name", ""),
            char_class=char_dict.get("char_class", ""),
            description=char_dict.get("description", ""),
        )
        world = WorldSetting(
            name=world_dict.get("name", ""),
            genre=world_dict.get("genre", ""),
            description=world_dict.get("description", ""),
            tone=world_dict.get("tone", ""),
            system_rules=world_dict.get("system_rules", ""),
            starting_scenario=world_dict.get("starting_scenario", ""),
        )

        phase_str = gs_dict.get("phase", GamePhase.PLAYING.value)
        try:
            phase = GamePhase(phase_str)
        except ValueError:
            phase = GamePhase.PLAYING

        game_state = GameState(
            phase=phase,
            character=character,
            world=world,
            turn_count=gs_dict.get("turn_count", 0),
            current_state=gs_dict.get("current_state", {}),
        )

        save_data = SaveData(
            game_state=game_state,
            history_summary=data_dict.get("history_summary", ""),
            recent_exchanges=data_dict.get("recent_exchanges", []),
            timestamp=data_dict.get("timestamp", ""),
            save_name=data_dict.get("save_name", slot_name),
        )

        # game_state도 업데이트
        self.game_state = game_state

        logger.info("게임 로드 완료: {} (턴 {})", slot_name, game_state.turn_count)
        return save_data

    def list_saves(self) -> list[dict]:
        """저장된 세이브 파일 목록을 반환한다.

        Returns:
            [{name, character, world, timestamp, turn_count}] 형태의 목록
        """
        saves: list[dict] = []
        for json_file in sorted(self.save_dir.glob("*.json")):
            # Genspark 세션 파일은 제외
            if "session" in json_file.name.lower():
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                gs = data.get("game_state", {})
                saves.append({
                    "name": data.get("save_name", json_file.stem),
                    "file": json_file.stem,
                    "character": gs.get("character", {}).get("name", "?"),
                    "char_class": gs.get("character", {}).get("char_class", "?"),
                    "world": gs.get("world", {}).get("name", "?"),
                    "timestamp": data.get("timestamp", "")[:19].replace("T", " "),
                    "turn_count": gs.get("turn_count", 0),
                })
            except Exception as exc:
                logger.warning("세이브 파일 파싱 실패: {} — {}", json_file, exc)

        return saves

    def delete_save(self, slot_name: str) -> bool:
        """세이브 파일을 삭제한다.

        Args:
            slot_name: 삭제할 세이브 슬롯 이름

        Returns:
            삭제 성공이면 True
        """
        safe_name = "".join(c for c in slot_name if c.isalnum() or c in "-_ ").strip()
        file_path = self.save_dir / f"{safe_name}.json"

        if file_path.exists():
            file_path.unlink()
            logger.info("세이브 삭제: {}", file_path)
            return True

        logger.warning("삭제할 세이브 없음: {}", file_path)
        return False
