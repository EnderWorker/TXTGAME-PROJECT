"""
AI 응답 파서 모듈.

AI가 아래 형식으로 응답하도록 프롬프트에서 지시한다:

    [서사]
    (장면 묘사)

    [상태]
    ```json
    { "hp": 80, ... }
    ```

    [선택지]
    1. 선택지1
    2. 선택지2

이 모듈은 해당 형식에서 각 섹션을 파싱한다.
형식이 부분적으로 깨져있어도 최대한 데이터를 복구한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class GameResponse:
    """파싱된 AI 게임 응답."""
    narrative: str = ""                          # [서사] 섹션
    state: dict = field(default_factory=dict)    # [상태] JSON
    choices: list[str] = field(default_factory=list)  # [선택지] 목록
    is_game_over: bool = False                   # [GAME_OVER] 태그
    is_combat: bool = False                      # [COMBAT] 태그
    raw_text: str = ""                           # 원본 텍스트 (디버깅용)


class ResponseParser:
    """AI 텍스트 응답을 GameResponse로 파싱한다."""

    def parse(self, raw_response: str) -> GameResponse:
        """메인 파싱 메서드.

        1. [서사], [상태], [선택지] 태그로 섹션 분리
        2. 태그가 없으면 전체를 narrative로 폴백
        3. [상태]에서 JSON 추출
        4. JSON 실패 시 정규식으로 key-value 추출
        5. [선택지]에서 번호 리스트 추출
        6. [GAME_OVER], [COMBAT] 태그 감지

        Args:
            raw_response: AI로부터 받은 원본 텍스트

        Returns:
            파싱된 GameResponse
        """
        response = GameResponse(raw_text=raw_response)

        if not raw_response.strip():
            return response

        # 태그 존재 여부 확인
        has_narrative = self._has_tag(raw_response, "서사")
        has_state = self._has_tag(raw_response, "상태")
        has_choices = self._has_tag(raw_response, "선택지")

        if not has_narrative and not has_state and not has_choices:
            # 형식 없음 — 전체를 서사로 처리
            logger.debug("응답 형식 태그 없음 — 전체를 서사로 처리")
            response.narrative = raw_response.strip()
        else:
            # 섹션별 파싱
            if has_narrative:
                response.narrative = self._extract_section(raw_response, "서사").strip()
            else:
                # [서사] 태그 없어도 [상태] 이전 텍스트를 서사로 처리
                first_tag = re.search(r'\[(?:상태|선택지)\]', raw_response, re.IGNORECASE)
                if first_tag:
                    response.narrative = raw_response[:first_tag.start()].strip()

            if has_state:
                state_text = self._extract_section(raw_response, "상태")
                response.state = self._parse_state_json(state_text)

            if has_choices:
                choices_text = self._extract_section(raw_response, "선택지")
                response.choices = self._parse_choices(choices_text)

        # 특수 태그 감지
        response.is_game_over = self._has_tag(raw_response, "GAME_OVER")
        response.is_combat = self._has_tag(raw_response, "COMBAT")

        logger.debug(
            "파싱 완료 — 서사:{}자, 상태키:{}, 선택지:{}, 게임오버:{}, 전투:{}",
            len(response.narrative),
            list(response.state.keys()),
            len(response.choices),
            response.is_game_over,
            response.is_combat,
        )
        return response

    def _extract_section(self, text: str, section_name: str) -> str:
        """[섹션명] ~ 다음 [태그] 사이 텍스트를 추출한다 (대소문자 무시).

        Args:
            text: 전체 응답 텍스트
            section_name: 찾을 섹션 이름

        Returns:
            섹션 내용 (없으면 빈 문자열)
        """
        # [섹션명] 위치 찾기 (대소문자 무시)
        pattern_start = re.compile(
            rf'\[{re.escape(section_name)}\]', re.IGNORECASE
        )
        match_start = pattern_start.search(text)
        if not match_start:
            return ""

        start = match_start.end()

        # 다음 섹션 태그는 반드시 줄 시작 위치에 있어야 한다.
        # (JSON 배열 안의 [...] 와 구분하기 위함)
        pattern_next = re.compile(r'^\[[^\]]+\]', re.MULTILINE)
        match_next = pattern_next.search(text, start)

        if match_next:
            return text[start:match_next.start()]
        else:
            return text[start:]

    def _parse_state_json(self, state_text: str) -> dict:
        """상태 텍스트에서 JSON을 파싱한다.

        시도 순서:
        1. ```json ... ``` 코드블록 내부 추출
        2. { } 로 감싸진 부분 직접 추출
        3. 정규식으로 "키": 값 패턴 추출
        4. 모두 실패 시 빈 dict

        Args:
            state_text: [상태] 섹션 텍스트

        Returns:
            파싱된 상태 dict
        """
        # 1. 코드블록 추출
        code_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', state_text)
        if code_block:
            json_str = code_block.group(1)
            try:
                result = json.loads(json_str)
                logger.debug("JSON 코드블록 파싱 성공")
                return result
            except json.JSONDecodeError as e:
                logger.debug("JSON 코드블록 파싱 실패: {}", e)

        # 2. 중괄호 내부 추출
        brace_match = re.search(r'\{[\s\S]*\}', state_text)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
                logger.debug("JSON 중괄호 파싱 성공")
                return result
            except json.JSONDecodeError:
                # JSON이 약간 잘못된 경우 수정 시도
                fixed = self._fix_json(brace_match.group(0))
                try:
                    result = json.loads(fixed)
                    logger.debug("JSON 수정 후 파싱 성공")
                    return result
                except json.JSONDecodeError as e:
                    logger.debug("JSON 중괄호 파싱 실패: {}", e)

        # 3. 정규식 key-value 패턴
        result = {}
        # "key": value 또는 "key": "value" 패턴
        kv_pattern = re.compile(r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|\d+(?:\.\d+)?|\[.*?\]|true|false|null)')
        for match in kv_pattern.finditer(state_text):
            key = match.group(1)
            val_str = match.group(2)
            try:
                result[key] = json.loads(val_str)
            except Exception:
                result[key] = val_str.strip('"')
        if result:
            logger.debug("정규식 key-value 파싱: {}개 항목", len(result))
            return result

        logger.debug("상태 파싱 실패 — 빈 dict 반환")
        return {}

    def _fix_json(self, json_str: str) -> str:
        """일반적인 JSON 오류를 수정한다 (trailing comma, 작은따옴표 등)."""
        # 후행 쉼표 제거
        fixed = re.sub(r',\s*}', '}', json_str)
        fixed = re.sub(r',\s*]', ']', fixed)
        # 작은따옴표를 큰따옴표로 (간단한 경우만)
        fixed = re.sub(r"'([^']*)'", r'"\1"', fixed)
        return fixed

    def _parse_choices(self, choices_text: str) -> list[str]:
        """선택지 텍스트에서 번호 매긴 항목 목록을 추출한다.

        '1. ', '1) ', '① ', '- ' 등 다양한 형식을 지원한다.

        Args:
            choices_text: [선택지] 섹션 텍스트

        Returns:
            선택지 문자열 리스트 (번호 제거된 텍스트)
        """
        choices: list[str] = []
        lines = choices_text.strip().splitlines()

        # 다양한 번호 형식 패턴
        number_patterns = [
            re.compile(r'^\s*\d+[.)]\s+(.+)'),           # 1. 또는 1)
            re.compile(r'^\s*[①②③④⑤]\s*(.+)'),         # 원문자
            re.compile(r'^\s*[a-zA-Z][.)]\s+(.+)'),      # a. 또는 a)
            re.compile(r'^\s*[-*•]\s+(.+)'),              # 불릿
            re.compile(r'^\s*\[(\d+)\]\s*(.+)'),          # [1]
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # [GAME_OVER], [COMBAT] 등의 태그 제외
            if re.match(r'^\[(?:GAME_OVER|COMBAT|서사|상태|선택지)\]', line, re.IGNORECASE):
                continue

            matched = False
            for pattern in number_patterns:
                m = pattern.match(line)
                if m:
                    # 마지막 그룹이 텍스트
                    text = m.group(m.lastindex).strip()
                    if text:
                        choices.append(text)
                    matched = True
                    break

            # 번호 패턴 없지만 짧고 의미있는 줄이면 포함
            if not matched and 3 <= len(line) <= 100 and not line.startswith('['):
                choices.append(line)

        return choices[:6]  # 최대 6개

    def _has_tag(self, text: str, tag: str) -> bool:
        """텍스트에 특정 태그가 있는지 확인한다 (대소문자 무시).

        Args:
            text: 검색할 텍스트
            tag: 찾을 태그 이름 ([] 제외)

        Returns:
            태그가 있으면 True
        """
        pattern = re.compile(rf'\[{re.escape(tag)}\]', re.IGNORECASE)
        return bool(pattern.search(text))
