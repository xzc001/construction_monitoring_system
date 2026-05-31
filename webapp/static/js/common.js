// 公共工具: 时钟 + fetch 封装
function pad(n) { return String(n).padStart(2, "0"); }

function tickClock() {
  const els = [document.getElementById("clock"), document.getElementById("foot-time")];
  function update() {
    const d = new Date();
    const t = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    const full = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${t}`;
    if (els[0]) els[0].textContent = t;
    if (els[1]) els[1].textContent = full + " · 北京时间";
  }
  update();
  setInterval(update, 1000);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

function fmtTime(s) {
  if (s == null) return "--:--";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${pad(m)}:${pad(sec)}`;
}

document.addEventListener("DOMContentLoaded", tickClock);


// ============ 告警动作(报告 / 指定邮箱发送 / 播放结束自动发送)—— 全模块页共用 ============
(function () {
  let _result = null;      // 当前演示结果(各页 loadResult 通过 updateAlertActions 传入)
  let _autoSentRun = null; // 同一结果自动发送只触发一次
  let wired = null;        // init 后挂载的刷新函数

  // 立即定义为全局: 各页 loadResult 里仍调用 updateAlertActions(r)
  window.updateAlertActions = function (r) {
    _result = r;
    _autoSentRun = null;
    if (wired) wired();
  };

  function init() {
    const btnReport = document.getElementById("btn-report");
    const btnEmail = document.getElementById("btn-email");
    if (!btnReport || !btnEmail) return;   // 非模块页(首页等)跳过
    const aaStatus = document.getElementById("aa-status");
    const aaHint = document.getElementById("aa-hint");
    const video = document.getElementById("video");
    const h1 = document.querySelector(".page-head h1");
    const LOCATION = "演示点位 · " + ((h1 && h1.textContent.trim()) || "现场");

    // 注入: 收件邮箱输入框 + 播放结束自动发送开关(插在按钮行之后、状态行之前)
    if (aaStatus && !document.getElementById("cms-email")) {
      const row = document.createElement("div");
      row.className = "aa-mail";
      row.innerHTML =
        '<input id="cms-email" type="email" autocomplete="email" ' +
        'placeholder="收件邮箱(留空 = 用默认收件人)" />' +
        '<label class="cms-auto" title="视频播放结束后自动生成报告并发送到上面填写的邮箱">' +
        '<input type="checkbox" id="cms-auto" /><span>播放结束自动发送报告</span></label>';
      aaStatus.parentNode.insertBefore(row, aaStatus);
    }
    if (!document.getElementById("cms-mail-style")) {
      const st = document.createElement("style");
      st.id = "cms-mail-style";
      st.textContent =
        ".aa-mail{display:flex;flex-direction:column;gap:10px;margin:12px 0 6px}" +
        ".aa-mail #cms-email{font-family:var(--font-mono);font-size:13px;padding:10px 12px;" +
        "background:var(--bg);border:1px solid var(--border);color:var(--text-bright);" +
        "width:100%;box-sizing:border-box;transition:border-color .2s}" +
        ".aa-mail #cms-email:focus{outline:none;border-color:var(--amber)}" +
        ".aa-mail #cms-email::placeholder{color:var(--text-dim)}" +
        ".aa-mail .cms-auto{display:flex;align-items:center;gap:8px;font-family:var(--font-mono);" +
        "font-size:12px;color:var(--text-dim);cursor:pointer;user-select:none}" +
        ".aa-mail .cms-auto input{accent-color:var(--amber);width:15px;height:15px;cursor:pointer;margin:0}" +
        ".aa-mail .cms-auto:hover{color:var(--amber)}";
      document.head.appendChild(st);
    }
    const emailInput = document.getElementById("cms-email");
    const autoChk = document.getElementById("cms-auto");

    let emailReady = false;
    api("/api/alerting/status")
      .then((s) => { emailReady = !!s.email; refresh(); })
      .catch(() => { emailReady = false; });

    function refresh() {
      const has = !!(_result && _result.n_alerts > 0);
      btnReport.disabled = !has;
      btnEmail.disabled = !has || !emailReady;
      if (autoChk) autoChk.disabled = !emailReady || !has;
      btnEmail.title = emailReady ? "" : "邮箱未配置";
      if (aaHint && !aaHint.innerHTML) {
        aaHint.innerHTML = '填写「收件邮箱」点"发送到邮箱"即把事故报告发过去;勾选"自动发送"则视频放完自动发(留空邮箱用默认收件人)。';
      }
    }
    wired = refresh;
    refresh();

    function buildForm() {
      const fd = new FormData();
      fd.append("run", _result.run);
      fd.append("alert_idx", "0");
      fd.append("location", LOCATION);
      fd.append("to_email", (emailInput.value || "").trim());
      return fd;
    }

    btnReport.onclick = async () => {
      if (!_result) return;
      aaStatus.className = "aa-status busy";
      aaStatus.textContent = "正在生成报告...";
      try {
        const r = await fetch("/api/report", { method: "POST", body: buildForm() });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || r.status);
        aaStatus.className = "aa-status ok";
        aaStatus.innerHTML = `✓ 报告已生成 — <a href="${j.report_url}" target="_blank">打开 PDF</a>`;
        window.open(j.report_url, "_blank");
      } catch (e) {
        aaStatus.className = "aa-status err";
        aaStatus.textContent = "生成失败: " + e.message;
      }
    };

    async function sendEmail(auto) {
      if (!_result) return;
      aaStatus.className = "aa-status busy";
      aaStatus.textContent = (auto ? "播放结束 · " : "") + "正在生成报告并发送邮件...";
      btnEmail.disabled = true;
      try {
        const r = await fetch("/api/alerting/send", { method: "POST", body: buildForm() });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || r.status);
        const em = j.results && j.results.email;
        if (em && em.ok) {
          aaStatus.className = "aa-status ok";
          aaStatus.textContent = "✓ " + em.detail;
        } else {
          aaStatus.className = "aa-status err";
          aaStatus.textContent = "邮件未发送: " + (em ? em.detail : "未知错误");
        }
      } catch (e) {
        aaStatus.className = "aa-status err";
        aaStatus.textContent = "发送失败: " + e.message;
      } finally {
        refresh();
      }
    }

    btnEmail.onclick = () => sendEmail(false);

    if (video) {
      video.addEventListener("ended", () => {
        if (autoChk && autoChk.checked && emailReady &&
            _result && _result.n_alerts > 0 && _autoSentRun !== _result.run) {
          _autoSentRun = _result.run;   // 防止重复发送
          sendEmail(true);
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
