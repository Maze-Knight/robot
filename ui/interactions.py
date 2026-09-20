from __future__ import annotations

import logging
from typing import Any

from qqbot_agent_sdk import parse_interaction_event

from . import copywriting as copy
from .menus import MenuService


logger = logging.getLogger("elena.qq.ui")

_TEXT_ACTIONS = {
    "test:callback": "你点击了：回调测试",
    "feature:daily_draw": copy.DAILY_DRAW_PLACEHOLDER,
    "feature:collection": copy.COLLECTION_PLACEHOLDER,
    "experiment:random": copy.RANDOM_EXPERIMENT_PLACEHOLDER,
    "experiment:chat": copy.CHAT_EXPERIMENT_PLACEHOLDER,
    "notice:updates": copy.RECENT_UPDATES,
    "help:basic": copy.BASIC_HELP,
    "help:feedback": copy.FEEDBACK_PLACEHOLDER,
}


async def handle_interaction(
    event_type: str,
    raw: dict[str, Any],
    api: Any,
    menus: MenuService,
    trickcal_controller: Any | None = None,
    majsoul_controller: Any | None = None,
) -> None:
    interaction = parse_interaction_event(raw)
    scene = (
        "c2c"
        if interaction.is_c2c
        else "group"
        if interaction.is_group
        else interaction.scene or "guild"
    )
    button_data = interaction.data.resolved.button_data

    ack_result = "failed"
    try:
        await api.acknowledge_interaction(interaction.id)
        ack_result = "success"
    except Exception:
        logger.exception(
            "[INTERACTION] ACK失败 | scene=%s | interaction_id=%s",
            scene,
            interaction.id,
        )
        return

    logger.info(
        "[INTERACTION] scene=%s | chat_id=%s | user_id=%s | button_data=%s "
        "| interaction_id=%s | ack=%s | result=dispatching",
        scene,
        interaction.chat_id,
        interaction.operator_openid,
        button_data,
        interaction.id,
        ack_result,
    )

    if not interaction.chat_id:
        logger.error(
            "[INTERACTION] 缺少 chat_id | interaction_id=%s | result=failed",
            interaction.id,
        )
        return

    # acknowledge_interaction consumes the event id.  Follow-up OpenAPI
    # messages must be ordinary group/C2C sends; attaching it again makes QQ
    # reject the message with "请求参数event_id无效".
    follow_up_event_id: str | None = None

    try:
        if button_data == "menu:services":
            await menus.send_services_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data == "menu:experiments":
            await menus.send_experiments_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data == "menu:notices":
            await menus.send_notices_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data == "menu:help":
            await menus.send_help_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data == "menu:home":
            await menus.send_main_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data == "notice:status":
            await menus.send_terminal_status(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data.startswith("trickcal:") and trickcal_controller is not None:
            await trickcal_controller.handle_interaction(
                scene,
                interaction.chat_id,
                interaction.operator_openid,
                button_data,
                follow_up_event_id,
            )
        elif button_data.startswith("majsoul:") and majsoul_controller is not None:
            await majsoul_controller.handle_interaction(
                scene,
                interaction.chat_id,
                interaction.operator_openid,
                button_data,
                follow_up_event_id,
            )
        elif button_data == "menu:test":
            await menus.send_action_test_menu(
                scene, interaction.chat_id, event_id=follow_up_event_id
            )
        elif button_data in _TEXT_ACTIONS:
            await menus.send_plain_text(
                scene,
                interaction.chat_id,
                _TEXT_ACTIONS[button_data],
                event_id=follow_up_event_id,
            )
        else:
            await menus.send_plain_text(
                scene,
                interaction.chat_id,
                f"这个按钮不在当前设计图里：{button_data or '(empty)'}",
                event_id=follow_up_event_id,
            )
            logger.warning(
                "[INTERACTION] 未知 button_data | interaction_id=%s | button_data=%r",
                interaction.id,
                button_data,
            )
            return
    except Exception:
        logger.exception(
            "[INTERACTION] 动作执行失败 | scene=%s | button_data=%s "
            "| interaction_id=%s | ack=%s | result=failed",
            scene,
            button_data,
            interaction.id,
            ack_result,
        )
        return

    logger.info(
        "[INTERACTION] 动作完成 | scene=%s | button_data=%s "
        "| interaction_id=%s | ack=%s | result=success",
        scene,
        button_data,
        interaction.id,
        ack_result,
    )
