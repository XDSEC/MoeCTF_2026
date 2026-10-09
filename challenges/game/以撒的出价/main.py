import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import random
import time
import uuid
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Body,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from captcha.image import ImageCaptcha

from ret2shell_kit import PlatformFlagManager, Ret2ShellClient, Ret2ShellError

from store import Store
from ws import WsManager

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "game.json"  # 旧版 JSON 存档，仅用于一次性迁移到 SQLite
DATA_DB = BASE_DIR / "data" / "game.db"
STATIC_DIR = BASE_DIR / "public"

ROOM_DURATION_MS = 30_000
RESULT_DURATION_MS = 10_000
# 每 Room 的保底基础分：指数衰减在目标远离所有出价时（如反转房全场低出价）
# 会让全员得分掉到 0.x。保底分保证参与出价的玩家至少拿到一个可读的分数。
MIN_SCORE_PER_ROOM = 5.0

# 自动开局：系统每 10 分钟开一局
GAME_INTERVAL_MS = 1 * 60 * 1000
# 有人加入且开局时间已过时，给一个短缓冲，避免刚加入就要等满 10 分钟
START_GRACE_MS = 30_000
# 打完一局后，等待玩家「自主选择是否继续下一局」的窗口；到点无人继续则滚动等待
CONTINUE_GRACE_MS = 90_000

# 一局目标人数：少于 TARGET_PLAYERS 位人类玩家时，用机器人补足到 20 人
TARGET_PLAYERS = 20

# 生涯总分「定三取五」：
#   至少打满 MIN_GAMES_FOR_RANK 局才能进入排行榜；
#   生涯分 = 生涯最好 BEST_N_GAMES 场的单局均分（不足 N 场则取全部已打场次的均分）。
# 防止新手打一两把高分就上榜霸榜。
MIN_GAMES_FOR_RANK = 3
BEST_N_GAMES = 5

# 排行榜冻结开关：置为 True 后生涯数据停止累加（榜单定榜），
# 但自动开局 / 对局结算 / FLAG 发放完全不受影响——选手照常参赛，
# 完整打完一局仍会拿到动态 FLAG（见 finish_game 与 public_state 的 my_flag 判定）。
# 修改后需重启服务（systemctl restart tboi / 重启 uvicorn）才生效。
# 首次观察到本开关为 True 时，会把当时的排行榜快照写入 leaderboard_snapshots 作为定榜存档。
LEADERBOARD_FROZEN = False

# ---------------------------------------------------------------------------
# 反作弊 / 人机验证配置
# ---------------------------------------------------------------------------
# 目标：分析选手的出价行为，发现可疑自动化（机器直连 WebSocket、脚本出价等）。
# 行为可疑分累计到 SUSPICION_THRESHOLD 后，要求该选手在 CAPTCHA_WINDOW_MS
# （15 秒）内完成人机验证；不通过（答错用完次数或超时）则禁赛 BAN_DURATION_MS
# （1 天）。另外 WebSocket 握手要求携带 HTTP 签发、与 session 绑定的短期 token，
# 配合 Origin / UA 校验，阻止未经过网页流程的机器客户端直连比赛。
# 除行为触发外，每次出价后还有 CAPTCHA_SPOTCHECK_PROB 概率随机点名验证
# （与行为分析无关），让「行为上不可疑但其实是机器」的客户端也逃不掉抽查。

# 人机验证：15 秒限时，最多试 CAPTCHA_MAX_ATTEMPTS 次，全部错误 / 超时 -> 禁赛。
# 题目为 captcha 库渲染的图片验证码单选：6 个候选文本，选出与图片一致的那个。
CAPTCHA_WINDOW_MS = 15_000
CAPTCHA_MAX_ATTEMPTS = 2
# 图片验证码字符集（去掉易混淆的 0/O、1/I/L，保证图片可读），随机取 4 个字符。
CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CAPTCHA_TEXT_LEN = 4
CAPTCHA_IMAGE_SIZE = (280, 90)  # 图片尺寸（宽, 高）
# 随机抽查概率：每次出价后触发随机验证的概率（0.03 = 平均每 33 次出价点名一次）。
# 抽查与行为分析独立，但仍受验证通过后的 VERIFY_COOLDOWN_MS 宽限约束，避免反复打扰。
CAPTCHA_SPOTCHECK_PROB = 0.03
# 「验证失败次数」指标：计入该指标的禁赛原因。每次验证失败（答错用尽次数 / 超时）
# 都会 apply_ban 并落一条禁赛审计记录，故按这些 reason 统计 bans 表行数即为累计次数。
CAPTCHA_FAIL_TIMEOUT = "人机验证超时"
CAPTCHA_FAIL_WRONG = "人机验证失败次数过多"
CAPTCHA_FAIL_BAN_REASONS = (CAPTCHA_FAIL_TIMEOUT, CAPTCHA_FAIL_WRONG)
# 禁赛时长：1 天
BAN_DURATION_MS = 24 * 3600 * 1000
# 行为可疑分阈值：达到即触发验证。设计上单个「超快反应」信号（1.0）不触发，
# 需要叠加其它信号（如出价连发 +0.6 / 无人类活动 +0.5）才触发，降低误伤。
SUSPICION_THRESHOLD = 1.5
# 可疑分随时间衰减：每 SUSPICION_DECAY_S 秒乘 SUSPICION_DECAY，避免一次
# 快出价长期「留案底」。通过验证后立即清零。
SUSPICION_DECAY = 0.9
SUSPICION_DECAY_S = 60
# 验证通过后的「宽限」：宽限期内行为不再触发新验证，防止反复打扰正常玩家。
VERIFY_COOLDOWN_MS = 10 * 60 * 1000
# WebSocket 握手 token 有效期：由 HTTP POST /api/ws_token 签发，与 session 绑定，
# 短期有效。超过有效期需重新签发（前端每次重连前签发）。
WS_TOKEN_TTL_MS = 60_000
# 握手时拒绝的明显机器 User-Agent 子串（小写匹配）；真实浏览器 UA 不含这些。
BOT_UA_SUBSTRINGS = ("curl", "wget", "python-requests", "python urllib", "go-http-client", "java/", "okhttp", "node-fetch", "axios", "httpclient")

# ---------------------------------------------------------------------------
# 鉴权 / 动态 FLAG 配置
# ---------------------------------------------------------------------------

# Ret2Shell 平台 API 地址
R2S_BASE_URL = os.getenv("R2S_BASE_URL", "https://ctf.xidian.edu.cn/api")
# 可选：平台 token（管理员）
R2S_TOKEN = os.getenv("R2S_TOKEN", "")
# session cookie 签名密钥，生产环境必须改为随机值
SESSION_SECRET = os.getenv("SESSION_SECRET", "TnfaFKi7XjrNhVZzwZrbfsk6FxRUk4")
# FLAG 生成密钥，必须与平台评测脚本保持一致
FLAG_KEY = os.getenv("FLAG_KEY", "qayHEbV2tzibPwTof8TnQb4Br18Dqi")
FLAG_PREFIX = os.getenv("FLAG_PREFIX", "moectf")
FLAG_TEMPLATE = os.getenv("FLAG_TEMPLATE", "have-fun-in-game-of-game-theory")
# 隐写模式：leet（默认，ret2shell-kit 0.1.5 可往返）或 uuid
FLAG_MODE = os.getenv("FLAG_MODE", "leet")
# 本地开发模拟平台：为 1 时接受任意识别码，返回固定假身份
R2S_MOCK = os.getenv("R2S_MOCK", "0") == "1"

# info 日志：控制台 + data/info.log（已被 .gitignore 覆盖）
logger = logging.getLogger("tboi")
INFO_LOG = BASE_DIR / "data" / "info.log"
INFO_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(INFO_LOG, encoding="utf-8"),
    ],
)
# 不把 httpx 的每一条 HTTP 请求打进 info 日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

LEVELS = [
    {"budget": 100, "rooms": ["normal", "normal", "treasure", "boss"]},
    {"budget": 500, "rooms": ["normal", "special", "treasure", "boss"]},
    {"budget": 1000, "rooms": ["normal", "special", "treasure", "special", "boss"]},
]

# 一局总房间数，用于把当局总分折算成“场均分”（0~100 量级，便于阅读）
TOTAL_ROOMS = sum(len(level["rooms"]) for level in LEVELS)

ITEMS: dict[str, dict[str, Any]] = {
    # ---- 常见道具 ----
    "score_amulet": {
        "name": "积分护符",
        "desc": "每次获得分数时得分 +10（固定加分，参与比例乘算）",
        "rarity": "common",
    },
    "mom_heart": {
        "name": "妈妈的心脏",
        "desc": "Boss Room 中的得分 x200%（不包含本次出价）",
        "rarity": "common",
    },
    "lucky_sack": {
        "name": "福袋",
        "desc": "一次性：返还下一笔出价 75% 的资金（用后消耗）",
        "rarity": "common",
    },
    "perfect_vision": {
        "name": "完美视力",
        "desc": "争夺道具时，出价按 1.5 倍计算（仅影响出价之和与道具竞争，得分公式仍按原出价）",
        "rarity": "common",
    },
    "steal_purse": {
        "name": "偷钱袋",
        "desc": "每个房间开始时，从总资产第一名（资金最高者）偷取 10% 的资金，从对方账户扣除",
        "rarity": "common",
    },
    # ---- 稀有道具 ----
    "sacred_heart": {
        "name": "圣心",
        "desc": "后续得分 x150%",
        "rarity": "rare",
    },
    "steam_sale": {
        "name": "Steam大促",
        "desc": "后续出价扣除的资金减少 30%（按折扣后实际扣除校验资金）",
        "rarity": "rare",
    },
    "brimstone": {
        "name": "硫磺火",
        "desc": "计算得分时可在出价的 80%~125% 区间取最高分（平均出价仍按初始出价计算）；多件时区间上下限按件数连乘（0.8ⁿ×~1.25ⁿ×）",
        "rarity": "rare",
    },
    "divine_cloak": {
        "name": "神圣斗篷",
        "desc": "每层首次竞争失败退回所有资金",
        "rarity": "rare",
    },
    "six_dice": {
        "name": "六面骰",
        "desc": "1/6 概率使所有者当前房间的得分 x200%",
        "rarity": "rare",
    },
    "interest": {
        "name": "利息",
        "desc": "每个房间开始时资金 +10%，进入下一层的初始资金 +20%",
        "rarity": "rare",
    },
    # ---- 诅咒道具 ----
    "black_crown": {
        "name": "黑王子之冠",
        "desc": "结算时总得分 +25%，每拥有一个其他道具加成 -5%，最低不低于 +5%",
        "rarity": "cursed",
    },
    "poor_amulet": {
        "name": "穷人护符",
        "desc": "当前资金低于本层初始资金 30% 时每次得分 +20，否则 +5（固定加分，参与比例乘算）；进入下一房间资金 -10%",
        "rarity": "cursed",
    },
    "eternal_d6": {
        "name": "永恒六面骰",
        "desc": "后续得分 x150%，但有 25% 概率使当前房间得分清零",
        "rarity": "cursed",
    },
    "extra_choice": {
        "name": "更多选择",
        "desc": "可同时对房间的两个道具出价；同时参与时两方得分之和 x75%",
        "rarity": "cursed",
    },
}

# 旧版本道具键 -> 新键映射（中途升级存档时把旧道具迁到新道具池）；
# 未出现在映射里的旧道具（钱袋 / 隐形斗篷 / D6）已在池中删除，加载时直接移除。
LEGACY_ITEM_MAP = {
    "saber": "sacred_heart",        # 马刀/圣心 -> 圣心
    "double_tears": "perfect_vision",  # 双倍眼泪 -> 完美视力
    "cursed_crown": "black_crown",  # 诅咒王冠 -> 黑王子之冠
}

# 角色：开局前玩家在等待大厅选择，开局时自动携带该角色的初始道具（伊甸为随机一件）。
# 人类用所选角色；机器人开局时随机分到一个角色。
CHARACTERS: dict[str, dict[str, Any]] = {
    "isaac": {"name": "以撒", "item": "six_dice"},        # D6 = 六面骰
    "soul": {"name": "游魂", "item": "divine_cloak"},     # 神圣斗篷
    "azazel": {"name": "阿撒泻勒", "item": "brimstone"},  # 硫磺火
    "eden": {"name": "伊甸", "item": "random"},           # 随机一件道具
    "jacob_esau": {"name": "雅各和以扫", "item": "extra_choice"},  # 更多选择
}

BOT_NAMES = [
    "Azazel",
    "Magdalene",
    "Cain",
    "Judas",
    "Isaac",
    "Eve",
    "Samson",
    "Lilith",
    "The Forgotten",
    "Bethany",
    "Lazarus",
    "The Keeper",
    "Apollyon",
    "The Lost",
    "Eden",
    "Delirium",
    "Hush",
    "Mega Satan",
    "Blue Baby",
    "The Inner",
]

# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def now_ms() -> int:
    return int(time.time() * 1000)


def fmt_ts(ts_ms: int) -> str:
    """毫秒时间戳 -> 可读时间（本地时区），用于禁赛提示。"""
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(ts_ms / 1000))
    except Exception:
        return str(ts_ms)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def new_id() -> str:
    return uuid.uuid4().hex


def new_player(
    name: str,
    is_bot: bool = False,
    player_id: Optional[str] = None,
    auth: Optional[dict] = None,
) -> dict[str, Any]:
    return {
        "id": player_id or new_id(),
        "name": name.strip() or "无名玩家",
        "is_bot": is_bot,
        "auth": auth,  # None 或 {kind, platform_id, name, account?}
        "character": None,  # 开局前所选角色（key，见 CHARACTERS）；None 时开局随机分配
        "total_score": 0,
        "level_funds": 0,
        "items": [],
        "score_mult": 1.0,        # 比例倍率（圣心 / 永恒六面骰 各 x1.5，叠乘）
        "flat_score": 0,          # 固定加分（积分护符 +10/个；穷人护符按房间动态/件），先加进 base 再参与比例乘算
        "payment_mult": 1.0,      # 支付倍率（Steam大促 x0.7，叠乘）
        "lucky_bag": 0,           # 福袋（一次性）：未使用次数，每次支付扣 1 次
        "bid_power": 1.0,         # 有效出价倍率（完美视力 x1.5，只影响求和与竞争）
        "interest": False,        # 利息
        "poor": False,            # 穷人护符
        "poor_count": 0,          # 穷人护符持有数量（得分按数量叠加）
        "brimstone": False,       # 硫磺火
        "brimstone_count": 0,     # 硫磺火持有数量（得分出价区间按数量叠加）
        "divine_cloak": False,    # 神圣斗篷
        "divine_used": False,     # 神圣斗篷：本层是否已用过（每层首次失败退回资金）
        "six_dice": False,        # 六面骰
        "mom_heart": False,       # 妈妈的心脏
        "steal": False,           # 偷钱袋
        "black_crown": False,     # 黑王子之冠
        "eternal_d6": False,      # 永恒六面骰
        "extra_choice": False,    # 更多选择：可同时参与两个道具的竞争
        "level_start_funds": 0,   # 本层初始资金（穷人护符阈值依据）
        "ready": True,  # 是否愿意继续下一局（finish_game 时置 False，点「继续下一局」再置 True）
    }


def _reset_item_stats(player: dict[str, Any]) -> None:
    """把道具相关效果字段重置为初始值，再按当前 items 重建（新局 / 存档恢复共用）。

    这样 load_dict 恢复旧存档时，只要 items 列表是对的，所有倍率与 flag
    都会与道具严格一致，不会因为旧状态里缺少新字段而错乱。
    """
    player["score_mult"] = 1.0
    player["flat_score"] = 0
    player["payment_mult"] = 1.0
    player["lucky_bag"] = 0
    player["bid_power"] = 1.0
    player["interest"] = False
    player["poor"] = False
    player["poor_count"] = 0
    player["brimstone"] = False
    player["brimstone_count"] = 0
    player["divine_cloak"] = False
    player["divine_used"] = False
    player["six_dice"] = False
    player["mom_heart"] = False
    player["steal"] = False
    player["black_crown"] = False
    player["eternal_d6"] = False
    player["extra_choice"] = False
    for key in player.get("items", []):
        _apply_item_effects(player, key)


def _apply_item_effects(player: dict[str, Any], item_key: str) -> None:
    """应用单个道具的常驻效果（不修改 items 列表，供 apply_item 与 _reset_item_stats 共用）。"""
    if item_key == "sacred_heart":
        player["score_mult"] *= 1.5
    elif item_key == "steam_sale":
        player["payment_mult"] *= 0.7
    elif item_key == "brimstone":
        player["brimstone"] = True
        player["brimstone_count"] += 1  # 硫磺火按数量叠加：得分出价区间上下限连乘 0.8ⁿ/1.25ⁿ
    elif item_key == "lucky_sack":
        player["lucky_bag"] += 1  # 福袋：一次性返还，持有数即未用次数
    elif item_key == "perfect_vision":
        player["bid_power"] *= 1.5
    elif item_key == "score_amulet":
        player["flat_score"] += 10
    elif item_key == "interest":
        player["interest"] = True
    elif item_key == "divine_cloak":
        player["divine_cloak"] = True
    elif item_key == "six_dice":
        player["six_dice"] = True
    elif item_key == "mom_heart":
        player["mom_heart"] = True
    elif item_key == "steal_purse":
        player["steal"] = True
    elif item_key == "black_crown":
        player["black_crown"] = True
    elif item_key == "poor_amulet":
        player["poor"] = True
        player["poor_count"] += 1  # 穷人护符按数量叠加（+20/+5 × 持有数）
    elif item_key == "eternal_d6":
        player["score_mult"] *= 1.5
        player["eternal_d6"] = True
    elif item_key == "extra_choice":
        player["extra_choice"] = True


def apply_item(player: dict[str, Any], item_key: str) -> None:
    player["items"].append(item_key)
    _apply_item_effects(player, item_key)


def pick_item() -> str:
    # 按稀有度加权：常见 > 稀有 > 诅咒（权重 4:2:1），保证「常见出现率最高」
    weights = {"common": 4, "rare": 2, "cursed": 1}
    pool = []
    for key, info in ITEMS.items():
        pool.extend([key] * weights.get(info["rarity"], 1))
    return random.choice(pool)


def room_config(level: int, room_type: str) -> dict[str, Any]:
    """按层 + 房间类型确定出价上限与得分参数。

    - 第 2/3 层整体放开到 1~999（用户确认「按层整体放开」）；
      第 1 层普通/宝物房仍 1~99。
    - 特殊 / Boss 房永远允许 1~999。
    - range_max > 99 的房间用更宽的得分参数（c=50, σ=100），
      否则普通房间用紧参数（c=10, σ=10），保证「猜平均」在对应量级上仍有意义。
    """
    range_cap = 999 if level >= 2 else 99
    if room_type in ("special", "boss"):
        range_cap = max(range_cap, 999)
    if range_cap > 99:
        return {
            "range_max": range_cap,
            "c": 50,
            "sigma": 100,
        }
    return {
        "range_max": range_cap,
        "c": 10,
        "sigma": 10,
    }


def room_modifiers(room_type: str) -> list[str]:
    mods: list[str] = []
    if room_type == "boss":
        mods.append("double")
    if room_type == "special" and random.random() < 0.45:
        mods.append("reverse")
    return mods


def room_target(room: dict[str, Any], avg: float) -> float:
    """计算本房间的目标值；反转房在 min(出价上限, 本层资金) 的镜像轴上翻转。

    原实现从 range_max（如第 2 层特殊房是 999）镜像，平均出价低时目标会被推到
    700+，而本层资金只有 500，玩家出价根本够不着目标（“玩不了”）。以本层资金
    作为镜像基准，保证反转目标始终落在玩家资金可触及的范围内。
    """
    target = (2 / 3) * avg + room["c"]
    if "reverse" in room["modifiers"]:
        mirror = min(room["range_max"], room.get("budget", room["range_max"]))
        target = mirror - target
    return clamp(target, 1, room["range_max"])


# 机器人出价策略（_make_bot 随机分配，保存在 bot 的 bot_strategy 字段）。
# 每个策略 = 一组参数，决定「单间最多花整层预算的几倍均分份」与「留多少保底」：
#   slice_mult   单间上限 = 剩余房间均分份 × 该系数（>1 激进，<1 省着花）
#   reserve_frac 非 boss 间不花的保底 = 整层预算 × 该比例（保证撑到 boss 房）
# 目标价的跟随方式（贴近 / 抢道具 / 捡漏 / 搅局）在 bot_bid 里按策略名分支。
BOT_STRATEGIES = {
    "steady":      {"slice_mult": 1.0, "reserve_frac": 0.12},  # 稳健：均分花，留 12%
    "gambler":     {"slice_mult": 1.1, "reserve_frac": 0.15},  # 博彩：死贴目标价，追求高分
    "aggressive":  {"slice_mult": 1.5, "reserve_frac": 0.05},  # 进取：重金抢道具，容易提前破产
    "sniper":      {"slice_mult": 0.8, "reserve_frac": 0.20},  # 捡漏：出低价捡便宜，最省钱
    "joker":       {"slice_mult": 2.0, "reserve_frac": 0.08},  # 搅局者：高方差乱出价，拉升/砸盘均价
}

# 策略出现权重：搅局者只占一小撮（约 11%），当「佐料」而非常态
BOT_STRATEGY_WEIGHTS = {
    "steady": 1.0, "gambler": 1.0, "aggressive": 1.0, "sniper": 1.0, "joker": 0.5,
}


def bot_bid(player: dict[str, Any], room: dict[str, Any], item_key: str) -> Optional[int]:
    """为机器人在指定道具侧出价。普通机器人只参与一个道具；「额外选择」机器人双参。

    资金按跨侧合计：本层资金减去其它道具侧已出价后，才是本侧可用预算。
    预算按「剩余房间数」规划：单间上限 = 剩余均分份 × 策略系数，且非 boss 间留保底，
    避免机器人一层钱全砸在第一间、后段房间（尤其 boss 房）集体没钱退场。
    """
    if player["level_funds"] <= 0:
        return None
    committed = sum(
        room["bids"].get(k, {}).get(player["id"], 0)
        for k in room["items"]
        if k != item_key
    )
    budget = player["level_funds"] - committed
    if budget <= 0:
        return None

    raw_strat = player.get("bot_strategy")
    strat_key = raw_strat if isinstance(raw_strat, str) and raw_strat in BOT_STRATEGIES else "steady"
    strat = BOT_STRATEGIES[strat_key]

    # —— 预算规划：算出本间可花的硬上限 ——
    level = LEVELS[room["level"] - 1]
    level_budget = level["budget"]
    rooms_left = len(level["rooms"]) - room["room_number"]  # 本间之后的房间数
    is_boss = room.get("room_type") == "boss"
    share = player["level_funds"] / max(1, rooms_left + 1)  # 含本间在内的均分份
    cap = share * strat["slice_mult"]
    if is_boss:
        cap = max(cap, player["level_funds"] * 0.7)  # boss 房放开到剩余资金的七成
    # 「额外选择」bot 一房间双参，两侧各按半份花，避免单间破产
    if player.get("extra_choice") and len(room["items"]) >= 2:
        cap = cap / 2

    # —— 目标价与出价偏好（策略差异所在） ——
    side_bids = room["bids"].get(item_key, {})
    if side_bids:
        pred_avg = sum(side_bids.values()) / len(side_bids)
    else:
        # 没有历史时按层预算的比例猜，而不是拍脑袋 500（否则 L2 首波虚高、加速破产）
        pred_avg = min(room["range_max"], level_budget * 0.6)

    target = room_target(room, pred_avg)

    if strat_key == "gambler":
        # 博彩型：死贴目标价，只求得分，不追道具
        desire = target + random.uniform(-3, 3)
    elif strat_key == "aggressive":
        # 进取型：一半概率大幅抬高抢道具，否则正常出价
        desire = target + (
            random.uniform(8, 35) if random.random() < 0.5 else random.uniform(-5, 8)
        )
    elif strat_key == "sniper":
        # 捡漏型：压低出价捡便宜，偶尔赌一把小概率抢到
        desire = target - random.uniform(8, 25) + (
            random.uniform(15, 40) if random.random() < 0.2 else 0
        )
    elif strat_key == "joker":
        # 搅局型：不管输赢，只为把均价搅乱。高方差三连：
        #   1) 12% 发疯梭一把（把均价拉爆）；2) 45% 上下乱跳（拉高/砸低）；
        #   3) 剩下随机乱点（完全不可预测）。从不贴着目标出价。
        r = random.random()
        if r < 0.12:
            desire = player["level_funds"] * random.uniform(0.5, 0.8)
        elif r < 0.45:
            desire = target + random.uniform(target * 0.3, max(40, target * 0.9))
        elif r < 0.75:
            desire = random.uniform(1, max(1, target * 0.3))
        else:
            desire = random.uniform(1, room["range_max"] * 0.6)
    else:
        # 稳健型：大部分贴近目标，偶尔抬一点想赢道具
        desire = target + (
            random.uniform(6, 25) if random.random() < 0.3 else random.uniform(-8, 8)
        )

    bid = int(round(desire))
    bid = max(1, min(room["range_max"], bid))
    bid = min(bid, max(1, int(round(cap))))
    # 破产保护：非 boss 间留保底，不把全部身家赌在一间上
    if not is_boss:
        keep = level_budget * strat["reserve_frac"]
        bid = min(bid, max(1, int(round(player["level_funds"] - keep))))
    return bid


# ---------------------------------------------------------------------------
# 鉴权 / FLAG
# ---------------------------------------------------------------------------

def player_id_for(identity: dict) -> str:
    """由平台用户身份派生游戏内玩家 id：用户 -> u{id}。

    保证同一平台身份跨会话、跨对局使用同一个 id，生涯分随之延续。
    """
    return f"u{identity['platform_id']}"


def lookup_identity(code: str) -> dict:
    """用一次性临时识别码向平台换取用户身份信息。

    返回 {kind: "user", platform_id, name, account?}。

    Raises:
        ValueError: 识别码不是合法十六进制等格式错误。
        Ret2ShellError: 平台返回非 2xx / 网络错误 / 绑定码不存在或已过期。
    """
    if R2S_MOCK:
        return {"kind": "user", "platform_id": 114514, "name": "Mock 用户", "account": "mock_user"}

    with Ret2ShellClient(R2S_BASE_URL, token=R2S_TOKEN or None) as client:
        user = client.account.get_user_info(code)  # 一次性临时识别码（十六进制）
        return {
            "kind": "user",
            "platform_id": user.id,
            "name": user.nickname or user.account,
            "account": user.account,
        }


def generate_flag(identity: dict) -> str:
    """按与比赛平台相同的方式生成动态 FLAG（编码用户 ID）。

    使用 ret2shell-kit 的 PlatformFlagManager，确保 FLAG_KEY / FLAG_TEMPLATE /
    FLAG_PREFIX / FLAG_MODE 与平台评测脚本保持一致即可互相验证。
    """
    mgr = PlatformFlagManager(
        encrypt_key=FLAG_KEY,
        prefix=FLAG_PREFIX,
        template=FLAG_TEMPLATE,
    )
    platform_id = identity["platform_id"]
    if FLAG_MODE == "leet":
        return mgr.generate_leet_flag(platform_id)
    return mgr.generate_uuid_flag(platform_id)


# ---------------------------------------------------------------------------
# WebSocket 握手 token 与验证码
# ---------------------------------------------------------------------------

# 进行中的人机验证答案：challenge id -> 正确文本（纯内存，不落库，
# 服务器重启后自然作废）。玩家状态里只存图片 / 选项 / 时限 / 剩余次数，不存答案。
CAPTCHA_ANSWERS: dict[str, str] = {}


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_ws_token(seed: str, exp: int) -> str:
    """签发 WebSocket 握手 token：base64(payload).hmac。payload 绑定 seed + 过期时间。

    seed 与 session 绑定（已登录 = 玩家 id；匿名 = 匿名会话 id），保证 WS 连接
    必须由一次 HTTP 流程背书，机器无法绕过网页直接连 WS 出价。
    """
    raw = _b64e(json.dumps({"seed": seed, "exp": exp}).encode())
    sig = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_ws_token(token: str) -> Optional[dict]:
    """校验握手 token，合法返回 {seed, exp}，否则返回 None。"""
    try:
        raw, sig = token.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None
    expect = hmac.new(SESSION_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(raw))
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get("seed"):
        return None
    if int(payload.get("exp", 0)) < now_ms():
        return None
    return {"seed": payload["seed"], "exp": int(payload["exp"])}


def _captcha_text(length: int = CAPTCHA_TEXT_LEN) -> str:
    """随机生成 length 个不混淆字符组成的验证码文本（如 "3F7K"）。"""
    return "".join(random.choice(CAPTCHA_CHARS) for _ in range(length))


def _captcha_image(text: str) -> str:
    """把验证码文本渲染成 PNG（captcha 库，自带噪点 / 干扰线 / 颜色），
    返回可直接放进 <img src> 的 base64 data URI。只在发起验证时调用一次。
    """
    data = ImageCaptcha(
        width=CAPTCHA_IMAGE_SIZE[0], height=CAPTCHA_IMAGE_SIZE[1]
    ).generate(text)
    b64 = base64.b64encode(data.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _captcha_options(correct: str) -> list[str]:
    """生成 6 个互不相同的候选文本（与正确答案同长度同字符集），洗牌后返回。

    集合去重保证互不相同，洗牌保证正确项位置随机，前端据此渲染 6 选 1。
    """
    options = {correct}
    while len(options) < 6:
        options.add(_captcha_text(len(correct)))
    opts = list(options)
    random.shuffle(opts)
    return opts


# ---------------------------------------------------------------------------
# 游戏状态
# ---------------------------------------------------------------------------

class Game:
    """对局状态机（全部同步方法）。

    并发不变量：所有 Game 方法必须保持「同步且内部无 await」。单线程事件循环
    下这保证每个方法原子执行，多选手同时出价 / game_loop / HTTP / WS 之间不会
    交错。不要改成异步（例如把 save() 变 awaitable）——那会立刻打开真正的竞态。
    """

    def __init__(self) -> None:
        self.state: dict[str, Any] = self._new_state()
        # 行为分析（仅内存、不持久化）：{pid: {bid_times, react_samples, suspicion, ...}}
        # 服务器重启后清零；禁赛记录在 state["bans"] 里，随 runtime_state 持久化。
        self._behavior: dict[str, dict[str, Any]] = {}

    def _new_state(self) -> dict[str, Any]:
        return {
            "status": "lobby",        # lobby / playing / finished
            "players": [],            # 本局参与者（人类长期保留 + 机器人局内临时）
            "queue": [],              # 对局进行中加入的人类，排队等下一局
            "stats": {},              # 生涯记录：{id: {games_played, total_score, scores, finished_games}}
            "game_number": 0,         # 已完成的局数（下一局编号 +1）
            "leaderboard_frozen_at": None,  # 排行榜冻结时刻（毫秒）；None = 未冻结
            "next_game_at": now_ms() + GAME_INTERVAL_MS,  # 自动开局时间戳（毫秒）
            "current_level": 0,
            "current_room_index": -1,
            "room": None,
            "history": [],
        }

    # -- 序列化 ------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return self.state

    def load_dict(self, data: dict[str, Any]) -> None:
        self.state = data
        # 兼容旧存档：补齐新字段
        for key, value in self._new_state().items():
            self.state.setdefault(key, value)
        # 兼容旧生涯存档：旧版只有累计场均分 total_score，没有逐场记录 scores。
        # 无法还原逐场数据，用场均近似填充（此时生涯分 ≈ 场均），等玩家再打新局后自然更新。
        for st in self.state.get("stats", {}).values():
            if "scores" not in st:
                games = st.get("games_played", 0)
                avg = st.get("total_score", 0.0) / games if games else 0.0
                st["scores"] = [avg] * min(games, BEST_N_GAMES) if games else []
            # 旧存档没有「拿到过 FLAG 的局数」，用生涯局数近似（即便含被禁赛的场次，
            # 也只会让老玩家多看到一次自己的 FLAG——FLAG 本身按 platform_id 确定性生成，
            # 不影响正确性）。
            st.setdefault("finished_games", st.get("games_played", 0))
        # 兼容旧版本道具：改名道具迁到新键，已删除道具（钱袋 / 隐形斗篷 / D6）移除，
        # 然后按 items 重建所有效果字段（倍率 / flag），保证与新道具池行为一致。
        for p in self.state.get("players", []):
            items = []
            for k in p.get("items", []):
                nk = LEGACY_ITEM_MAP.get(k, k)
                if nk not in ITEMS:
                    continue  # 该道具已从道具池删除
                if nk not in items:
                    items.append(nk)
            p["items"] = items
            for field in ("total_score", "level_funds", "level_start_funds", "ready"):
                p.setdefault(field, 0 if field != "ready" else True)
            p.setdefault("character", None)  # 角色：旧存档没有，开局前选择 / 开局随机分配
            # 进行中的人机验证：答案只存在内存（CAPTCHA_ANSWERS），重启后作废，直接清掉
            p["captcha"] = None
            _reset_item_stats(p)

    # -- 玩家 --------------------------------------------------------------
    def human_players(self) -> list[dict[str, Any]]:
        return [p for p in self.state["players"] if not p.get("is_bot")]

    def add_player(
        self,
        name: str,
        is_bot: bool = False,
        player_id: Optional[str] = None,
        auth: Optional[dict] = None,
    ) -> dict[str, Any]:
        if is_bot:
            if self.state["status"] == "playing":
                raise HTTPException(400, "对局进行中不能添加机器人")
            player = new_player(name, is_bot=True)
            self.state["players"].append(player)
            self.save()
            return player

        # 禁赛拦截：人类玩家处于禁赛期（含已存在玩家重新加入）不允许加入对局
        ban = self._active_ban(player_id) if player_id else None
        if ban:
            raise HTTPException(
                403,
                f"您因可疑行为已被禁赛，解禁时间：{fmt_ts(ban['until'])}。"
                "如有疑问请联系管理员。",
            )

        # 同一平台身份已存在则复用（刷新昵称），保证跨会话身份一致
        if player_id:
            existing = self.get_player(player_id)
            if existing:
                if auth:
                    existing["auth"] = auth
                if name:
                    existing["name"] = name.strip() or existing["name"]
                existing["ready"] = True  # 重新加入 = 愿意继续下一局
                self._nudge_next_game()
                self.save()
                self._persist_player(existing)
                return existing

        player = new_player(name, player_id=player_id, auth=auth)
        if self.state["status"] in ("lobby", "finished"):
            # 等待大厅 / 上一局刚结束：直接加入（下一局自动开始时参与；已就绪）
            self.state["players"].append(player)
        else:
            # 对局进行中：进入等待队列，下一局再加入
            self.state["queue"].append(player)
        self._nudge_next_game()
        self.save()
        self._persist_player(player)
        return player

    def _nudge_next_game(self) -> None:
        """有人加入/续局时，保证下一局至少在 START_GRACE_MS 之后才开始。

        用于：打完一局后有人点「继续下一局」时，给其他人留出加入时间；
        也顺带覆盖旧逻辑「开局时间已过且只有一位人类时尽快开局」。
        对局进行中不调用（status == playing 时直接返回）。
        """
        s = self.state
        if s["status"] == "playing":
            return
        now = now_ms()
        if now + START_GRACE_MS > s.get("next_game_at", 0):
            s["next_game_at"] = now + START_GRACE_MS

    def add_authenticated(self, identity: dict) -> dict[str, Any]:
        """按平台身份加入对局：id 由用户 ID 派生，昵称用平台昵称。"""
        return self.add_player(
            identity["name"], player_id=player_id_for(identity), auth=identity
        )

    def get_player(self, player_id: str) -> Optional[dict[str, Any]]:
        for p in self.state["players"] + self.state["queue"]:
            if p["id"] == player_id:
                return p
        return None

    # -- 游戏控制 ----------------------------------------------------------
    def _reset_game_player(self, p: dict[str, Any]) -> None:
        """把一位玩家重置为“新一局”的初始状态（身份与生涯记录保留）。"""
        p["total_score"] = 0
        p["level_funds"] = 0
        p["level_start_funds"] = 0
        p["items"] = []
        _reset_item_stats(p)

    def soft_reset(self) -> None:
        """服务器重启时把进行中的对局带回大厅，但保留人类玩家与生涯记录。"""
        s = self.state
        s["status"] = "lobby"
        s["room"] = None
        s["history"] = []
        s["current_level"] = 0
        s["current_room_index"] = -1
        s["players"] = self.human_players()
        if not s.get("next_game_at") or s["next_game_at"] < now_ms() + 5000:
            s["next_game_at"] = now_ms() + GAME_INTERVAL_MS
        self.save()

    def start_game(self, automatic: bool = False) -> bool:
        """开一局：把等待队列并入玩家，机器人补足到 20 人，然后开始。

        自动开局且没有人类玩家时返回 False（不真正开始），等待有人加入。
        """
        s = self.state
        if s["status"] == "playing":
            raise HTTPException(400, "游戏已经在进行中")

        # 名单 = 大厅里 ready 的人类（打完一局未点「继续下一局」的自动退出）
        #        + 等待队列中的人类（对局进行中加入，已表示愿意进下一局），去重
        humans = [p for p in self.human_players() if p.get("ready", True)]
        ids = {p["id"] for p in humans}
        for p in s["queue"]:
            if p["id"] not in ids:
                humans.append(p)
                ids.add(p["id"])
        if not humans:
            if automatic:
                return False
            raise HTTPException(400, "至少需要一名人类玩家")

        s["queue"] = []
        s["players"] = humans
        for p in humans:
            p["ready"] = True  # 进入本局即视为已就绪
            self._reset_game_player(p)

        # 用机器人补足到 20 人
        while len(humans) < TARGET_PLAYERS:
            humans.append(self._make_bot())
        s["players"] = humans

        # 角色初始道具：人类用开局前所选角色（未选则随机），机器人随机角色
        for p in s["players"]:
            self._apply_character(p)

        s["game_number"] += 1
        s["current_level"] = 0
        s["current_room_index"] = -1
        s["history"] = []
        s["next_game_at"] = now_ms() + GAME_INTERVAL_MS
        s["status"] = "playing"
        self.start_level()
        self.save()
        try:
            store.record_game_start(
                s["game_number"], len(self.human_players()), len(s["players"]), now_ms()
            )
        except Exception as e:
            logger.error(f"record_game_start 写库失败: {e}")
        return True

    def _make_bot(self) -> dict[str, Any]:
        used = {p["name"] for p in self.state["players"]}
        available = [n for n in BOT_NAMES if n not in used]
        name = random.choice(available) if available else f"Bot {len(self.state['players'])+1}"
        bot = new_player(name, is_bot=True)
        # 按权重随机分配出价策略（稳健 / 博彩 / 进取 / 捡漏 / 搅局），
        # 形成多样化的资金使用节奏；搅局者权重较低，只作点缀
        bot["bot_strategy"] = random.choices(
            list(BOT_STRATEGIES),
            weights=[BOT_STRATEGY_WEIGHTS[k] for k in BOT_STRATEGIES],
            k=1,
        )[0]
        return bot

    def restart_game(self) -> None:
        self.start_game(automatic=False)

    def _apply_character(self, player: dict[str, Any]) -> None:
        """开局时按角色赋予初始道具；未选角色随机分配，伊甸掷一件随机道具。"""
        key = player.get("character") or random.choice(list(CHARACTERS))
        player["character"] = key
        item_key = CHARACTERS[key]["item"]
        if item_key == "random":
            item_key = pick_item()
        apply_item(player, item_key)

    def set_character(self, player: dict[str, Any], character_key: str) -> None:
        """等待大厅中选择角色（开局前可随时修改）；对局进行中禁止修改。"""
        if self.state["status"] == "playing":
            raise HTTPException(400, "对局进行中不能修改角色")
        if character_key not in CHARACTERS:
            raise HTTPException(400, "未知角色")
        player["character"] = character_key
        self.save()

    def start_level(self) -> None:
        level_index = self.state["current_level"]
        level = LEVELS[level_index]
        for p in self.state["players"]:
            budget = level["budget"]
            if p.get("interest"):
                # 利息：进入下一层时初始资金 +20%
                budget = int(budget * 1.2)
            p["level_funds"] = budget
            p["level_start_funds"] = budget  # 穷人护符的「本层初始资金」阈值基准
            p["divine_used"] = False         # 神圣斗篷：每层重新获得一次失败退款
        self.state["current_room_index"] = 0
        self.open_room()

    def open_room(self) -> None:
        level_index = self.state["current_level"]
        room_type = LEVELS[level_index]["rooms"][self.state["current_room_index"]]
        cfg = room_config(level_index + 1, room_type)
        mods = room_modifiers(room_type)

        # 先结算「Room 开始」效果：利息资金 +10%（每个房间，含首间）；
        # 穷人护符资金 -10%（进入「下一个」房间时，不含本层首间）。
        for p in self.state["players"]:
            if p.get("interest"):
                p["level_funds"] += int(p["level_funds"] * 0.10)
            if p.get("poor") and self.state["current_room_index"] > 0:
                p["level_funds"] -= int(p["level_funds"] * 0.10)
            if p["level_funds"] < 0:
                p["level_funds"] = 0

        # 偷钱袋：每个房间「开始时」（出价前）结算，从总资产第一名偷取 10%。
        # 这样偷到的钱能用于本房间出价——层末/局末最后一间也不至于偷来只当留存。
        self._apply_steal()

        items = self._roll_room_items()
        room = {
            "level": level_index + 1,
            "room_number": self.state["current_room_index"] + 1,
            "room_type": room_type,
            "range_max": cfg["range_max"],
            "c": cfg["c"],
            "sigma": cfg["sigma"],
            "budget": LEVELS[level_index]["budget"],  # 反转目标的镜像基准（min(range_max, budget)）
            "modifiers": mods,
            "items": items,
            "phase": "bidding",
            "started_at": now_ms(),
            "deadline": now_ms() + ROOM_DURATION_MS,
            "result_end": None,
            "bids": {},
            "result": None,
        }
        self.state["room"] = room
        self.save()

    def _roll_room_items(self) -> list[str]:
        """生成本房间的两个互不相同道具。"""
        items: list[str] = []
        while len(items) < 2:
            key = pick_item()
            if key in items:
                continue
            items.append(key)
        return items

    def settle_room(self) -> bool:
        """结算当前房间。真正发生 bidding → result 转变时返回 True，否则 False。

        返回布尔值让调用方（game_loop / api_skip）据实决定是否广播，避免
        重复触发产生多余的 settle 广播（并发审计发现的问题）。

        单房间双道具：两个道具各自独立竞拍、分数分开计算。普通玩家只能参与
        其中一个；拥有「额外选择」的玩家可同时参与两个，该局得分按
        （两个得分相加）×0.75 计算。
        """
        room = self.state["room"]
        if not room or room["phase"] != "bidding":
            return False

        items = room["items"]

        # 两个道具侧都没有出价：直接进入 result（空结果）
        if not any(room["bids"].get(k) for k in items):
            room["phase"] = "result"
            room["result_end"] = now_ms() + RESULT_DURATION_MS
            room["result"] = {
                "sides": [
                    {
                        "item": k,
                        "item_name": ITEMS[k]["name"],
                        "avg": 0,
                        "target": 0,
                        "winner_id": None,
                        "winner_name": None,
                        "entries": [],
                    }
                    for k in items
                ],
                "combined": {},
            }
            self.state["history"].append({
                "type": "room",
                "level": room["level"],
                "room": room["room_number"],
                "room_type": room["room_type"],
                "items": [
                    {"item": k, "winner_name": None, "avg": 0, "target": 0}
                    for k in items
                ],
            })
            self.save()
            self._persist_room(room)
            return True

        # 分侧结算（各自独立 avg/target/score/pay/winner），先不累加总分
        side_results = []
        combined = {}    # pid -> 两侧原始得分之和
        side_count = {}  # pid -> 参与的侧数
        for item_key in items:
            sr = self._settle_side(room, item_key)
            side_results.append(sr)
            for e in sr["entries"]:
                combined[e["player_id"]] = combined.get(e["player_id"], 0.0) + e["score"]
                side_count[e["player_id"]] = side_count.get(e["player_id"], 0) + 1

        # 统一计入总分：更多选择（extra_choice）双参玩家 (s1+s2)×0.75；
        # 黑王子之冠在计入时叠加动态加成（+25% − 5%×其他道具数，最低 +5%）。
        # 初始加成 +25%：现在每个玩家开局都自带一个角色道具，「其他道具数」天然 ≥1，故基准上调。
        per_side_scores = [
            {e["player_id"]: e["score"] for e in sr["entries"]}
            for sr in side_results
        ]
        combined_detail = {}
        for pid, raw in combined.items():
            player = self.get_player(pid)
            if not player:
                continue
            double_participant = player.get("extra_choice") and side_count[pid] >= 2
            final = raw * 0.75 if double_participant else raw
            if player.get("black_crown"):
                other_items = max(0, len(player.get("items", [])) - 1)  # 除黑王子之冠外的道具数
                bonus = max(0.05, 0.25 - 0.05 * other_items)
                final *= 1 + bonus
            if double_participant:
                combined_detail[pid] = {
                    "s1": round(per_side_scores[0].get(pid, 0), 2),
                    "s2": round(per_side_scores[1].get(pid, 0), 2),
                    "final": round(final, 2),
                }
            player["total_score"] += final

        # 赢家按各自道具侧拿道具（更多选择玩家可能双赢）
        for sr in side_results:
            if sr["winner_id"]:
                winner = self.get_player(sr["winner_id"])
                assert winner is not None, "竞拍赢家必然存在"
                apply_item(winner, sr["item"])

        room["phase"] = "result"
        room["result_end"] = now_ms() + RESULT_DURATION_MS
        room["result"] = {
            "sides": [
                {
                    "item": sr["item"],
                    "item_name": ITEMS[sr["item"]]["name"],
                    "avg": sr["avg"],
                    "target": sr["target"],
                    "winner_id": sr["winner_id"],
                    "winner_name": sr["winner_name"],
                    "entries": sr["entries"],
                }
                for sr in side_results
            ],
            "combined": combined_detail,
        }

        self.state["history"].append({
            "type": "room",
            "level": room["level"],
            "room": room["room_number"],
            "room_type": room["room_type"],
            "items": [
                {
                    "item": sr["item"],
                    "winner_name": sr["winner_name"],
                    "avg": sr["avg"],
                    "target": sr["target"],
                }
                for sr in side_results
            ],
        })
        self.save()
        self._persist_room(room)
        return True

    def _apply_steal(self) -> None:
        """偷钱袋：每个房间开始时（出价前），从「总资产第一名」（资金最高者）偷取 10%。

        在 open_room 调用（Room 开始效果之后、出价之前），让偷到的钱能用于本房间出价。
        目标资金为 0 时无事发生。
        """
        for thief in [p for p in self.state["players"] if p.get("steal")]:
            others = [p for p in self.state["players"] if p["id"] != thief["id"]]
            if not others:
                continue
            top = max(others, key=lambda p: p["level_funds"])
            steal = int(top["level_funds"] * 0.10)
            if steal <= 0:
                continue
            top["level_funds"] -= steal
            thief["level_funds"] += steal

    def _settle_side(self, room: dict[str, Any], item_key: str) -> dict[str, Any]:
        """结算房间中一个道具侧的竞拍：独立平均/目标/得分/支付/赢家。

        只扣支付、不累加 total_score（总分由 settle_room 统一计入，以支持
        「更多选择」双参玩家的 (s1+s2)×0.75 合并规则）。

        道具效果在这一层生效：
        - 平均出价用「有效出价」（完美视力 x1.5 计入求和）；得分公式仍按初始出价。
        - 硫磺火在出价 80%~125% 区间取最接近目标的值作为得分出价（平均仍按初始出价）。
        - 固定加分（积分护符 +10/个；穷人护符 +20/+5 动态/件，按数量叠加）先加进 base，再被比例乘算（圣心/永恒六面骰 x1.5）放大。
        - 六面骰 1/6 概率得分 x200%；永恒六面骰 25% 概率得分清零；妈妈的心脏在 Boss 房 x200%。
        - 神圣斗篷每层首次竞争失败退回全部支付资金。
        """
        side_bids = room["bids"].get(item_key, {})
        if not side_bids:
            return {
                "item": item_key,
                "avg": 0,
                "target": 0,
                "winner_id": None,
                "winner_name": None,
                "entries": [],
            }

        # 有效出价：完美视力（及叠乘）的 bid_power 只计入「出价之和」与「道具竞争」。
        eff_bids: dict[str, float] = {}
        for pid, bid in side_bids.items():
            player = self.get_player(pid)
            eff_bids[pid] = bid * (player["bid_power"] if player else 1.0)

        avg = sum(eff_bids.values()) / len(eff_bids)
        target = room_target(room, avg)
        # 平局时先出价者获胜（dict 保持插入顺序，同旧 `>` 判定）
        winner_id = max(eff_bids, key=lambda pid: eff_bids[pid])

        entries = []
        for pid, bid in list(side_bids.items()):
            player = self.get_player(pid)
            if not player:
                continue

            # 硫磺火：得分时可在出价 80%~125% 区间取最高分（取最接近目标的值）；
            # 多件时区间上下限连乘（0.8ⁿ×~1.25ⁿ×，与「重复道具可叠加」一致）
            scoring_bid = bid
            n_brim = player.get("brimstone_count", 0)
            if n_brim:
                scoring_bid = clamp(
                    target, bid * (0.8 ** n_brim), bid * (1.25 ** n_brim)
                )

            base = 100 * math.exp(-abs(scoring_bid - target) / room["sigma"])
            base = max(base, MIN_SCORE_PER_ROOM)  # 保底分：避免远离目标时得分掉到 0.x

            # 固定加分先加进 base，再被比例乘算（乘区道具）放大：
            # 积分护符 +10/个；穷人护符按资金动态 +20/+5，按持有数量叠加
            fixed = player["flat_score"]
            if player.get("poor_count", 0):
                low_thresh = player.get("level_start_funds", 0) * 0.3
                poor_bonus = 20 if player["level_funds"] < low_thresh else 5
                fixed += poor_bonus * player["poor_count"]
            score = (base + fixed) * player["score_mult"]

            if "double" in room["modifiers"]:
                score *= 2
            # 妈妈的心脏：Boss Room 中的得分 x200%（不涉及出价/支付）
            if player.get("mom_heart") and room["room_type"] == "boss":
                score *= 2
            # 六面骰：1/6 概率当前房间得分 x200%
            if player.get("six_dice") and random.random() < 1 / 6:
                score *= 2
            # 永恒六面骰：25% 概率本房间得分清零
            if player.get("eternal_d6") and random.random() < 0.25:
                score = 0

            # 全付：所有参与者都扣钱；Steam大促（x0.7）作用于 payment_mult
            pay = int(round(bid * player["payment_mult"]))
            # 福袋：一次性返还 75%，下一笔支付只扣 25%（用后消耗并从道具列表移除）
            if player.get("lucky_bag", 0) > 0:
                pay = int(round(bid * player["payment_mult"] * 0.25))
                player["lucky_bag"] -= 1
                if "lucky_sack" in player["items"]:
                    player["items"].remove("lucky_sack")
            pay = max(0, min(pay, player["level_funds"]))
            player["level_funds"] -= pay

            # 神圣斗篷：每层首次竞争失败退回该次支付的全部资金（之后本层不再触发）
            divine_refund = False
            if (
                player.get("divine_cloak")
                and not player.get("divine_used")
                and pid != winner_id
            ):
                player["divine_used"] = True
                player["level_funds"] += pay
                pay = 0
                divine_refund = True

            entries.append({
                "player_id": pid,
                "player_name": player["name"],
                "bid": bid,
                "effective_bid": round(eff_bids[pid], 2),
                "score": round(score, 2),
                "paid": pay,
                "divine_refund": divine_refund,
            })

        winner_name = None
        if winner_id:
            winner = self.get_player(winner_id)
            winner_name = winner["name"] if winner else None

        return {
            "item": item_key,
            "avg": round(avg, 2),
            "target": round(target, 2),
            "winner_id": winner_id,
            "winner_name": winner_name,
            "entries": entries,
        }

    def advance(self) -> None:
        if self.state["status"] != "playing":
            return

        level_index = self.state["current_level"]
        rooms = LEVELS[level_index]["rooms"]
        self.state["current_room_index"] += 1

        if self.state["current_room_index"] >= len(rooms):
            # 层结束：剩余资金 10% 转分
            for p in self.state["players"]:
                bonus = int(math.floor(p["level_funds"] * 0.1))
                p["total_score"] += bonus
                p["level_funds"] = 0

            # 记录层结算
            self.state["history"].append({
                "type": "level_end",
                "level": level_index + 1,
                "details": "本层结束，剩余资金的 10% 转化为积分",
            })

            self.state["current_level"] += 1
            if self.state["current_level"] >= len(LEVELS):
                self.finish_game()
                return
            self.start_level()
        else:
            self.open_room()

    def finish_game(self) -> None:
        s = self.state
        stats = s.setdefault("stats", {})
        # 「已完成局数」：与生涯计分完全解耦，冻结与否都无条件累加。
        # public_state 用它判断是否把 FLAG 下发给本人——若沿用 games_played，
        # 冻结后生涯局数停止增长，新参赛选手打完一局也永远看不到自己的 FLAG。
        # 必须无条件覆盖所有人类（含本局被禁赛者），否则冻结后「第一局就被禁赛」
        # 的选手在 stats 里没有任何条目，FLAG 展示会静默消失——而同样场景在未冻结时
        # 因为下面的 games_played 兜底是能显示的。冻结不应改变 FLAG 的任何行为。
        for p in self.human_players():
            st = stats.setdefault(
                p["id"], {"games_played": 0, "total_score": 0.0, "scores": []}
            )
            st["finished_games"] = st.get("finished_games", 0) + 1

        # 记录生涯成绩（只算人类；机器人不进入生涯分）
        # 排行榜冻结后不再累加生涯数据：榜单定榜。注意这里只掐掉「生涯计分」，
        # 下面的 FLAG 发放循环与自动开局 / 对局结算完全不受影响——
        # 冻结后选手照常参赛，完整打完一局仍会拿到 FLAG。
        if not LEADERBOARD_FROZEN:
            for p in self.human_players():
                st = stats.setdefault(p["id"], {"games_played": 0, "total_score": 0.0, "scores": []})
                st["games_played"] += 1
                # 折算成“单局均分”（总分 / 总房间数），量级接近 0~100，便于阅读
                game_score = round(p["total_score"] / TOTAL_ROOMS, 2)
                st["total_score"] += game_score
                # 定三取五：只保留生涯最好 BEST_N_GAMES 场的单局均分
                scores = st.setdefault("scores", [])
                scores.append(game_score)
                scores.sort(reverse=True)
                del scores[BEST_N_GAMES:]

        # 为完成本局的人类玩家生成动态 FLAG，并写入 info 日志。
        # 本循环只负责「发放 + 审计」；是否把 FLAG 下发给本人由 public_state 依据
        # finished_games 判定（见上面的注释）。
        # 被禁赛的玩家本局被禁止出价，不视为完整完成，跳过 FLAG。
        for p in self.human_players():
            auth = p.get("auth")
            if not auth:
                continue
            if self._active_ban(p["id"]):
                logger.info(f"玩家被禁赛，本局不发放 FLAG: id={p['id']}")
                continue
            try:
                flag = generate_flag(auth)
            except Exception as e:
                logger.error(f"生成 FLAG 失败: {auth} {e}")
                continue
            p["last_flag"] = flag
            logger.info(
                f"玩家完成一局获得 FLAG: 昵称={p['name']} "
                f"{auth['kind']}_id={auth['platform_id']} FLAG={flag}"
            )
            try:
                store.record_flag(
                    p["id"], auth.get("platform_id"), s["game_number"], flag, now_ms()
                )
            except Exception as e:
                logger.error(f"record_flag 写库失败: {p['id']} {e}")

        # 移除机器人，人类留在大厅等待下一局；未点「继续下一局」的自动退出
        for p in self.human_players():
            p["ready"] = False
        s["players"] = self.human_players()
        s["status"] = "finished"
        s["room"] = None
        # 给一段「自主选择是否继续」的窗口；到点无人继续则由 game_loop 滚动等待
        s["next_game_at"] = now_ms() + CONTINUE_GRACE_MS
        self.save()

        # 审计记录：生涯镜像 / 对局结束 / 最终排名
        try:
            for p in self.human_players():
                self._persist_player(p)
            store.record_game_finish(s["game_number"], now_ms())
            ranked = sorted(
                self.human_players(), key=lambda p: p["total_score"], reverse=True
            )
            store.record_rankings(
                s["game_number"],
                [
                    {
                        "id": p["id"],
                        "total_score": p["total_score"],
                        "level_funds": p["level_funds"],
                    }
                    for p in ranked
                ],
            )
        except Exception as e:
            logger.error(f"finish_game 审计写库失败: {e}")

        # 排行榜冻结时，把定榜快照落库一次（幂等；放在审计写入之后，保证
        # players 表已是最新）
        self.ensure_freeze_snapshot()

    # -- 排行榜冻结 --------------------------------------------------------
    def ensure_freeze_snapshot(self) -> None:
        """冻结生效时把当前排行榜落库一次，作为定榜存档（幂等）。

        触发时机：进程启动（lifespan）+ 每次 finish_game 收尾。
        因为冻结后生涯数据不再累加，榜单内容此后恒定，所以「首次观察到冻结」
        与「之后任意时刻」拍下的快照内容一致，幂等不会丢信息。

        幂等的唯一依据是**数据库**里有没有 leaderboard_snapshots 记录，
        内存里的 s["leaderboard_frozen_at"] 只是给前端展示用的缓存，不参与「是否该落库」
        的判断——否则想重新定榜（清表重来）就得同时清掉 runtime_state JSON 深处的一个键，
        很容易漏掉。这里反而会在发现库里已有快照时用库里的时刻回填缓存，保证前端显示一致。
        """
        if not LEADERBOARD_FROZEN:
            return
        s = self.state
        try:
            existing = store.get_leaderboard_snapshot()
        except Exception as e:
            logger.error(f"get_leaderboard_snapshot 读库失败: {e}")
            return
        if existing:
            # 库里已有定榜存档：只同步展示用的时刻，绝不重复插、也不刷新时刻
            frozen_at = existing[0]["frozen_at"]
            if s.get("leaderboard_frozen_at") != frozen_at:
                s["leaderboard_frozen_at"] = frozen_at
                self.save()
            return
        frozen_at = now_ms()
        rows = career_leaderboard()
        if not rows:
            # 空快照会将「库里有存档」这一幂等标记永久置位，此后即便有人达标也无法再定榜，
            # 所以这里只告警、不落库（下次 finish_game / 重启会再试一次）。
            logger.warning(
                f"排行榜冻结时无人达标，暂不落定榜快照: 冻结时间={fmt_ts(frozen_at)}"
            )
            return
        try:
            store.record_leaderboard_snapshot(frozen_at, rows)
        except Exception as e:
            logger.error(f"record_leaderboard_snapshot 写库失败: {e}")
            return
        s["leaderboard_frozen_at"] = frozen_at
        logger.info(
            f"排行榜已冻结: 冻结时间={fmt_ts(frozen_at)} 入榜人数={len(rows)}"
        )
        self.save()

    # -- 生涯分（定三取五） ------------------------------------------------
    def _career(self) -> tuple[list[dict[str, Any]], float]:
        """返回 (带生涯数据的玩家列表, 全局场均分)。

        生涯分「定三取五」：
          - 至少打满 MIN_GAMES_FOR_RANK 局才能进入排行榜（eligible）；
          - 生涯分 = 生涯最好 BEST_N_GAMES 场的单局均分的平均；
            不足 BEST_N_GAMES 场时取全部已打场次的均分。
        """
        s = self.state
        stats = s.get("stats", {})
        # 全局场均（所有人类所有场次的均分，仅信息展示，不参与生涯分公式）
        total_games = sum(st["games_played"] for st in stats.values())
        total_cum = sum(st["total_score"] for st in stats.values())
        global_avg = total_cum / total_games if total_games else 0.0
        # 人机验证失败次数（来自禁赛审计表，供排行榜展示）
        fail_counts = store.get_ban_counts(CAPTCHA_FAIL_BAN_REASONS)

        in_game_ids = {p["id"] for p in s["players"]}
        rows: list[dict[str, Any]] = []
        # 生涯列表只保留人类玩家（机器人为局内临时对象，不进入生涯）
        for p in s["players"] + s["queue"]:
            if p.get("is_bot"):
                continue
            st = stats.get(p["id"], {"games_played": 0, "total_score": 0.0, "scores": []})
            games = st["games_played"]
            cum = st["total_score"]
            avg = cum / games if games else None
            # scores 已在 finish_game 里裁剪为「最好 BEST_N_GAMES 场」，这里直接取均值
            scores = st.get("scores") or []
            career = (sum(scores) / len(scores)) if scores else None
            rows.append({
                "id": p["id"],
                "name": p["name"],
                "character": p.get("character"),
                "is_bot": p.get("is_bot", False),
                "in_game": p["id"] in in_game_ids,
                "ready": p.get("ready", True),   # 是否愿意继续下一局（finished 后前端据此显示「继续下一局」）
                "total_score": round(p.get("total_score", 0), 2),   # 本局总分
                "level_funds": p.get("level_funds", 0),
                "items": p.get("items", []),
                "career": round(career, 2) if career is not None else None,  # 生涯分（最好 N 场均分）
                "eligible": games >= MIN_GAMES_FOR_RANK,           # 是否够局数上榜
                "avg": round(avg, 2) if avg is not None else None,  # 生涯场均
                "games_played": games,
                "verify_failures": fail_counts.get(p["id"], 0),   # 人机验证失败累计次数
            })
        return rows, round(global_avg, 2)

    # -- 出价 --------------------------------------------------------------
    def place_bid(self, player_id: str, item_key: str, value: int) -> None:
        if self.state["status"] != "playing":
            raise HTTPException(400, "游戏不在进行中")
        room = self.state["room"]
        if not room or room["phase"] != "bidding":
            raise HTTPException(400, "当前不在出价阶段")
        player = self.get_player(player_id)
        if not player:
            raise HTTPException(404, "玩家不存在")

        # 反作弊拦截（人类玩家）：禁赛期间 / 有待完成的人机验证时禁止出价
        if not player.get("is_bot"):
            ban = self._active_ban(player_id)
            if ban:
                raise HTTPException(
                    403,
                    f"您因可疑行为已被禁赛，解禁时间：{fmt_ts(ban['until'])}。"
                    "如有疑问请联系管理员。",
                )
            cap = player.get("captcha")
            if cap and cap.get("pending"):
                raise HTTPException(
                    403,
                    "检测到可疑操作，请先在 15 秒内完成人机验证（见弹出窗口）再出价。",
                )

        if item_key not in room["items"]:
            raise HTTPException(400, "目标道具不在当前房间")
        if player["level_funds"] <= 0:
            raise HTTPException(400, "资金不足，当前房间只能观战")
        if not isinstance(value, int) or value < 1 or value > room["range_max"]:
            raise HTTPException(400, f"出价必须是 1~{room['range_max']} 的整数")

        # 普通玩家只能在两侧选一侧；改投另一侧时撤掉原侧出价（换选）。
        # 「额外选择」玩家可以同时参与两个，不受此限制。
        if not player.get("extra_choice"):
            for other in room["items"]:
                if other != item_key and player_id in room["bids"].get(other, {}):
                    del room["bids"][other][player_id]
                    if not room["bids"][other]:
                        del room["bids"][other]

        # 资金按跨侧合计校验。折扣/返还道具（Steam大促 x0.7 / 福袋一次性 x0.25）按
        # 「实际扣除」校验：返还类道具可支撑高于当前资金的出价（仍受房间出价上限约束）。
        other_items = [k for k in room["items"] if k != item_key]
        committed = sum(
            room["bids"].get(k, {}).get(player_id, 0) for k in other_items
        ) + value
        payable = int(round(committed * player["payment_mult"]))
        # 福袋：尚未使用时可把本次合计出价按返还 75% 校验（用后即消耗）
        if player.get("lucky_bag", 0) > 0:
            payable = int(round(committed * player["payment_mult"] * 0.25))
        if payable > player["level_funds"]:
            raise HTTPException(400, "按折扣后实际扣除的资金超过当前剩余资金")

        room["bids"].setdefault(item_key, {})[player_id] = value
        self.save()

        # 反作弊：出价已被接受后先做行为分析（可疑分累计达到阈值触发验证），
        # 再随机抽查（与行为无关的小概率点名验证）。都放在 save 之后，保证
        # 出价先落地、验证再介入，避免误伤正常出价。
        if not player.get("is_bot"):
            self._check_behavior(player, room, now_ms())
            self._maybe_spotcheck(player)

    # -- 反作弊：行为分析 / 人机验证 / 禁赛 ---------------------------------
    def _behavior_for(self, player_id: str) -> dict[str, Any]:
        """取玩家行为分析记录（内存态，缺省初始化）。"""
        return self._behavior.setdefault(
            player_id,
            {
                "bid_times": [],            # 近 10s 的出价时刻（用于检测连发 / 高频出价）
                "react_samples": {},        # room_sig -> 反应时间(ms)，每房间只留最新
                "suspicion": 0.0,           # 累计可疑分（带时间衰减）
                "suspicion_at": now_ms(),
                "consistency_flagged": False,  # 跨房间时间一致性信号只计一次
                "burst_at": 0,              # 最近一次「连发」信号的时间（防同一段重复累计）
                "spam_at": 0,               # 最近一次「高频出价」信号的时间
                "activity_seen": False,     # 浏览器是否上报过人类活动（鼠标/键盘）
                "no_activity_flagged": False,  # 「未见活动信号却持续出价」只计一次
                "bids_no_activity": 0,      # 未见活动信号时的累计出价次数
                "last_verified_at": 0,      # 最近一次通过人机验证的时刻
            },
        )

    def _suspicion_score(self, b: dict[str, Any], now: int) -> float:
        """带衰减的可疑分：距最近一次累加越久，分越低，避免「留案底」。"""
        age_s = (now - b.get("suspicion_at", now)) / 1000.0
        if age_s <= 0:
            return b.get("suspicion", 0.0)
        return b.get("suspicion", 0.0) * (SUSPICION_DECAY ** (age_s / SUSPICION_DECAY_S))

    def _active_ban(self, player_id: str) -> Optional[dict[str, Any]]:
        """返回仍在有效期内的禁赛记录，否则 None（过期视为已解除）。"""
        ban = self.state.get("bans", {}).get(player_id)
        if ban and ban.get("until", 0) > now_ms():
            return ban
        return None

    def _issue_captcha(self, player: dict[str, Any]) -> None:
        """发起一次人机验证：captcha 库渲染的图片验证码单选（6 选 1），15 秒限时。

        答案（正确文本）只存内存 CAPTCHA_ANSWERS（key=challenge id），玩家状态里
        只落图片 / 选项 / 时限 / 剩余次数，避免答案随 runtime_state 持久化而泄露。
        触发后立即 save 以便广播给本人。
        """
        now = now_ms()
        text = _captcha_text()
        options = _captcha_options(text)
        cid = new_id()
        CAPTCHA_ANSWERS[cid] = text
        player["captcha"] = {
            "pending": True,
            "id": cid,
            "image": _captcha_image(text),
            "options": options,
            "deadline": now + CAPTCHA_WINDOW_MS,
            "attempts_left": CAPTCHA_MAX_ATTEMPTS,
        }
        self.save()

    def _maybe_spotcheck(self, player: dict[str, Any]) -> None:
        """随机抽查人机验证：与行为分析无关，每次出价后以小概率点名验证。

        与行为触发验证共用同一套弹窗 / 倒计时 / 禁赛逻辑，因此同样受
        VERIFY_COOLDOWN_MS 宽限约束，避免反复打扰正常玩家；已有进行中的验证
        或正在禁赛期时不再叠加。
        """
        if player.get("is_bot") or player.get("captcha"):
            return
        if self._active_ban(player["id"]):
            return
        b = self._behavior_for(player["id"])
        if now_ms() - b.get("last_verified_at", 0) < VERIFY_COOLDOWN_MS:
            return
        if random.random() >= CAPTCHA_SPOTCHECK_PROB:
            return
        self._issue_captcha(player)
        logger.info(
            f"随机抽查[{player['id']}] {player['name']}: 随机点名人机验证 "
            f"(challenge={player['captcha']['id']})"
        )

    def answer_captcha(
        self, player_id: str, cid: str, answer: Any
    ) -> tuple[bool, str]:
        """处理人机验证答案。返回 (是否通过, 提示消息)。

        通过：清除 pending、可疑分清零并记录 last_verified_at（宽限期内不再触发）。
        答错：扣一次机会，机会用尽或超时 -> apply_ban 禁赛 1 天。
        """
        player = self.get_player(player_id)
        if not player:
            return False, "玩家不存在"
        cap = player.get("captcha")
        if not cap or not cap.get("pending"):
            return False, "当前没有待完成的人机验证"
        if cap.get("id") != cid:
            return False, "验证会话不匹配，请刷新后重试"
        if now_ms() > cap["deadline"]:
            self.apply_ban(player_id, CAPTCHA_FAIL_TIMEOUT)
            return False, "验证超时，已禁赛 1 天。"
        correct = CAPTCHA_ANSWERS.get(cid)
        # 前端提交所选候选文本；对大小写 / 首尾空白宽容后与内存答案比较
        chosen = str(answer).strip() if answer is not None else ""
        if correct is not None and chosen == correct:
            player["captcha"] = None
            CAPTCHA_ANSWERS.pop(cid, None)
            b = self._behavior_for(player_id)
            b["suspicion"] = 0.0
            b["suspicion_at"] = now_ms()
            b["last_verified_at"] = now_ms()
            self.save()
            logger.info(f"行为分析[{player_id}] 人机验证通过，可疑分已清零")
            return True, "验证通过，可以继续出价。"
        cap["attempts_left"] -= 1
        if cap["attempts_left"] <= 0:
            self.apply_ban(player_id, CAPTCHA_FAIL_WRONG)
            return False, "验证码错误次数过多，已禁赛 1 天。"
        self.save()
        return False, f"验证码错误，剩余 {cap['attempts_left']} 次机会。"

    def apply_ban(self, player_id: str, reason: str) -> None:
        """禁赛 1 天：写入 state['bans']（随 runtime_state 持久化）并审计落库。

        同时清除进行中的人机验证（已没意义）。机器人不会被调用。
        """
        now = now_ms()
        until = now + BAN_DURATION_MS
        self.state.setdefault("bans", {})[player_id] = {
            "until": until,
            "reason": reason,
            "banned_at": now,
        }
        player = self.get_player(player_id)
        if player:
            # 清除进行中的验证（含内存中的答案），避免悬挂
            cid = (player.get("captcha") or {}).get("id")
            if isinstance(cid, str):
                CAPTCHA_ANSWERS.pop(cid, None)
            player["captcha"] = None
        self.save()
        auth = (player or {}).get("auth") or {}
        try:
            store.record_ban(player_id, auth.get("platform_id"), until, reason, now)
        except Exception as e:
            logger.error(f"record_ban 写库失败: {player_id} {e}")
        name = player["name"] if player else "?"
        logger.info(
            f"玩家禁赛: 昵称={name} id={player_id} reason={reason} "
            f"解禁时间={fmt_ts(until)}"
        )

    def _check_behavior(self, player: dict[str, Any], room: dict[str, Any], now: int) -> None:
        """出价后累计行为可疑分，达到阈值触发人机验证。

        信号（均为启发式，权重见注释）：
          - 反应时间 < 200ms（几乎必是机器）；200~500ms（极快）—— 依据
            房间 started_at 到出价落地的间隔。
          - 2 秒内出价连发 >= 3 次。
          - 跨房间反应时间标准差 < 40ms（>= 4 个房间，机器定时器特征）。
          - 从未上报浏览器人类活动（鼠标/键盘 activity）却持续出价 >= 3 次。
        单个「超快反应」不触发（1.0 < 1.5），需叠加其它信号，降低误伤。
        """
        pid = player["id"]
        b = self._behavior_for(pid)
        # started_at 缺失（手工构造的 room / 旧快照）时跳过反应时间信号，其余信号不受影响
        started = room.get("started_at")
        react: Optional[int] = max(0, now - started) if isinstance(started, int) else None
        if react is not None:
            b["react_samples"][f"{room.get('level', 0)}:{room.get('room_number', 0)}"] = react
        b["bid_times"].append(now)
        b["bid_times"] = [t for t in b["bid_times"] if now - t < 10_000]

        add = 0.0
        reasons: list[str] = []
        if react is not None and react < 200:
            add += 1.0
            reasons.append(f"出价反应时间异常({react}ms)")
        elif react is not None and react < 500:
            add += 0.4
            reasons.append(f"出价反应时间极快({react}ms)")
        # 2 秒内出价 >= 3 次：一段「连发」只计一次（防止真人连续改价被重复累计）
        if len(b["bid_times"]) >= 3 and now - b.get("burst_at", 0) > 2000:
            add += 0.6
            b["burst_at"] = now
            reasons.append("2 秒内出价连发 3 次")
        # 10 秒内出价 >= 10 次：持续高频出价（典型机器脚本特征），同样只计一次
        if len(b["bid_times"]) >= 10 and now - b.get("spam_at", 0) > 10_000:
            add += 1.0
            b["spam_at"] = now
            reasons.append("10 秒内高频出价 10 次")
        if not b.get("consistency_flagged"):
            samples = list(b["react_samples"].values())
            if len(samples) >= 4:
                mean = sum(samples) / len(samples)
                variance = sum((x - mean) ** 2 for x in samples) / len(samples)
                if math.sqrt(variance) < 40:
                    add += 0.8
                    b["consistency_flagged"] = True
                    reasons.append("跨房间反应时间过于一致")
        if not b.get("activity_seen") and not b.get("no_activity_flagged"):
            b["bids_no_activity"] = b.get("bids_no_activity", 0) + 1
            if b["bids_no_activity"] >= 3:
                add += 0.5
                b["no_activity_flagged"] = True
                reasons.append("未检测到人类活动信号却持续出价")

        effective = self._suspicion_score(b, now)
        b["suspicion"] = effective + add
        b["suspicion_at"] = now
        if add and reasons:
            logger.info(
                f"行为分析[{pid}] {player['name']}: " + "; ".join(reasons)
                + f" 累计可疑分={round(b['suspicion'], 2)}"
            )
        if b["suspicion"] >= SUSPICION_THRESHOLD and not player.get("captcha"):
            if now - b.get("last_verified_at", 0) >= VERIFY_COOLDOWN_MS:
                self._issue_captcha(player)
                b["suspicion"] = 0.0
                b["suspicion_at"] = now
                logger.info(
                    f"行为分析[{pid}] 触发人机验证: 累计可疑分达到阈值 "
                    f"(challenge={player['captcha']['id']})"
                )

    def note_activity(self, player_id: str) -> None:
        """浏览器上报人类活动（鼠标 / 键盘）后置位，行为分析据此区分真人。"""
        self._behavior_for(player_id)["activity_seen"] = True

    # -- 状态输出 ----------------------------------------------------------
    def public_state(
        self,
        my_player_id: Optional[str] = None,
        my_identity: Optional[dict] = None,
    ) -> dict[str, Any]:
        s = self.state
        room = s.get("room")
        public_room = None
        if room:
            items_info = []
            my_bids = {}
            for k in room["items"]:
                info = ITEMS[k]
                items_info.append({
                    "key": k,
                    "name": info["name"],
                    "desc": info["desc"],
                    "rarity": info["rarity"],
                })
                if my_player_id:
                    my_bids[k] = room["bids"].get(k, {}).get(my_player_id)
            public_room = {
                "level": room["level"],
                "room_number": room["room_number"],
                "room_type": room["room_type"],
                "range_max": room["range_max"],
                "budget": room.get("budget"),  # 反转目标镜像基准：min(range_max, budget)
                "modifiers": room["modifiers"],
                "items": items_info,
                "my_bids": my_bids,
                "phase": room["phase"],
                "deadline": room["deadline"],
                "result_end": room.get("result_end"),
                "result": room.get("result"),
                "bid_count": sum(len(room["bids"].get(k, {})) for k in room["items"]),
            }

        career, global_avg = self._career()
        participants = [
            {
                "id": p["id"],
                "name": p["name"],
                "character": p.get("character"),
                "is_bot": p["is_bot"],
                "total_score": round(p["total_score"], 2),
                "level_funds": p["level_funds"],
                "items": p["items"],
            }
            for p in s["players"]
        ]

        next_in = s.get("next_game_at") or 0

        # 当前登录身份与本人的动态 FLAG（只回传给本人，不泄露给他人）
        me = None
        my_flag = None
        if my_identity:
            me = {
                "kind": my_identity["kind"],
                "name": my_identity["name"],
                "platform_id": my_identity["platform_id"],
                "player_id": my_player_id,  # 供前端判断是否已加入当前对局
                "character": None,          # 本人当前所选角色（在局内时）
            }
            me_player = self.get_player(my_player_id) if my_player_id else None
            if me_player:
                me["character"] = me_player.get("character")
                # 待完成的人机验证：只下发图片 / 选项 / 时限 / 剩余次数，不下发答案
                cap = me_player.get("captcha")
                if cap and cap.get("pending"):
                    me["captcha"] = {
                        "id": cap["id"],
                        "image": cap["image"],
                        "options": cap["options"],
                        "deadline": cap["deadline"],
                        "attempts_left": cap["attempts_left"],
                    }
                else:
                    me["captcha"] = None
            ban = self._active_ban(my_player_id) if my_player_id else None
            if ban:
                me["banned_until"] = ban["until"]
            # 「是否拿过 FLAG」用独立计数 finished_games 判定，而不是生涯局数 games_played：
            # 排行榜冻结后 games_played 停止累加，若仍用它做门槛，
            # 冻结后首次参赛的选手打完一局也永远看不到自己的 FLAG。
            my_stats = s.get("stats", {}).get(my_player_id or "") or {}
            finished = my_stats.get("finished_games")
            if finished is None:
                finished = my_stats.get("games_played", 0)  # 兜底：尚未迁移的旧快照
            if finished >= 1:
                try:
                    my_flag = generate_flag(my_identity)
                except Exception:
                    my_flag = None

        return {
            "status": s["status"],
            "game_number": s["game_number"],
            "next_game_in_ms": max(0, next_in - now_ms()),
            "global_avg": global_avg,
            "target_players": TARGET_PLAYERS,
            "min_games_for_rank": MIN_GAMES_FOR_RANK,
            "best_n_games": BEST_N_GAMES,
            "current_level": s["current_level"] + 1 if s["status"] != "lobby" else 0,
            "current_room_index": s["current_room_index"] + 1 if s["status"] != "lobby" else 0,
            "room": public_room,
            "players": career,          # 所有人类（含等待队列）的生涯数据
            "participants": participants,  # 本局参与者（人类 + 机器人）
            "characters": [             # 可选角色（前端角色选择卡片数据源）
                {
                    "key": k,
                    "name": v["name"],
                    "item": v["item"],
                    "item_name": ITEMS[v["item"]]["name"] if v["item"] != "random" else "随机一件道具",
                }
                for k, v in CHARACTERS.items()
            ],
            "history": s["history"],
            "leaderboard": career_leaderboard(),  # 全场排行榜（所有打过对局的人类玩家）
            "leaderboard_frozen": LEADERBOARD_FROZEN,      # 排行榜是否已冻结（定榜）
            "leaderboard_frozen_at": s.get("leaderboard_frozen_at"),  # 冻结时刻（毫秒）
            "me": me,
            "my_flag": my_flag,
        }

    # -- 持久化 ------------------------------------------------------------
    def _persist_player(self, p: dict[str, Any]) -> None:
        """把人类玩家的生涯镜像写进 SQLite（失败只记日志，不影响游戏进行）。"""
        if p.get("is_bot"):
            return
        try:
            auth = p.get("auth") or {}
            st = self.state.get("stats", {}).get(
                p["id"], {"games_played": 0, "total_score": 0.0}
            )
            store.upsert_player(
                p["id"],
                p["name"],
                auth.get("kind", "user"),
                auth.get("platform_id"),
                st["games_played"],
                st["total_score"],
                st.get("scores", []),
                p.get("last_flag"),
            )
        except Exception as e:
            logger.error(f"upsert_player 写库失败: {p['id']} {e}")

    def _persist_room(self, room: dict[str, Any]) -> None:
        """把已结算房间的完整记录写进 SQLite（含赢家道具归属）。

        机器人是局内临时对象，不进 career 表，所以赢家是机器人时
        只记房间结果，不记 player_items（避免外键引用不存在的玩家）。
        """
        try:
            res = room.get("result") or {}
            sides = res.get("sides", [])
            store.record_room(
                self.state.get("game_number", 0),
                room["level"],
                room["room_number"],
                room["room_type"],
                [
                    {
                        "item": sr["item"],
                        "avg": sr.get("avg", 0),
                        "target": sr.get("target", 0),
                        "winner_id": sr.get("winner_id"),
                        "winner_name": sr.get("winner_name"),
                    }
                    for sr in sides
                ],
                room.get("bids", {}),
                res or None,
                now_ms(),
            )
            # 每个道具侧各自归属（同一人类赢家双赢时记两行）
            for sr in sides:
                wid = sr.get("winner_id")
                winner = self.get_player(wid) if wid else None
                if winner and not winner.get("is_bot"):
                    store.record_item(
                        wid,
                        self.state.get("game_number", 0),
                        room["level"],
                        room["room_number"],
                        sr["item"],
                        now_ms(),
                    )
        except Exception as e:
            logger.error(f"record_room 写库失败: {e}")

    def save(self) -> None:
        try:
            store.write_runtime_state(self.state)
        except Exception as e:
            logger.error(f"runtime_state 写库失败: {e}")


store = Store(DATA_DB)
ws_manager = WsManager()
game = Game()


def career_leaderboard() -> list[dict[str, Any]]:
    """全场排行榜：打满 MIN_GAMES_FOR_RANK 局的人类玩家，按生涯分（最好 BEST_N_GAMES 场均分）降序。

    数据源为 SQLite players 表（生涯镜像，含 scores_json），覆盖已离开 / 不再在线的玩家；
    与 `Game._career()` 使用同一套「定三取五」公式，保证和「排行榜」口径一致。
    读库失败时返回空表，不影响对局进行。
    """
    rows = store.get_players()
    fail_counts = store.get_ban_counts(CAPTCHA_FAIL_BAN_REASONS)
    played = [r for r in rows if r.get("games_played", 0) >= MIN_GAMES_FOR_RANK]
    out = []
    for r in played:
        games = r["games_played"]
        cum = r["total_score"]
        avg = cum / games if games else None
        # 旧数据可能没有逐场记录（scores_json 为空），此时退化为“场均”
        scores = json.loads(r.get("scores_json") or "[]") or []
        best = sorted(scores, reverse=True)[:BEST_N_GAMES]
        career = (sum(best) / len(best)) if best else (avg or 0.0)
        out.append({
            "id": r["id"],
            "name": r["name"],
            "games_played": games,
            "avg": round(avg, 2) if avg is not None else None,
            "career": round(career, 2),
            "verify_failures": fail_counts.get(r["id"], 0),
        })
    out.sort(key=lambda x: x["career"], reverse=True)
    return out

# ---------------------------------------------------------------------------
# 后台循环
# ---------------------------------------------------------------------------

async def game_loop() -> None:
    while True:
        try:
            await asyncio.sleep(1)
            s = game.state

            # 反作弊：进行中的人机验证超时 -> 禁赛 1 天；顺手清理悬挂的验证码答案。
            # 逐秒扫描人类玩家（含等待队列），只在真正发生变更时广播一次。
            captcha_changed = False
            for p in list(s["players"]) + list(s.get("queue", [])):
                if p.get("is_bot"):
                    continue
                cap = p.get("captcha")
                if cap and cap.get("pending") and now_ms() >= cap.get("deadline"):
                    if isinstance(cap.get("id"), str):
                        CAPTCHA_ANSWERS.pop(cap.get("id"), None)
                    game.apply_ban(p["id"], CAPTCHA_FAIL_TIMEOUT)
                    captcha_changed = True
            if captcha_changed:
                await ws_manager.broadcast(game, change="captcha")
            # 禁赛记录超过阈值时清理过期项，避免 runtime_state 无限膨胀
            bans = s.get("bans")
            if bans and len(bans) > 200:
                now = now_ms()
                pruned = {k: v for k, v in bans.items() if v.get("until", 0) > now}
                if len(pruned) != len(bans):
                    s["bans"] = pruned
                    game.save()

            # 自动开局：每 10 分钟一局
            if (
                s["status"] in ("lobby", "finished")
                and s.get("next_game_at")
                and now_ms() >= s["next_game_at"]
            ):
                started = False
                try:
                    started = game.start_game(automatic=True)
                except HTTPException:
                    pass  # 没有人类玩家等情况，等下一轮
                if started:
                    await ws_manager.broadcast(game, change="game_start")
                else:
                    # 无人就绪 / 无人加入：滚动等待，避免每秒空转；
                    # 打完一局后这也实现了「无人点继续就一直等」。
                    game.state["next_game_at"] = now_ms() + CONTINUE_GRACE_MS
                continue

            if s["status"] != "playing":
                continue

            room = s["room"]
            if not room:
                continue
            if room["phase"] == "bidding":
                # 机器人自动出价（不逐条持久化，但实时广播 bid_count）
                changed = False
                for p in game.state["players"]:
                    if not p.get("is_bot"):
                        continue
                    # 普通机器人整间房间只参与一个道具：一旦在任意道具侧出过价，
                    # 后续每秒的循环就直接跳过，避免跨秒把两个道具都出价（没有「更多选择」
                    # 却双参）；「更多选择」机器人两个道具都参与。
                    if p.get("extra_choice"):
                        order = list(room["items"])
                    else:
                        if any(
                            p["id"] in room["bids"].get(k, {}) for k in room["items"]
                        ):
                            continue  # 本房间任意一侧已出价，不再参与其它道具
                        candidates = [
                            k for k in room["items"]
                            if p["id"] not in room["bids"].get(k, {})
                        ]
                        if not candidates:
                            continue
                        order = [random.choice(candidates)]
                    for item_key in order:
                        if p["id"] in room["bids"].get(item_key, {}):
                            continue  # 该道具侧已出价
                        bid = bot_bid(p, room, item_key)
                        if bid is not None:
                            room["bids"].setdefault(item_key, {})[p["id"]] = bid
                            changed = True
                if changed:
                    await ws_manager.broadcast(game, change="bid")
                    # 广播期间其它协程可能推进了状态（如 api_skip 已结算），
                    # 重新取当前 room，避免用陈旧引用判断 deadline（并发审计）
                    room = s["room"]
                if room and room["phase"] == "bidding" and now_ms() >= room["deadline"]:
                    if game.settle_room():
                        await ws_manager.broadcast(game, change="settle")
            elif room["phase"] == "result" and room.get("result_end") and now_ms() >= room["result_end"]:
                game.advance()
                await ws_manager.broadcast(game, change="advance")
        except Exception as e:
            # 开发阶段不要让循环挂掉
            print("game_loop error:", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.connect()

    # 一次性迁移：旧版 data/game.json 还没进库时导入，并改名备份
    if store.read_runtime_state() is None and DATA_FILE.exists():
        try:
            store.write_runtime_state(json.loads(DATA_FILE.read_text(encoding="utf-8")))
            DATA_FILE.rename(DATA_FILE.with_suffix(".json.bak"))
        except Exception:
            logger.warning("game.json 迁移失败", exc_info=True)

    # 尝试从 SQLite 恢复
    data = store.read_runtime_state()
    if data:
        game.load_dict(data)
        # 服务器重启时如果对局正在进行，回到大厅，但保留玩家与生涯记录
        if game.state.get("status") != "lobby":
            game.soft_reset()
    # 排行榜冻结：启动时把定榜快照落库一次（幂等；已是冻结状态时不会重复插）
    game.ensure_freeze_snapshot()
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()
    store.close()


app = FastAPI(title="The Biding of the Isaac", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=7 * 24 * 3600,   # 7 天
    same_site="lax",
    https_only=False,        # 生产环境建议开启 HTTPS 后改为 True
)


@app.get("/api/state")
async def api_state(request: Request, player_id: Optional[str] = Query(default=None)):
    # 优先以 session 身份为准；player_id 仅作为未鉴权浏览时的只读“我”标识
    identity = request.session.get("identity")
    my_id = player_id_for(identity) if identity else player_id
    return JSONResponse(game.public_state(my_id, identity))


@app.post("/api/ws_token")
async def api_ws_token(request: Request):
    """签发 WebSocket 握手 token：短期有效、与 session 绑定、经 HTTP 签发。

    前端每次连接 /ws 前先调用本接口；WS 端点校验 token 签名 / 过期 / 与 session
    身份一致，从而把「连接」绑定到一次真实 HTTP 流程，阻止机器不经过网页直连
    出价。已登录绑定平台玩家 id；未登录绑定匿名会话 id（匿名只能观战，不能出价）。
    """
    identity = request.session.get("identity")
    if identity:
        seed = player_id_for(identity)
    else:
        # 匿名浏览器：会话里记录一个随机种子，确保 token 与本次会话 cookie 绑定
        seed = "anon:" + request.session.setdefault("anon_id", uuid.uuid4().hex)
    exp = now_ms() + WS_TOKEN_TTL_MS
    return {"token": sign_ws_token(seed, exp), "exp": exp}


@app.post("/api/auth")
async def api_auth(request: Request, body: dict = Body(...)):
    """用一次性临时用户识别码向平台验证身份，并写入 session cookie。

    验证通过后自动加入对局；用户 ID / 用户名记录在 session 中，
    并打印到 info 日志，前端展示获取到的用户名。
    """
    temp_code = str(body.get("tempCode", "")).strip()
    if not temp_code:
        raise HTTPException(400, "请提供临时用户识别码")

    try:
        identity = await asyncio.to_thread(lookup_identity, temp_code)
    except ValueError as e:
        raise HTTPException(400, f"识别码格式不正确: {e}")
    except Ret2ShellError as e:
        logger.warning(f"平台鉴权失败: {e}")
        raise HTTPException(401, "验证失败：识别码无效、已过期或平台暂时不可用")

    request.session["identity"] = identity
    player = game.add_authenticated(identity)
    logger.info(
        f"选手鉴权成功: platform_id={identity['platform_id']} "
        f"昵称={identity['name']} -> 加入对局"
    )
    await ws_manager.broadcast(game, change="join")
    return {"playerId": player["id"], "identity": identity}


@app.post("/api/join")
async def api_join(request: Request):
    """已登录（session 有身份）但不在本局的玩家重新加入。

    幂等：同一平台身份已存在则复用（进等待队列 / 回大厅列表），
    由 `add_authenticated` / `add_player` 处理。
    """
    identity = request.session.get("identity")
    if not identity:
        raise HTTPException(401, "请先完成鉴权（POST /api/auth）再加入")
    player = game.add_authenticated(identity)
    await ws_manager.broadcast(game, change="join")
    return {"playerId": player["id"], "identity": identity}


@app.post("/api/character")
async def api_character(request: Request, body: dict = Body(...)):
    """等待大厅中选择角色（开局前可随时修改）；对局进行中禁止修改。"""
    identity = request.session.get("identity")
    if not identity:
        raise HTTPException(401, "请先完成鉴权再加入游戏")
    character_key = str(body.get("character", ""))
    if character_key not in CHARACTERS:
        raise HTTPException(400, "未知角色")
    player = game.get_player(player_id_for(identity))
    if not player:
        raise HTTPException(404, "玩家不存在")
    game.set_character(player, character_key)
    await ws_manager.broadcast(game, change="character")
    return {"ok": True}


@app.post("/api/restart")
async def api_restart():
    if not game.human_players():
        raise HTTPException(400, "没有玩家，无法开始新一局")
    game.start_game(automatic=False)
    await ws_manager.broadcast(game, change="game_start")
    return {"ok": True}


@app.post("/api/bid")
async def api_bid(request: Request, body: dict = Body(...)):
    # 以 session 身份为准，不信任客户端传入的 playerId
    identity = request.session.get("identity")
    if not identity:
        raise HTTPException(401, "请先完成鉴权再加入游戏")
    item_key = body.get("item")
    if not isinstance(item_key, str) or not item_key:
        raise HTTPException(400, "请选择参与的道具")
    value: object = body.get("value")
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise HTTPException(400, "出价必须是整数")
    try:
        value = int(value)
    except Exception:
        raise HTTPException(400, "出价必须是整数")
    game.place_bid(player_id_for(identity), item_key, value)
    await ws_manager.broadcast(game, change="bid")
    return {"ok": True}


@app.post("/api/captcha")
async def api_captcha(request: Request, body: dict = Body(...)):
    """HTTP 兜底：提交人机验证答案（WS 不可用时）。"""
    identity = request.session.get("identity")
    if not identity:
        raise HTTPException(401, "请先完成鉴权再加入游戏")
    pid = player_id_for(identity)
    ok, message = game.answer_captcha(pid, str(body.get("id", "")), body.get("answer"))
    await ws_manager.broadcast(game, change="captcha")
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}


@app.post("/api/skip")
async def api_skip():
    # 开发用：强制结束当前出价阶段
    if game.state["status"] == "playing" and game.state["room"]:
        room = game.state["room"]
        if room["phase"] == "bidding":
            if game.settle_room():
                await ws_manager.broadcast(game, change="skip")
            return {"ok": True}
        elif room["phase"] == "result":
            game.advance()
            await ws_manager.broadcast(game, change="skip")
            return {"ok": True}
    return {"ok": False}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket 通道：推送个性化状态 + 接收出价。

    反作弊握手（阻止机器不经过网页直连出价）：
      1. Origin 必须与 Host 同源（浏览器必带 Origin；脚本客户端常缺失或伪造）；
      2. User-Agent 不能是明显机器库（curl / requests / go-http-client 等）；
      3. 必须携带 POST /api/ws_token 签发、与 session 绑定的短期 token，经
         Sec-WebSocket-Protocol 子协议 `tboi.v1.<token>` 传入。
    任一不通过即关闭连接，不会进入对局。

    身份从 session cookie 读取（SessionMiddleware 对 ws scope 只读有效）；
    鉴权 / 加入仍走 HTTP（session 写入不通过 WS 持久化）。
    """
    # 1) Origin 校验
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")
    if origin and host:
        o = urlsplit(origin)
        if o.netloc and o.netloc != host:
            await websocket.close(code=1008, reason="origin mismatch")
            return

    # 2) User-Agent 校验
    ua = (websocket.headers.get("user-agent") or "").lower()
    if not ua or any(sub in ua for sub in BOT_UA_SUBSTRINGS):
        await websocket.close(code=1008, reason="unsupported client")
        return

    # 3) 握手 token 校验：签名 / 过期 / 与 session 身份一致
    subprotocols = websocket.scope.get("subprotocols") or []
    matched_sp = next((sp for sp in subprotocols if sp.startswith("tboi.v1.")), None)
    token = matched_sp[len("tboi.v1."):] if matched_sp else None
    payload = verify_ws_token(token) if token else None
    if not payload:
        await websocket.close(code=1008, reason="missing or invalid ws token")
        return
    identity = websocket.session.get("identity")
    if identity:
        expect_seed = player_id_for(identity)
    else:
        expect_seed = "anon:" + websocket.session.get("anon_id", "")
    if not expect_seed or payload["seed"] != expect_seed:
        await websocket.close(code=1008, reason="token identity mismatch")
        return

    my_player_id = player_id_for(identity) if identity else None
    await ws_manager.connect(websocket, identity, my_player_id, subprotocol=matched_sp)
    try:
        await ws_manager.send_state(websocket, game)
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                try:
                    await websocket.send_json({"type": "error", "message": "消息格式错误"})
                except Exception:
                    break
                continue

            if not isinstance(msg, dict):
                await websocket.send_json({"type": "error", "message": "消息格式错误"})
                continue

            mtype = msg.get("type")
            if mtype == "bid":
                if not identity or not my_player_id:
                    await websocket.send_json(
                        {"type": "error", "message": "请先完成鉴权（POST /api/auth）再出价"}
                    )
                    continue
                item_key = msg.get("item")
                if not isinstance(item_key, str) or not item_key:
                    await websocket.send_json(
                        {"type": "error", "message": "请选择参与的道具"}
                    )
                    continue
                value: object = msg.get("value")
                if value is None or isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    await websocket.send_json({"type": "error", "message": "出价必须是整数"})
                    continue
                try:
                    value = int(value)
                except Exception:
                    await websocket.send_json({"type": "error", "message": "出价必须是整数"})
                    continue
                try:
                    game.place_bid(my_player_id, item_key, value)
                except HTTPException as e:
                    await websocket.send_json({"type": "error", "message": e.detail})
                    continue
                await ws_manager.broadcast(game, change="bid")
                await websocket.send_json({"type": "ok", "message": "出价已提交"})
            elif mtype == "activity":
                # 浏览器人类活动信号（鼠标/键盘）：行为分析据此区分真人
                if identity and my_player_id:
                    game.note_activity(my_player_id)
            elif mtype == "captcha_answer":
                if not identity or not my_player_id:
                    await websocket.send_json(
                        {"type": "error", "message": "请先完成鉴权（POST /api/auth）再验证"}
                    )
                    continue
                ok, message = game.answer_captcha(
                    my_player_id, str(msg.get("id", "")), msg.get("answer")
                )
                await websocket.send_json(
                    {"type": "captcha", "status": "ok" if ok else "fail", "message": message}
                )
                await ws_manager.broadcast(game, change="captcha")
            elif mtype == "refresh":
                await ws_manager.send_state(websocket, game)
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype in ("auth", "join"):
                await websocket.send_json(
                    {"type": "error", "message": "请使用 HTTP POST /api/auth 或 /api/join 完成鉴权/加入"}
                )
            else:
                await websocket.send_json({"type": "error", "message": "未知消息类型"})
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
