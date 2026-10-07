const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let state = null;
let timerInterval = null;
let countdownInterval = null;
// 客户端锚点：每次收到状态时把 next_game_in_ms 换算成本地开始时间，
// 供 500ms 的 tick 平滑递减，避免倒计时只在状态推送（几秒一次）时跳变。
let nextGameAt = 0;

// 双道具：当前选中的参与道具 key（房间变化 / 进入结算时重置）
let selectedItem = null;
let lastRoomSig = "";

// 当前登录玩家是否拥有「更多选择」（可同时参与两个道具的竞争）
function hasExtraChoice() {
  const pid = myPlayerId();
  const me = (state.participants || []).find((p) => p.id === pid);
  return !!(me && me.items && me.items.includes("extra_choice"));
}

// WebSocket：实时推送状态 + 出价；断线后指数退避重连
let ws = null;
let wsGen = 0;             // 代际计数器：防止旧 socket 的迟到消息覆盖新状态
let wsReady = false;       // WS 是否已连接（断线时退化为 HTTP 兜底轮询）
let wsReconnectDelay = 1000;

function getPlayerId() {
  return localStorage.getItem("tboi_player_id") || "";
}

function setPlayerId(id) {
  localStorage.setItem("tboi_player_id", id);
}

// 当前会话的身份 id：优先 session 推导的 me.player_id，回退 localStorage
function myPlayerId() {
  return (state && state.me && state.me.player_id) || getPlayerId();
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

// ---------- 渲染 ----------

function render() {
  if (!state) return;
  const status = state.status;
  const waiting = $("#waiting");
  const playing = $("#playing");
  waiting.classList.toggle("hidden", status === "playing");
  playing.classList.toggle("hidden", status !== "playing");
  if (status === "playing") {
    renderPlaying();
  } else {
    renderWaiting();
  }
  renderRank();
  renderLeaderboard();
  renderFreeze();
  renderHistory();
  renderAuth();
  renderAntiCheat();
  updateCountdowns();
  // 背景音乐：仅在用户输入临时识别码并加入（state.me 存在）后才播放；
  // 未登录只浏览不发声。对局中播 begin，等待大厅（lobby / finished）播 waiting。
  ensureMusic(state.me ? (status === "playing" ? "begin" : "waiting") : null);
}

// ---------- 背景音乐 ----------
// 等待大厅（lobby / finished）播放 waiting.m4a，对局中播放 begin.m4a，循环播放。
// 一局结束后切回等待大厅会自然切回等待音乐。浏览器自动播放策略要求先有用户
// 交互才能带声音播放，因此首次点击 / 按键时解锁并重试。
const BG_MUSIC = {
  waiting: "/static/assets/waiting.m4a",
  begin: "/static/assets/begin.m4a",
};
let musicKind = "";          // 当前目标音乐："" | "waiting" | "begin"

function ensureMusic(kind) {
  if (kind === musicKind) return;
  musicKind = kind;
  const el = $("#bg-music");
  if (!el) return;
  if (!kind) {
    el.pause();
    el.currentTime = 0;
    return;
  }
  el.src = BG_MUSIC[kind];
  el.loop = true;
  el.play().catch(() => {});   // 未解锁前静默失败，每次交互时重试
}

// 浏览器自动播放策略要求用户交互后才能带声音播放；每次交互都尝试补播，
// 直到真正播出声（el.paused 为假则跳过，避免重复 play）。
function unlockAudio() {
  const el = $("#bg-music");
  if (el && musicKind && el.paused) el.play().catch(() => {});
}
document.addEventListener("pointerdown", unlockAudio);
document.addEventListener("keydown", unlockAudio);
document.addEventListener("touchstart", unlockAudio);

// ---------- 反作弊：人类活动信号 + 人机验证 + 禁赛 ----------
// 浏览器把鼠标 / 键盘 / 触摸行为节流上报给服务端（2s 一次），行为分析据此区分
// 真人玩家与「直连出价 / 脚本出价」的机器：后者不会产生这些信号。
let lastActivitySent = 0;
function reportActivity() {
  const now = Date.now();
  if (now - lastActivitySent < 2000) return;
  lastActivitySent = now;
  if (wsReady && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "activity" }));
  }
}
document.addEventListener("pointerdown", reportActivity);
document.addEventListener("keydown", reportActivity);
document.addEventListener("touchstart", reportActivity);

let captchaTimer = null;
let captchaSelected = -1;   // 单选当前选中的选项下标 0~5，-1 = 未选

function fmtDate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function renderAntiCheat() {
  const me = state && state.me;
  const overlay = $("#captcha-overlay");
  const banner = $("#ban-banner");
  if (!overlay || !banner) return;

  // 禁赛提示：只对本人展示
  if (me && me.banned_until) {
    banner.classList.remove("hidden");
    banner.textContent = `🚫 您因可疑行为已被禁赛 1 天，解禁时间：${fmtDate(new Date(me.banned_until))}。期间无法加入对局或出价。如有疑问请联系管理员。`;
  } else {
    banner.classList.add("hidden");
  }

  // 人机验证弹窗：15 秒倒计时 + 剩余次数 + 图片验证码单选
  const cap = me && me.captcha;
  if (cap) {
    overlay.classList.remove("hidden");
    $("#captcha-status").textContent = `剩余 ${cap.attempts_left} 次机会`;
    renderCaptchaOptions(cap);
    startCaptchaCountdown(cap.deadline);
  } else {
    overlay.classList.add("hidden");
    overlay.dataset.cid = "";
    captchaSelected = -1;
    stopCaptchaCountdown();
  }
}

// 单选：选中第 i 个选项（0~5），高亮并记录下标，供 submitCaptcha 提交。
function selectCaptchaOption(i) {
  captchaSelected = i;
  $$("#captcha-options .captcha-option").forEach((el, k) => {
    el.classList.toggle("selected", k === i);
  });
}

// 渲染验证码图片 + 6 个候选文本选项。只在题目（cid）变化时重建，
// 保留跨状态推送的选中态。
function renderCaptchaOptions(cap) {
  const wrap = $("#captcha-options");
  const img = $("#captcha-image");
  if (!wrap) return;
  if (wrap.dataset.cid === cap.id) return;
  wrap.dataset.cid = cap.id;
  captchaSelected = -1;
  if (img && cap.image) img.src = cap.image;   // base64 data URI，无需额外请求
  wrap.innerHTML = "";
  (cap.options || []).forEach((t, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "captcha-option";
    b.textContent = t;
    b.addEventListener("click", () => selectCaptchaOption(i));
    wrap.appendChild(b);
  });
}

function startCaptchaCountdown(deadline) {
  if (captchaTimer) clearInterval(captchaTimer);
  const el = $("#captcha-countdown");
  const tick = () => {
    const left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
    el.textContent = left;
    if (left <= 0 && captchaTimer) {
      clearInterval(captchaTimer);
      captchaTimer = null;
    }
  };
  tick();
  captchaTimer = setInterval(tick, 250);
}

function stopCaptchaCountdown() {
  if (captchaTimer) {
    clearInterval(captchaTimer);
    captchaTimer = null;
  }
}

// 提交验证码答案：优先 WebSocket，WS 不可用时走 HTTP 兜底
async function submitCaptcha() {
  const cap = state && state.me && state.me.captcha;
  const statusEl = $("#captcha-status");
  if (!cap) return;
  if (captchaSelected < 0) {
    statusEl.textContent = "请从 6 个选项中选出与图片文字一致的答案。";
    return;
  }
  const answer = (cap.options || [])[captchaSelected];   // 提交候选文本，而非下标
  if (wsReady && ws) {
    ws.send(JSON.stringify({ type: "captcha_answer", id: cap.id, answer }));
    statusEl.textContent = "正在验证...";
    return;
  }
  try {
    const r = await api("/api/captcha", {
      method: "POST",
      body: JSON.stringify({ id: cap.id, answer }),
    });
    statusEl.textContent = r.message || "验证通过，可以继续出价。";
  } catch (e) {
    statusEl.textContent = e.message || "验证失败";
    await refresh();
  }
}

// 登录状态条 + 加入按钮 + 动态 FLAG 展示（只展示本人身份与本人 FLAG）
// 三态：
//   未登录             -> 显示识别码输入 + 「验证并加入」
//   已登录但不在本局     -> 显示「加入对局」按钮（重新加入）
//   已登录且在本局       -> 隐藏整行
function renderAuth() {
  const me = state.me;
  const pid = (me && me.player_id) || getPlayerId();
  const mePlayer = (state.players || []).find((p) => p.id === pid);
  const inPlayers = !!mePlayer;
  const finished = state.status === "finished";
  const statusEl = $("#auth-status");
  if (statusEl) {
    if (!me) {
      statusEl.textContent = "未登录 · 请输入临时用户识别码验证后加入";
    } else if (finished) {
      statusEl.textContent = mePlayer && mePlayer.ready
        ? `已就绪：${me.name}（用户 ${me.platform_id}）· 等待下一局自动开始`
        : `本局已结束：${me.name}（用户 ${me.platform_id}）· 点击「继续下一局」进入下一局`;
    } else {
      statusEl.textContent = `已登录：${me.name}（用户 ${me.platform_id}）${inPlayers ? "" : " · 尚未加入当前对局"}`;
    }
  }
  const needAuth = !me;
  const needRejoin = me && (finished ? !mePlayer || !mePlayer.ready : !inPlayers);
  const authRow = $("#auth-row");
  if (authRow) authRow.classList.toggle("hidden", !(needAuth || needRejoin));
  const loginEl = $("#auth-login");
  if (loginEl) loginEl.classList.toggle("hidden", !needAuth);
  const rejoinBtn = $("#rejoin-btn");
  if (rejoinBtn) {
    rejoinBtn.classList.toggle("hidden", !needRejoin);
    rejoinBtn.textContent = finished ? "继续下一局" : "加入对局";
  }

  const flagBox = $("#flag-box");
  if (flagBox) {
    if (state.my_flag) {
      $("#flag-value").textContent = state.my_flag;
      flagBox.classList.remove("hidden");
    } else {
      flagBox.classList.add("hidden");
    }
  }
}

function renderWaiting() {
  const isFinished = state.status === "finished";

  $("#waiting-title").textContent = isFinished ? "上一局已结束" : "等待大厅";
  const banner = $("#waiting-banner");
  banner.classList.toggle("hidden", !isFinished);
  banner.textContent = isFinished
    ? "本局已结束。点击上方「继续下一局」进入下一局；不点击则自动退出，由机器人补位。"
    : "等待下一局自动开始。";

  const humans = (state.players || []).filter((p) => !p.is_bot);
  const bots = (state.participants || []).filter((p) => p.is_bot);
  const target = state.target_players || 20;
  const fill = Math.max(0, target - humans.length);
  const nextGame = (state.game_number || 0) + 1;
  const readyCount = humans.filter((p) => p.ready !== false).length;
  $("#waiting-note").textContent = isFinished
    ? `下一局：第 ${nextGame} 局 · ${readyCount}/${humans.length} 位玩家选择继续 · 开局不足 ${target} 人时自动补足机器人（还差 ${fill} 个）`
    : `下一局：第 ${nextGame} 局 · 已等待 ${humans.length} 位玩家 · 开局不足 ${target} 人时自动补足机器人（还差 ${fill} 个）`;

  const list = $("#player-list");
  list.innerHTML = "";
  humans.forEach((p) => {
    const chip = document.createElement("span");
    chip.className = "player-chip";
    const waiting = isFinished ? p.ready === false : !p.in_game;
    chip.textContent = charTag(p) + p.name + (waiting ? " ⏳" : "");
    list.appendChild(chip);
  });
  bots.forEach((p) => {
    const chip = document.createElement("span");
    chip.className = "player-chip";
    chip.textContent = charTag(p) + p.name + " 🤖";
    list.appendChild(chip);
  });

  renderCharacters();
}

// 等待大厅的角色选择：本人已在局内（含等待队列）时可选择，开局前可随时修改
function renderCharacters() {
  const box = $("#character-box");
  const me = state.me;
  const pid = myPlayerId();
  const mePlayer = (state.players || []).find((p) => p.id === pid);
  const show = !!(me && mePlayer);
  box.classList.toggle("hidden", !show);
  if (!show) return;
  const current = mePlayer.character || null;
  const cards = (state.characters || [])
    .map((c) => {
      const sel = c.key === current ? " selected" : "";
      return `
        <div class="character-card${sel}" data-character="${c.key}">
          <div class="character-icon">${charIcon(c.key)}</div>
          <h4>${escapeHtml(c.name)}</h4>
          <div class="desc">初始携带 ${escapeHtml(c.item_name)}</div>
        </div>`;
    })
    .join("");
  $("#character-cards").innerHTML = cards;
}

function renderPlaying() {
  const room = state.room;
  const me = state.players.find((p) => p.id === myPlayerId());
  const inGame = me ? me.in_game : false;
  const waitingBanner = $("#midgame-banner");

  // 对局进行中加入的玩家：排队等下一局
  if (me && !inGame) {
    waitingBanner.classList.remove("hidden");
    $("#spectator-box").classList.add("hidden");
    $("#bid-box").classList.add("hidden");
    $("#result-box").classList.add("hidden");
    $("#location").textContent = "等待下一局…";
    $("#funds").textContent = "";
    return;
  }
  waitingBanner.classList.add("hidden");

  if (!room) return;
  const funds = me ? me.level_funds : 0;

  // 房间 / 阶段切换时清空选中状态与输入框
  const sig = `${room.level}:${room.room_number}:${room.phase}`;
  if (sig !== lastRoomSig) {
    lastRoomSig = sig;
    selectedItem = null;
    $("#bid-input").value = "";
  }

  $("#location").textContent =
    `${roomIcon(room.room_type)} Level ${room.level} / Room ${room.room_number} · ${roomTypeName(room.room_type)}`;
  $("#funds").textContent = `资金：${funds}`;

  const mods = room.modifiers || [];
  let modHtml = "";
  mods.forEach((m) => {
    modHtml += `<span class="modifier">${modifierName(m)}</span>`;
  });
  const modsEl = $("#room-mods");
  // 无特殊规则时显示实际房间类型，与位置栏（roomTypeName）保持一致，避免「普通房间」与
  // 特殊 / 宝物 / Boss 等类型互相冲突。
  if (modsEl) modsEl.innerHTML = modHtml || `<span class="modifier">${roomTypeName(room.room_type)}</span>`;

  // 双道具：每侧一张卡片，点击选中参与的道具；已有出价的侧高亮显示
  const items = room.items || [];
  const myBids = room.my_bids || {};
  const hasExtra = hasExtraChoice();
  const cards = items
    .map((it) => {
      const rarity = it.rarity || ITEM_RARITY[it.key] || "common";
      const myBid = myBids[it.key];
      const selected = selectedItem === it.key;
      const cls = ["item-card", "rarity-" + rarity, selected ? "selected" : ""].join(" ");
      const note = myBid != null
        ? `<div class="my-bid">你已出价 ${myBid}</div>`
        : (hasExtra ? `<div class="my-bid hint">更多选择：可同时参与两侧</div>` : "");
      return `
        <div class="${cls}" data-item="${it.key}">
          <span class="rarity-badge rarity-badge-${rarity}">${rarityName(rarity)}</span>
          <div class="item-icon">${itemIcon(it.key)}</div>
          <h3>${escapeHtml(it.name)}</h3>
          <div class="desc">${escapeHtml(it.desc)}</div>
          ${note}
        </div>`;
    })
    .join("");
  $("#item-cards").innerHTML = cards;

  const bidInput = $("#bid-input");
  bidInput.min = 1;
  bidInput.max = room.range_max;
  bidInput.placeholder = `1 ~ ${room.range_max}`;

  // 反转目标房间：出价阶段就提示玩家，避免“一律追低”踩坑。
  // 镜像基准 = min(出价上限, 本层资金)：第 2 层预算 500，目标最高只能到 500（可达）。
  const mirrorBase = Math.min(room.range_max, room.budget || room.range_max);
  const hint = $("#room-rule-hint");
  if (hint) {
    if (mods.includes("reverse")) {
      hint.classList.remove("hidden");
      hint.innerHTML = `⚠️ <b>反转目标</b>：目标 ≈ ${mirrorBase} − (2/3×平均出价 + C)，平均出价越低目标越高。别一律追低！`;
    } else {
      hint.classList.add("hidden");
    }
  }

  const canBid = room.phase === "bidding" && me && funds > 0;
  const noMe = !me;
  $("#spectator-box").classList.toggle("hidden", (canBid || room.phase !== "bidding") && !noMe);
  $("#bid-box").classList.toggle("hidden", !canBid || noMe);
  $("#result-box").classList.toggle("hidden", room.phase !== "result");

  const specText = $("#spectator-box h3");
  const specDesc = $("#spectator-box p");
  if (noMe) {
    if (specText) specText.textContent = "你还没有加入";
    if (specDesc) specDesc.textContent = "请在上方输入临时用户识别码验证后加入，下一局会自动开始。";
  } else if (funds <= 0) {
    if (specText) specText.textContent = "观战中";
    if (specDesc) specDesc.textContent = "资金不足，本房间只能观望。";
  }

  if (room.phase === "bidding") {
    const bids = room.my_bids || {};
    const bidKeys = items.filter((it) => bids[it.key] != null);
    if (bidKeys.length === 0) {
      $("#bid-status").textContent = selectedItem
        ? `已选中「${itemName(selectedItem)}」，请输入出价并提交。`
        : "请点击选择要参与的道具。";
    } else if (bidKeys.length === 1) {
      const k = bidKeys[0].key;
      $("#bid-status").textContent = `你已出价 ${bids[k]}（${itemName(k)}），可修改出价，或点击另一张卡片换选（原出价会被撤掉）。`;
    } else {
      $("#bid-status").textContent =
        `你已对两个道具各出价：${bidKeys.map((it) => `${bids[it.key]}（${itemName(it.key)}）`).join("、")}，可以修改。`;
    }
  }

  if (room.phase === "result" && room.result) {
    renderResult(room.result, room);
  }

  updateTimer(room);
}

function updateTimer(room) {
  if (timerInterval) clearInterval(timerInterval);
  const timerEl = $("#timer");
  const tick = () => {
    if (!room) return;
    if (room.phase === "bidding") {
      const left = Math.max(0, Math.floor((room.deadline - Date.now()) / 1000));
      timerEl.textContent = `出价剩余：${left}s`;
    } else if (room.phase === "result") {
      const left = room.result_end ? Math.max(0, Math.floor((room.result_end - Date.now()) / 1000)) : 0;
      timerEl.textContent = `结果展示：${left}s`;
    }
  };
  tick();
  timerInterval = setInterval(tick, 500);
}

// 下一局倒计时（等待大厅 + 对局中等待的玩家横幅）
function updateCountdowns() {
  if (!state) return;
  // 基于本地锚点平滑递减，而不是每次都用上一次轮询（2 秒）的服务器快照
  const remaining = Math.max(0, nextGameAt - Date.now());
  const text = fmtMs(remaining);
  const el = $("#waiting-countdown");
  if (el) el.textContent = `下一局开始：${text}`;
  const mb = $("#midgame-banner");
  if (mb && state.status === "playing") {
    const me = state.players.find((p) => p.id === myPlayerId());
    if (me && !me.in_game) {
      mb.classList.remove("hidden");
      mb.textContent = `你已进入等待队列，下一局开始：${text}`;
    } else {
      mb.classList.add("hidden");
    }
  }
}

function fmtMs(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function renderResult(result, room) {
  const box = $("#result-box");
  const sides = result && result.sides;
  if (!result || !sides || !sides.length) {
    box.innerHTML = "<p>本房间无人出价。</p>";
    return;
  }
  // 反转目标房间：目标值已被镜像翻转，标注出来避免误读
  const reverse = room && room.modifiers && room.modifiers.includes("reverse");

  const sideHtml = sides
    .map((side) => {
      const entries = side.entries || [];
      const rows = entries
        .slice()
        .sort((a, b) => b.effective_bid - a.effective_bid)
        .map((e) => {
          const bidText = e.hidden ? "???" : e.bid;
          const cls = e.player_id === side.winner_id ? "winner-row" : "";
          return `<tr class="${cls}">
            <td>${escapeHtml(e.player_name)}</td>
            <td>${bidText}</td>
            <td>${e.effective_bid}</td>
            <td>${e.score}</td>
            <td>${e.paid}</td>
          </tr>`;
        })
        .join("");
      return `
        <div class="side-result">
          <h4>${itemIcon(side.item)} ${escapeHtml(side.item_name || itemName(side.item))}</h4>
          <p>平均出价：${side.avg} · 目标值：${side.target}${reverse ? "（反转目标）" : ""} · 赢家：${escapeHtml(side.winner_name || "无")}</p>
          <table class="result-table">
            <thead>
              <tr><th>玩家</th><th>出价</th><th>有效出价</th><th>得分</th><th>支付</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    })
    .join("");

  // 『更多选择』双参玩家：本局得分 = (s1 + s2) × 0.75
  const combined = result.combined || {};
  const combinedHtml = Object.entries(combined)
    .map(([pid, c]) => {
      const name = entryName(pid, sides);
      return `<p class="combined-note">${escapeHtml(name)} 本局得分 = ${c.s1} + ${c.s2} = <b>${c.final}</b>（更多选择 × 0.75）</p>`;
    })
    .join("");

  box.innerHTML = `
    <h3>本房间结果</h3>
    ${sideHtml}
    ${combinedHtml ? `<div class="combined-box"><h4>『更多选择』双参结算</h4>${combinedHtml}</div>` : ""}
  `;
}

// 由出价记录反查玩家名（combined 只有 pid，名字从两侧 entries 里找）
function entryName(pid, sides) {
  for (const s of sides) {
    for (const e of s.entries || []) {
      if (e.player_id === pid) return e.player_name;
    }
  }
  return pid;
}

function renderRank() {
  const tbody = $("#rank-body");
  if (!state) return;

  const note = $("#rank-note");
  if (note) {
    const frozen = freezeNote();
    note.textContent =
      (frozen ? `${frozen} ` : "") +
      `全局场均 ${state.global_avg} 分 · 生涯分采用「定三取五」（至少 ${state.min_games_for_rank} 局上榜，取最好 ${state.best_n_games} 场均分），对局中按本局总分排序`;
  }

  const playing = state.status === "playing";
  const meId = myPlayerId();
  let list;
  if (playing) {
    // 本局参与者（人类 + 机器人）按本局总分排，等待中的玩家排后面
    const parts = (state.participants || []).slice();
    const waiting = (state.players || []).filter((p) => p.in_game === false);
    list = parts.concat(waiting).sort((a, b) => b.total_score - a.total_score);
  } else {
    // 达标（>= 门槛局数）玩家按生涯分排前，未达标排后
    list = (state.players || []).slice().sort((a, b) => {
      if (!!a.eligible !== !!b.eligible) return a.eligible ? -1 : 1;
      return (b.career ?? -Infinity) - (a.career ?? -Infinity);
    });
  }

  tbody.innerHTML = list
    .map((p, i) => {
      const itemNames = (p.items || []).map((k) => itemIcon(k) + " " + itemName(k)).join("、") || "无";
      const flag = p.in_game === false ? " ⏳" : "";
      const career = p.eligible && p.career != null ? p.career : "-";
      const games = p.games_played != null ? p.games_played : "-";
      const avg = p.avg != null ? p.avg : "-";
      const mine = p.id === meId ? ' class="me-row"' : "";
      return `<tr${mine}>
        <td>${i + 1}</td>
        <td>${charTag(p)}${escapeHtml(p.name)}${flag}${p.is_bot ? " 🤖" : ""}</td>
        <td>${career}</td>
        <td>${games}</td>
        <td>${avg}</td>
        <td>${p.total_score}</td>
        <td>${p.level_funds}</td>
        <td>${escapeHtml(itemNames)}</td>
      </tr>`;
    })
    .join("");
}

// 人机验证失败次数单元格：非零时高亮（反作弊透明度，提示频繁未通过验证的玩家）
function vfCell(p) {
  const vf = p.verify_failures != null ? p.verify_failures : "-";
  if (typeof vf === "number" && vf > 0) return `<td class="vf-warn">${vf}</td>`;
  return `<td>${vf}</td>`;
}

// 排行榜冻结（定榜）提示条：冻结后生涯数据停止累加，榜单不再变化；
// 但参赛与 FLAG 发放不受影响（服务端 finish_game 只掐掉生涯计分那一段）。
function freezeNote() {
  if (!state || !state.leaderboard_frozen) return "";
  const at = state.leaderboard_frozen_at;
  const when = at ? `（${fmtDate(new Date(at))}）` : "";
  return `排行榜已冻结${when}，冻结后新打完的对局不计入生涯分；FLAG 照常发放。`;
}

function renderFreeze() {
  const box = $("#freeze-banner");
  if (!box || !state) return;
  const text = freezeNote();
  if (text) {
    box.textContent = text;
    box.classList.remove("hidden");
  } else {
    box.classList.add("hidden");
  }
}

// 全场排行榜：打满门槛局数的人类玩家按生涯分（定三取五）排名（含已离开者），
// 数据来自服务端 state.leaderboard（SQLite players 生涯镜像）。
function renderLeaderboard() {
  const tbody = $("#lb-body");
  if (!tbody || !state) return;
  const list = state.leaderboard || [];
  const note = $("#lb-note");
  if (note) {
    const frozen = freezeNote();
    note.textContent =
      (frozen ? `${frozen} ` : "") +
      `共 ${list.length} 位玩家达标（≥ ${state.min_games_for_rank} 局）· 生涯分取最好 ${state.best_n_games} 场的单局均分 · 「验证失败」= 人机验证未通过的累计次数，每局结束自动更新`;
  }
  const meId = myPlayerId();
  tbody.innerHTML = list
    .map((p, i) => {
      const mine = p.id === meId;
      return `<tr${mine ? ' class="me-row"' : ""}>
        <td>${i + 1}</td>
        <td>${escapeHtml(p.name)}${mine ? "（我）" : ""}</td>
        <td>${p.career}</td>
        <td>${p.games_played}</td>
        <td>${p.avg}</td>
        ${vfCell(p)}
      </tr>`;
    })
    .join("");
}

function renderHistory() {
  const list = $("#history-list");
  if (!state) return;
  const history = state.history || [];
  if (!history.length) {
    list.innerHTML = "<p class='muted'>暂无历史记录。</p>";
    return;
  }
  list.innerHTML = history
    .slice()
    .reverse()
    .map((h) => {
      if (h.type === "level_end") {
        return `<div class="history-item"><span class="history-title">Level ${h.level} 结束</span><div>${escapeHtml(h.details || "")}</div></div>`;
      }
      const roomEmoji = roomIcon(h.room_type || "normal");
      const items = (h.items && h.items.length) ? h.items
        : [{ item: h.item, winner_name: h.winner_name, avg: h.avg, target: h.target }];
      const itemLines = items
        .map((it) => {
          const name = itemName(it.item);
          const win = it.winner_name ? `赢家：${escapeHtml(it.winner_name)}` : "无人出价";
          return `${itemIcon(it.item)} ${escapeHtml(name)} · ${win} · 平均：${it.avg} · 目标：${it.target}`;
        })
        .join("<br>");
      return `<div class="history-item">
        <span class="history-title">${roomEmoji} Level ${h.level} / Room ${h.room}</span>
        <div>${itemLines}</div>
      </div>`;
    })
    .join("");
}

// ---------- 工具 ----------

function roomTypeName(t) {
  return { normal: "普通房间", special: "特殊房间", treasure: "宝物房间", boss: "Boss房间" }[t] || t;
}

function modifierName(m) {
  return { reverse: "反转目标", double: "双倍得分" }[m] || m;
}

const ITEM_RARITY = {
  // 常见
  score_amulet: "common",
  mom_heart: "common",
  lucky_sack: "common",
  perfect_vision: "common",
  steal_purse: "common",
  // 稀有
  sacred_heart: "rare",
  steam_sale: "rare",
  brimstone: "rare",
  divine_cloak: "rare",
  six_dice: "rare",
  interest: "rare",
  // 诅咒
  black_crown: "cursed",
  poor_amulet: "cursed",
  eternal_d6: "cursed",
  extra_choice: "cursed",
};

const CHARACTER_EMOJI = {
  isaac: "👶",
  soul: "👻",
  azazel: "😈",
  eden: "🌿",
  jacob_esau: "👬",
};

function charIcon(key) {
  return CHARACTER_EMOJI[key] || "❓";
}

// 角色名：优先用服务端 state.characters（与后端 CHARACTERS 保持同步）
function charName(key) {
  const c = (state.characters || []).find((x) => x.key === key);
  return c ? c.name : key;
}

// 排行榜 / 等待大厅玩家名的角色前缀，如 "👶 以撒 · 张三"。
// 隐藏其他选手的角色身份：只对本人显示角色，他人不显示。
function charTag(p) {
  if (!p || !p.character) return "";
  if (p.id !== myPlayerId()) return "";
  return `${charIcon(p.character)} ${escapeHtml(charName(p.character))} · `;
}

function rarityName(r) {
  return { common: "常见", rare: "稀有", cursed: "诅咒" }[r] || r;
}

const ITEM_EMOJI = {
  sacred_heart: "❤️",
  steam_sale: "🛒",
  brimstone: "🔥",
  lucky_sack: "🎒",
  perfect_vision: "👁️",
  score_amulet: "📿",
  interest: "📈",
  divine_cloak: "🧥",
  six_dice: "🎲",
  mom_heart: "💗",
  steal_purse: "👜",
  black_crown: "👑",
  poor_amulet: "🥀",
  eternal_d6: "🔮",
  extra_choice: "🔀",
};

const ROOM_EMOJI = {
  normal: "🚪",
  special: "✨",
  treasure: "💎",
  boss: "👹",
};

function itemName(key) {
  const names = {
    sacred_heart: "圣心",
    steam_sale: "Steam大促",
    brimstone: "硫磺火",
    lucky_sack: "福袋",
    perfect_vision: "完美视力",
    score_amulet: "积分护符",
    interest: "利息",
    divine_cloak: "神圣斗篷",
    six_dice: "六面骰",
    mom_heart: "妈妈的心脏",
    steal_purse: "偷钱袋",
    black_crown: "黑王子之冠",
    poor_amulet: "穷人护符",
    eternal_d6: "永恒六面骰",
    extra_choice: "更多选择",
  };
  return names[key] || key;
}

function itemIcon(key) {
  return ITEM_EMOJI[key] || "❓";
}

function roomIcon(type) {
  return ROOM_EMOJI[type] || "🚪";
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ---------- 交互 ----------

// HTTP 兜底：仅当 WebSocket 断开时轮询
async function refresh() {
  try {
    state = await api(`/api/state?player_id=${encodeURIComponent(getPlayerId())}`);
    // 用本地时钟锚定下一局开始时间，倒计时才可以在两次推送之间每秒更新
    nextGameAt = Date.now() + (state.next_game_in_ms || 0);
    render();
  } catch (e) {
    console.error(e);
  }
}

async function auth() {
  const code = $("#auth-code").value.trim();
  if (!code) return;
  const data = await api("/api/auth", {
    method: "POST",
    body: JSON.stringify({ tempCode: code }),
  });
  setPlayerId(data.playerId);
  $("#auth-code").value = "";
  connectWebSocket(); // 重连以带上新 cookie
  await refresh();
}

// 已登录但不在本局：重新加入
async function rejoin() {
  const data = await api("/api/join", { method: "POST" });
  setPlayerId(data.playerId);
  connectWebSocket();
  await refresh();
}

async function submitBid() {
  const value = parseInt($("#bid-input").value, 10);
  const statusEl = $("#bid-status");
  const pid = myPlayerId();

  if (!pid) {
    alert("请先完成鉴权（输入临时用户识别码）加入游戏，再开始对局。");
    return;
  }

  // 反作弊：被禁赛 / 有人机验证未完成时给出友好提示（服务端为最终裁决）
  const me = state && state.me;
  if (me && me.banned_until) {
    alert(`您因可疑行为已被禁赛 1 天，解禁时间：${fmtDate(new Date(me.banned_until))}。`);
    return;
  }
  if (me && me.captcha) {
    alert("检测到可疑操作，请先完成弹出窗口的人机验证（15 秒限时）再出价。");
    return;
  }

  if (isNaN(value) || value < 1) {
    alert("请输入一个有效的出价数字。");
    return;
  }

  const maxBid = state.room && state.room.range_max;
  if (maxBid && value > maxBid) {
    alert(`本房间出价上限为 ${maxBid}，请重新输入。`);
    return;
  }

  if (!selectedItem) {
    alert("请先点击选择要参与的道具。");
    return;
  }

  const btn = $("#bid-btn");
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "提交中...";
  statusEl.textContent = "正在提交出价...";

  // 优先走 WebSocket：一次连接复用，避免反复建立 HTTP 请求
  if (wsReady && ws) {
    try {
      ws.send(JSON.stringify({ type: "bid", item: selectedItem, value }));
    } catch (e) {
      onWsError(e.message);
    }
    return; // 按钮在收到下一帧 state/error 时复位
  }

  // WS 不可用时的 HTTP 兜底
  try {
    await api("/api/bid", {
      method: "POST",
      body: JSON.stringify({ playerId: pid, item: selectedItem, value }),
    });
    await refresh();
    statusEl.textContent = `出价成功：${value}（${itemName(selectedItem)}）`;
  } catch (e) {
    statusEl.textContent = "出价失败：" + e.message;
    alert(e.message || "出价失败");
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
}

// ---------- WebSocket ----------

function updateWsStatus(connected) {
  const el = $("#ws-status");
  if (!el) return;
  el.classList.remove("hidden");
  el.textContent = connected ? "● 实时连接" : "● 已断线，重连中…";
  el.style.color = connected ? "#7ee787" : "#f0a3a3";
}

async function connectWebSocket() {
  const gen = ++wsGen;
  if (ws) {
    try { ws.close(); } catch (e) {}
    ws = null;
  }
  // 反作弊握手：先经 HTTP 签发短期 token（与 session 绑定），以子协议携带。
  // 服务器据此确认连接来自真实网页流程；机器直接连 /ws 会因缺少 token 被拒。
  let token = "";
  try {
    const r = await api("/api/ws_token", { method: "POST" });
    token = (r && r.token) || "";
  } catch (e) {
    console.error("ws_token 获取失败:", e);
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const sock = new WebSocket(`${proto}://${location.host}/ws`, token ? ["tboi.v1." + token] : []);
  ws = sock;

  sock.onopen = () => {
    if (gen !== wsGen) return;
    wsReady = true;
    wsReconnectDelay = 1000;
    updateWsStatus(true);
  };
  sock.onmessage = (ev) => {
    if (gen !== wsGen) return;
    handleWsMessage(ev.data);
  };
  sock.onclose = () => {
    if (gen !== wsGen) return;
    wsReady = false;
    ws = null;
    updateWsStatus(false);
    setTimeout(connectWebSocket, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 15000); // 指数退避，上限 15s
  };
  sock.onerror = () => {
    try { sock.close(); } catch (e) {}
  };
}

function handleWsMessage(raw) {
  let msg;
  try {
    msg = JSON.parse(raw);
  } catch (e) {
    return;
  }
  if (msg.type === "state") {
    state = msg.data;
    nextGameAt = Date.now() + (state.next_game_in_ms || 0);
    render();
    resetBidButton();
  } else if (msg.type === "error") {
    onWsError(msg.message);
  } else if (msg.type === "captcha") {
    const statusEl = $("#captcha-status");
    if (statusEl) statusEl.textContent = msg.message || (msg.status === "ok" ? "验证通过。" : "验证失败。");
  }
}

function onWsError(message) {
  const statusEl = $("#bid-status");
  if (statusEl) statusEl.textContent = "出价失败：" + message;
  console.error("ws error:", message);
  resetBidButton();
}

// 出价按钮复位：WS 提交后按钮保持禁用，直到收到下一帧 state/error
function resetBidButton() {
  const btn = $("#bid-btn");
  if (btn) {
    btn.disabled = false;
    btn.textContent = "提交出价";
  }
}

// ---------- 事件绑定 ----------

async function safeAction(fn) {
  try {
    await fn();
  } catch (e) {
    alert(e.message || "操作失败");
  }
}

$("#auth-btn").addEventListener("click", () => safeAction(auth));
$("#auth-code").addEventListener("keydown", (e) => {
  if (e.key === "Enter") safeAction(auth);
});
$("#rejoin-btn").addEventListener("click", () => safeAction(rejoin));
$("#bid-btn").addEventListener("click", submitBid);

// 人机验证：提交按钮 + 数字键 1~6 直接选中对应选项（弹窗全屏遮罩下安全）
$("#captcha-submit").addEventListener("click", () => safeAction(submitCaptcha));
document.addEventListener("keydown", (e) => {
  const overlay = $("#captcha-overlay");
  if (!overlay || overlay.classList.contains("hidden")) return;
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= 6) selectCaptchaOption(n - 1);
});

// 点击道具卡片选择参与的道具；普通玩家若已在另一侧出价，允许「换选」——
// 提交新侧出价时后端会自动撤掉原侧出价。
$("#item-cards").addEventListener("click", (e) => {
  const card = e.target.closest(".item-card");
  if (!card) return;
  const key = card.dataset.item;
  if (!state || !state.room) return;
  const myBids = state.room.my_bids || {};
  const otherKey = Object.keys(myBids).find((k) => k !== key && myBids[k] != null);
  if (otherKey && !hasExtraChoice()) {
    if (!confirm(`你已对「${itemName(otherKey)}」出价，改选「${itemName(key)}」会撤掉原出价。确定换选？`)) return;
  }
  selectedItem = selectedItem === key ? null : key;
  renderPlaying();
});
// 等待大厅点击角色卡片：选择 / 切换角色，开局前可随时修改
$("#character-cards").addEventListener("click", async (e) => {
  const card = e.target.closest(".character-card");
  if (!card) return;
  const key = card.dataset.character;
  if (!key) return;
  try {
    await api("/api/character", {
      method: "POST",
      body: JSON.stringify({ character: key }),
    });
    await refresh();
  } catch (err) {
    alert(err.message || "选择角色失败");
  }
});
$("#copy-flag-btn").addEventListener("click", async () => {
  const flag = $("#flag-value").textContent;
  if (!flag) return;
  const btn = $("#copy-flag-btn");
  try {
    await navigator.clipboard.writeText(flag);
    btn.textContent = "已复制";
    setTimeout(() => { btn.textContent = "复制"; }, 1500);
  } catch (e) {
    alert("复制失败，请手动复制：" + flag);
  }
});

$("#bid-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitBid();
});

$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
  });
});

connectWebSocket();
// WebSocket 断开时才退化为 HTTP 轮询
setInterval(() => { if (!wsReady) refresh(); }, 2000);
countdownInterval = setInterval(updateCountdowns, 500);
