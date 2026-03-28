"""
Text RPG 커스텀 Textual 위젯 모음.

각 위젯은 게임 UI의 특정 영역을 담당한다.
"""

from __future__ import annotations

from loguru import logger
from textual.app import ComposeResult
from textual.widgets import Input, RichLog, Static


class HPBar(Static):
    """HP를 색상 프로그레스 바로 표시하는 위젯.

    비율에 따라 색상이 변한다:
    - 66% 이상: 초록
    - 33% 이상: 노랑
    - 33% 미만: 빨강
    """

    BAR_WIDTH: int = 20  # 바 길이 (문자 수)

    def __init__(
        self,
        label: str = "HP",
        current: int = 100,
        maximum: int = 100,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._current = current
        self._maximum = maximum

    def on_mount(self) -> None:
        self._render_bar()

    def update_value(self, current: int, maximum: int) -> None:
        """HP 값을 업데이트하고 바를 다시 렌더링한다.

        Args:
            current: 현재 HP
            maximum: 최대 HP
        """
        self._current = max(0, current)
        self._maximum = max(1, maximum)
        self._render_bar()

    def _render_bar(self) -> None:
        """현재 값에 맞는 색상 바 텍스트를 업데이트한다."""
        ratio = self._current / self._maximum if self._maximum > 0 else 0
        filled = int(ratio * self.BAR_WIDTH)
        empty = self.BAR_WIDTH - filled

        # 색상 결정
        if ratio > 0.66:
            color = "green"
        elif ratio > 0.33:
            color = "yellow"
        else:
            color = "red"

        bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"
        text = f"[bold]{self._label}[/bold] {bar} [dim]{self._current}/{self._maximum}[/dim]"
        self.update(text)


class StatPanel(Static):
    """게임 상태 정보 패널.

    HP/MP 바, 레벨, 골드, 위치, 인벤토리, 효과, 퀘스트를 표시한다.
    update_stats(state_dict) 메서드로 갱신한다.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state: dict = {}

    def compose(self) -> ComposeResult:
        yield HPBar(label="HP", current=100, maximum=100, id="hp-bar")
        yield HPBar(label="MP", current=50, maximum=50, id="mp-bar")
        yield Static("", id="stat-details")

    def update_stats(self, state: dict) -> None:
        """상태 dict로 패널 내용을 갱신한다.

        Args:
            state: AI 응답에서 파싱된 상태 dict
        """
        if not state:
            return

        self._state = state

        # HP 바 업데이트
        try:
            hp_bar = self.query_one("#hp-bar", HPBar)
            hp_bar.update_value(
                int(state.get("hp", 100)),
                int(state.get("max_hp", 100)),
            )
        except Exception as exc:
            logger.debug("HP 바 업데이트 실패: {}", exc)

        # MP 바 업데이트
        try:
            mp_bar = self.query_one("#mp-bar", HPBar)
            mp_bar.update_value(
                int(state.get("mp", 50)),
                int(state.get("max_mp", 50)),
            )
        except Exception as exc:
            logger.debug("MP 바 업데이트 실패: {}", exc)

        # 상세 정보 업데이트
        lines: list[str] = []

        level = state.get("level", 1)
        exp = state.get("exp", 0)
        gold = state.get("gold", 0)
        lines.append(f"[bold cyan]Lv.{level}[/bold cyan]  EXP: [yellow]{exp}[/yellow]  G: [yellow]{gold}[/yellow]")

        location = state.get("location", "")
        if location:
            lines.append(f"\n[bold]위치[/bold] [cyan]{location}[/cyan]")

        quest = state.get("quest", "")
        if quest:
            lines.append(f"\n[bold]퀘스트[/bold]\n[green]{quest}[/green]")

        inventory = state.get("inventory", [])
        if inventory:
            items_str = ", ".join(str(i) for i in inventory[:6])
            suffix = "..." if len(inventory) > 6 else ""
            lines.append(f"\n[bold]인벤토리[/bold]\n[dim]{items_str}{suffix}[/dim]")

        effects = state.get("effects", [])
        if effects:
            eff_str = ", ".join(str(e) for e in effects)
            lines.append(f"\n[bold]상태효과[/bold] [red]{eff_str}[/red]")

        try:
            details = self.query_one("#stat-details", Static)
            details.update("\n".join(lines))
        except Exception as exc:
            logger.debug("stat-details 업데이트 실패: {}", exc)


class NarrativeLog(RichLog):
    """스크롤 가능한 서사 텍스트 로그.

    새 서사가 추가되면 자동으로 하단으로 스크롤한다.
    Rich 마크업 렌더링을 지원한다.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=True, highlight=False, **kwargs)

    def add_narrative(self, text: str) -> None:
        """서사 텍스트를 로그에 추가하고 하단으로 스크롤한다.

        Args:
            text: 추가할 서사 텍스트 (Rich 마크업 사용 가능)
        """
        if not text.strip():
            return

        # 구분선 추가
        self.write("[dim]" + "─" * 50 + "[/dim]")
        self.write(text)
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        """시스템 메시지를 다른 스타일로 추가한다.

        Args:
            text: 시스템 메시지 텍스트
        """
        self.write(f"[dim italic]{text}[/dim italic]")
        self.scroll_end(animate=False)

    def add_player_action(self, text: str) -> None:
        """플레이어 행동을 강조 스타일로 추가한다.

        Args:
            text: 플레이어 입력 텍스트
        """
        self.write(f"\n[bold magenta]▶ {text}[/bold magenta]")
        self.scroll_end(animate=False)


class ChoicePanel(Static):
    """선택지 표시 패널.

    update_choices(choices) 메서드로 선택지 목록을 갱신한다.
    선택지가 비어있으면 자유 행동 안내를 표시한다.
    """

    DEFAULT_MSG = "[dim]자유롭게 행동을 입력하세요[/dim]"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._choices: list[str] = []

    def update_choices(self, choices: list[str]) -> None:
        """선택지 목록을 업데이트하고 패널을 다시 렌더링한다.

        Args:
            choices: 표시할 선택지 텍스트 목록
        """
        self._choices = choices
        self._render()

    def _render(self) -> None:
        """선택지를 패널에 렌더링한다."""
        if not self._choices:
            self.update(
                "[bold dim]── 행동 선택 ──[/bold dim]\n" + self.DEFAULT_MSG
            )
            return

        lines: list[str] = ["[bold]── 선택지 ──[/bold]"]
        for i, choice in enumerate(self._choices, 1):
            lines.append(f"[bold red]{i}.[/bold red] {choice}")

        self.update("\n".join(lines))

    def on_mount(self) -> None:
        self._render()


class GameInput(Input):
    """게임 플레이어 입력 위젯.

    로딩 중에는 비활성화하고 placeholder를 변경한다.
    """

    PLACEHOLDER_READY = "행동을 입력하세요... (숫자로 선택지 선택 가능)"
    PLACEHOLDER_LOADING = "게임 마스터가 이야기를 구상 중입니다..."

    def __init__(self, **kwargs) -> None:
        super().__init__(
            placeholder=self.PLACEHOLDER_READY,
            **kwargs,
        )

    def set_loading(self, is_loading: bool) -> None:
        """로딩 상태를 설정한다.

        Args:
            is_loading: True면 비활성화, False면 활성화
        """
        self.disabled = is_loading
        self.placeholder = (
            self.PLACEHOLDER_LOADING if is_loading else self.PLACEHOLDER_READY
        )

    def set_ready(self) -> None:
        """입력 가능 상태로 복원하고 포커스를 준다."""
        self.disabled = False
        self.placeholder = self.PLACEHOLDER_READY
        self.focus()
