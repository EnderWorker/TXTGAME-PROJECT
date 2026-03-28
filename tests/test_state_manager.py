"""
StateManager 단위 테스트.

tempfile.mkdtemp()으로 임시 디렉터리를 사용하므로 실제 saves/ 폴더에 영향을 주지 않는다.

실행:
    python tests/test_state_manager.py       # 직접 실행
    pytest tests/test_state_manager.py -v    # pytest 사용
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows cp949 환경에서 유니코드 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.engine.models import Character, GamePhase, GameState, WorldSetting
from src.engine.response_parser import GameResponse, ResponseParser
from src.engine.state_manager import StateManager


def _make_state_manager(tmp_dir: str) -> StateManager:
    """임시 디렉터리를 사용하는 StateManager를 생성한다."""
    sm = StateManager(save_dir=tmp_dir)
    sm.game_state.character = Character(name="테스트용사", char_class="전사")
    sm.game_state.world = WorldSetting(
        name="테스트 왕국",
        genre="판타지",
        description="테스트용 세계관",
        tone="진지함",
        system_rules="- 테스트 규칙",
        starting_scenario="테스트 시작",
    )
    return sm


def _make_history_stub():
    """테스트용 NarrativeHistory 스텁."""
    from src.engine.history import NarrativeHistory
    h = NarrativeHistory()
    h.summary = "테스트 요약"
    h.active_exchanges = [{"role": "player", "content": "안녕", "timestamp": "2024-01-01T00:00:00"}]
    return h


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 1: update_from_response — 정상 상태 갱신
# ══════════════════════════════════════════════════════════════
def test_update_from_response_normal() -> None:
    """AI 응답 상태 dict로 game_state.current_state가 갱신된다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        response = GameResponse(
            narrative="전투 시작!",
            state={"hp": 80, "max_hp": 100, "gold": 50},
        )
        sm.update_from_response(response)

        assert sm.game_state.current_state.get("hp") == 80
        assert sm.game_state.current_state.get("gold") == 50
        assert sm.game_state.phase != GamePhase.GAME_OVER
    print("  ✅ test_update_from_response_normal 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 2: update_from_response — GAME_OVER 페이즈 전환
# ══════════════════════════════════════════════════════════════
def test_update_from_response_game_over() -> None:
    """is_game_over=True 이면 phase가 GAME_OVER로 전환된다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        response = GameResponse(
            narrative="쓰러졌다...",
            state={"hp": 0},
            is_game_over=True,
        )
        sm.update_from_response(response)

        assert sm.game_state.phase == GamePhase.GAME_OVER
    print("  ✅ test_update_from_response_game_over 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 3: save_game → 파일 생성 확인
# ══════════════════════════════════════════════════════════════
def test_save_game_creates_file() -> None:
    """save_game() 호출 시 지정한 이름의 JSON 파일이 생성된다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        history = _make_history_stub()

        path_str = sm.save_game(history, "슬롯1")
        saved_path = Path(path_str)

        assert saved_path.exists(), f"파일이 생성되지 않음: {saved_path}"
        assert saved_path.suffix == ".json"
    print("  ✅ test_save_game_creates_file 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 4: save_game → load_game 왕복 테스트
# ══════════════════════════════════════════════════════════════
def test_save_load_roundtrip() -> None:
    """저장 후 로드 시 캐릭터 이름, 세계관, 턴 수가 복원된다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        sm.game_state.turn_count = 7
        history = _make_history_stub()

        sm.save_game(history, "왕복테스트")

        sm2 = StateManager(save_dir=tmp)
        save_data = sm2.load_game("왕복테스트")

        assert save_data.game_state.character.name == "테스트용사"
        assert save_data.game_state.world.name == "테스트 왕국"
        assert save_data.game_state.turn_count == 7
        assert save_data.history_summary == "테스트 요약"
    print("  ✅ test_save_load_roundtrip 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 5: list_saves — 파일 목록 조회
# ══════════════════════════════════════════════════════════════
def test_list_saves() -> None:
    """저장된 세이브 파일 목록을 올바르게 반환한다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        history = _make_history_stub()

        sm.save_game(history, "파일A")
        sm.save_game(history, "파일B")

        saves = sm.list_saves()
        file_stems = [s["file"] for s in saves]

        assert len(saves) == 2, f"저장 파일 수 불일치: {saves}"
        assert "파일A" in file_stems
        assert "파일B" in file_stems
    print("  ✅ test_list_saves 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 6: delete_save — 삭제 후 목록에서 제거
# ══════════════════════════════════════════════════════════════
def test_delete_save() -> None:
    """delete_save() 호출 후 해당 파일이 목록에서 제거된다."""
    with tempfile.TemporaryDirectory() as tmp:
        sm = _make_state_manager(tmp)
        history = _make_history_stub()

        sm.save_game(history, "삭제대상")
        assert len(sm.list_saves()) == 1

        result = sm.delete_save("삭제대상")
        assert result is True, "delete_save가 True를 반환해야 함"
        assert len(sm.list_saves()) == 0, "삭제 후 목록이 비어야 함"

        # 존재하지 않는 파일 삭제 시 False
        result2 = sm.delete_save("없는파일")
        assert result2 is False
    print("  ✅ test_delete_save 통과")


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_update_from_response_normal,
    test_update_from_response_game_over,
    test_save_game_creates_file,
    test_save_load_roundtrip,
    test_list_saves,
    test_delete_save,
]


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  StateManager 단위 테스트")
    print("=" * 60 + "\n")

    passed = 0
    failed = 0

    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test_fn.__name__} 실패: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {test_fn.__name__} 예외: {e}")
            failed += 1

    print(f"\n{'─' * 60}")
    print(f"  결과: {passed}개 통과 / {failed}개 실패 / 총 {passed + failed}개")
    print(f"{'─' * 60}\n")

    if failed > 0:
        sys.exit(1)
