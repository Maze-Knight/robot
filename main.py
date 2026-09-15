from __future__ import annotations

import asyncio
import logging
import re
import sys
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any

from config import ConfigurationError, Settings, load_settings
from runtime import APP_DIR, RESOURCE_DIR, AlreadyRunningError, InstanceLock


BOT_NAME = "艾琳娜"
REPLY_TEXT = "艾琳娜收到啦！"
TRIGGERS = {"测试", "ping"}
MENU_TRIGGERS = {"菜单", "/help", "/menu"}
MARKDOWN_TRIGGER = "/test-markdown"
LOG_DIR = APP_DIR / "logs"
logger = logging.getLogger("elena.qq")

ReplyFunction = Callable[[str], Awaitable[dict[str, Any]]]
SendTextFunction = Callable[..., Awaitable[dict[str, Any]]]
UIFunction = Callable[[], Awaitable[dict[str, Any]]]
PluginHandler = Callable[[Any], Awaitable[bool]]


@dataclass(slots=True)
class MessageContext:
    platform: str
    scene_type: str
    group_id: str | None
    user_id: str
    message_id: str
    content: str
    event_type: str
    message_type: int
    reply: ReplyFunction = field(repr=False)
    show_main_menu: UIFunction | None = field(default=None, repr=False)
    show_markdown_test: UIFunction | None = field(default=None, repr=False)
    steam_handler: PluginHandler | None = field(default=None, repr=False)
    gift_handler: PluginHandler | None = field(default=None, repr=False)
    draw_handler: PluginHandler | None = field(default=None, repr=False)
    menu_handler: PluginHandler | None = field(default=None, repr=False)


class SecretRedactionFilter(logging.Filter):
    """Keep credentials and access tokens out of application log handlers."""

    _TOKEN_PATTERNS = (
        re.compile(r"(?i)(authorization\s*[:=]?\s*QQBot\s+)\S+"),
        re.compile(r"(?i)(access[_ -]?token\s*[\"']?\s*[:=]\s*[\"']?)\S+"),
        re.compile(r"(?i)(client[_ -]?secret\s*[\"']?\s*[:=]\s*[\"']?)\S+"),
    )

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self._secrets = tuple(value for value in secrets if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "***REDACTED***")
        for pattern in self._TOKEN_PATTERNS:
            message = pattern.sub(r"\1***REDACTED***", message)
        record.msg = message
        record.args = ()
        return True


class SessionState:
    """Thread-safe in-memory Gateway session state used for reconnect/resume."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._sequence: int | None = None

    def get(self) -> tuple[str | None, int | None]:
        with self._lock:
            return self._session_id, self._sequence

    def set(self, session_id: str | None, sequence: int | None) -> None:
        with self._lock:
            self._session_id = session_id
            self._sequence = sequence


def configure_logging(settings: Settings) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redactor = SecretRedactionFilter((settings.app_secret, settings.steam_api_key))

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redactor)

    file_handler = RotatingFileHandler(
        LOG_DIR / "bot.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def handle_message(context: MessageContext) -> None:
    """Framework-neutral message entry point reserved for future plugins."""
    normalized = context.content.strip().casefold()
    action: Awaitable[dict[str, Any]] | None = None
    action_name = ""
    if normalized in TRIGGERS:
        action = context.reply(REPLY_TEXT)
        action_name = "回复"
    elif normalized in MENU_TRIGGERS and context.show_main_menu is not None:
        action = context.show_main_menu()
        action_name = "主菜单发送"
    elif normalized == MARKDOWN_TRIGGER and context.show_markdown_test is not None:
        action = context.show_markdown_test()
        action_name = "Markdown 测试发送"

    if action is not None:
        try:
            await action
        except Exception:
            logger.exception(
                "%s失败 | scene=%s | message_id=%s",
                action_name,
                context.scene_type,
                context.message_id,
            )
            return
        logger.info(
            "%s成功 | scene=%s | message_id=%s",
            action_name,
            context.scene_type,
            context.message_id,
        )
        return

    for handler_name, handler in (
        ("Steam消息", context.steam_handler),
        ("礼包查询", context.gift_handler),
        ("每日抽取", context.draw_handler),
        ("菜单指令", context.menu_handler),
    ):
        if handler is None:
            continue
        try:
            handled = await handler(context)
        except Exception:
            logger.exception(
                "%s处理失败 | scene=%s | message_id=%s",
                handler_name,
                context.scene_type,
                context.message_id,
            )
            return
        if handled:
            logger.info(
                "%s处理成功 | scene=%s | message_id=%s",
                handler_name,
                context.scene_type,
                context.message_id,
            )
            return


def make_message_context(
    event: Any,
    event_type: str,
    send_text: SendTextFunction,
    *,
    show_main_menu: UIFunction | None = None,
    show_markdown_test: UIFunction | None = None,
    steam_handler: PluginHandler | None = None,
    gift_handler: PluginHandler | None = None,
    draw_handler: PluginHandler | None = None,
    menu_handler: PluginHandler | None = None,
) -> MessageContext:
    """Convert an SDK InboundEvent into the stable application context."""

    async def reply(content: str) -> dict[str, Any]:
        return await send_text(
            event.chat_scope,
            event.chat_id,
            content,
            reply_to=event.message_id,
            markdown=False,
        )

    return MessageContext(
        platform="qq_official",
        scene_type=event.chat_scope,
        group_id=event.chat_id if event.chat_scope == "group" else None,
        user_id=event.user_id,
        message_id=event.message_id,
        content=event.content,
        event_type=event_type,
        message_type=event.message_type,
        reply=reply,
        show_main_menu=show_main_menu,
        show_markdown_test=show_markdown_test,
        steam_handler=steam_handler,
        gift_handler=gift_handler,
        draw_handler=draw_handler,
        menu_handler=menu_handler,
    )


async def run_bot(settings: Settings) -> None:
    # The SDK reads endpoint overrides while importing its constants module.
    settings.apply_sdk_environment()

    import httpx
    import qqbot_agent_sdk.websocket as websocket_module
    from qqbot_agent_sdk import (
        EventParser,
        Intent,
        QQApiClient,
        QQWebSocket,
        WSCallbacks,
    )
    from ui.interactions import handle_interaction
    from ui.menus import MenuService, TerminalStatus
    from steam.client import SteamClient
    from steam.commands import SteamController
    from steam.monitor import SteamMonitor
    from steam.repository import SteamRepository
    from steam.service import SteamService
    from gifts.client import GiftApiClient
    from gifts.commands import GiftController
    from gifts.service import GiftQueryService
    from daily_draw.catalog import DrawCatalog, DrawCatalogError
    from daily_draw.card import DailyDrawCardRenderer
    from daily_draw.commands import DailyDrawController
    from daily_draw.repository import DrawRepository
    from daily_draw.service import DailyDrawService

    # SDK 1.2.2 has no public per-client intents argument and otherwise requests
    # unrelated guild/interaction privileges. Keep this pinned-version project
    # on the minimum official bit required for group + C2C messages.
    if int(Intent.GROUP_MESSAGES) != 1 << 25:
        raise RuntimeError("SDK 的 GROUP_MESSAGES intent 值发生变化，请重新核对官方文档")
    websocket_module.DEFAULT_INTENTS = Intent.GROUP_MESSAGES | Intent.INTERACTION
    logger.info(
        "Gateway Intents：GROUP_AND_C2C_EVENT (1<<25) + INTERACTION (1<<26)"
    )

    session = SessionState()
    shutdown = asyncio.Event()
    main_loop = asyncio.get_running_loop()
    parser = EventParser()

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        api = QQApiClient(
            app_id=settings.app_id,
            client_secret=settings.app_secret,
            log_tag=BOT_NAME,
        )
        api.setup(http_client)
        terminal_status = TerminalStatus()
        menus = MenuService(api, terminal_status)
        steam_repository = SteamRepository(
            APP_DIR / "data" / "steam.sqlite3"
        )
        await steam_repository.initialize()
        steam_client = SteamClient(
            http_client,
            settings.steam_api_key,
            api_base=settings.steam_api_base,
            timeout=settings.steam_request_timeout,
            retries=settings.steam_retry_times,
        )
        steam_service = SteamService(steam_client, steam_repository)
        from steam.card import SteamCardRenderer

        steam_card_renderer = SteamCardRenderer(http_client)
        steam_controller = SteamController(
            steam_service, menus, steam_card_renderer.render
        )
        gift_client = GiftApiClient(
            http_client,
            settings.gift_api_base_url,
            timeout=settings.gift_request_timeout,
        )
        gift_service = GiftQueryService(gift_client)
        gift_controller = GiftController(gift_service, menus)
        draw_repository = DrawRepository(APP_DIR / "data" / "daily_draw.sqlite3")
        await draw_repository.initialize()
        try:
            draw_catalog = DrawCatalog.load(APP_DIR / "daily_draw_pool.json")
        except DrawCatalogError as exc:
            logger.error("[DAILY_DRAW] 奖池配置无效 | reason=%s", exc)
            draw_catalog = DrawCatalog(())
        if draw_catalog.ready:
            pool_reset = await draw_repository.ensure_pool_version(draw_catalog.pool_id)
            if pool_reset:
                logger.warning(
                    "[DAILY_DRAW] pool changed | previous draw and collection records cleared"
                )
        draw_service = DailyDrawService(draw_catalog, draw_repository)
        draw_controller = DailyDrawController(
            draw_service,
            menus,
            DailyDrawCardRenderer(RESOURCE_DIR / "daily_draw_assets"),
        )
        steam_monitor = SteamMonitor(settings.steam_monitor_enabled)
        if steam_monitor.enabled:
            logger.warning(
                "[STEAM] STEAM_MONITOR_ENABLED=true ignored: phase-two scheduler is inactive"
            )
        logger.info(
            "[STEAM] active query initialized | api_key_configured=%s | monitor_enabled=false",
            steam_client.configured,
        )
        logger.info(
            "[GIFT] query initialized | api_configured=%s",
            gift_client.configured,
        )
        logger.info(
            "[DAILY_DRAW] initialized | pool_ready=%s | daily_limit=1x10",
            draw_catalog.ready,
        )

        async def on_message_event(event_type: str, raw: dict[str, Any]) -> None:
            try:
                event = parser.parse(event_type, raw)
                if event is None:
                    logger.warning("忽略无法解析的消息事件 | event_type=%s", event_type)
                    return

                context = make_message_context(
                    event,
                    event_type,
                    api.send_text,
                    show_main_menu=lambda: menus.send_main_menu(
                        event.chat_scope, event.chat_id, event.message_id
                    ),
                    show_markdown_test=lambda: menus.send_action_test_menu(
                        event.chat_scope, event.chat_id, event.message_id
                    ),
                    steam_handler=steam_controller.handle_text,
                    gift_handler=gift_controller.handle_text,
                    draw_handler=draw_controller.handle_text,
                    menu_handler=menus.handle_text,
                )
                logger.info(
                    "收到消息 | received_at=%s | event_type=%s | message_type=%s "
                    "| scene=%s | group_id=%s | user_id=%s | message_id=%s | content=%r",
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    context.event_type,
                    context.message_type,
                    context.scene_type,
                    context.group_id or "-",
                    context.user_id,
                    context.message_id,
                    context.content,
                )
                await handle_message(context)
            except Exception:
                # A malformed or failed single message must not terminate the bot.
                logger.exception("单条消息处理异常 | event_type=%s", event_type)

        async def on_interaction_event(
            event_type: str, raw: dict[str, Any]
        ) -> None:
            try:
                await handle_interaction(
                    event_type, raw, api, menus, steam_controller
                )
            except Exception:
                logger.exception("交互事件处理异常 | event_type=%s", event_type)

        def on_connected() -> None:
            terminal_status.set_gateway_online(True)
            logger.info("当前连接状态：ONLINE（Gateway 已 READY/RESUMED，机器人可用）")

        def on_disconnected() -> None:
            terminal_status.set_gateway_online(False)
            logger.warning("当前连接状态：DISCONNECTED（SDK 将自动重连）")

        def on_fatal_error(code: str, message: str) -> None:
            terminal_status.set_gateway_online(False)
            logger.error("Gateway 致命错误 | code=%s | message=%s", code, message)
            main_loop.call_soon_threadsafe(shutdown.set)

        def on_ready(ready: Any) -> None:
            username = getattr(getattr(ready, "user", None), "username", "")
            logger.info("机器人身份就绪 | name=%s", username or BOT_NAME)

        callbacks = WSCallbacks(
            on_message_event=on_message_event,
            on_connected=on_connected,
            on_disconnected=on_disconnected,
            on_fatal_error=on_fatal_error,
            get_token=api.ensure_token_sync,
            get_session=session.get,
            set_session=session.set,
            set_heartbeat_interval=lambda seconds: logger.debug(
                "Gateway 心跳间隔：%.1f 秒", seconds
            ),
            clear_token=api.clear_token,
            fail_pending=lambda reason: logger.warning("挂起请求失败：%s", reason),
            get_gateway_url=api.get_gateway_url_sync,
            on_interaction_event=on_interaction_event,
            on_ready=on_ready,
        )
        websocket = QQWebSocket(callbacks=callbacks, log_tag=BOT_NAME)

        logger.info("当前连接状态：AUTHENTICATING")
        await api.ensure_token()
        logger.info("AppID / AppSecret 鉴权成功（敏感凭证未输出）")
        gateway_url = await api.get_gateway_url()
        logger.info("当前连接状态：CONNECTING")
        websocket.start(gateway_url, main_loop)

        try:
            await shutdown.wait()
        finally:
            logger.info("正在关闭机器人连接")
            await websocket.async_stop()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")

    try:
        with InstanceLock():
            try:
                settings = load_settings()
            except ConfigurationError as exc:
                print(f"配置错误：{exc}", file=sys.stderr)
                return 2

            configure_logging(settings)
            logger.info(
                "启动时间：%s | bot=%s | Python=%s | runtime_dir=%s",
                datetime.now().astimezone().isoformat(timespec="seconds"),
                BOT_NAME,
                sys.version.split()[0],
                APP_DIR,
            )
            try:
                asyncio.run(run_bot(settings))
            except KeyboardInterrupt:
                logger.info("收到 Ctrl+C，机器人已停止")
                return 0
            except Exception:
                logger.exception("机器人启动或运行失败")
                return 1
    except AlreadyRunningError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
