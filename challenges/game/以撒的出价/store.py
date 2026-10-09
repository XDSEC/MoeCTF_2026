"""SQLite 持久化层。

`Game` 对象在内存中是实时状态的权威来源；每次状态变更时
`Game.save()` 会把整局状态序列化写入 `runtime_state` 单行（崩溃恢复用），
并在生命周期事件（开局 / 结算 / 结束 / 发 FLAG）发生时写入规范化审计表，
对应 AGENT.md §7.3 的「玩家信息 / 游戏局信息 / 每轮结果 / 道具归属 / 最终排名」。

使用 stdlib sqlite3 + threading.Lock（check_same_thread=False）：写入都很短，
数据量小，不需要额外的 aiosqlite 依赖。每个写方法都是原子事务：
出错时回滚并重新抛出，由调用方 try/except 吞掉并记日志，游戏继续跑。
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (              -- 玩家信息（生涯镜像，仅人类）
    id           TEXT PRIMARY KEY,                -- u{platform_id}
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'user',
    platform_id  INTEGER,
    games_played INTEGER NOT NULL DEFAULT 0,
    total_score  REAL NOT NULL DEFAULT 0,         -- 累计场均分（stats.total_score）
    scores_json  TEXT NOT NULL DEFAULT '[]',      -- 生涯最好 N 场的单局均分（定三取五）
    last_flag    TEXT,
    updated_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS games (                -- 游戏局信息
    game_number  INTEGER PRIMARY KEY,             -- 第几局
    started_at   INTEGER NOT NULL,
    finished_at  INTEGER,
    human_count  INTEGER NOT NULL,
    player_count INTEGER NOT NULL,
    status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (                -- 每轮结果（单房间双道具，两侧各自结算）
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_number INTEGER NOT NULL REFERENCES games(game_number),
    level       INTEGER NOT NULL,
    room_number INTEGER NOT NULL,
    room_type   TEXT NOT NULL,
    item        TEXT NOT NULL,                    -- 道具侧 1
    avg         REAL,
    target      REAL,
    winner_id   TEXT,
    winner_name TEXT,
    item2       TEXT,                             -- 道具侧 2
    avg2        REAL,
    target2     REAL,
    winner_id2  TEXT,
    winner_name2 TEXT,
    bids_json   TEXT NOT NULL,                    -- {item: {pid: bid}}
    result_json TEXT,                             -- result.sides
    settled_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rooms_game ON rooms(game_number, level, room_number);

CREATE TABLE IF NOT EXISTS player_items (         -- 道具归属（仅人类赢家）
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL REFERENCES players(id),
    game_number INTEGER NOT NULL REFERENCES games(game_number),
    level       INTEGER NOT NULL,
    room_number INTEGER NOT NULL,
    item        TEXT NOT NULL,
    won_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_player ON player_items(player_id, game_number);

CREATE TABLE IF NOT EXISTS game_rankings (        -- 最终排名
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_number INTEGER NOT NULL REFERENCES games(game_number),
    player_id   TEXT NOT NULL REFERENCES players(id),
    rank        INTEGER NOT NULL,
    total_score REAL NOT NULL,
    level_funds INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rankings_game ON game_rankings(game_number);

CREATE TABLE IF NOT EXISTS flags (                -- 动态 FLAG 发放记录
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL,
    platform_id INTEGER,
    game_number INTEGER NOT NULL,
    flag        TEXT NOT NULL,
    issued_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flags_player ON flags(player_id);

CREATE TABLE IF NOT EXISTS runtime_state (        -- 运行时快照（唯一一行，权威）
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    state_json  TEXT NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bans (                 -- 反作弊：禁赛审计（供管理后台排查）
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   TEXT NOT NULL,
    platform_id INTEGER,
    until_ms    INTEGER NOT NULL,                 -- 解禁时间（毫秒时间戳）
    reason      TEXT NOT NULL,
    issued_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bans_player ON bans(player_id);

CREATE TABLE IF NOT EXISTS leaderboard_snapshots ( -- 定榜存档（排行榜冻结瞬间的榜单）
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    frozen_at    INTEGER NOT NULL,                -- 冻结时刻（毫秒时间戳，同一批快照相同）
    rank         INTEGER NOT NULL,                -- 名次（1 起）
    player_id    TEXT NOT NULL,
    name         TEXT NOT NULL,
    career       REAL NOT NULL,                   -- 生涯分（定三取五）
    games_played INTEGER NOT NULL,
    avg          REAL
);
CREATE INDEX IF NOT EXISTS idx_lb_snap ON leaderboard_snapshots(frozen_at);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None
        # RLock：写方法（write_runtime_state / record_*）先拿锁再走 _tx -> _cursor ->
        # connect；若此时连接尚未建立，connect 会再次进入同一把锁。非重入的 Lock
        # 会让同线程自我死锁（只有先调用过 connect() 的路径才侥幸避开）。跨线程互斥
        # 语义不变，RLock 只是允许同线程重入。
        self._lock = threading.RLock()

    # -- 连接 -------------------------------------------------------------
    def connect(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            # 兼容旧库：players 表曾没有 scores_json 列，这里补齐
            cols = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
            if "scores_json" not in cols:
                conn.execute("ALTER TABLE players ADD COLUMN scores_json TEXT NOT NULL DEFAULT '[]'")
            # 兼容旧库：rooms 表曾在单道具时代没有 item2 侧列，这里补齐
            rcols = {row[1] for row in conn.execute("PRAGMA table_info(rooms)")}
            for col, decl in (
                ("item2", "TEXT"),
                ("avg2", "REAL"),
                ("target2", "REAL"),
                ("winner_id2", "TEXT"),
                ("winner_name2", "TEXT"),
            ):
                if col not in rcols:
                    conn.execute(f"ALTER TABLE rooms ADD COLUMN {col} {decl}")
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _cursor(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """原子事务：异常时回滚并重新抛出，不留悬挂事务。"""
        conn = self._cursor()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # -- 运行时快照（权威） ------------------------------------------------
    def read_runtime_state(self) -> Optional[dict[str, Any]]:
        try:
            with self._lock:
                row = self._cursor().execute(
                    "SELECT state_json FROM runtime_state WHERE id = 1"
                ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except Exception:
            return None

    def write_runtime_state(self, state: dict[str, Any]) -> None:
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO runtime_state (id, state_json, updated_at) "
                "VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json, "
                "updated_at = excluded.updated_at",
                (json.dumps(state, ensure_ascii=False), int(time.time() * 1000)),
            )

    # -- 玩家生涯镜像 -------------------------------------------------------
    def upsert_player(
        self,
        player_id: str,
        name: str,
        kind: str,
        platform_id: Optional[int],
        games_played: int,
        total_score: float,
        scores: list[float],
        last_flag: Optional[str],
    ) -> None:
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO players (id, name, kind, platform_id, games_played, "
                "total_score, scores_json, last_flag, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, "
                "kind = excluded.kind, platform_id = excluded.platform_id, "
                "games_played = excluded.games_played, total_score = excluded.total_score, "
                "scores_json = excluded.scores_json, "
                "last_flag = excluded.last_flag, updated_at = excluded.updated_at",
                (
                    player_id,
                    name,
                    kind,
                    platform_id,
                    games_played,
                    total_score,
                    json.dumps(scores, ensure_ascii=False),
                    last_flag,
                    int(time.time() * 1000),
                ),
            )

    def get_players(self) -> list[dict[str, Any]]:
        """返回所有人类玩家的生涯镜像（全场排行榜数据源，含已离开者）。

        只读；失败返回空列表，不影响对局（与 `max_game_number` 同风格）。
        注意：必须在锁外先取连接（`_cursor` 未连接时会触发 `connect()`，
        而 `connect()` 也要拿同一把非可重入锁，持锁调用会死锁）。
        """
        try:
            conn = self._cursor()
            with self._lock:
                rows = conn.execute(
                    "SELECT id, name, kind, platform_id, games_played, total_score, "
                    "scores_json, updated_at FROM players ORDER BY updated_at"
                ).fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "kind": r[2],
                    "platform_id": r[3],
                    "games_played": r[4],
                    "total_score": r[5],
                    "scores_json": r[6],
                    "updated_at": r[7],
                }
                for r in rows
            ]
        except Exception:
            return []

    # -- 游戏局 -------------------------------------------------------------
    def max_game_number(self) -> int:
        """已入库的最大局号；用于 /api/reset 后让局号单调递增，避免审计表 UNIQUE 冲突。"""
        try:
            with self._lock:
                row = self._cursor().execute(
                    "SELECT COALESCE(MAX(game_number), 0) FROM games"
                ).fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0

    def record_game_start(
        self, game_number: int, human_count: int, player_count: int, started_at: int
    ) -> None:
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO games (game_number, started_at, human_count, "
                "player_count, status) VALUES (?, ?, ?, ?, 'playing')",
                (game_number, started_at, human_count, player_count),
            )

    def record_game_finish(self, game_number: int, finished_at: int) -> None:
        with self._lock, self._tx() as conn:
            conn.execute(
                "UPDATE games SET finished_at = ?, status = 'finished' "
                "WHERE game_number = ?",
                (finished_at, game_number),
            )

    # -- 每轮结果 + 道具归属 ------------------------------------------------
    def record_room(
        self,
        game_number: int,
        level: int,
        room_number: int,
        room_type: str,
        results: list[dict[str, Any]],
        bids: dict[str, Any],
        result: Optional[dict[str, Any]],
        settled_at: int,
    ) -> None:
        """记录一房结算。results 为两个道具侧各自的结果：
        [{item, avg, target, winner_id, winner_name}, ...]，映射到 item/item2 两列。
        """
        r1 = results[0] if results else {}
        r2 = results[1] if len(results) > 1 else {}
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO rooms (game_number, level, room_number, room_type, "
                "item, avg, target, winner_id, winner_name, "
                "item2, avg2, target2, winner_id2, winner_name2, "
                "bids_json, result_json, settled_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    game_number,
                    level,
                    room_number,
                    room_type,
                    r1.get("item") or "none",
                    r1.get("avg", 0),
                    r1.get("target", 0),
                    r1.get("winner_id"),
                    r1.get("winner_name"),
                    r2.get("item"),
                    r2.get("avg", 0),
                    r2.get("target", 0),
                    r2.get("winner_id"),
                    r2.get("winner_name"),
                    json.dumps(bids, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False) if result else None,
                    settled_at,
                ),
            )

    def record_item(
        self,
        player_id: str,
        game_number: int,
        level: int,
        room_number: int,
        item: str,
        won_at: int,
    ) -> None:
        """道具归属（仅人类赢家调用）。"""
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO player_items (player_id, game_number, level, "
                "room_number, item, won_at) VALUES (?, ?, ?, ?, ?, ?)",
                (player_id, game_number, level, room_number, item, won_at),
            )

    # -- 最终排名 -----------------------------------------------------------
    def record_rankings(
        self, game_number: int, ranked_rows: list[dict[str, Any]]
    ) -> None:
        with self._lock, self._tx() as conn:
            conn.executemany(
                "INSERT INTO game_rankings (game_number, player_id, rank, "
                "total_score, level_funds) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        game_number,
                        row["id"],
                        idx + 1,
                        row["total_score"],
                        row["level_funds"],
                    )
                    for idx, row in enumerate(ranked_rows)
                ],
            )

    # -- 排行榜定榜存档 -----------------------------------------------------
    def record_leaderboard_snapshot(
        self, frozen_at: int, rows: list[dict[str, Any]]
    ) -> None:
        """落一份定榜快照：冻结瞬间的排行榜，一个玩家一行。

        `rows` 即 career_leaderboard() 的返回值，名次按列表顺序（1 起）。
        """
        with self._lock, self._tx() as conn:
            conn.executemany(
                "INSERT INTO leaderboard_snapshots (frozen_at, rank, player_id, "
                "name, career, games_played, avg) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        frozen_at,
                        idx + 1,
                        row["id"],
                        row["name"],
                        row["career"],
                        row["games_played"],
                        row.get("avg"),
                    )
                    for idx, row in enumerate(rows)
                ],
            )

    def get_leaderboard_snapshot(self) -> list[dict[str, Any]]:
        """读回最近一次定榜快照（赛后公示 / 导出 / 校验用），按名次升序。

        只取 frozen_at 最大的那一批：表里可能存有多批快照（如先解冻改分再重新定榜），
        不按批次过滤的话名次会交错成 1,1,2,2。
        """
        with self._lock:
            cur = self._cursor().execute(
                "SELECT frozen_at, rank, player_id, name, career, games_played, avg "
                "FROM leaderboard_snapshots "
                "WHERE frozen_at = (SELECT MAX(frozen_at) FROM leaderboard_snapshots) "
                "ORDER BY rank ASC"
            )
            return [
                {
                    "frozen_at": r[0],
                    "rank": r[1],
                    "id": r[2],
                    "name": r[3],
                    "career": r[4],
                    "games_played": r[5],
                    "avg": r[6],
                }
                for r in cur.fetchall()
            ]

    # -- FLAG ---------------------------------------------------------------
    def record_flag(
        self,
        player_id: str,
        platform_id: Optional[int],
        game_number: int,
        flag: str,
        issued_at: int,
    ) -> None:
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO flags (player_id, platform_id, game_number, flag, "
                "issued_at) VALUES (?, ?, ?, ?, ?)",
                (player_id, platform_id, game_number, flag, issued_at),
            )

    # -- 反作弊：禁赛审计 ------------------------------------------------
    def get_ban_counts(self, reasons: tuple[str, ...]) -> dict[str, int]:
        """累计「人机验证失败次数」：按玩家统计指定禁赛原因的审计行数。

        每次验证失败（答错用尽次数 / 超时）都会经 apply_ban 落一条禁赛审计记录，
        因此按 player_id 统计这些 reason 的行数即为累计验证失败次数。排行榜据此展示。
        读库失败返回空表，不影响对局（与 `get_players` 同风格）。
        """
        if not reasons:
            return {}
        try:
            conn = self._cursor()
            ph = ",".join("?" for _ in reasons)
            with self._lock:
                rows = conn.execute(
                    f"SELECT player_id, COUNT(*) FROM bans "
                    f"WHERE reason IN ({ph}) GROUP BY player_id",
                    reasons,
                ).fetchall()
            return {pid: int(cnt) for pid, cnt in rows}
        except Exception:
            return {}

    def record_ban(
        self,
        player_id: str,
        platform_id: Optional[int],
        until_ms: int,
        reason: str,
        issued_at: int,
    ) -> None:
        """记录一次禁赛（供管理后台排查；权威状态在 runtime_state['bans']）。"""
        with self._lock, self._tx() as conn:
            conn.execute(
                "INSERT INTO bans (player_id, platform_id, until_ms, reason, "
                "issued_at) VALUES (?, ?, ?, ?, ?)",
                (player_id, platform_id, until_ms, reason, issued_at),
            )
