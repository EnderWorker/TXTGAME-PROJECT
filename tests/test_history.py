"""
NarrativeHistory 단위 테스트.

compact()는 실제 브릿지 연결이 필요하므로 테스트 범위에서 제외한다.
나머지 메서드 (add_exchange, needs_compaction, get_recent, serialization)를 검증한다.

실행:
    python tests/test_history.py       # 직접 실행
    pytest tests/test_history.py -v    # pytest 사용
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows cp949 환경에서 유니코드 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.engine.history import NarrativeHistory


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 1: add_exchange — full_log와 active_exchanges 모두 기록
# ══════════════════════════════════════════════════════════════
def test_add_exchange_both_logs() -> None:
    """add_exchange() 호출 시 full_log와 active_exchanges 양쪽에 추가된다."""
    h = NarrativeHistory()
    h.add_exchange("player", "북쪽으로 간다")
    h.add_exchange("assistant", "북쪽에는 숲이 있습니다.")

    assert len(h.full_log) == 2, f"full_log 크기 불일치: {len(h.full_log)}"
    assert len(h.active_exchanges) == 2
    assert h.full_log[0]["role"] == "player"
    assert h.full_log[1]["content"] == "북쪽에는 숲이 있습니다."
    print("  ✅ test_add_exchange_both_logs 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 2: needs_compaction — 최대치 초과 여부
# ══════════════════════════════════════════════════════════════
def test_needs_compaction() -> None:
    """active_exchanges가 max_exchanges를 초과하면 needs_compaction()이 True를 반환한다."""
    h = NarrativeHistory(max_exchanges=3)

    assert not h.needs_compaction(), "초기 상태에서 압축 필요 없음"

    for i in range(3):
        h.add_exchange("player", f"행동 {i}")

    assert not h.needs_compaction(), "정확히 max_exchanges 개수일 때는 False"

    h.add_exchange("player", "한 개 더")
    assert h.needs_compaction(), "max_exchanges 초과 시 True"
    print("  ✅ test_needs_compaction 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 3: get_recent — 최근 N개만 반환
# ══════════════════════════════════════════════════════════════
def test_get_recent() -> None:
    """get_recent(n)은 active_exchanges의 마지막 n개를 반환한다."""
    h = NarrativeHistory()
    for i in range(10):
        h.add_exchange("player", f"행동 {i}")

    recent = h.get_recent(3)
    assert len(recent) == 3, f"반환 개수 불일치: {len(recent)}"
    assert recent[-1]["content"] == "행동 9"
    assert recent[0]["content"] == "행동 7"

    # n > 전체 개수인 경우 전부 반환
    all_recent = h.get_recent(100)
    assert len(all_recent) == 10
    print("  ✅ test_get_recent 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 4: to_serializable / from_serializable 왕복
# ══════════════════════════════════════════════════════════════
def test_serialization_roundtrip() -> None:
    """to_serializable → from_serializable 왕복 후 데이터가 동일하다."""
    h = NarrativeHistory(max_exchanges=15)
    h.summary = "영웅이 용사가 되는 이야기"
    h.add_exchange("player", "마을에 도착했다")
    h.add_exchange("assistant", "마을 사람들이 환영한다")

    data = h.to_serializable()
    h2 = NarrativeHistory.from_serializable(data)

    assert h2.summary == h.summary
    assert len(h2.active_exchanges) == len(h.active_exchanges)
    assert h2.max_exchanges == 15
    # full_log는 active_exchanges로 복원됨
    assert len(h2.full_log) == len(h.active_exchanges)
    print("  ✅ test_serialization_roundtrip 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 5: export_full_log — 텍스트 포맷 확인
# ══════════════════════════════════════════════════════════════
def test_export_full_log() -> None:
    """export_full_log()는 role과 content를 포함한 텍스트를 반환한다."""
    h = NarrativeHistory()
    h.add_exchange("player", "검을 뽑는다")
    h.add_exchange("assistant", "적이 쓰러진다")

    log_text = h.export_full_log()

    assert "PLAYER" in log_text.upper(), "player 역할이 출력에 포함되어야 함"
    assert "검을 뽑는다" in log_text
    assert "적이 쓰러진다" in log_text
    assert isinstance(log_text, str)
    print("  ✅ test_export_full_log 통과")


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_add_exchange_both_logs,
    test_needs_compaction,
    test_get_recent,
    test_serialization_roundtrip,
    test_export_full_log,
]


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  NarrativeHistory 단위 테스트")
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
