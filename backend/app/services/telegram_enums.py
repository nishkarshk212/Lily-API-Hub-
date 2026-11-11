"""Pyrogram-compatible Telegram ButtonStyle enums and coloured InlineKeyboard builders."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

try:
    from pyrogram.enums import ButtonStyle  # type: ignore[attr-defined]
except Exception:
    class ButtonStyle(str, Enum):
        """Telegram inline button visual styles matching pyrogram.enums.ButtonStyle."""

        DEFAULT = "default"
        PRIMARY = "primary"
        SUCCESS = "success"
        DANGER = "danger"


def resolve_button_style_value(style: Optional[Union[ButtonStyle, str]]) -> Optional[str]:
    """Normalize a ButtonStyle enum (or string) to Telegram Bot API's optional 'style' value."""
    if style is None:
        return None
    raw = style.value if isinstance(style, Enum) else str(style)
    cleaned = str(raw).strip().lower()
    if cleaned in ("primary", "success", "danger"):
        return cleaned
    return None


def ikb_button(
    text: str,
    *,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[Union[ButtonStyle, str]] = ButtonStyle.DEFAULT,
    icon_custom_emoji_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct a Telegram Bot API InlineKeyboardButton dict with Pyrogram ButtonStyle styling."""
    btn: Dict[str, Any] = {"text": text}
    if callback_data is not None:
        btn["callback_data"] = callback_data
    elif url is not None:
        btn["url"] = url
    style_val = resolve_button_style_value(style)
    if style_val:
        btn["style"] = style_val
    if icon_custom_emoji_id:
        btn["icon_custom_emoji_id"] = str(icon_custom_emoji_id)
    return btn


def ikb_markup(rows: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Wrap rows of inline buttons into Telegram InlineKeyboardMarkup JSON."""
    return {"inline_keyboard": rows}
