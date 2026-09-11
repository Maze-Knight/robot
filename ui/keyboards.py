from __future__ import annotations

from dataclasses import dataclass

from qqbot_agent_sdk import InlineKeyboard
from qqbot_agent_sdk.dto import (
    KeyboardButton,
    KeyboardButtonAction,
    KeyboardButtonPermission,
    KeyboardButtonRenderData,
    KeyboardContent,
    KeyboardRow,
)


OFFICIAL_DOCS_URL = "https://bot.q.qq.com/wiki/"


@dataclass
class CompatibleKeyboardButtonAction(KeyboardButtonAction):
    """Fill fields present in the current QQ spec but absent from SDK 1.2.2.

    Official action types: 0=URL/mini-app, 1=callback, 2=command.
    """

    enter: bool | None = None
    reply: bool | None = None
    anchor: int | None = None
    unsupport_tips: str = "当前 QQ 客户端不支持此按钮"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = super().to_dict()
        payload["unsupport_tips"] = self.unsupport_tips
        if self.enter is not None:
            payload["enter"] = self.enter
        if self.reply is not None:
            payload["reply"] = self.reply
        if self.anchor is not None:
            payload["anchor"] = self.anchor
        return payload


@dataclass
class CompatibleKeyboardButton(KeyboardButton):
    """Serialize only fields documented by QQ's current button protocol."""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = super().to_dict()
        # qqbot-agent-sdk 1.2.2 emits an undocumented group_id field.  QQ's
        # group OpenAPI rejects some values with rows.buttons.group_id invalid.
        payload.pop("group_id", None)
        return payload


def _button(
    button_id: str,
    label: str,
    data: str,
    *,
    action_type: int = 1,
    style: int = 1,
    enter: bool | None = None,
    reply: bool | None = None,
) -> KeyboardButton:
    return CompatibleKeyboardButton(
        id=button_id,
        render_data=KeyboardButtonRenderData(
            label=label,
            visited_label=label,
            style=style,
        ),
        action=CompatibleKeyboardButtonAction(
            type=action_type,
            data=data,
            permission=KeyboardButtonPermission(type=2),
            click_limit=0,
            enter=enter,
            reply=reply,
        ),
    )


def _keyboard(rows: list[list[KeyboardButton]]) -> InlineKeyboard:
    return InlineKeyboard(
        content=KeyboardContent(
            rows=[KeyboardRow(buttons=buttons) for buttons in rows]
        )
    )


def _command_button(
    button_id: str, label: str, command: str, *, style: int = 1
) -> KeyboardButton:
    """Create a command button so group replies stay inside the passive window."""
    return _button(
        button_id,
        label,
        command,
        action_type=2,
        style=style,
        enter=True,
        reply=False,
    )


def build_main_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("home_services", "📟 市政服务", "/市政服务"),
                _command_button("home_experiments", "🧪 实验项目", "/实验项目"),
            ],
            [
                _command_button("home_notices", "📢 公告记录", "/公告记录"),
                _command_button("home_help", "📖 使用说明", "/使用说明"),
            ],
        ]
    )


def build_services_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("service_steam", "🎮 Steam 监测站", "/Steam监测站"),
                _command_button("service_draw", "🎲 每日抽取", "/每日抽取"),
            ],
            [
                _command_button("service_collection", "📖 图鉴", "/图鉴"),
                _command_button("service_home", "🔙 返回终端", "/返回终端", style=0),
            ],
        ]
    )


def build_steam_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("steam_profile", "👤 我的档案", "/我的档案"),
                _command_button("steam_status", "📡 当前状态", "/当前状态"),
            ],
            [
                _command_button("steam_bind", "🔗 身份登记", "/身份登记"),
                _command_button("steam_back", "🔙 返回市政服务", "/市政服务", style=0),
            ],
        ]
    )


def build_steam_result_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("steam_unbind", "❌ 解除登记", "/解除登记", style=0),
                _command_button("steam_result_back", "🔙 返回监测站", "/Steam监测站", style=0),
            ]
        ]
    )


def build_steam_unbound_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("steam_unbound_bind", "🔗 身份登记", "/身份登记"),
                _command_button("steam_unbound_back", "🔙 返回监测站", "/Steam监测站", style=0),
            ]
        ]
    )


def build_experiments_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("experiment_random", "🎲 随机实验", "/随机实验"),
                _command_button("experiment_chat", "💬 对话测试", "/对话测试"),
            ],
            [_command_button("experiment_home", "🔙 返回终端", "/返回终端", style=0)],
        ]
    )


def build_notices_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("notice_updates", "🆕 最近更新", "/最近更新"),
                _command_button("notice_status", "📡 终端状态", "/终端状态"),
            ],
            [_command_button("notice_home", "🔙 返回终端", "/返回终端", style=0)],
        ]
    )


def build_help_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _command_button("help_basic", "📘 基础用法", "/基础用法"),
                _command_button("help_feedback", "📝 反馈建议", "/反馈建议"),
            ],
            [_command_button("help_home", "🔙 返回终端", "/返回终端", style=0)],
        ]
    )


def build_action_test_keyboard() -> InlineKeyboard:
    return _keyboard(
        [
            [
                _button("test_callback", "回调按钮 type=1", "test:callback"),
                _button(
                    "test_command",
                    "指令按钮 type=2",
                    "/test-markdown",
                    action_type=2,
                    enter=True,
                    reply=False,
                ),
            ],
            [
                _button(
                    "test_url",
                    "QQ 官方文档 type=0",
                    OFFICIAL_DOCS_URL,
                    action_type=0,
                    style=0,
                ),
                _button("test_home", "返回主菜单", "menu:home", style=0),
            ],
        ]
    )
