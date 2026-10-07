# The Biding of the Isaac

一个致敬《以撒的结合》的多人竞拍网页游戏。  
玩家不需要写脚本，只需要在网页上每轮提交一个数字，系统自动结算、排名并展示历史。

---

## 1. 游戏概念

- 玩家参与一局游戏，一局由多个 **Level（层）** 组成。
- 每个 Level 包含若干个 **Room（房间）**。
- 每个 Room 是一个竞拍/挑战回合。
- 玩家在每个 Room 提交一个数字作为“出价”。
- 所有玩家都要扣除自己的出价资金。
- 出价最高者获得该 Room 的道具。
- 道具提供后续效果，可以跨 Room、跨 Level 保留。
- 最终按累计得分排名。

---

## 2. 核心规则

### 2.1 出价

- 普通 Room：出价范围 `1 ~ 99`。
- 特殊 Room：出价范围 `1 ~ 999`。
- 出价不能超过当前 Level 的剩余资金。
- 如果剩余资金不足，玩家不能参与该 Room，只能观战。

### 2.2 信息透明

- 每个 Room 开始时，必须公开本 Room 的特殊规则，例如反转目标、双倍得分、1~999 范围等。
- 不能让玩家猜当前规则。
- 历史规则也应公开，方便玩家复盘和学习。

### 2.3 全付拍卖

每个 Room 结算时：

- 所有参与玩家都扣除自己的出价。
- 无论是否赢得道具，出价都会扣除。

例如：

| 玩家 | 出价 | 扣除 |
|---|---:|---:|
| A | 30 | -30 |
| B | 20 | -20 |
| C | 40 | -40 |
| D | 10 | -10 |

### 2.4 得分公式

设本 Room 所有参与出价的平均值为：

\[
A = \frac{1}{n}\sum_{i=1}^{n} bid_i
\]

目标值为：

\[
T = \frac{2}{3}A + C
\]

常量 `C` 与 `σ` 按房间出价量级设置（当前实现见 `room_config()`）：

| 房间量级 | `range_max` | `C` | `σ` |
|---|---:|---:|---:|
| 普通 / 宝物房（第 1 层） | 99 | 10 | 10 |
| 第 2/3 层全部房间，以及特殊 / Boss 房 | 999 | 50 | 100 |

单轮基础得分：

\[
score = 100 \times e^{-|bid_i - T| / \sigma}
\]

出价越接近 `T` 得分越高，封顶 100 分，再叠加道具倍率 / 固定加分 / Boss 双倍。目标值 `T` 会被限制在 `1 ~ range_max` 之间。**每轮有 `MIN_SCORE_PER_ROOM`（5）分保底**：当目标远离所有出价（典型如反转房全场低出价）时指数衰减会让全员掉到 0.x，保底分保证参与出价的玩家至少拿到可读分数。

#### 反转目标（特殊房）

特殊 Room 有 45% 概率携带「反转目标」修饰（`room_modifiers()`）。反转房把目标值在**镜像基准**（出价上限与本层资金取小者）上镜像翻转：

\[
T_{reverse} = \min(range\_max,\; level\_budget) - \left(\frac{2}{3}A + C\right)
\]

仍受 `1 ~ range_max` 限制（实现见 `room_target()`）。**反转房的目标与平均值负相关**：平均出价越低，目标越贴近镜像基准。第 2 层资金 500 小于 `range_max` 999，镜像基准取 500，目标最高到 500，保证玩家资金可触及；第 3 层资金 1000 > 999，基准仍为 999。例如第 2 层 `A = 100, C = 50` 时 `T ≈ 383`；第 3 层同参数 `T ≈ 882`。该规则在 Room 开始时通过 `modifiers: ["reverse"]` 公开，玩家应据此调整策略，而不是一律追低。

### 2.5 道具归属

- 出价最高者获得本 Room 道具。
- 如果多个玩家出价相同，可以随机决定，或按当前总得分较低者优先，便于翻盘。

### 2.6 观战状态

- 如果玩家主动不出价，或剩余资金不足，则当前 Room 进入观战。
- 观战玩家本 Room 得 0 分。
- 观战玩家仍可看到出价结果、历史记录和排名。
- 下一个 Level 开始后重新获得资金，恢复参与。

### 2.7 最终排名

- 一局结束后，按累计总得分排名。
- 可以设置平分规则：总得分相同则比较剩余资金、道具数或最后一轮得分。

---

## 3. Level 与 Room 结构

### 3.1 推荐结构

```text
一局
├── Level 1
│   ├── Room 1
│   ├── Room 2
│   ├── Room 3
│   └── Room 4
├── Level 2
│   ├── Room 1
│   ├── Room 2
│   ├── Room 3
│   └── Room 4
└── Level 3
    ├── Room 1
    ├── Room 2
    ├── Room 3
    ├── Room 4
    └── Room 5
```

### 3.2 Level 资金建议

| Level | 房间数 | Level 资金 | 说明 |
|---|---:|---:|---|
| Level 1 | 4 | 100 | 普通房间 |
| Level 2 | 4 | 500 | 开始出现特殊房间，支持较高出价 |
| Level 3 | 5 | 1000 | 支持 1~999 大额出价 |

Level 结束时：

- 剩余资金可以按 10% 转化为额外积分；
- 或者直接清零；
- 建议保留“剩余资金转少量分”，让省钱也有策略价值。

---

## 4. Room 类型

### 4.1 普通 Room

- 出价范围 `1 ~ 99`。
- 一个普通道具。
- 基础结算。

### 4.2 宝物 Room

- 出现稀有或强力道具。
- 通常需要较高出价才能获得。
- 适合前期攒钱、后期一波流。

### 4.3 特殊 Room

- 出价范围 `1 ~ 999`。
- 可以带有特殊规则：
  - 反转目标（见 §2.4：目标 = `min(range_max, 本层资金) − (2/3·A + C)`，与平均值负相关，低平均会得到接近镜像基准的目标）
  - 双倍得分
  - 中位数结算
  - 临时增加资金
  - 全房间特殊道具

### 4.4 Boss Room

- 每个 Level 的最后一个 Room。
- 可以设置：
  - 高价值道具
  - 双倍积分
  - 特殊规则
  - 剩余资金自动转化为出价能力
  - 决定该 Level 的排名变化

---

## 5. 道具系统

道具可以跨 Room、跨 Level 保留，形成玩家的 Build。

### 5.1 规定道具示例

| 道具 | 稀有度 | 效果 |
|---|---|---|
| 积分护符 | common | 每次获得分数时得分 +10（固定加分，参与比例乘算） |
| 妈妈的心脏 | common | Boss Room 中得分 ×200%（不包含本次出价） |
| 福袋 | common | 一次性：返还下一笔出价 75% 的资金（用后消耗） |
| 完美视力 | common | 争夺道具时出价按 1.5 倍计算（仅影响出价之和与道具竞争，得分公式仍按原出价） |
| 偷钱袋 | common | 每个房间开始时从总资产第一名（资金最高者）偷取 10% 的资金，从对方账户扣除（先偷后出价，偷到的钱可用于本房间竞拍） |
| 圣心 | rare | 后续得分 ×150% |
| Steam大促 | rare | 后续出价扣除的资金减少 30%（按折扣后实际扣除校验资金） |
| 硫磺火 | rare | 计算得分时可在出价的 80%~125% 区间取最高分（平均出价仍按初始出价计算）；多件时区间上下限按件数连乘（0.8ⁿ×~1.25ⁿ×） |
| 神圣斗篷 | rare | 每层首次竞争失败退回所有资金 |
| 六面骰 | rare | 1/6 概率使当前房间得分 ×200% |
| 利息 | rare | 每个 Room 开始资金 +10%，进入下一层初始资金 +20% |
| 黑王子之冠 | cursed | 结算时总得分 +25%，每拥有一个其他道具加成 -5%，最低不低于 +5% |
| 穷人护符 | cursed | 当前资金低于本层初始资金 30% 时每次得分 +20，否则 +5（固定加分，参与比例乘算）；进入下一房间资金 -10% |
| 永恒六面骰 | cursed | 后续得分 ×150%，但有 25% 概率使当前房间得分清零 |
| 更多选择 | cursed | 可同时对房间的两个道具出价；同时参与时两方得分之和 ×75% |

稀有度含义：common（常见，出现率最高）→ rare（稀有，效果较强）→ cursed（诅咒，强力但自带代价）。道具池 15 个（5 常见 / 6 稀有 / 4 诅咒），掉落按稀有度加权（权重 4:2:1，见 `pick_item()`），实测约 common 56% / rare 33% / cursed 11%。

### 5.2 道具效果分类

- **经济类**：增加资金、减少出价消耗、返还资金。
- **得分类**：增加得分、倍率、固定加分。
- **竞拍类**：提高赢得道具的概率、影响出价计算。
- **干扰类**：隐藏信息、偷取资金、影响他人。
- **诅咒类**：强效果，但同时带有负面效果。

### 5.3 道具叠加

当前实现（`_apply_item_effects`）：

- **比例类叠乘**：`score_mult` 如 圣心 ×1.5 与 永恒六面骰 ×1.5 → 1.5 × 1.5；`payment_mult` 仅 Steam大促 ×0.7（支付 = 出价 × payment_mult）。福袋不再乘 `payment_mult`，改为一次性返还（见 5.3 资金校验）。
- **固定加分先加进 base，再参与比例乘算**：`flat_score`（积分护符 +10/个；穷人护符按资金动态 +20 或 +5，按持有数量叠加）先加进 base，再乘 `score_mult`；妈妈的心脏（Boss ×2）、六面骰（1/6 ×2）、永恒六面骰（25% 清零）在 `_settle_side` 内按事件顺序触发。
- **重复道具可叠加**：除偷钱袋外，所有道具效果只作用于持有者自身；乘区道具倍率连乘（圣心 ×1.5/件、永恒六面骰 ×1.5/件、硫磺火得分出价区间上下限 0.8ⁿ/1.25ⁿ），固定加分按件数相加（积分护符 +10/件、穷人护符 +20/+5 按件数）。硫磺火用 `brimstone_count` 记录持有数，`scoring_bid = clamp(target, bid·0.8ⁿ, bid·1.25ⁿ)`。偷钱袋是唯一直接作用于他人的道具：每房间开始时（出价前）从「资金最高者」偷 10% 加到自己账户（`_apply_steal`）。
- **资金校验按实际扣除**：`place_bid` 用 `committed × payment_mult`（Steam大促 x0.7）校验；福袋一次性返还——持有未用福袋时按 `committed × payment_mult × 0.25` 校验（用后消耗，见 `lucky_bag`）。返还/折扣道具可支撑高于当前资金的出价（仍受房间出价上限约束）。
- 效果从 `player["items"]` 重建：`_reset_item_stats` 清零后由 `_apply_item_effects` 逐个重算，新增道具只需改这两处。

### 5.4 角色与初始道具

开局前玩家在等待大厅选择一个角色（`POST /api/character`，对局进行中禁止修改），开局时自动携带该角色的初始道具：

| 角色 | 初始道具 | 备注 |
|---|---|---|
| 以撒 | D6（六面骰 `six_dice`） | |
| 游魂 | 神圣斗篷 `divine_cloak` | |
| 阿撒泻勒 | 硫磺火 `brimstone` | |
| 伊甸 | 随机一件道具 | 开局时用 `pick_item()` 掷出 |
| 雅各和以扫 | 更多选择 `extra_choice` | 可同时参与两个道具 |

实现：`CHARACTERS` 常量 + `Game._apply_character()`（未选角色随机分配；机器人开局时也随机分到一个角色）。人类所选角色持久保存在玩家状态里，下一局沿用，可随时在大厅修改。

---

## 6. 网页功能需求

### 6.1 当前 Room 页面

- 当前 Level 和 Room 编号
- 当前 Room 类型
- 当前道具名称、描述、稀有度
- 倒计时
- 出价输入框
- 我的 Level 剩余资金
- 我的总得分和当前排名
- 我的道具列表
- 是否处于观战状态

### 6.2 排行榜页面

- 总得分排名
- 剩余资金
- 赢得道具数
- 每个玩家拥有的道具
- 最近几轮排名变化

### 6.3 历史记录页面

每个 Room 展示：

- 道具名称
- 赢家
- 赢家出价
- 所有玩家出价
- 平均出价
- 目标值
- 每人的得分变化
- 每人的资金变化
- 特殊规则说明

---

## 7. 后端设计要求

### 7.1 游戏状态

需要管理：

- 当前游戏局
- 当前 Level / Room
- 每个玩家的资金、得分、道具
- 当前 Room 的出价
- 倒计时状态
- Room 结算结果
- 历史记录

### 7.2 实时通信（WebSocket 推送）

已实现为 WebSocket 推送（`ws.py` 的 `WsManager`）：

- 前端连接 `ws://host/ws`，服务端登记后先推一帧当前状态，之后每次状态变更由服务端广播。
- 广播是**个性化**的：对每个连接按 `(pid, identity)` 调用 `game.public_state(...)`，只回传本人的 `me` / `my_bid` / `my_flag`，不泄露他人出价与身份。
- 消息协议（JSON）：服务端 → 客户端 `{"type":"state","data":{...}}`（`data._change` 标注变更来源，客户端忽略）；客户端 → 服务端 `{"type":"bid","value":N}`（出价）、`{"type":"refresh"}`（重拉状态）、`{"type":"ping"}` → `pong`；出错回 `{"type":"error","message":...}`。
- 出价走 WS，减少反复建立 HTTP 连接的开销；HTTP `POST /api/bid` 保留作为 WS 不可用时的兜底。
- 断线指数退避重连（1s 起、上限 15s），前端用代际计数器丢弃过期 socket 的迟到帧；WS 断开时保留 2s 一次的 HTTP 兜底轮询。
- **鉴权必须走 HTTP**：Starlette `SessionMiddleware` 对 `"websocket"` scope 只读有效，session 写入不会通过 WS 持久化，因此 `POST /api/auth` / `POST /api/join` 仍为 HTTP，之后连接 WS。

### 7.3 持久化（SQLite）

已实现为 SQLite（`store.py` 的 `Store`），混合方案：**运行时快照 + 规范化审计表**。

- `runtime_state`（单行，id=1）保存整局 JSON 快照，是崩溃恢复的权威；`Game.save()` 每次都写它。
- 审计表在生命周期事件写入，记录历史：
  - `players` — 玩家生涯镜像（仅人类）：id/name/kind/platform_id/games_played/total_score/scores_json/last_flag
  - `games` — 游戏局：game_number/started_at/finished_at/human_count/player_count/status
  - `rooms` — 每轮结果：level/room_number/room_type/item/avg/target/winner/bids_json/result_json
  - `player_items` — 道具归属（仅人类赢家）：player_id/game_number/level/room_number/item
  - `game_rankings` — 最终排名：game_number/player_id/rank/total_score/level_funds
  - `flags` — FLAG 发放记录：player_id/game_number/flag/issued_at
  - `bans` — 禁赛审计（见 §13.3）：player_id/until_ms/reason/issued_at
  - `leaderboard_snapshots` — 定榜存档（见 §11.4）：frozen_at/rank/player_id/name/career/games_played/avg，仅在排行榜冻结时写入，一个玩家一行
- 实现：stdlib `sqlite3`，`check_same_thread=False` + `threading.Lock`，`PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`。每个写方法都是原子事务（`_tx()` 上下文管理器，异常回滚），写失败由调用方 try/except 吞掉并记日志，游戏继续跑。
- 机器人不写入 `players`/`player_items`/`game_rankings`，避免外键断裂、保证审计数据有意义。
- 首次运行若存在旧的 `data/game.json`，会一次性迁移进 SQLite 并把旧文件改名 `game.json.bak`。

### 7.4 结算流程

1. 倒计时结束。
2. 锁定所有出价。
3. 计算平均出价。
4. 计算目标值。
5. 计算每个玩家的得分。
6. 应用道具效果。
7. 扣除所有玩家资金。
8. 确定道具归属。
9. 更新玩家状态。
10. 写入历史记录。
11. 进入下一个 Room 或下一个 Level。

---

## 8. MVP 开发范围

第一版建议只做：

- 1 局游戏
- 3 个 Level
- 每个 Level 3~5 个 Room
- 普通 Room + Boss Room
- 5~8 个道具
- 不出主动技能
- 只做网页出价、排行榜、历史记录
- WebSocket 推送（状态 / 出价 / 结算）

暂缓：

- 复杂主动技能
- 多道具同时竞拍
- 公会/组队系统
- 复杂动画特效
- 观战聊天

---

## 9. 可调参数

所有效果都建议做成配置，方便后续平衡：

```text
game:
  levels: 3
  rooms_per_level: [4, 4, 5]

level_budgets:
  - 100
  - 150
  - 500

scoring:
  normal:
    c: 10
    sigma: 10
  special:
    c: 50
    sigma: 100

room_probabilities:
  normal: 0.6
  treasure: 0.15
  special: 0.15
  boss: 0.1

# 赛事定榜：置位后生涯计分停止累加（榜单定榜），但参赛与 FLAG 发放不受影响
leaderboard_frozen: false

item_pool:
  - 积分护符        # score_amulet (common)
  - 妈妈的心脏      # mom_heart (common)
  - 福袋            # lucky_sack (common)
  - 完美视力        # perfect_vision (common)
  - 偷钱袋          # steal_purse (common)
  - 圣心            # sacred_heart (rare)
  - Steam大促       # steam_sale (rare)
  - 硫磺火          # brimstone (rare)
  - 神圣斗篷        # divine_cloak (rare)
  - 六面骰          # six_dice (rare)
  - 利息            # interest (rare)
  - 黑王子之冠      # black_crown (cursed)
  - 穷人护符        # poor_amulet (cursed)
  - 永恒六面骰      # eternal_d6 (cursed)
  - 更多选择        # extra_choice (cursed)
```

---

## 10. 开发提示

- 名称：**The Biding of the Isaac**
- 中文名：**以撒的出价**
- 核心体验：全付拍卖 + 有限资金 + 道具 Build + Roguelike 楼层推进。
- 玩家输入越简单越好：每轮只提交一个数字。
- 随机性来自特殊 Room 和道具池，不应该让玩家猜当前规则。
- 网页需要让观战者也看得懂，尤其要展示平均出价和目标值。

---

## 11. 自动开局 / 机器人补位 / 生涯总分

### 11.1 自动开局

- 系统每 `GAME_INTERVAL_MS`（10 分钟）自动开一局。
- 后台 `game_loop` 每秒检查：`status` 为 `lobby` 或 `finished` 且到达 `next_game_at` 时调用 `start_game(automatic=True)`。
- 开局即设定下一次开局时间；一局约 9 分钟，正好错开 10 分钟节奏。
- 大厅与“等待下一局”的横幅展示 `next_game_in_ms` 倒计时。
- 若到点但没有人类玩家，则不开始；此时有人加入会触发 `START_GRACE_MS`（30 秒）缓冲，尽快开局。
- 服务器重启时若对局进行中，`soft_reset()` 回到大厅，但保留人类玩家与生涯记录。

### 11.2 机器人补位

- 开局时人类玩家不足 `TARGET_PLAYERS`（20）人，则用机器人补足到 20 人。
- 机器人为局内临时对象，局结束时移除；人类玩家长期保留在 `players`。
- 对局进行中加入的人类进入 `queue`，下一局自动开局时并入。
- 机器人自动出价逻辑见 `bot_bid()`。每个机器人创建时随机分配一种出价策略（`BOT_STRATEGIES`）：
  - **稳健**：按「剩余房间均分份」花钱，留 12% 保底；
  - **博彩**：死贴目标价 ±3，只求得分不抢道具，留 15% 保底；
  - **进取**：半数概率大幅抬高抢道具（单间可花均分份 1.5 倍），留 5% 保底，容易提前破产；
  - **捡漏**：压低目标价 8~25 出价捡便宜，只花均分份 0.8 倍，留 20% 保底。
  - **搅局者**（权重约 11%，只作点缀）：不管输赢，只为把均价搅乱——12% 发疯梭一把（剩余资金 50~80%）、45% 在目标价上下大跳（拉高/砸低）、其余随机乱点；单间可花均分份 2 倍、只留 8% 保底，从不贴着目标出价。效果：拉大各房间均价波动，让「猜平均」变得不可预测。
  单间上限 = 剩余房间均分份 × 策略系数；boss 房放开到剩余资金七成；「更多选择」机器人双参时两侧各按半份花。非 boss 间始终留保底，避免机器人一层钱全砸在第一间、后段房间（尤其 boss 房）集体没钱退场。

### 11.3 生涯总分（定三取五）

排行榜“生涯分”采用「定三取五」，防止“新手一把高分就上榜”：

```text
入榜门槛 = 至少 MIN_GAMES_FOR_RANK（3）局
生涯分   = 生涯最好 BEST_N_GAMES（5）场的单局均分（不足 5 场取全部场次的均分）
```

- `stats` 按玩家 id 记录 `games_played`、累计场均分 `total_score`，以及生涯最好 `BEST_N_GAMES` 场的单局均分 `scores`（当局总分 ÷ `TOTAL_ROOMS`，量级接近 0~100）。
- `Game._career()` 与 `career_leaderboard()` 共用同一套公式；排行榜只列 `games_played >= MIN_GAMES_FOR_RANK` 的玩家。
- 机器人不进入生涯记录。

#### 两个计数器：`games_played` 与 `finished_games`

`stats` 里有两个**语义不同、必须分开**的局数计数（见 §11.4）：

| 字段 | 语义 | 写入方式 |
|---|---|---|
| `games_played` | 生涯局数，**参与生涯分公式**，是入榜门槛 | 仅在未冻结时累加（`finish_game` 循环 A） |
| `finished_games` | 「已完成局数」，**只用于判断是否把 FLAG 下发给本人** | 无条件累加，冻结与否都 +1，覆盖所有人类（含被禁赛者） |

`public_state` 决定要不要下发 `my_flag` 时只能看 `finished_games`。若沿用 `games_played`，排行榜冻结后它恒不再增长，冻结后首次参赛的选手就会「FLAG 生成了却永远看不到」。旧存档由 `load_dict` 用 `games_played` 回填该字段。

### 11.4 排行榜冻结（赛事定榜）

模块级开关 `LEADERBOARD_FROZEN`（`main.py` 顶部常量区，默认 `False`），改后需**重启**生效。置 `True` 后：

- `finish_game` 循环 A（生涯累加）整体门控跳过 —— `games_played` / `total_score` / `scores` 停在冻结时刻，榜单定榜。
- 循环 B（发 FLAG）、结算、自动开局、审计表写入**全部不受影响**；`finished_games` 照常累加，所以冻结后首次参赛的选手仍能看到自己的 FLAG。
- 定榜存档：`Game.ensure_freeze_snapshot()` 在 `lifespan` 启动时与每次 `finish_game` 收尾被调用，把 `career_leaderboard()` 落库到 `leaderboard_snapshots` 并记 info 日志（`排行榜已冻结: 冻结时间=... 入榜人数=...`）。**幂等依据只有数据库**（表里有没有记录），内存里的 `state["leaderboard_frozen_at"]` 仅作前端展示缓存，发现库里已有记录时用库里的时刻回填。
- 冻结时若无人打满 `MIN_GAMES_FOR_RANK`，**不落空快照**（否则「库里有存档」的幂等标记会被永久占住，此后即便有人达标也无法再定榜），只记 warning，等下局再试。
- 想重新定榜：`DELETE FROM leaderboard_snapshots`（不清 `runtime_state`）。注意这不会恢复生涯数据，只是重新录一次档；要真正让分数继续增长须先解冻。
- `public_state` 额外下发 `leaderboard_frozen` 与 `leaderboard_frozen_at`，前端顶部与两个排行榜据此显示定榜提示。

## 12. 鉴权与动态 FLAG

### 12.1 鉴权机制

- 选手必须输入**一次性临时用户识别码**（十六进制码），经 `POST /api/auth` 调用 ret2shell-kit 向平台换取用户身份后，才能加入对局。
- 身份存于 session cookie（`SessionMiddleware`）；玩家 id 由平台身份派生：用户 `u{id}`，保证跨会话/跨对局一致，生涯分延续。
- 已鉴权但不在当前局的玩家，前端顶栏显示「加入对局」按钮，点击 `POST /api/join`（幂等：已在局内则复用现有玩家，否则进等待队列下一局并入），返回 `{playerId, identity}`。
- `POST /api/auth` 与 `POST /api/join` 必须走 HTTP（session 写入不通过 WebSocket 持久化）；成功后都通过 WS 广播 `change="join"`。
- `/api/state` 返回 `me`（当前登录身份，含 `me.player_id` 供前端判断是否已在本局）与 `my_flag`（本人已完成对局时的 FLAG），只回传本人，不泄露他人。
- 未鉴权只能看 `/api/state`，`/api/bid` 会返回 401。
- 鉴权成功与 FLAG 发放通过 `logging.getLogger("tboi")` 写入 `data/info.log`。
- `R2S_MOCK=1` 时接受任意识别码并返回固定假身份，便于本地开发。

### 12.2 动态 FLAG

- 一局结束（`Game.finish_game`）时，对每个完成本局的人类玩家生成 FLAG 并写入 info 日志。**被禁赛的玩家本局跳过**（不发 `last_flag`、不写 `flags` 表），不视为完整完成。
- 使用 `ret2shell_kit.PlatformFlagManager`（Leet / UUID 两种模式），编码用户 ID。
- `FLAG_KEY` / `FLAG_TEMPLATE` / `FLAG_PREFIX` / `FLAG_MODE` 必须与平台评测脚本一致，平台才能验证。
- 同一用户 FLAG 确定性生成（ID + 密钥 + 模板），重复完成对局展示同一个 FLAG。
- `/api/state` 返回 `me`（当前登录身份）与 `my_flag`（本人已完成对局时的 FLAG），只回传本人，不泄露他人。
- **展示门槛**：`public_state` 依据 `stats[player_id]["finished_games"] >= 1`（而非 `games_played`）判断是否把 `my_flag` 下发给本人，`my_flag` 由 session 里的 identity **重新生成**（不读 `p["last_flag"]`，也不读 `flags` 表）。这与「是否发放/审计」是两个独立判定，务必不要合并——原因见 §11.3 的两个计数器与 §11.4。

## 13. 反作弊（行为分析 / 人机验证 / 禁赛）

目标：识别脚本/机器直接出价作弊，对其限时 15 秒人机验证，不通过则禁赛 1 天；同时从握手层阻止机器绕过网页直连 WebSocket 参赛。所有启发式阈值见 main.py 顶部 `CAPTCHA_*` / `SUSPICION_*` / `VERIFY_*` / `WS_TOKEN_*` / `BOT_UA_SUBSTRINGS` 常量。

### 13.1 握手层：阻止机器直连 WS

`/ws` 入口三道闸（任一道不过即 close 1008，不进入对局）：

1. **Origin 校验**：浏览器必带 `Origin`，脚本客户端常缺失或伪造；Origin 的 netloc 必须等于 `Host`，否则拒绝。
2. **User-Agent 校验**：缺失 UA 或命中机器库指纹（`curl` / `wget` / `python-requests` / `go-http-client` / `okhttp` 等）直接拒绝。
3. **短期握手 token**：先 `POST /api/ws_token` 签发 HMAC-SHA256 签名、带过期时间（`WS_TOKEN_TTL_MS`，60 秒）的 token，经 `Sec-WebSocket-Protocol` 子协议 `tboi.v1.<token>` 传入；签名用 `SESSION_SECRET`，`hmac.compare_digest` 比对。token 的 `seed` 必须与 session 派生的身份一致（登录用户 `u{id}`，未登录 `anon:{anon_id}`），防止把别人的 token 搬到自己连接上用。

浏览器必须走完整页面流程才能拿到合法 token；纯脚本（即便模拟了 Origin/UA）也拿不到签名密钥，无法直连参赛。

### 13.2 行为分析（`Game._check_behavior`）

每笔出价后累计「可疑分」，带随时间衰减（`SUSPICION_DECAY ** (age / SUSPICION_DECAY_S)`，60 秒半衰系数 0.9）。信号与权重：

| 信号 | 触发条件 | 加分 |
|---|---|---|
| 超快反应 | 房间 `started_at` 到出价的间隔 < 200ms | +1.0 |
| 极快反应 | 间隔 200~500ms | +0.4 |
| 出价连发 | 2 秒内 ≥ 3 次（每段只计一次） | +0.6 |
| 高频刷价 | 10 秒内 ≥ 10 次（每段只计一次） | +1.0 |
| 反应过于一致 | ≥ 4 个房间的反应时间标准差 < 40ms（机器定时器特征） | +0.8 |
| 无人类活动 | 从未上报鼠标/键盘 `activity` 信号却出价 ≥ 3 次（只计一次） | +0.5 |

设计上避免误伤真人：单个超快反应（+1.0）低于阈值（`SUSPICION_THRESHOLD` = 1.5），必须叠加其它信号才触发；连发/高频/无活动信号均为「一段只计一次」；分数 60 秒内衰减。浏览器在鼠标/键盘事件（2 秒节流）时经 WS 发 `{"type":"activity"}`，`Game.note_activity` 置位。

### 13.3 人机验证与禁赛

- 验证题目为**图片验证码单选**：`Game._issue_captcha` 用 `captcha` 库（`ImageCaptcha`，依赖 Pillow）把随机 4 字符（`CAPTCHA_TEXT_LEN`，字符集 `CAPTCHA_CHARS`，去掉 0/O、1/I/L 等易混淆字符）渲染成 PNG，再以 base64 data URI 下发给本人；同时生成 6 个互不相同的候选**文本**（`_captcha_options`，与正确答案同长度同字符集、集合去重后洗牌），玩家选出与图片一致的那个。正确答案文本只存内存 `CAPTCHA_ANSWERS`（**不落库、不进 `public_state`**），前端提交所选候选文本，15 秒（`CAPTCHA_WINDOW_MS`）内可答 `CAPTCHA_MAX_ATTEMPTS` 次。
- **两种触发方式**：
  1. **行为触发**：可疑分 ≥ 1.5 且无进行中验证、且距上次通过 ≥ `VERIFY_COOLDOWN_MS`（10 分钟）时触发（见 §13.2）。
  2. **随机抽查**：每次出价后以 `CAPTCHA_SPOTCHECK_PROB`（0.03）概率随机点名（`Game._maybe_spotcheck`），与行为分析无关，让「行为上不可疑但其实是机器」的客户端也逃不掉抽查；同样受宽限期约束、已有验证时不叠加。
- 验证未完成时 `place_bid` 返回 403；`game_loop` 每秒扫描超时验证，自动按「人机验证超时」禁赛。
- 答错扣次数，用尽 → 禁赛；答对 → 清除可疑分、置 `last_verified_at`（进入 10 分钟宽限）。HTTP `POST /api/captcha` 为 WS 不可用时的兜底。
- 禁赛：`state["bans"]` 记录 `until`（24h）/reason，重启存活；同步审计到 SQLite `bans` 表（`store.record_ban`）。禁赛期内不能加入、不能出价，`finish_game` 结算时不发 FLAG。`me.banned_until` 与 `me.captcha`（图片 / 6 个选项 / 倒计时 / 剩余次数，**不含正确答案文本**）只回传本人。
- **「验证失败次数」指标**：每次验证失败（答错用尽次数 / 超时）都经 `apply_ban` 落一条禁赛审计记录，`store.get_ban_counts(CAPTCHA_FAIL_BAN_REASONS)` 按玩家统计这些 reason 的行数即为累计失败次数。`_career()` 与 `career_leaderboard()` 输出 `verify_failures` 字段，「排行榜」与「全场排行榜」据此渲染「验证失败」列（非零高亮）。计入该指标的禁赛原因由 `CAPTCHA_FAIL_TIMEOUT` / `CAPTCHA_FAIL_WRONG` 定义，人工封禁等其它原因不计入。

### 13.4 测试

`python _test_anticheat.py`（临时 SQLite，不污染 data/game.db）覆盖：token 签发/校验/篡改/过期与 seed 绑定、行为触发验证（含图片 data URI + 6 选 1 选项断言）、随机抽查独立触发验证、验证期间拦截出价、答对清分+宽限、答错用尽禁赛、超时禁赛、禁赛期无法加入/出价、排行榜验证失败次数（只统计验证失败类禁赛）、`public_state` 不泄露答案（但下发图片与 6 个选项）、被禁玩家不发 FLAG、正常人类节奏不触发、可疑分衰减。

`_smoke_ws.py` 为**实时握手冒烟测试**：先 `uvicorn main:app --port 8321` 起服务，再 `uv run python _smoke_ws.py`，用原生 socket 走真实 HTTP Upgrade，验证无 token / 机器 UA / 篡改 token / 跨域 Origin 均被拒，合法 token + session cookie 握手成功并收到 state、WS 出价不产生协议错误。

`python _test_freeze.py`（临时 SQLite，见 §11.4）覆盖：冻结后生涯数据停止累加（但 `finished_games` 照常 +1）、**冻结后首次参赛仍能拿到 FLAG（核心回归）**、未冻结时生涯照常累加、被禁赛玩家不发 FLAG 且冻结不改变其可见性（同一场景冻结/未冻结两种视图必须一致）、冻结后新玩家不入榜、定榜快照只落一次且缓存丢失时按库回填、未冻结时不拍快照、无人达标不落空快照且清表后可重新定榜、多批快照只读回最新一批、旧存档补齐 `finished_games` 与 `leaderboard_frozen_at`。

测试均为**自跑脚本不是 pytest**：`import main as M`、模块级换临时 `Store`、`assert` + `print("[ok] ...")`、在各自的 `main()` 里手动登记用例。改 `main.py` 的模块级开关（如 `LEADERBOARD_FROZEN`）时，读取点必须**在调用时按名字查模块全局**，否则 `M.LEADERBOARD_FROZEN = True` 覆盖不了，测试会静默失去意义。

## 当前代码结构（MVP）

```text
main.py          # FastAPI 服务 + 游戏逻辑（鉴权、FLAG、自动开局、生涯分、广播触发点）
store.py         # SQLite 访问层（runtime_state 权威快照 + 审计表，见 §7.3）
ws.py            # WebSocket 连接管理（个性化广播，见 §7.2）
public/          # 网页前端
  index.html
  style.css
  app.js
data/game.db     # SQLite 数据库（运行时自动生成；首次运行从 game.json 迁移）
data/game.json.bak  # 旧 JSON 状态文件（首次迁移后改名保留，可删）
data/info.log    # 鉴权 / FLAG / 反作弊事件的 info 日志（运行时生成）
_test_anticheat.py  # 反作弊冒烟测试（临时 SQLite，见 §13.4）
_test_items.py      # 道具 / 结算 / 角色冒烟测试（临时 SQLite）
_test_freeze.py     # 排行榜冻结（定榜）冒烟测试（临时 SQLite，见 §11.4 / §13.4）
_smoke_ws.py        # 实时 WS 握手冒烟测试（需先起服务，见 §13.4）
pyproject.toml   # uv 项目配置
```

运行：

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

本地开发（不接真实平台）：

```bash
R2S_MOCK=1 uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`。
