"""
Genspark chat.genspark.ai DOM 셀렉터 중앙 관리.

Genspark UI가 업데이트되면 이 파일의 셀렉터만 수정하면 된다.
각 속성은 쉼표로 구분된 CSS 셀렉터 후보 문자열이며,
_find_element()에서 앞에서부터 순서대로 시도하여 첫 번째로 찾은 요소를 사용한다.
"""


class GensparkSelectors:
    """Genspark chat.genspark.ai DOM 셀렉터 모음."""

    # 채팅 입력란 (textarea 또는 contenteditable div)
    # 실제 DOM 확인 후 수정 필요
    CHAT_INPUT: str = (
        "textarea[placeholder*='message'], "
        "textarea[data-testid='chat-input'], "
        "div[contenteditable='true']"
    )

    # 전송 버튼
    # 실제 DOM 확인 후 수정 필요
    SEND_BUTTON: str = (
        "button[data-testid='send-button'], "
        "button[aria-label*='Send'], "
        "button[type='submit']"
    )

    # AI 응답 컨테이너 (마지막 것이 최신 응답)
    # 실제 DOM 확인 후 수정 필요
    RESPONSE_CONTAINER: str = (
        "div[class*='message'][class*='assistant'], "
        "div[class*='response'], "
        "div[class*='answer']"
    )

    # 응답 내부 텍스트 영역 (마크다운 렌더링 영역)
    # 실제 DOM 확인 후 수정 필요
    RESPONSE_TEXT: str = (
        "div[class*='markdown'], "
        "div[class*='prose'], "
        "div[class*='content']"
    )

    # 스트리밍 중 표시 (응답 생성 중 인디케이터)
    # 실제 DOM 확인 후 수정 필요
    STREAMING_INDICATOR: str = (
        "div[class*='loading'], "
        "div[class*='typing'], "
        "span[class*='cursor']"
    )

    # 모델 선택 드롭다운 버튼
    # 실제 DOM 확인 후 수정 필요
    MODEL_SELECTOR_BUTTON: str = (
        "button[class*='model'], "
        "div[class*='model-select']"
    )

    # 모델 목록 개별 옵션
    # 실제 DOM 확인 후 수정 필요
    MODEL_OPTION: str = (
        "div[class*='option'], "
        "li[class*='model']"
    )

    # 새 대화 시작 버튼
    # 실제 DOM 확인 후 수정 필요
    NEW_CHAT_BUTTON: str = (
        "button[aria-label*='New'], "
        "a[href*='new'], "
        "button[class*='new-chat']"
    )

    # 로그인 버튼 (미로그인 상태에서 보임)
    # 실제 DOM 확인 후 수정 필요
    LOGIN_BUTTON: str = (
        "button[class*='login'], "
        "a[href*='login']"
    )

    # 로그인 완료 상태 지표
    # 실제 DOM 확인 후 수정 필요
    LOGGED_IN_INDICATOR: str = (
        "div[class*='avatar'], "
        "img[class*='profile'], "
        "button[class*='user']"
    )
