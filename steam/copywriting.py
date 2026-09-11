from __future__ import annotations

from datetime import datetime, timezone

from .client import SteamApiError, SteamConfigurationError, SteamInputError
from .service import PlayerResult


STEAM_HOME = """# 🎮 Steam 监测站

状态、游戏、时长……都在监测范围内。

别紧张，本市长只是喜欢数据。"""

BIND_GUIDE = """把 SteamID 发过来。

格式：
绑定steam 7656119xxxxxxxxxx

也支持好友码或 Steam 个人主页链接。

别填错。本市长不负责替你猜。"""

NOT_BOUND = "系统里没有你的 Steam 身份。\n\n先去做身份登记。"
UNBOUND = "登记已解除。\n\n以后查不到数据可别说是终端坏了。"
UNBOUND_EMPTY = "系统里本来就没有你的 Steam 身份。这次不是终端忘了。"


def bind_success(player_name: str, steam_id: str) -> str:
    return (
        "身份登记完成。\n\n"
        f"Steam：{player_name}\nSteamID：{steam_id}\n\n"
        "很好，至少这次数据是对的。"
    )


def _duration_text(since: datetime | None) -> str | None:
    if since is None:
        return None
    seconds = max(0, int((datetime.now(timezone.utc) - since).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}小时{minutes}分钟" if hours else f"{minutes}分钟"


def profile(result: PlayerResult) -> str:
    player = result.player
    lines = ["👤 Steam 档案", "", f"名称：{player.name}", f"状态：{player.presence}"]
    if player.game_id:
        lines.append(f"当前游戏：{player.game_name or '未知游戏'}")
    lines.extend([f"SteamID：{player.steam_id}", "", "档案正常。没什么值得大惊小怪的。"])
    return "\n".join(lines)


def status(result: PlayerResult) -> str:
    player = result.player
    lines = ["📡 Steam 状态", "", f"用户：{player.name}", f"状态：{player.presence}"]
    if player.game_id:
        lines.append(f"当前游戏：{player.game_name or '未知游戏'}")
        duration = _duration_text(result.observed_game_since)
        if duration:
            lines.append(f"本终端已持续观测：{duration}")
    lines.extend(["", "数据正常。监测站还没坏。"])
    return "\n".join(lines)


def error_text(exc: Exception) -> str:
    if isinstance(exc, SteamConfigurationError):
        return "Steam 接口参数还没登记。让技术部门先填写 STEAM_API_KEY。"
    if isinstance(exc, SteamInputError):
        return "这个 SteamID 不对。\n\n再检查一次，别让本市长替你排查输入错误。"
    if isinstance(exc, SteamApiError) and exc.status_code == 429:
        return "Steam 请求太多，外部系统开始限流了。稍后再试。"
    if isinstance(exc, SteamApiError) and exc.status_code in {401, 403}:
        return "Steam 拒绝了接口凭证。需要技术部门检查 API Key。"
    if isinstance(exc, SteamApiError) and "timeout" in str(exc).lower():
        return "Steam 那边没响应。\n\n先声明，这不是本终端的问题。"
    return "数据有点不对。\n\n……暂时记作外部系统异常。"

