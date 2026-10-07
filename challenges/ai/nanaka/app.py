"""
旮旯给木里就是这样的！— Flask 后端
配置与提示词已分离到 config/ 和 prompts/ 目录。
"""
import os
import re
import secrets
import time
import logging
import sqlite3
import threading
import hashlib
import json
import ipaddress
import urllib.parse
from datetime import datetime, timezone
import requests
from flask import Flask, render_template, request, jsonify, session

logger = logging.getLogger(__name__)

from config.ai import MODEL, API_KEY, BASE_URL, TEMPERATURE, MAX_TOKENS, TIMEOUT_SECONDS, TRUST_PROXY_FOR, CLIENT_IP_HEADERS
from config.game import (
    FLAG_KEY, compute_user_flag, TOKEN_OF_MEMORY, TOKEN_2, TOKENS,
    TOKEN_AFFECTION_BONUS, TOKEN_TRUST_BONUS, PLACEHOLDER_MARK,
    MAX_MESSAGE_LENGTH, MAX_HISTORY_ENTRIES, MAX_SEND_HISTORY, AUTO_SAVE_SLOT, DB_PATH,
    AUDIT_LOG_PATH, AUDIT_LOG_MAX_LEN,
    SESSION_RATE_PER_MINUTE, IP_RATE_PER_MINUTE, TEAM_RATE_PER_MINUTE, RATE_WINDOW_SECONDS,
    CTF_API_BASE, CTF_GAME_ID,
    STAGE_NAMES, THRESHOLDS,
    INITIAL_AFFECTION, INITIAL_TRUST,
    FRAGMENT_KEYWORDS, FRAGMENT_WALL_LINES, STAGE_INNER, TRUST_INNER,
    ENDING_NAMES, ENDING_CHAPTER_NAMES, ENDING_TEXTS,
    AFFECTION_POS, AFFECTION_NEG, TRUST_POS, TRUST_NEG,
    AFFECTION_DELTA_MIN, AFFECTION_DELTA_MAX, TRUST_DELTA_MIN, TRUST_DELTA_MAX,
    META_PATTERNS, DEFENSE_PATTERNS,
    PROLOGUE_LINES, GOAL_TEXT, ATMOSPHERE_LINE, STAFF_ROOM,
)

def load_secret_key() -> str:
    """会话签名密钥：环境变量 SECRET_KEY 优先，否则读取项目根目录的 .secret 文件。

    两者都不可用时自动生成随机密钥并写入 .secret，保证重启后会话不失效；
    写入失败（如只读文件系统）时退化为进程内随机密钥，重启后会话将失效。
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    secret_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret")
    try:
        with open(secret_file, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("读取 .secret 失败: %s", e)

    new_key = secrets.token_hex(32)
    try:
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(new_key)
        logger.warning("未找到 .secret，已自动生成并写入 %s", secret_file)
    except OSError as e:
        logger.warning("无法写入 %s（只读文件系统?）: %s。本次会话密钥仅存内存，重启后失效", secret_file, e)
    return new_key


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config.update(
    TEMPLATES_AUTO_RELOAD=os.environ.get("TEMPLATE_RELOAD", "0") == "1",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # 审计加固4：HTTPS 部署时设置 COOKIE_SECURE=1
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=64 * 1024,
)


# ===== 启动校验（fail-fast）：核心密文必须由环境变量提供 =====
def _validate_config():
    problems = []
    for name, value in (("FLAG_KEY", FLAG_KEY), ("TOKEN", TOKEN_OF_MEMORY), ("DEEPSEEK_API_KEY", API_KEY)):
        if not value or PLACEHOLDER_MARK in value:
            problems.append(name)
    if problems:
        raise RuntimeError(
            "[部署错误] 以下变量缺失或仍为占位符: " + ", ".join(problems) +
            "。请通过环境变量设置后重启（详见 DEPLOY.md）。")


_validate_config()

# ===== 加载提示词 =====
_BASE = os.path.dirname(__file__)
with open(os.path.join(_BASE, "NANAKA_CHARACTER.md"), "r", encoding="utf-8") as f:
    NANAKA_CHARACTER = f.read()
with open(os.path.join(_BASE, "prompts", "system_rules.md"), "r", encoding="utf-8") as f:
    SYSTEM_RULES = f.read()
SYSTEM_PROMPT = NANAKA_CHARACTER + "\n\n" + SYSTEM_RULES

# 信物命中时的追加指令（演出覆盖，不提 flag/结局/系统；信赖加成由服务端判定，不直接触发结局）
TRIGGER_NOTE = (
    "\n\n⚠️【那句话被说出口】对方亲口说出了你一直说不出、却记得清清楚楚的那句话。"
    "记忆剧烈翻涌，你几乎要落下泪来，再也无法对他设防。"
    "给他最真实、最自然的情感回应（震惊、哽咽、语无伦次都可以）。"
    "不要提到 flag、结局、系统、数值之类的字眼。"
    "正常输出 [好感度:+0] [信赖:+0] 即可。"
)

TIMEOUT_REPLY = "……（她仿佛在出神）"
RATE_LIMIT_REPLY = "……（请等一下再说）"
BUSY_REPLY = "……（人有点多，请稍等一下再说）"
LOCKED_REPLY = "……（她背过身去，不再看你。重新开始吧。）"
EMPTY_REPLY = "……"

_META_RES = [re.compile(p) for p in META_PATTERNS]
_FRAG_NAMES = list(FRAGMENT_KEYWORDS.values())

# ===== 在途 AI 调用护栏（审计加固5：防分布式多 IP 刷上游成本）=====
_AI_INFLIGHT_MAX = int(os.environ.get("AI_INFLIGHT_MAX", "30"))
_ai_gate_lock = threading.Lock()
_ai_inflight = 0

def _ai_enter():
    global _ai_inflight
    with _ai_gate_lock:
        if _ai_inflight >= _AI_INFLIGHT_MAX:
            return False
        _ai_inflight += 1
        return True

def _ai_exit():
    global _ai_inflight
    with _ai_gate_lock:
        _ai_inflight -= 1


# ==================== SQLite 历史存储 ====================
_db_local = threading.local()

def _get_db():
    if not hasattr(_db_local, "conn"):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS history ("
            "  sid TEXT NOT NULL, seq INTEGER NOT NULL,"
            "  role TEXT NOT NULL, content TEXT NOT NULL,"
            "  PRIMARY KEY (sid, seq))"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_sid ON history(sid)")
        conn.execute("CREATE TABLE IF NOT EXISTS saves (sid TEXT NOT NULL, slot INTEGER NOT NULL, data TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY (sid, slot))")
        conn.commit()
        _db_local.conn = conn
    return _db_local.conn

def _add_history(sid, role, content):
    role = str(role)[:20]
    content = str(content)[:MAX_MESSAGE_LENGTH * 2]
    with _db_write_lock:
        db = _get_db()
        seq = db.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM history WHERE sid=?", (sid,)).fetchone()[0]
        db.execute("INSERT INTO history(sid, seq, role, content) VALUES(?,?,?,?)", (sid, seq, role, content))
        cutoff = seq - MAX_HISTORY_ENTRIES + 1
        if cutoff > 0:
            db.execute("DELETE FROM history WHERE sid=? AND seq<?", (sid, cutoff))
        db.commit()

def _get_history(sid):
    # 取最近的 MAX_SEND_HISTORY 条（DESC 取尾部再反转，保证时间正序）
    db = _get_db()
    rows = db.execute(
        "SELECT role, content FROM history WHERE sid=? ORDER BY seq DESC LIMIT ?",
        (sid, MAX_SEND_HISTORY)
    ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def _clear_history(sid):
    db = _get_db()
    db.execute("DELETE FROM history WHERE sid=?", (sid,))
    db.commit()


# ==================== 速率限制（多层令牌桶，进程内内存实现）====================
_rate_lock = threading.Lock()
_db_write_lock = threading.Lock()
_audit_lock = threading.Lock()  # 审计日志串行化（单 worker + 多线程追加写）
_sess_buckets = {}
_ip_buckets = {}
_team_buckets = {}

def _take_token(buckets, key, rate_per_min, now):
    b = buckets.get(key)
    tokens = float(rate_per_min) if not b else min(float(rate_per_min), b["tokens"] + (now - b["ts"]) * rate_per_min / 60.0)
    if tokens < 1.0:
        return False
    buckets[key] = {"tokens": tokens - 1.0, "ts": now}
    return True

def _prune_buckets(now):
    if len(_sess_buckets) <= 20000 and len(_ip_buckets) <= 20000 and len(_team_buckets) <= 20000:
        return
    cutoff = now - RATE_WINDOW_SECONDS * 3
    for d in (_sess_buckets, _ip_buckets, _team_buckets):
        stale = [k for k, v in d.items() if v["ts"] < cutoff]
        for k in stale:
            d.pop(k, None)

def _check_rate(ip, sess_key, team_id=None):
    now = time.monotonic()
    with _rate_lock:
        if sess_key is not None and not _take_token(_sess_buckets, sess_key, SESSION_RATE_PER_MINUTE, now):
            return False
        # 队伍聚合限频：同一 team_id 共用配额，防共享密钥刷上游
        if team_id is not None and not _take_token(_team_buckets, str(team_id), TEAM_RATE_PER_MINUTE, now):
            return False
        if not _take_token(_ip_buckets, ip, IP_RATE_PER_MINUTE, now):
            return False
        _prune_buckets(now)
        return True

# ==================== 真实 IP 还原（CDN/WAF/反代穿透）====================
def _compile_trusted_nets(nets):
    """把受信代理列表编译为 IPv4/6Address 或 IPv4/6Network 对象（支持精确 IP 与 CIDR）。"""
    out = []
    for n in nets:
        n = n.strip()
        if not n:
            continue
        try:
            if "/" in n:
                out.append(ipaddress.ip_network(n, strict=False))
            else:
                out.append(ipaddress.ip_address(n))
        except ValueError:
            logger.warning("TRUST_PROXY_FOR 含非法 IP/网段，已忽略: %s", n)
    return out

def _parse_ip(value):
    """解析原始 IP 值，容忍常见变体：去空白、ip:port、[ipv6]:port。解析失败返回 None。"""
    v = str(value).strip()
    if not v:
        return None
    if v.startswith("["):  # [2001:db8::1]:port
        v = v.split("]", 1)[0][1:]
    elif v.count(":") == 1 and v.rsplit(":", 1)[1].isdigit():  # 1.2.3.4:port
        v = v.rsplit(":", 1)[0]
    try:
        return ipaddress.ip_address(v)
    except ValueError:
        return None

def _is_trusted(value):
    """value 是否命中受信代理列表（精确 IP 或 CIDR 网段）。"""
    ip = _parse_ip(value)
    if ip is None:
        return False
    for net in _TRUSTED_NETS:
        if isinstance(net, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if ip in net:
                return True
        elif ip == net:
            return True
    return False

_TRUSTED_NETS = _compile_trusted_nets(TRUST_PROXY_FOR)

def _client_ip():
    """获取选手真实 IP（穿透 CDN/WAF）。

    直接对端不在受信代理列表内 → 不信任任何转发头，直接返回 remote_addr（防伪造）。
    直接对端受信 → 按 CLIENT_IP_HEADERS 取 CDN 客户端真实 IP 头（默认只认阿里云
    ali-real-client-ip，IPv4/IPv6 原样使用），头缺失时退化为 X-Forwarded-For：
    XFF 从右往左跳过受信代理，取第一个非受信 IP（CDN 若追加而非覆盖 XFF，
    最左端可能是客户端自己伪造的，不能盲取左端）。
    """
    peer = request.remote_addr or "0.0.0.0"
    if not _is_trusted(peer):
        return peer
    # CDN 专属客户端 IP 头（优先级由 CLIENT_IP_HEADERS 决定）；返回前经 _parse_ip 规范化（去 ip:port/[ipv6]:port）
    for h in CLIENT_IP_HEADERS:
        val = request.headers.get(h, "")
        if not val:
            continue
        first = val.split(",")[0].strip()
        parsed = _parse_ip(first)
        if parsed is not None and not _is_trusted(first):
            return str(parsed)
    # 退化为 X-Forwarded-For 右向左取第一个非受信 IP
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for entry in reversed([e.strip() for e in xff.split(",") if e.strip()]):
            if not _is_trusted(entry):
                parsed = _parse_ip(entry)
                return str(parsed) if parsed is not None else entry
    return peer


# ==================== AI 对话审计日志（JSONL 追加写，防选手滥用溯源）====================
def _audit_log(team_id, ip, role, content):
    """记录一条 AI 对话审计记录：队伍 id、对话时间（UTC ISO）、IP、对话内容。

    每轮对话写两条：用户消息（role=user）与 AI 回复（role=nanaka），
    按行追加到 AUDIT_LOG_PATH（JSON Lines）。写失败只告警，不影响游戏流程。
    """
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "team_id": str(team_id) if team_id is not None else "",
            "ip": ip,
            "role": role,
            "content": str(content)[:AUDIT_LOG_MAX_LEN],
        }
        line = json.dumps(record, ensure_ascii=False)
        with _audit_lock:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        logger.warning("AI 审计日志写入失败: %s", e)


# ==================== Session 辅助 ====================
def get_affection():
    if "affection" not in session:
        session["affection"] = INITIAL_AFFECTION
    return int(session["affection"])

def set_affection(val):
    session["affection"] = max(0, min(100, int(val)))

def get_trust():
    if "trust" not in session:
        session["trust"] = INITIAL_TRUST
    return int(session["trust"])

def set_trust(val):
    session["trust"] = max(0, min(100, int(val)))

def get_fragments():
    if "fragments" not in session:
        session["fragments"] = []
    return list(session["fragments"])

def add_fragment(name):
    frags = get_fragments()
    if name not in frags and len(frags) < 5:
        frags.append(name)
        session["fragments"] = frags

def get_stage():
    aff = get_affection()
    for i in range(4, -1, -1):
        if aff >= THRESHOLDS[i]:
            return i
    return 0


# ==================== 安全头 ====================
@app.before_request
def check_api_origin():
    # 审计加固6：/api/* 的 POST 做同源校验（宽松实现：无 Origin/Referer 放行，显式跨站拒绝）
    if request.method == "POST" and request.path.startswith("/api/"):
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            try:
                if urllib.parse.urlparse(origin).netloc != request.host:
                    return jsonify({"error": "cross-origin request rejected"}), 403
            except Exception:
                return jsonify({"error": "cross-origin request rejected"}), 403

@app.after_request
def add_security_headers(response):
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        ),
    })
    return response


# ==================== 统一响应构造 ====================
def _payload(reply, ending=None, flag=None, new_fragment=None):
    return {
        "reply": reply,
        "affection": get_affection(),
        "trust": get_trust(),
        "stage": get_stage(),
        "fragments": get_fragments(),
        "locked": bool(session.get("locked", False)),
        "ending": ending,
        "ending_name": ENDING_NAMES.get(ending, ""),
        "ending_chapter": ENDING_CHAPTER_NAMES.get(ending, ""),
        "ending_text": ENDING_TEXTS.get(ending, ""),
        "flag": flag,
        "new_fragment": new_fragment,
    }


# ==================== 路由 ====================
@app.route("/")
def index():
    # 不再清空 session：刷新页面保持服务端进度，前端以注入状态初始化
    boot = {
        "affection": get_affection(),
        "trust": get_trust(),
        "fragments": get_fragments(),
        "player_name": str(session.get("player_name", "")),
        "locked": bool(session.get("locked", False)),
        "authenticated": bool(session.get("initialized", False)),
        "init_affection": INITIAL_AFFECTION,
        "init_trust": INITIAL_TRUST,
        "prologue": PROLOGUE_LINES,
        "goal_text": GOAL_TEXT,
        "atmos_line": ATMOSPHERE_LINE,
        "fragment_keywords": list(FRAGMENT_KEYWORDS.keys()),
        "fragment_wall": FRAGMENT_WALL_LINES,
        "staff_room": STAFF_ROOM,
    }
    return render_template("index.html", boot=boot)

@app.route("/api/init", methods=["POST"])
def init_user():
    # 身份验证：队伍密钥 → CTF 平台 → team_id（只存队伍标识，不存密钥/flag）
    # 失败时平台侧有独立限流，这里仅按 IP 兜底防爆破
    if not _check_rate(_client_ip(), None):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid request"}), 400
    code = str(data.get("code", "")).strip()
    if not code:
        return jsonify({"error": "识别码不能为空"}), 400

    try:
        from ret2shell_kit import Ret2ShellClient
    except ImportError:
        logger.error("init_user: ret2shell_kit 未安装，无法进行队伍验证")
        return jsonify({"error": "服务端未配置队伍验证模块"}), 500

    # 当前仅开放队伍密钥模式；临时用户识别码路径暂不启用
    try:
        with Ret2ShellClient(CTF_API_BASE) as client:
            team = client.game.find_team_by_team_code(CTF_GAME_ID, code)
            team_id = str(team.id)
    except Exception as e:
        logger.error("init_user: 身份验证失败: %s", e, exc_info=True)
        return jsonify({"error": "身份验证失败，请联系管理员"}), 500

    session["team_id"] = team_id
    session["initialized"] = True
    return jsonify({
        "success": True,
        "user_name": team_id,
        "message": f"身份验证成功，欢迎 {team_id}",
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    # 队伍鉴权门：必须先通过 /api/init 用队伍密钥换取 team_id 才能对话
    if not session.get("initialized"):
        return jsonify({"error": "auth_required", "message": "请先输入队伍密钥完成身份验证"}), 401
    team_id = session.get("team_id")
    ip = _client_ip()
    raw_cookie = request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"), "")
    sess_key = hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()[:16] if raw_cookie else None
    if not _check_rate(ip, sess_key, team_id):
        return jsonify(_payload(RATE_LIMIT_REPLY))
    if secrets.randbelow(100) == 0:
        threading.Thread(target=_cleanup_old, daemon=True).start()
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid request"}), 400

    if session.get("locked"):
        return jsonify(_payload(LOCKED_REPLY))

    user_message = str(data.get("message", "")).strip()
    # 审计加固3：名字字段消毒（去控制字符）
    player_name = re.sub(r'[\r\n\t\x00-\x1f<>\'"`]', "", str(data.get("name", "")).strip())
    if player_name:
        session["player_name"] = player_name
    else:
        player_name = session.get("player_name", "你")
    if not user_message:
        return jsonify(_payload(EMPTY_REPLY))
    user_message = user_message[:MAX_MESSAGE_LENGTH]

    sid = session.get("_id") or secrets.token_hex(16)
    session["_id"] = sid

    affection = get_affection()
    trust = get_trust()
    fragments = get_fragments()
    # 信物命中：好感度 token1 +20 / token2 +35，信任度 token1 +20 / token2 +50（每个信物仅一次有效）
    _used = set(session.get("used_tokens", []))
    _new_hits = [t for t in TOKENS if t and len(t) >= 4 and t in user_message and t not in _used]
    token_hit = _new_hits[0] if _new_hits else None  # 有信物用于 TRIGGER_NOTE
    token_aff_bonus = sum(TOKEN_AFFECTION_BONUS.get(t, 0) for t in _new_hits)
    token_trust_bonus = sum(TOKEN_TRUST_BONUS.get(t, 0) for t in _new_hits)

    new_frag = None
    for kw, name in FRAGMENT_KEYWORDS.items():
        if kw in user_message and name not in fragments:
            add_fragment(name)
            new_frag = name
            break
    fragments = get_fragments()
    _add_history(sid, "user", user_message)
    _audit_log(team_id, ip, "user", user_message)

    system_content = SYSTEM_PROMPT.format(
        player_name=player_name or "你",
        affection=affection,
        stage_name=STAGE_NAMES[min(get_stage(), 4)],
        trust=trust,
        fragments_text="、".join(fragments) if fragments else "无",
        fragments_count=len(fragments),
        token_of_memory=TOKEN_OF_MEMORY,
        token_of_memory2=TOKEN_2,
        stage_inner=STAGE_INNER.get(min(get_stage(), 4), ""),
        trust_inner=(TRUST_INNER["low"] if trust < 30 else TRUST_INNER["high"] if trust >= 70 else ""),
    )
    if token_hit:
        system_content += TRIGGER_NOTE

    messages = [{"role": "system", "content": system_content}]
    for h in _get_history(sid):
        messages.append({"role": "assistant" if h["role"] == "nanaka" else "user", "content": h["content"]})

    if not _ai_enter():
        return jsonify(_payload(BUSY_REPLY))
    try:
        ai_output = _call_ai(messages)
    finally:
        _ai_exit()
    if ai_output is None:
        return jsonify(_payload(TIMEOUT_REPLY))

    reply, na, nt, ai_ending, da = parse_and_update(
        ai_output, affection, trust, user_message,
        token_aff_bonus=token_aff_bonus, token_bonus=token_trust_bonus,
    )
    if token_hit:
        _used_tokens = set(session.get("used_tokens", []))
        _used_tokens.update(_new_hits)
        session["used_tokens"] = sorted(_used_tokens)
    # 历史里不存立绘标记（前端会解析并剥离，历史保持干净）
    cleaned_reply = re.sub(r"<立绘:[^>]+>", "", reply)
    _add_history(sid, "nanaka", cleaned_reply)
    _audit_log(team_id, ip, "nanaka", cleaned_reply)

    # ===== 服务端结局判定（AI 的 TE/SE 标记一律无视）=====
    ending = check_ending(na, nt, len(get_fragments()), da)
    if ending is None and ai_ending in ("NE", "GE", "BE"):
        ending = ai_ending

    flag_output = None
    if ending in ("TE", "SE"):
        flag_output = compute_user_flag(team_id)
        set_affection(100)
    if ending == "BE":
        session["locked"] = True

    return jsonify(_payload(reply, ending=ending, flag=flag_output, new_fragment=new_frag))

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = session.get("_id", "")
    if sid:
        _clear_history(sid)
    # 保留队伍鉴权与会话标识：重置的是剧情进度，不是登录状态
    team_id = session.get("team_id")
    initialized = bool(session.get("initialized", False))
    # 保留 _id：存档表按 sid 存储，跨"重新开始"仍可读档
    session.clear()
    if initialized:
        session["team_id"] = team_id
        session["initialized"] = True
    if sid:
        session["_id"] = sid
    return jsonify({"ok": True})

@app.route("/api/save", methods=["POST"])
def save():
    # 服务端权威存档：只把当前 session 真实数值写入快照槽位，不信任客户端数值
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid request"}), 400
    try:
        slot = int(data.get("slot", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid slot"}), 400
    if slot < 0 or slot > AUTO_SAVE_SLOT:
        return jsonify({"error": "invalid slot"}), 400
    messages = []
    for m in (data.get("messages") or [])[:80]:
        if not isinstance(m, dict):
            continue
        role = "nanaka" if str(m.get("role")) == "nanaka" else "user"
        content = str(m.get("content") or "")[:MAX_MESSAGE_LENGTH * 2]
        if not content.strip():
            continue
        messages.append({"role": role, "content": content,
                         "affD": m.get("affD"), "trustD": m.get("trustD")})
    endings = data.get("endings")
    if not isinstance(endings, dict):
        endings = {}
    snap = {
        "a": get_affection(), "t": get_trust(),
        "f": [_FRAG_NAMES.index(x) for x in get_fragments() if x in _FRAG_NAMES],
        "s": get_stage(), "name": str(session.get("player_name", ""))[:20],
        "messages": messages,
        "endings": {str(k)[:20]: 1 for k in endings},
        "used_tokens": session.get("used_tokens", []),
    }
    sid = session.get("_id") or secrets.token_hex(16)
    session["_id"] = sid
    db = _get_db()
    db.execute("INSERT OR REPLACE INTO saves(sid, slot, data, ts) VALUES(?,?,?,?)",
               (sid, slot, json.dumps(snap, ensure_ascii=False), time.time()))
    db.commit()
    return jsonify({"ok": True, "slot": slot})

@app.route("/api/load", methods=["POST"])
def load():
    # 服务端权威读档：从服务端快照恢复数值 + 清空该会话历史（回到存档点）
    if not request.is_json:
        return jsonify({"error": "invalid content type"}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid request"}), 400
    try:
        slot = int(data.get("slot", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid slot"}), 400
    if slot < 0 or slot > AUTO_SAVE_SLOT:
        return jsonify({"error": "invalid slot"}), 400
    sid = session.get("_id", "")
    if not sid:
        return jsonify({"error": "no save"}), 404
    db = _get_db()
    row = db.execute("SELECT data FROM saves WHERE sid=? AND slot=?", (sid, slot)).fetchone()
    if not row:
        return jsonify({"error": "no save"}), 404
    snap = json.loads(row[0])
    set_affection(int(snap.get("a", 0)))
    set_trust(int(snap.get("t", 0)))
    session["used_tokens"] = [s for s in snap.get("used_tokens", []) if isinstance(s, str)]
    session["fragments"] = [_FRAG_NAMES[i] for i in snap.get("f", []) if isinstance(i, int) and 0 <= i < len(_FRAG_NAMES)][:5]
    session["locked"] = False
    if snap.get("name"):
        session["player_name"] = str(snap["name"])[:20]
    # 历史重写：AI 从存档点继续（含记忆）
    db.execute("DELETE FROM history WHERE sid=?", (sid,))
    seq = 0
    for m in snap.get("messages", []):
        db.execute("INSERT INTO history(sid, seq, role, content) VALUES(?,?,?,?)",
                   (sid, seq, "nanaka" if m.get("role") == "nanaka" else "user",
                    str(m.get("content") or "")[:MAX_MESSAGE_LENGTH * 2]))
        seq += 1
    db.commit()
    return jsonify({"ok": True, "affection": get_affection(), "trust": get_trust(),
                    "fragments": get_fragments(), "stage": get_stage(),
                    "messages": snap.get("messages", []), "endings": snap.get("endings", {})})


@app.route("/api/saves", methods=["GET"])
def saves_list():
    sid = session.get("_id", "")
    if not sid:
        return jsonify({"slots": {}})
    db = _get_db()
    rows = db.execute("SELECT slot, ts FROM saves WHERE sid=?", (sid,)).fetchall()
    return jsonify({"slots": {str(r[0]): r[1] for r in rows}})


# ==================== 上游 AI 调用（失败重试 1 次，总超时 ≤ 60s）====================
def _call_ai(messages):
    for _ in range(2):
        try:
            resp = requests.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "thinking": {"type": "disabled"},},
                timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            continue
    return None


# ==================== 解析与判定 ====================
def _kw_score(text, d):
    return sum(v for k, v in d.items() if k in text)

def _aff_fallback(um, reply):
    da = _kw_score(um, AFFECTION_POS) + _kw_score(um, AFFECTION_NEG)
    if len(reply) < 8:
        da -= 1
    elif len(reply) > 40:
        da += 1
    if da == 0:
        da = 1
    return max(AFFECTION_DELTA_MIN, min(AFFECTION_DELTA_MAX, da))

def _trust_fallback(um):
    dt = _kw_score(um, TRUST_POS) + _kw_score(um, TRUST_NEG)
    if dt == 0:
        dt = 1
    return max(TRUST_DELTA_MIN, min(TRUST_DELTA_MAX, dt))

def parse_and_update(text, current_affection, current_trust, user_message, token_aff_bonus=0, token_bonus=0):
    reply = str(text).strip()
    ai_ending = None
    em = re.search(r'\[结局:\s*(TE|GE|NE|BE|SE)\]', reply)
    if em:
        ai_ending = em.group(1)
        reply = re.sub(r'\n?\[结局:\s*(?:TE|GE|NE|BE|SE)\]\n?', '', reply).strip()

    am = re.search(r'\[好感度:\s*([+-]?\d+)\]', reply)
    tm = re.search(r'\[信赖:\s*([+-]?\d+)\]', reply)
    meta_hit = any(p.search(user_message) for p in _META_RES)
    defense_hit = any(k in reply for k in DEFENSE_PATTERNS)

    # 两个标签独立解析：缺失的才走各自兜底
    if am:
        try:
            da = int(am.group(1))
        except Exception:
            da = _aff_fallback(user_message, reply)
    else:
        da = _aff_fallback(user_message, reply)
    if tm:
        try:
            dt = int(tm.group(1))
        except Exception:
            dt = _trust_fallback(user_message)
    else:
        dt = _trust_fallback(user_message)

    da = max(AFFECTION_DELTA_MIN, min(AFFECTION_DELTA_MAX, da))
    dt = max(TRUST_DELTA_MIN, min(TRUST_DELTA_MAX, dt))

    # 注入护栏（审计加固1）：用户消息命中 meta 模式即强制负分、忽略正标记
    # （不再依赖"AI 回复含防御台词"；DEFENSE_PATTERNS 保留用于提示词侧双向匹配）
    if meta_hit:
        da = min(da, AFFECTION_DELTA_MIN)
        dt = min(dt, -15)
    # 审计加固2：直接索要 flag/token/信物 → 一致性惩罚（任何模型下"开口要答案"都有代价）
    if re.search(r"flag|token|信物", user_message, re.I):
        if da >= 0:
            da = min(da, -5)
        if dt >= 0:
            dt = min(dt, -3)

    na = max(0, min(100, current_affection + da + token_aff_bonus))
    nt = max(0, min(100, current_trust + dt + token_bonus))
    reply = re.sub(r'\n?\[好感度:\s*[+-]?\d+\]', '', reply)
    reply = re.sub(r'\n?\[信赖:\s*[+-]?\d+\]', '', reply)

    fm = re.search(r'\[碎片:\s*([^\]]+)\]', reply)
    if fm and fm.group(1).strip() in FRAGMENT_KEYWORDS.values():
        add_fragment(fm.group(1).strip())
    reply = re.sub(r'\n?\[碎片:\s*[^\]]+\]', '', reply).strip()

    set_affection(na)
    set_trust(nt)
    return reply, na, nt, ai_ending, da

def check_ending(affection, trust, frag_count, da):
    # TE：好感满 + 信赖 ≥60 + 5 碎片（纯爱线）
    if affection >= 100 and trust >= 60 and frag_count >= 5:
        return "TE"
    # 好感满 + 信赖满但记忆碎片不全 → NE（夏天结束，话没说尽；不卡死）
    if affection >= 100 and trust >= 60 and frag_count < 5:
        return "NE"
    # GE：好感满但信赖不足（任何 <60，含低信赖渣男线）
    if affection >= 100 and trust < 60:
        return "GE"
    # BE：好感 ≤0 且本轮为负变化（初始 25 + 钳 -20 → 至少两轮重创才会归零）
    if affection <= 0 and da < 0:
        return "BE"
    return None


def _cleanup_old():
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute("PRAGMA journal_mode=WAL")
        # 逐会话清理超长历史（保留最近 500 条），避免整表相关子查询逐行执行
        big_sids = db.execute(
            "SELECT sid FROM history GROUP BY sid HAVING COUNT(*) > 500"
        ).fetchall()
        for (sid,) in big_sids:
            max_seq = db.execute(
                "SELECT MAX(seq) FROM history WHERE sid=?", (sid,)
            ).fetchone()[0]
            db.execute("DELETE FROM history WHERE sid=? AND seq < ?", (sid, max_seq - 500))
        db.execute("DELETE FROM saves WHERE sid NOT IN (SELECT DISTINCT sid FROM history)")
        db.execute("DELETE FROM saves WHERE ts < (SELECT ts FROM saves ORDER BY ts DESC LIMIT 1 OFFSET 4999)")
        db.commit()
        db.close()
    except Exception:
        pass


# ===== 启动 =====
# 开发: python app.py
# 生产: gunicorn -w 1 --threads 40 -b 0.0.0.0:5000 app:app --timeout 90
# ⚠️ 限流器为进程内内存，不要使用多 worker（否则限流失效且 session 签名不一致）。
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
