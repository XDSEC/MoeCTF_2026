"""
CTF 答题平台 - 外部环境
==========================
功能：
  1. 无需身份验证，直接进入答题
  2. 三道 CTF 图片/文字问答（每题唯一答案，限提交次数，答错锁定）
  3. 题目支持展示图片（static/images/ 目录）
  4. 答对全部题目 → 领取环境变量 FLAG 中的 flag
"""

import sqlite3
import os
import secrets
from datetime import timedelta
from flask import (
    Flask, render_template, request, url_for,
    redirect, flash, jsonify, session
)

# ---------------------------------------------------------------------------
# 应用初始化
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32).hex())
app.permanent_session_lifetime = timedelta(days=7)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "ctf_platform.db")

# ---------------------------------------------------------------------------
# Flag：从环境变量 FLAG 获取
# ---------------------------------------------------------------------------
FLAG = os.environ.get("FLAG", "moectf{this-is-a-default-flag}")

# ---------------------------------------------------------------------------
# 题库（共 3 题，答对全部题目即可领取 flag）
#   - question:     题目文本
#   - answer:       唯一正确答案（比较时不区分大小写）
#   - max_attempts: 每题最大提交次数，答错达到上限后锁定
#   - image:        可选，static/images/ 目录下的图片文件名，用于在题目中展示图片
# ---------------------------------------------------------------------------
CHALLENGES = [
    {
        "id": 1,
        "category": "西复问答",
        "question": "西电B楼可从平地直接进入的楼层总和为？（答案格式 ^\\s*\\d+\\s*$）",
        "answer": "10",
        "max_attempts": 2,
        "image": "",
    },
    {
        "id": 2,
        "category": "OSINT",
        "question": "这张照片是在哪所院校的哪栋楼的几层拍的？（答案格式 院校名楼名-层，如 复旦大学逸夫楼-1）",
        "answer": "同济大学衷和楼-13",
        "max_attempts": 3,
        "image": "challenge2.jpg",
    },
    {
        "id": 3,
        "category": "西复问答",
        "question": "西电湖人的发生时间？（答案格式yyyyddmm）",
        "answer": "20230911",
        "max_attempts": 2,
        "image": "",
    },
]

# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构（幂等）。username 列存访问者会话 ID。"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_challenges (
            username      TEXT NOT NULL,
            challenge_id  INTEGER NOT NULL,
            attempts      INTEGER DEFAULT 0,
            solved        INTEGER DEFAULT 0,
            locked        INTEGER DEFAULT 0,
            PRIMARY KEY (username, challenge_id)
        );
        CREATE TABLE IF NOT EXISTS claimed_flags (
            username    TEXT NOT NULL,
            flag_level  INTEGER NOT NULL,   -- 固定为 1
            claimed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (username, flag_level)
        );
    """)
    conn.commit()
    conn.close()


init_db()

# ---------------------------------------------------------------------------
# 访问者标识（无需登录，靠会话 cookie 区分不同答题者）
# ---------------------------------------------------------------------------
def get_visitor_id() -> str:
    """获取当前访问者的会话 ID，首次访问时自动生成。"""
    if "visitor_id" not in session:
        session["visitor_id"] = secrets.token_hex(8)
    return session["visitor_id"]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def get_user_stats(username: str) -> dict:
    """{ challenge_id: {attempts, solved, locked} }"""
    conn = get_db()
    rows = conn.execute(
        "SELECT challenge_id, attempts, solved, locked FROM user_challenges WHERE username = ?",
        (username,)
    ).fetchall()
    conn.close()
    return {
        r["challenge_id"]: {
            "attempts": r["attempts"],
            "solved":   r["solved"],
            "locked":   r["locked"],
        }
        for r in rows
    }


def count_solved(username: str) -> int:
    conn = get_db()
    r = conn.execute(
        "SELECT COUNT(*) AS cnt FROM user_challenges WHERE username = ? AND solved = 1",
        (username,)
    ).fetchone()
    conn.close()
    return r["cnt"] if r else 0


def has_claimed(username: str, level: int) -> bool:
    conn = get_db()
    r = conn.execute(
        "SELECT 1 FROM claimed_flags WHERE username = ? AND flag_level = ?",
        (username, level)
    ).fetchone()
    conn.close()
    return r is not None


def mark_claimed(username: str, level: int):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO claimed_flags (username, flag_level) VALUES (?, ?)",
        (username, level)
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 路由 — 答题
# ---------------------------------------------------------------------------
@app.route("/")
def quiz():
    vid = get_visitor_id()
    stats = get_user_stats(vid)
    solved_cnt = count_solved(vid)

    challenges = []
    for ch in CHALLENGES:
        s = stats.get(ch["id"], {"attempts": 0, "solved": 0, "locked": 0})
        challenges.append({
            "id":           ch["id"],
            "category":     ch["category"],
            "question":     ch["question"],
            "image":        ch.get("image"),
            "max_attempts": ch["max_attempts"],
            "attempts":     s["attempts"],
            "solved":       s["solved"],
            "locked":       s["locked"],
            "remaining":    max(0, ch["max_attempts"] - s["attempts"]),
        })

    return render_template("quiz.html",
                           challenges=challenges,
                           solved_count=solved_cnt,
                           total_count=len(CHALLENGES),
                           flag_eligible=solved_cnt >= len(CHALLENGES),
                           flag_claimed=has_claimed(vid, 1))


@app.route("/submit/<int:challenge_id>", methods=["POST"])
def submit_answer(challenge_id):
    vid = get_visitor_id()
    challenge = next((c for c in CHALLENGES if c["id"] == challenge_id), None)
    if not challenge:
        return jsonify({"ok": False, "msg": "题目不存在"}), 404

    answer = request.form.get("answer", "").strip()
    if not answer:
        return jsonify({"ok": False, "msg": "请输入答案"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT attempts, solved, locked FROM user_challenges WHERE username=? AND challenge_id=?",
        (vid, challenge_id)
    ).fetchone()

    attempts = row["attempts"] if row else 0
    solved   = row["solved"]   if row else 0
    locked   = row["locked"]   if row else 0

    if solved:
        conn.close()
        return jsonify({"ok": False, "msg": "✅ 你已经答对了这道题"})

    if locked:
        conn.close()
        return jsonify({"ok": False, "msg": "🔒 该题已被锁定，无法继续提交"})

    if attempts >= challenge["max_attempts"]:
        conn.close()
        return jsonify({"ok": False, "msg": "❌ 已达到最大提交次数"})

    # 检查答案（大小写不敏感）
    correct = answer.lower() == challenge["answer"].lower()

    new_attempts = attempts + 1
    new_solved   = 1 if correct else 0
    new_locked   = 1 if (not correct and new_attempts >= challenge["max_attempts"]) else 0

    if row:
        conn.execute(
            "UPDATE user_challenges SET attempts=?, solved=?, locked=? WHERE username=? AND challenge_id=?",
            (new_attempts, new_solved, new_locked, vid, challenge_id)
        )
    else:
        conn.execute(
            "INSERT INTO user_challenges (username, challenge_id, attempts, solved, locked) VALUES (?, ?, ?, ?, ?)",
            (vid, challenge_id, new_attempts, new_solved, new_locked)
        )
    conn.commit()
    conn.close()

    solved_cnt = count_solved(vid)

    if correct:
        return jsonify({
            "ok": True,
            "msg": "🎉 回答正确！",
            "solved_count": solved_cnt,
            "total_count":  len(CHALLENGES),
            "locked":       False,
        })
    else:
        remaining = max(0, challenge["max_attempts"] - new_attempts)
        return jsonify({
            "ok":       False,
            "msg":      f"❌ 回答错误。剩余尝试次数：{remaining}" if remaining > 0 else "❌ 回答错误，该题已被锁定",
            "locked":   new_locked == 1,
            "remaining": remaining,
        })


# ---------------------------------------------------------------------------
# 路由 — Flag 领取
# ---------------------------------------------------------------------------
@app.route("/flag")
def get_flag():
    vid = get_visitor_id()
    solved_cnt = count_solved(vid)

    if solved_cnt < len(CHALLENGES):
        flash(f"需要答对全部 {len(CHALLENGES)} 题才能领取 flag（当前已答对 {solved_cnt} 题）", "error")
        return redirect(url_for("quiz"))

    already = has_claimed(vid, 1)
    if not already:
        mark_claimed(vid, 1)

    return render_template("flag.html",
                           flag=FLAG,
                           solved_count=solved_cnt,
                           total_count=len(CHALLENGES),
                           already_claimed=already)


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
