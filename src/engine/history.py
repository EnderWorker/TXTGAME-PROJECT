"""
게임 서사 히스토리 관리 모듈.

대화 교환을 기록하고 컨텍스트 한도 초과 시 자동으로 요약·압축한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from .prompt_builder import PromptBuilder

if TYPE_CHECKING:
    from ..bridge.genspark_bridge import GensparkBridge
    from .state_manager import StateManager


class NarrativeHistory:
    """대화 히스토리를 관리하고 필요 시 컨텍스트를 압축한다."""

    def __init__(self, max_exchanges: int = 25) -> None:
        """
        Args:
            max_exchanges: 압축 전 최대 대화 교환 수
        """
        self.full_log: list[dict] = []       # 전체 기록 (role, content, timestamp)
        self.active_exchanges: list[dict] = []  # 현재 컨텍스트의 활성 교환
        self.summary: str = ""               # 압축된 이전 이야기 요약
        self.max_exchanges: int = max_exchanges

    # ── 공개 메서드 ──────────────────────────────────────────────────────────

    def add_exchange(self, role: str, content: str) -> None:
        """대화 교환을 기록에 추가한다.

        Args:
            role: 발화자 역할 ("player", "assistant", "system")
            content: 발화 내용
        """
        entry: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self.full_log.append(entry)
        self.active_exchanges.append(entry)
        logger.debug("교환 추가 ({}) — 활성: {}/{}", role, len(self.active_exchanges), self.max_exchanges)

    def needs_compaction(self) -> bool:
        """현재 활성 교환 수가 최대치를 초과했는지 확인한다."""
        return len(self.active_exchanges) > self.max_exchanges

    async def compact(
        self,
        bridge: "GensparkBridge",
        prompt_builder: PromptBuilder,
        state_manager: "StateManager",
    ) -> str:
        """컨텍스트를 압축하고 새 세션에서 게임을 재개한다.

        1. active_exchanges를 텍스트로 변환
        2. 요약 요청 프롬프트 생성
        3. 새 대화에서 요약 요청 전송 → 요약 텍스트 수신
        4. 기존 summary에 새 요약 병합
        5. 또 다른 새 대화에서 게임 재개 프롬프트 전송
        6. active_exchanges 초기화
        7. 재개 응답 텍스트 반환

        Args:
            bridge: GensparkBridge 인스턴스
            prompt_builder: PromptBuilder 인스턴스
            state_manager: StateManager 인스턴스

        Returns:
            게임 재개 응답 텍스트
        """
        logger.info("컨텍스트 압축 시작 (활성 교환: {}개)", len(self.active_exchanges))

        # 1. 요약 요청
        summary_prompt = prompt_builder.build_summary_request(self.active_exchanges)

        await bridge.start_new_conversation()
        new_summary = await bridge.send_message(summary_prompt)
        logger.info("요약 수신 완료 ({}자)", len(new_summary))

        # 4. 요약 병합
        if self.summary:
            self.summary = f"{self.summary}\n\n[이후 이야기]\n{new_summary}"
        else:
            self.summary = new_summary

        # 5. 새 세션에서 게임 재개
        await bridge.start_new_conversation()
        gs = state_manager.game_state
        resume_prompt = prompt_builder.build_session_resume_prompt(
            world=gs.world,
            character=gs.character,
            summary=self.summary,
            current_state=gs.current_state,
        )
        resume_response = await bridge.send_message(resume_prompt)
        logger.info("게임 재개 응답 수신 ({}자)", len(resume_response))

        # 6. active_exchanges 초기화 (새 세션 기록만 유지)
        self.active_exchanges = []
        self.add_exchange("system", resume_prompt)
        self.add_exchange("assistant", resume_response)

        logger.info("컨텍스트 압축 완료 — 새 세션 시작")
        return resume_response

    def get_recent(self, n: int = 10) -> list[dict]:
        """최근 N개의 교환을 반환한다.

        Args:
            n: 반환할 최대 개수

        Returns:
            최근 교환 목록
        """
        return self.active_exchanges[-n:]

    def export_full_log(self) -> str:
        """전체 기록을 읽기 쉬운 텍스트로 변환한다."""
        lines: list[str] = []
        for entry in self.full_log:
            ts = entry.get("timestamp", "")[:19]
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            lines.append(f"[{ts}] [{role.upper()}]\n{content}\n")
        return "\n".join(lines)

    def to_serializable(self) -> dict:
        """세이브 파일 저장을 위한 직렬화."""
        return {
            "summary": self.summary,
            "active_exchanges": self.active_exchanges,
            "full_log_count": len(self.full_log),
            "max_exchanges": self.max_exchanges,
        }

    @classmethod
    def from_serializable(cls, data: dict) -> "NarrativeHistory":
        """세이브 파일 로드를 위한 역직렬화.

        Args:
            data: to_serializable()로 직렬화된 dict

        Returns:
            복원된 NarrativeHistory 인스턴스
        """
        h = cls(max_exchanges=data.get("max_exchanges", 25))
        h.summary = data.get("summary", "")
        h.active_exchanges = data.get("active_exchanges", [])
        # full_log는 세이브 파일에 포함하지 않음 (크기 절약)
        # active_exchanges를 full_log로 복원
        h.full_log = list(h.active_exchanges)
        return h
