"""
게임 데이터 모델.

모든 게임 상태, 캐릭터, 세계관, 세이브 데이터를 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GamePhase(Enum):
    """게임 진행 단계."""
    SETUP = "setup"
    PLAYING = "playing"
    COMBAT = "combat"
    GAME_OVER = "game_over"
    PAUSED = "paused"


@dataclass
class Character:
    """플레이어 캐릭터 정보."""
    name: str = ""
    char_class: str = ""
    description: str = ""


@dataclass
class WorldSetting:
    """세계관 설정."""
    name: str = ""
    genre: str = ""
    description: str = ""
    tone: str = ""
    system_rules: str = ""
    starting_scenario: str = ""


@dataclass
class GameState:
    """현재 게임 상태."""
    phase: GamePhase = GamePhase.SETUP
    character: Character = field(default_factory=Character)
    world: WorldSetting = field(default_factory=WorldSetting)
    turn_count: int = 0
    # 마지막 AI 응답에서 파싱된 상태 dict (hp, mp, location 등)
    current_state: dict = field(default_factory=dict)


@dataclass
class SaveData:
    """세이브 파일 데이터."""
    game_state: GameState = field(default_factory=GameState)
    history_summary: str = ""
    recent_exchanges: list = field(default_factory=list)
    timestamp: str = ""
    save_name: str = ""
