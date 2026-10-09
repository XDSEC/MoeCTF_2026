# The Biding of the Isaac

以撒的出价：多人全付竞拍网页游戏。

## 运行

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`。

本地开发（不接真实平台）可以开 mock 模式：

```bash
R2S_MOCK=1 uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`。Mock 模式下接受任意识别码并返回固定假身份。

### 验证改动

1. Network 面板应出现 `/ws` 连接，且**不再有每 2 秒一次的 `/api/state` 轮询**（仅在 WS 断开时兜底）。
2. 任意粘贴一个识别码 → 「验证并加入」→ 顶栏显示「已登录：Mock 用户」。
3. 输入识别码并加入后，等待大厅能听到 `waiting.m4a` 背景音乐；开局后自动切换为 `begin.m4a`；一局结束后回到等待大厅，恢复等待音乐。未登录只浏览不发声。
4. 开两个标签页：开局后两边实时同步；机器人出价让 `bid_count` 实时增长。
5. 提交出价后两页同时更新（走 WS）；超资金出价会收到 error 帧并显示「出价失败」。
6. 数据库检查：`python -c "import sqlite3;c=sqlite3.connect('data/game.db');print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())"` 应列出全部表，`data/game.json` 已被迁移改名 `.bak`。

## systemd 持久化部署（Linux 服务器）

项目自带 `deploy/` 模板：`tboi.service`、`tboi.env.example`、`nginx.example.conf`。游戏状态在内存中，**必须单 worker**（uvicorn 默认即单 worker，禁止 `--workers`）。

```bash
# 1. 专用低权限运行用户 + 目录（-m 建家目录，uv 缓存要用）
sudo useradd -r -m -s /usr/sbin/nologin tboi
sudo mkdir -p /opt/the-biding-of-the-isaac /etc/tboi
# 把整个项目（main.py / public/ / data/ / pyproject.toml 等）放到 /opt/the-biding-of-the-isaac
sudo chown -R tboi:tboi /opt/the-biding-of-the-isaac

# 2. 环境变量（先拷模板，填好后 chmod 600）
sudo cp deploy/tboi.env.example /etc/tboi/tboi.env
sudo chown root:tboi /etc/tboi/tboi.env && sudo chmod 600 /etc/tboi/tboi.env
sudoedit /etc/tboi/tboi.env   # 填 SESSION_SECRET（openssl rand -hex 32）、FLAG_KEY 等

# 3. 安装 uv 并同步依赖（以 tboi 用户建 .venv）
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo cp ~/.local/bin/uv /usr/local/bin/
sudo -u tboi -H sh -c 'cd /opt/the-biding-of-the-isaac && uv sync'

# 4. 安装并启动服务
sudo cp deploy/tboi.service /etc/systemd/system/tboi.service
sudo systemctl daemon-reload
sudo systemctl enable --now tboi
sudo systemctl status tboi
journalctl -u tboi -f          # 看日志；鉴权成功与 FLAG 发放也记在 data/info.log
```

升级代码后：`sudo -u tboi -H sh -c 'cd /opt/the-biding-of-the-isaac && uv sync'`，再 `sudo systemctl restart tboi`。

**对外暴露**（二选一）：

- **经 nginx 反向代理（推荐）**：用 `deploy/nginx.example.conf`。`/ws` 需要升级头；对局中 WS 长连接可能持续一局 6~7 分钟，超时设长一些。
- **直接公网**：把 `tboi.service` 里 `--host 127.0.0.1` 改成 `--host 0.0.0.0`，并自行上 TLS（如 caddy）。注意此时 `SESSION_SECRET` 必须改，且 `https_only=False` 的 cookie 不经 HTTPS 也只是明文加密的签名 cookie，仍建议上 HTTPS。

> 说明：session cookie 默认 `https_only=False`（`main.py`），走 nginx HTTPS 时代理把 `X-Forwarded-Proto: https` 传给应用即可正常登录。

## 当前功能

- **实时推送**：状态、出价、结算走 WebSocket 推送（`/ws`），无需轮询；断线自动重连，WS 不可用时回退 HTTP 轮询
- **出价走 WebSocket**：提交出价通过 WS 消息发送，避免反复建立 HTTP 连接；HTTP `/api/bid` 保留为兜底
- **鉴权加入**：选手须输入一次性临时用户识别码，经平台验证后才能加入对局；未鉴权只能查看状态，不能出价；已鉴权但不在当前局的玩家点顶栏「加入对局」按钮（`POST /api/join`）重新加入
- **系统每 10 分钟自动开一局**，大厅显示开局倒计时（无“立即开始”/“添加机器人”按钮，开局仅依赖自动调度）
- **不足 20 位人类玩家时，自动用机器人补足到 20 人**
- 对局进行中加入的玩家进入等待队列，下一局自动加入
- **一局结束后由玩家自主选择是否继续**：打完一局进入 90 秒「继续下一局」窗口，点击后下一局自动开始；不点则自动退出由机器人补位
- 一局 3 个 Level、13 个 Room，每 Room 全付竞拍
- 道具系统：15 种道具（经济 / 得分 / 竞拍 / 诅咒），稀有度分常见 / 稀有 / 诅咒
- **角色选择**：开局前在等待大厅选择角色（以撒 / 游魂 / 阿撒泻勒 / 伊甸 / 雅各和以扫），开局时携带角色初始道具，开局前可随时修改
- 特殊 Room：1~999 出价、反转目标、双倍得分
- Boss Room
- **生涯总分（定三取五）**：至少打满 3 局才能进入排行榜，取生涯最好 5 场的均分
- **动态 FLAG**：完整打完一局的人类玩家获得与比赛平台同款算法生成的 FLAG（默认 Leet 模式）
- **排行榜冻结（定榜）**：把 `main.py` 顶部的 `LEADERBOARD_FROZEN` 置为 `True` 并重启，生涯数据即停止累加、榜单定榜；**参赛与 FLAG 发放完全不受影响**——冻结后选手照常参赛，完整打完一局仍照常拿到 FLAG。冻结瞬间的榜单会落库到 `leaderboard_snapshots` 存档并记入 info 日志（详见下文「赛事定榜（排行榜冻结）」）
- **背景音乐**：登录并加入后播放——等待大厅循环 `public/assets/waiting.m4a`，对局中切换为 `begin.m4a`，一局结束回到等待大厅后恢复等待音乐
- 排行榜、全场排行榜（打满 3 局的人类玩家按生涯分排名，含已离开者）、历史记录
- 机器人自动出价，方便演示

## 鉴权与 FLAG

### 鉴权流程

1. 选手在页面输入**临时用户识别码**（一次性十六进制码）。
2. 服务器调用 ret2shell-kit 向比赛平台换取用户 ID 与昵称。
3. 用户 ID、用户名写入 **session cookie**；鉴权成功与 FLAG 发放会打印到 **info 日志**（`data/info.log`）。
4. 前端展示获取到的用户名。

### 动态 FLAG

- 用 `ret2shell_kit.PlatformFlagManager` 生成，与比赛平台算法一致。
- **`FLAG_KEY`、`FLAG_TEMPLATE`、`FLAG_PREFIX`、`FLAG_MODE` 必须与平台评测脚本保持一致**，否则平台无法验证。
- 同一用户的 FLAG 由其 ID + 密钥 + 模板确定性生成，反复完成对局展示同一个 FLAG。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `R2S_BASE_URL` | `https://ctf.xidian.edu.cn/api` | 平台 API 地址 |
| `R2S_TOKEN` | 空 | 可选平台 token |
| `SESSION_SECRET` | `dev-secret-change-me` | session cookie 签名密钥，**生产必须改** |
| `FLAG_KEY` | `change-me` | FLAG 加密密钥，**须与平台一致** |
| `FLAG_PREFIX` | `flag` | FLAG 前缀 |
| `FLAG_TEMPLATE` | `XIDIAN_CTF_2026_...` | FLAG 模板，**须与平台一致** |
| `FLAG_MODE` | `leet` | 隐写模式：`leet` / `uuid`（0.1.5 的 UUID 往返有 bug，默认 leet） |
| `R2S_MOCK` | 空 | `1` 时本地模拟平台，接受任意识别码 |

### 注意事项

- 临时用户识别码是**一次性**绑定码，消费后不可复用；会话失效后需重新获取。
- 首次运行时请先 `uv sync` 安装依赖（含 `ret2shell-kit`、`itsdangerous`、`websockets`）。

## WebSocket 协议（`/ws`）

服务端 → 客户端：

```json
{"type": "state", "data": { ...完整公开状态，含本连接的 me / my_bid / my_flag... }}
{"type": "error", "message": "..."}
```

客户端 → 服务端：

```json
{"type": "bid", "value": 42}
{"type": "refresh"}
{"type": "ping"}
```

- 鉴权（`/api/auth`）与加入（`/api/join`）走 HTTP，因为 session 写入只会在 HTTP 响应时持久化。
- 断线后前端指数退避重连（1s 起、上限 15s）；WS 断开时保留 2s 一次的 HTTP 兜底轮询。

## 数据持久化（SQLite）

- 状态保存在 `data/game.db`（首次运行会自动创建；若存在旧的 `data/game.json` 会一次性迁移并改名 `game.json.bak`）。
- `runtime_state` 单行保存整局快照（崩溃恢复用）；`players / games / rooms / player_items / game_rankings / flags / bans` 审计表记录生涯、每轮结果、道具归属、FLAG 发放与禁赛。
- `leaderboard_snapshots` 保存定榜存档（冻结瞬间的排行榜，一个玩家一行），只在排行榜冻结时写入，见下文「赛事定榜」。
- 机器人不写入生涯/道具/排名表。写失败不影响游戏运行（记入日志后继续）。

## 规则速览

- 出价上限按层放开：第 1 层普通/宝物房 `1~99`；第 2/3 层全部房间以及特殊/Boss 房 `1~999`
- 所有参与者都要扣除自己的出价
- 最高有效出价者赢得道具
- 每个 Level 有独立资金，资金不足只能观战
- 一局结束后按总分排名

### 目标值与得分

每个 Room 结算时，先取所有出价的平均值 `A`，再算目标值：

```text
T = 2/3 × A + C
```

常量 `C` 和得分公式中的 `σ` 由房间出价量级决定（实现见 `room_config()`）：

| 房间量级 | `range_max` | `C` | `σ` |
|---|---:|---:|---:|
| 普通 / 宝物房（第 1 层） | 99 | 10 | 10 |
| 第 2/3 层全部房间、特殊 / Boss 房 | 999 | 50 | 100 |

单轮得分：

```text
score = 100 × e^(-|出价 − T| / σ)
```

出价越接近目标 `T` 得分越高，上限 100 分；道具倍率、固定加分、Boss 双倍在此基础上叠加。目标值 `T` 会被限制在 `1 ~ range_max` 之间。每轮有 `MIN_SCORE_PER_ROOM`（5）分保底：当目标远离所有出价（如反转房全场低出价）时，指数衰减会把全员得分压到 0.x，保底分保证参与出价的玩家至少拿到一个可读的分数。

### 反转目标（特殊房）

特殊 Room 有 **45% 概率**携带「反转目标」规则（`room_modifiers()`）。反转房会把目标值在整个出价范围上镜像翻转：

```text
T = range_max − (2/3 × A + C)
```

仍限制在 `1 ~ range_max` 内。**注意：反转房的目标与平均值负相关**——大家出价越低，目标反而越接近上限。例如平均出价 100 时，反转目标约为 `999 − (2/3×100 + 50) ≈ 882`。房间开始时会在 `modifiers` 中标注 `reverse`，看清规则再出价，别一律追低。

## 生涯总分（定三取五）

排行榜的“生涯分”采用「定三取五」：

- **入榜门槛**：至少打满 `MIN_GAMES_FOR_RANK`（3）局才能进入排行榜，防止新手打一两把高分就上榜。
- **取分方式**：生涯分 = 生涯最好 `BEST_N_GAMES`（5）场的单局均分；不足 5 场时，直接取已打场次的均分。
- **单局均分**：该局总分 ÷ 一局房间数（13 个 Room），量级接近 0~100。
- 机器人不参与生涯记录。

## 可调参数（main.py 顶部）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `GAME_INTERVAL_MS` | 600000 | 每 10 分钟自动开一局 |
| `TARGET_PLAYERS` | 20 | 每局补足到 20 人 |
| `MIN_GAMES_FOR_RANK` | 3 | 进入排行榜所需最少局数 |
| `BEST_N_GAMES` | 5 | 生涯分取最好 N 场的单局均分 |
| `ROOM_DURATION_MS` | 30000 | 每个房间出价时长 |
| `CONTINUE_GRACE_MS` | 90000 | 一局结束后等待玩家「继续下一局」的窗口 |
| `MIN_SCORE_PER_ROOM` | 5.0 | 每轮保底基础分，避免出价远离目标时全员 0.x |
| `LEADERBOARD_FROZEN` | False | 排行榜冻结（定榜）开关，改后需重启；**不影响参赛与 FLAG 发放** |

## 赛事定榜（排行榜冻结）

比赛结束后排行榜需要定榜——榜单不再变化，但服务器通常还要继续开着，让选手照常参赛、打完一局仍然拿到 FLAG。把 `main.py` 顶部的开关置位并重启即可：

```python
LEADERBOARD_FROZEN = True   # main.py 顶部常量区
```

```bash
sudo systemctl restart tboi      # 或重启 uvicorn
```

冻结后：

- **生涯数据停止累加**：`games_played` / `total_score` / `scores` 停在冻结时刻，排行榜名次与分数不再变化；`leaderboard_snapshots` 与审计表（`game_rankings` / `flags` / `rooms`）照常写入。
- **参赛与 FLAG 完全不受影响**：自动开局、对局结算、动态 FLAG 发放一切照旧。冻结后**首次**参赛的选手打完一局照样在「当前房间」看到自己的 FLAG——FLAG 的展示门槛用的是独立的「已完成局数」计数，与生涯局数解耦，所以冻结不会把它掐掉。
- **定榜存档**：进程启动与每局结束时都会检查一次，首次观察到冻结就把当时的榜单落库到 `leaderboard_snapshots`（一个玩家一行，含名次、生涯分、局数），并记入 `data/info.log`（`排行榜已冻结: 冻结时间=... 入榜人数=...`）。同一份存档只落一次；若冻结时无人打满 `MIN_GAMES_FOR_RANK` 局，则不落空快照并记 warning，等有人达标后再落。
- **前端提示**：页面顶部与两个排行榜都会显示「排行榜已冻结（时刻），冻结后新打完的对局不计入生涯分；FLAG 照常发放」。

赛后导出定榜结果（表里若有多批快照，取 `frozen_at` 最大的那批）：

```bash
sqlite3 data/game.db "SELECT rank, name, career, games_played FROM leaderboard_snapshots \
  WHERE frozen_at = (SELECT MAX(frozen_at) FROM leaderboard_snapshots) ORDER BY rank"
```

想**重新定榜**（例如重跑一遍想换个冻结时刻）：清掉存档表，下一次开局结算时就会重新拍一份，不需要动 `runtime_state`：

```bash
sqlite3 data/game.db "DELETE FROM leaderboard_snapshots"
```

注意清表**不会**恢复生涯数据——榜单仍是冻结时的内容，只是重新录一次档。要真正让分数继续增长，得把 `LEADERBOARD_FROZEN` 改回 `False` 重启（已落库的定榜存档保留不动，方便前后对照）；等改判完毕后重新置为 `True` 并清掉旧存档，即可按新成绩再次定榜。
