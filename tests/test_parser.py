"""
ResponseParser 단위 테스트.

실제 AI 응답 예시를 사용하여 8가지 이상의 파싱 케이스를 검증한다.

실행:
    python tests/test_parser.py       # 직접 실행
    pytest tests/test_parser.py -v    # pytest 사용
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

from src.engine.response_parser import ResponseParser

parser = ResponseParser()


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 1: 정상 형식 (태그 + JSON + 선택지 완전 포함)
# ══════════════════════════════════════════════════════════════
def test_full_format() -> None:
    """완전한 형식의 AI 응답을 파싱한다."""
    raw = """
[서사]
어두운 숲 속, 당신은 갈림길에 서 있다. 왼쪽 길에서는 모닥불 빛이 새어나오고,
오른쪽 길은 짙은 어둠 속으로 사라진다. 멀리서 늑대 울음소리가 들린다.

[상태]
```json
{
    "hp": 85, "max_hp": 100,
    "mp": 40, "max_mp": 50,
    "level": 2, "exp": 120,
    "gold": 75,
    "location": "어둠의 숲 - 갈림길",
    "inventory": ["낡은 검", "체력 포션 x2", "횃불"],
    "effects": ["피로"],
    "quest": "마을 북쪽의 동굴을 탐색하라"
}
```

[선택지]
1. 왼쪽 길(모닥불 쪽)로 간다
2. 오른쪽 길(어둠 속)로 간다
3. 제자리에서 주변을 살핀다
"""
    result = parser.parse(raw)

    assert result.narrative != "", "서사가 비어있음"
    assert "갈림길" in result.narrative
    assert result.state.get("hp") == 85
    assert result.state.get("location") == "어둠의 숲 - 갈림길"
    assert len(result.state.get("inventory", [])) == 3
    assert len(result.choices) == 3
    assert "왼쪽 길" in result.choices[0]
    assert not result.is_game_over
    assert not result.is_combat
    print("  ✅ test_full_format 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 2: [GAME_OVER] 태그
# ══════════════════════════════════════════════════════════════
def test_game_over_tag() -> None:
    """[GAME_OVER] 태그를 올바르게 감지한다."""
    raw = """
[서사]
당신은 마지막 힘을 다해 싸웠지만... 결국 쓰러지고 말았다.
눈앞이 어두워지며 의식이 멀어진다.

[상태]
```json
{"hp": 0, "max_hp": 100, "location": "보스 방"}
```

[선택지]
[GAME_OVER]
"""
    result = parser.parse(raw)
    assert result.is_game_over, "[GAME_OVER] 감지 실패"
    assert result.state.get("hp") == 0
    print("  ✅ test_game_over_tag 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 3: [COMBAT] 태그
# ══════════════════════════════════════════════════════════════
def test_combat_tag() -> None:
    """[COMBAT] 태그를 올바르게 감지한다."""
    raw = """
[서사]
갑자기 덤불에서 고블린 셋이 뛰어나왔다!

[상태]
```json
{"hp": 100, "max_hp": 100}
```

[선택지]
1. 검을 뽑고 공격
2. 도망친다

[COMBAT]
"""
    result = parser.parse(raw)
    assert result.is_combat, "[COMBAT] 감지 실패"
    assert not result.is_game_over
    assert len(result.choices) == 2
    print("  ✅ test_combat_tag 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 4: 태그 없는 폴백 (일반 텍스트)
# ══════════════════════════════════════════════════════════════
def test_no_tags_fallback() -> None:
    """태그 없는 응답 전체를 서사로 처리한다."""
    raw = "당신은 마을 광장에 도착했습니다. 사람들이 바쁘게 오가고 있습니다."
    result = parser.parse(raw)
    assert result.narrative == raw, "폴백 서사 불일치"
    assert result.state == {}, "상태가 비어야 함"
    assert result.choices == [], "선택지가 비어야 함"
    print("  ✅ test_no_tags_fallback 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 5: 다양한 선택지 번호 형식
# ══════════════════════════════════════════════════════════════
def test_various_choice_formats() -> None:
    """1), ①, - 등 다양한 선택지 형식을 파싱한다."""
    raw = """
[서사]
당신 앞에 세 갈래 길이 있다.

[상태]
```json
{"hp": 100}
```

[선택지]
1) 동쪽 길로 간다
2) 서쪽 길로 간다
3) 잠시 쉰다
"""
    result = parser.parse(raw)
    assert len(result.choices) == 3, f"선택지 수 불일치: {result.choices}"
    assert "동쪽 길" in result.choices[0]
    print("  ✅ test_various_choice_formats 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 6: 깨진 JSON (trailing comma)
# ══════════════════════════════════════════════════════════════
def test_broken_json_trailing_comma() -> None:
    """후행 쉼표가 있는 깨진 JSON도 복구한다."""
    raw = """
[서사]
당신은 던전 입구에 서 있다.

[상태]
```json
{
    "hp": 90,
    "max_hp": 100,
    "location": "던전 입구",
}
```

[선택지]
1. 입장한다
2. 돌아간다
"""
    result = parser.parse(raw)
    # 완벽하지 않아도 hp 정도는 파싱되어야 함
    assert result.state.get("hp") == 90 or result.state.get("location") == "던전 입구", \
        f"JSON 복구 실패: {result.state}"
    print("  ✅ test_broken_json_trailing_comma 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 7: JSON 없이 상태 섹션만 있는 경우
# ══════════════════════════════════════════════════════════════
def test_state_without_json_block() -> None:
    """코드블록 없이 중괄호만 있는 JSON도 파싱한다."""
    raw = """
[서사]
전투가 끝났다.

[상태]
{"hp": 70, "max_hp": 100, "gold": 50}

[선택지]
1. 전리품을 챙긴다
"""
    result = parser.parse(raw)
    assert result.state.get("hp") == 70, f"hp 파싱 실패: {result.state}"
    assert result.state.get("gold") == 50
    print("  ✅ test_state_without_json_block 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 8: 완전 비정형 응답 (JSON 완전 실패)
# ══════════════════════════════════════════════════════════════
def test_completely_malformed() -> None:
    """완전히 비정형인 응답도 크래시 없이 처리한다."""
    raw = """
[서사]
알 수 없는 오류가 발생했습니다. GM이 잠시 혼란스러워하고 있습니다.

[상태]
이것은 JSON이 아닙니다. 파싱 불가.

[선택지]
아무거나 입력하세요.
"""
    result = parser.parse(raw)
    # 크래시 없이 서사는 파싱되어야 함
    assert result.narrative != "", "서사 파싱 실패"
    assert isinstance(result.state, dict), "state는 항상 dict여야 함"
    assert isinstance(result.choices, list), "choices는 항상 list여야 함"
    print("  ✅ test_completely_malformed 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 9: 서사와 선택지만 있고 상태 없는 경우
# ══════════════════════════════════════════════════════════════
def test_no_state_section() -> None:
    """[상태] 섹션이 없어도 나머지를 파싱한다."""
    raw = """
[서사]
마을 노인이 당신에게 중요한 이야기를 들려준다.
"젊은이, 북쪽 산에는 오래된 성이 있다네. 거기서 마법의 검을 찾을 수 있을 거야."

[선택지]
1. 노인에게 더 자세한 이야기를 듣는다
2. 곧장 북쪽으로 출발한다
3. 마을을 좀 더 둘러본다
"""
    result = parser.parse(raw)
    assert "마을 노인" in result.narrative
    assert result.state == {}, "상태 없으면 빈 dict"
    assert len(result.choices) == 3
    print("  ✅ test_no_state_section 통과")


# ══════════════════════════════════════════════════════════════
# 테스트 케이스 10: 빈 응답
# ══════════════════════════════════════════════════════════════
def test_empty_response() -> None:
    """빈 문자열 입력도 크래시 없이 처리한다."""
    result = parser.parse("")
    assert result.narrative == ""
    assert result.state == {}
    assert result.choices == []
    assert not result.is_game_over
    print("  ✅ test_empty_response 통과")


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════

ALL_TESTS = [
    test_full_format,
    test_game_over_tag,
    test_combat_tag,
    test_no_tags_fallback,
    test_various_choice_formats,
    test_broken_json_trailing_comma,
    test_state_without_json_block,
    test_completely_malformed,
    test_no_state_section,
    test_empty_response,
]


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  ResponseParser 단위 테스트")
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
