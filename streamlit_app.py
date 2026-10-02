"""쇼핑 리스트 - Streamlit 버전.

실행: streamlit run streamlit_app.py
데이터는 브라우저 localStorage 대신 같은 폴더의 shopping_list.json에 저장된다.
"""

import json
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).with_name("shopping_list.json")
MAX_NAME_LENGTH = 100

# Streamlit 라벨은 마크다운으로 해석되므로, 사용자 입력이 서식/링크/이모지
# 코드(:smile:)/색상(:red[...])/자동 링크(http://, 이메일) 등으로 바뀌지 않게
# 특수문자를 이스케이프한다.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|~<>$:&])")
# 자동 링크(http://, www., 이메일)는 역슬래시 이스케이프로 막히지 않으므로
# 보이지 않는 단어 연결자(U+2060)를 끼워 패턴을 끊는다.
_WORD_JOINER = "⁠"
_AUTOLINK_PATTERNS = [
    (re.compile(r"(?i)(h)(?=ttps?:)"), r"\1" + _WORD_JOINER),
    (re.compile(r"(?i)(w)(?=ww\.)"), r"\1" + _WORD_JOINER),
    (re.compile(r"@"), _WORD_JOINER + "@"),
]


def escape_markdown(text: str) -> str:
    for pattern, replacement in _AUTOLINK_PATTERNS:
        text = pattern.sub(replacement, text)
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def normalize_name(name: str) -> str:
    return str(name).strip()[:MAX_NAME_LENGTH]


# ---------- 저장소 ----------
# shopping_list.json이 유일한 원본이다. 여러 탭(세션)이 같은 파일을 쓰므로
# 매 실행과 매 변경 직전에 파일을 다시 읽고, 읽기-수정-쓰기를 잠금으로 묶는다.
# 세션마다 목록을 캐시해 두고 통째로 저장하면 다른 탭의 변경을 덮어쓴다.


@st.cache_resource
def _file_lock() -> threading.Lock:
    return threading.Lock()


def load_items() -> list[dict] | None:
    """파일에서 목록을 읽는다. 파일이 없거나 깨졌으면 [], 읽을 수 없으면 None."""
    try:
        parsed = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except ValueError:
        return []
    except OSError:
        return None
    if not isinstance(parsed, list):
        return []

    items = []
    for item in parsed:
        if (
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
            and item["name"].strip()
        ):
            items.append(
                {
                    "id": item["id"],
                    "name": normalize_name(item["name"]),
                    "checked": item.get("checked") is True,
                    "createdAt": item.get("createdAt") or int(time.time() * 1000),
                }
            )
    return items


def save_items() -> None:
    try:
        DATA_FILE.write_text(
            json.dumps(st.session_state.shopping_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 저장에 실패해도 세션 상태로 앱은 계속 동작한다.
        pass


def refresh_items() -> None:
    """파일의 최신 목록으로 세션 상태를 갱신한다. 파일을 읽을 수 없으면 기존 상태를 유지한다."""
    items = load_items()
    if items is not None:
        st.session_state.shopping_items = items


@contextmanager
def mutate_items():
    """최신 목록을 읽어 수정한 뒤 저장한다. 다른 세션과 동시에 쓰지 않도록 잠근다."""
    with _file_lock():
        refresh_items()
        yield
        save_items()


# ---------- 상태 변경 (위젯 콜백) ----------


def find_item(item_id: str) -> dict | None:
    return next((i for i in st.session_state.shopping_items if i["id"] == item_id), None)


def add_item() -> None:
    # 입력창 비우기는 폼의 clear_on_submit에 맡긴다. 여기서 session_state를 비우면
    # 브라우저 쪽 폼 값은 그대로 남아 다음 Enter 때 이전 값이 다시 제출된다.
    name = normalize_name(st.session_state.new_item)
    if not name:
        return
    with mutate_items():
        st.session_state.shopping_items.append(
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "checked": False,
                "createdAt": int(time.time() * 1000),
            }
        )


def toggle_item(item_id: str) -> None:
    with mutate_items():
        item = find_item(item_id)
        if item:
            item["checked"] = st.session_state[f"check_{item_id}"]


def start_editing(item_id: str) -> None:
    item = find_item(item_id)
    if item:
        st.session_state.editing_id = item_id
        st.session_state.edit_draft = item["name"]


def save_edit(item_id: str) -> None:
    name = normalize_name(st.session_state.edit_draft)
    with mutate_items():
        item = find_item(item_id)
        if item and name:
            item["name"] = name
    st.session_state.editing_id = None


def cancel_edit() -> None:
    st.session_state.editing_id = None


def delete_item(item_id: str) -> None:
    with mutate_items():
        st.session_state.shopping_items = [
            i for i in st.session_state.shopping_items if i["id"] != item_id
        ]


def clear_checked() -> None:
    with mutate_items():
        st.session_state.shopping_items = [
            i for i in st.session_state.shopping_items if not i["checked"]
        ]


# ---------- 화면 ----------

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")

st.markdown(
    """
    <style>
      .block-container { max-width: 560px; padding-top: 2.5rem; }
      /* 체크된 아이템 이름: 흐린 색 */
      .stCheckbox:has(input:checked) p { opacity: 0.55; }
      /* 수정·삭제 버튼: "우유 수정" 같은 라벨은 스크린 리더용으로만 두고 아이콘만 보인다 */
      [class*="st-key-edit_"] button [data-testid="stMarkdownContainer"],
      [class*="st-key-delete_"] button [data-testid="stMarkdownContainer"] {
        position: absolute; width: 1px; height: 1px; overflow: hidden;
        clip: rect(0, 0, 0, 0); white-space: nowrap;
      }
      /* Streamlit은 640px 미만에서 열을 세로로 쌓는다. 아이템 행과 입력 행은 한 줄을 유지한다. */
      [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width: 0 !important; }
      [data-testid="stColumn"]:has([class*="st-key-edit_"]),
      [data-testid="stColumn"]:has([class*="st-key-delete_"]) {
        flex: 0 0 44px !important; width: 44px !important;
      }
      [class*="st-key-edit_"] button,
      [class*="st-key-delete_"] button { min-width: 44px; min-height: 44px; }
      [data-testid="stColumn"]:has(.st-key-add_button) {
        flex: 0 0 auto !important; width: auto !important;
      }
      @media (max-width: 640px) {
        h1 { font-size: 1.75rem !important; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if "shopping_items" not in st.session_state:
    st.session_state.shopping_items = []
    st.session_state.editing_id = None
    st.session_state.edit_draft = ""

# 다른 탭에서 바뀐 내용을 반영한다.
refresh_items()
items = st.session_state.shopping_items
if st.session_state.editing_id and not find_item(st.session_state.editing_id):
    st.session_state.editing_id = None
total = len(items)
checked_count = sum(1 for i in items if i["checked"])

st.title("🛒 쇼핑 리스트")
st.caption(f"전체 {total}개 · 완료 {checked_count}개")
st.progress(checked_count / total if total else 0.0)

# F1. 추가: 폼이라 Enter로도 제출된다.
with st.form("add_form", clear_on_submit=True, border=True):
    col_input, col_button = st.columns([5, 1], vertical_alignment="bottom")
    col_input.text_input(
        "새 아이템",
        key="new_item",
        placeholder="살 물건을 입력하세요...",
        max_chars=MAX_NAME_LENGTH,
        label_visibility="collapsed",
    )
    col_button.form_submit_button(
        "추가", type="primary", on_click=add_item, key="add_button"
    )

if not items:
    st.info("쇼핑 리스트가 비어 있어요. 살 물건을 추가해 보세요!", icon="🛍️")
else:
    with st.container(border=True):
        for item in items:
            item_id = item["id"]

            # F2. 편집 모드
            if item_id == st.session_state.editing_id:
                with st.form(f"edit_form_{item_id}", border=False):
                    st.text_input(
                        "이름 수정",
                        key="edit_draft",
                        max_chars=MAX_NAME_LENGTH,
                        label_visibility="collapsed",
                    )
                    col_save, col_cancel = st.columns(2)
                    col_save.form_submit_button(
                        "저장",
                        type="primary",
                        on_click=save_edit,
                        args=(item_id,),
                        use_container_width=True,
                    )
                    col_cancel.form_submit_button(
                        "취소", on_click=cancel_edit, use_container_width=True
                    )
                continue

            # 일반 모드: F4 체크 / F2 수정 / F3 삭제
            col_check, col_edit, col_delete = st.columns(
                [8, 1, 1], vertical_alignment="center"
            )
            label = escape_markdown(item["name"])
            # 위젯이 기억하는 값 대신 파일의 최신 값을 보여 준다(다른 탭에서 바뀌었을 수 있음).
            st.session_state[f"check_{item_id}"] = item["checked"]
            col_check.checkbox(
                f"~~{label}~~" if item["checked"] else label,
                key=f"check_{item_id}",
                on_change=toggle_item,
                args=(item_id,),
            )
            col_edit.button(
                f"{label} 수정",
                icon=":material/edit:",
                key=f"edit_{item_id}",
                type="tertiary",
                on_click=start_editing,
                args=(item_id,),
            )
            col_delete.button(
                f"{label} 삭제",
                icon=":material/delete:",
                key=f"delete_{item_id}",
                type="tertiary",
                on_click=delete_item,
                args=(item_id,),
            )

st.button(
    "완료 항목 삭제",
    icon=":material/delete_sweep:",
    disabled=checked_count == 0,
    on_click=clear_checked,
)
