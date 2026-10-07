(function () {
  "use strict";

  /* ── DOM refs ──────────────────────────────────── */
  const $ = (s) => document.querySelector(s);
  const loadingEl = $("#loading");
  const cardEl = $("#question-card");
  const errorEl = $("#error");
  const qNumber = $("#q-number");
  const qText = $("#q-text");
  const optionsEl = $("#options");
  const resultEl = $("#result");
  const resultIcon = $("#result-icon");
  const resultMsg = $("#result-message");
  const explanationEl = $("#explanation");
  const nextBtn = $("#next-btn");
  const confettiCanvas = $("#confetti-canvas");

  let currentQuestion = null; // 当前题目数据
  let answered = false; // 是否已作答

  /* ── HTML 转义工具 ──────────────────────────────── */
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* ── 初始化 ─────────────────────────────────────── */
  loadQuestion();

  nextBtn.addEventListener("click", loadQuestion);

  /* ── 加载题目 ────────────────────────────────────── */
  async function loadQuestion() {
    answered = false;
    resultEl.classList.add("hidden");
    nextBtn.classList.add("hidden");
    cardEl.classList.add("hidden");
    errorEl.classList.add("hidden");
    loadingEl.classList.remove("hidden");

    try {
      const res = await fetch("/api/question");
      if (!res.ok) throw new Error("HTTP " + res.status);
      currentQuestion = await res.json();
      renderQuestion(currentQuestion);
      loadingEl.classList.add("hidden");
      cardEl.classList.remove("hidden");
    } catch (e) {
      console.error(e);
      loadingEl.classList.add("hidden");
      errorEl.classList.remove("hidden");
    }
  }

  /* ── 渲染题目 ────────────────────────────────────── */
  function renderQuestion(q) {
    qNumber.textContent = `第 #${q.id} 题`;
    qText.textContent = q.question;

    optionsEl.innerHTML = "";
    q.options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.dataset.key = opt.key;
      btn.innerHTML = `<span class="option-key">${opt.key}</span><span>${escapeHtml(opt.text)}</span>`;
      btn.addEventListener("click", () => handleAnswer(opt.key));
      optionsEl.appendChild(btn);
    });
  }

  /* ── 提交答案 ────────────────────────────────────── */
  async function handleAnswer(selected) {
    if (answered) return;
    answered = true;

    // 禁用所有选项
    const btns = document.querySelectorAll(".option-btn");
    btns.forEach((b) => (b.disabled = true));

    try {
      const res = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: currentQuestion.id,
          selected: selected,
        }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      // 标记正确 / 错误选项
      btns.forEach((b) => {
        if (b.dataset.key === data.correctAnswer) {
          b.classList.add("correct");
        } else if (b.dataset.key === selected && !data.correct) {
          b.classList.add("wrong");
        } else {
          b.classList.add("dimmed");
        }
      });

      // 选中选项加上弹跳动画（答对）
      if (data.correct) {
        const selectedBtn = [...btns].find((b) => b.dataset.key === selected);
        if (selectedBtn) selectedBtn.classList.add("bounce");
      }

      // 显示结果
      showResult(data);
    } catch (e) {
      console.error(e);
      answered = false;
      btns.forEach((b) => (b.disabled = false));
    }
  }

  /* ── 显示结果 ────────────────────────────────────── */
  function showResult(data) {
    if (data.correct) {
      resultIcon.textContent = "✅";
      resultMsg.textContent = "回答正确！🎉";
      resultMsg.style.color = "#2ecc71";
      resultEl.className = "result correct-bg";
      launchConfetti();
    } else {
      resultIcon.textContent = "❌";
      resultMsg.textContent = "回答错误";
      resultMsg.style.color = "#e74c3c";
      resultEl.className = "result wrong-bg";
    }

    explanationEl.innerHTML =
      `<strong>正确答案：</strong>${data.correctAnswer}. ${escapeHtml(data.correctText)}<br><br>` +
      `<strong>解析：</strong>${escapeHtml(data.explanation)}`;

    resultEl.classList.remove("hidden");
    nextBtn.classList.remove("hidden");
  }

  /* ── 五彩纸屑 🎊（用 canvas 简易实现） ───────────── */
  function launchConfetti() {
    const canvas = confettiCanvas;
    const ctx = canvas.getContext("2d");
    const W = (canvas.width = window.innerWidth);
    const H = (canvas.height = window.innerHeight);

    const particles = [];
    const COLORS = [
      "#ff6b6b",
      "#feca57",
      "#48dbfb",
      "#ff9ff3",
      "#54a0ff",
      "#5f27cd",
      "#2ecc71",
      "#f368e0",
    ];

    for (let i = 0; i < 120; i++) {
      particles.push({
        x: Math.random() * W,
        y: Math.random() * H * -1 - 20,
        w: Math.random() * 10 + 4,
        h: Math.random() * 6 + 3,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        rotation: Math.random() * 360,
        rotSpeed: (Math.random() - 0.5) * 8,
        vx: (Math.random() - 0.5) * 4,
        vy: Math.random() * 3 + 2,
        gravity: 0.06,
        opacity: 1,
      });
    }

    let frame;
    let startTime = performance.now();

    function draw() {
      const elapsed = performance.now() - startTime;
      if (elapsed > 3000) {
        ctx.clearRect(0, 0, W, H);
        cancelAnimationFrame(frame);
        return;
      }

      ctx.clearRect(0, 0, W, H);
      let alive = false;

      particles.forEach((p) => {
        p.x += p.vx;
        p.vy += p.gravity;
        p.y += p.vy;
        p.rotation += p.rotSpeed;
        p.opacity = Math.max(0, 1 - elapsed / 3000);

        if (p.opacity <= 0) return;
        alive = true;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.globalAlpha = p.opacity;
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      });

      if (alive) {
        frame = requestAnimationFrame(draw);
      }
    }

    draw();
  }
})();
