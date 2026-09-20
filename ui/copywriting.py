"""Centralized Elena persona copy for the municipal terminal UI."""

HOME_MARKDOWN = """# 🍹 莫纳提姆市政终端

由市长艾琳娜亲自监督设计。理论上不会出问题。

如果真的出了问题……先检查是不是你操作错了。"""

SERVICES_MARKDOWN = """# 📟 市政服务

能自动处理的事情就不要拿来烦市长。

所以我把它们都放这里了。"""

EXPERIMENTS_MARKDOWN = """# 🧪 实验项目

这里都是莫纳提姆最新技术成果。

发生异常属于正常实验现象。"""

NOTICES_MARKDOWN = """# 📢 公告记录

重要事项都会留在这里。

没看公告造成的损失，本市长概不负责。"""

HELP_MARKDOWN = """# 📖 使用说明

居然真的有人需要这个……

好吧，说明都整理好了。"""

DAILY_DRAW_PLACEHOLDER = "还在配置。不是设计问题，是实现速度没跟上。"
COLLECTION_PLACEHOLDER = "数据模块尚未接入。先别急着翻不存在的东西。"
RANDOM_EXPERIMENT_PLACEHOLDER = (
    "实验模块还没正式开放。乱按造成的结果不计入事故统计。"
)
CHAT_EXPERIMENT_PLACEHOLDER = "对话系统还在校准。至少理论上是这样。"
FEEDBACK_PLACEHOLDER = "反馈渠道还没接好。先记着，本市长迟早会处理。"

RECENT_UPDATES = """最近更新：
- QQ 官方 Gateway 已接通
- C2C 已验证
- QQ群消息已验证
- Markdown 菜单已验证
- InlineKeyboard 已验证"""

BASIC_HELP = """在群里 @艾琳娜 后发送命令。
C2C 直接发送即可。

不知道能做什么就输入：
菜单"""


def terminal_status_text(online: bool) -> str:
    if online:
        return "终端状态：在线\nGateway：已连接\n消息服务：正常"
    return "终端状态：连接异常\nGateway：未连接\n消息服务：等待恢复"
