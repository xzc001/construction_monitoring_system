// 电动车违规停放模块页逻辑
const video = document.getElementById("video");
const timeline = document.getElementById("timeline");
const playhead = document.getElementById("playhead");
const statusbar = document.getElementById("statusbar");
const stText = document.getElementById("st-text");
const stDesc = document.getElementById("st-desc");
const stTime = document.getElementById("st-time");

let RESULT = null;

const STATE_META = {
  no_violation: { cls: "s-no_violation", text: "正常 · 禁停区无车",       desc: "禁停区内无电动车,现场正常" },
  illegal_park: { cls: "s-illegal_park", text: "违规 · 电动车停入禁停区", desc: "电动车违规停放在禁停区/消防通道 —— 存在火灾与逃生风险,已触发告警!" },
};

(async function init() {
  let samples = [];
  try { samples = await api("/api/samples?module=ebike"); } catch (e) { return; }
  const box = document.getElementById("samples");
  samples.forEach((s, i) => {
    const chip = document.createElement("div");
    chip.className = "sample-chip" + (i === 0 ? " active" : "");
    chip.textContent = s.title;
    chip.onclick = () => {
      document.querySelectorAll(".sample-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      loadResult(s.run);
    };
    box.appendChild(chip);
  });
  if (samples.length) loadResult(samples[0].run);
})();

async function loadResult(run) {
  let r;
  try { r = await api(`/api/result/${run}`); } catch (e) { return; }
  RESULT = r;

  video.src = r.video_url;
  video.load();

  if (typeof spokenAlerts !== "undefined") { spokenAlerts.clear(); lastVoiceT = 0; }
  if (window.speechSynthesis) speechSynthesis.cancel();

  document.getElementById("m-dur").textContent = r.duration_s ?? "--";
  const mAlert = document.getElementById("m-alert");
  mAlert.textContent = r.n_alerts;
  mAlert.classList.toggle("alert", r.n_alerts > 0);
  document.getElementById("m-res").textContent = r.width ? `${r.width}×${r.height}` : "--";
  document.getElementById("m-elapsed").textContent = r.elapsed_seconds ? r.elapsed_seconds + "s" : "--";
  document.getElementById("tl-end").textContent = fmtTime(r.duration_s);

  renderTimeline(r);
  renderAlerts(r);
  setStatus(r.segments.length ? r.segments[0].state : "no_violation", 0);
  updateAlertActions(r);
}

function renderTimeline(r) {
  [...timeline.querySelectorAll(".seg, .alert-tick")].forEach((e) => e.remove());
  const dur = r.duration_s || 1;
  r.segments.forEach((s) => {
    const el = document.createElement("div");
    el.className = "seg " + s.state;
    el.style.left = (s.start_s / dur) * 100 + "%";
    el.style.width = ((s.end_s - s.start_s) / dur) * 100 + "%";
    el.title = `${s.state_cn}  ${fmtTime(s.start_s)}–${fmtTime(s.end_s)}`;
    if (s.frames > dur * r.fps * 0.12) {
      el.innerHTML = `<span class="lbl">${s.state_cn.split(" ")[0]}</span>`;
    }
    timeline.appendChild(el);
  });
  r.alerts.forEach((a) => {
    const t = document.createElement("div");
    t.className = "alert-tick";
    t.style.left = (a.time_seconds / dur) * 100 + "%";
    timeline.appendChild(t);
  });
}

timeline.onclick = (e) => {
  if (!RESULT || !video.duration) return;
  const rect = timeline.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  video.currentTime = ratio * video.duration;
};

function renderAlerts(r) {
  const list = document.getElementById("alert-list");
  document.getElementById("alert-count").textContent = `共 ${r.n_alerts} 起`;
  list.innerHTML = "";
  if (!r.alerts.length) {
    list.innerHTML = `<div class="empty-alert">本段视频未触发告警</div>`;
    return;
  }
  r.alerts.forEach((a, i) => {
    const card = document.createElement("div");
    card.className = "alert-card reveal";
    card.style.animationDelay = `${i * 0.08}s`;
    card.innerHTML = `
      ${a.screenshot_url ? `<img src="${a.screenshot_url}" data-full="${a.screenshot_url}" alt="告警截图" />` : ""}
      <div class="meta">
        <div class="t">⚠ 电动车违规停放</div>
        <div class="d">触发时刻 ${fmtTime(a.time_seconds)} (${a.time_seconds}s) · 事件 #${a.track_id}</div>
      </div>`;
    const img = card.querySelector("img");
    if (img) img.onclick = () => openLightbox(a.screenshot_url);
    list.appendChild(card);
    card.querySelector(".meta").onclick = () => { if (video.duration) video.currentTime = a.time_seconds; };
  });
}

function setStatus(state, t) {
  const m = STATE_META[state] || STATE_META.no_violation;
  statusbar.className = "statusbar " + m.cls;
  stText.textContent = m.text;
  stDesc.textContent = m.desc;
}

function currentSegmentState(t) {
  if (!RESULT) return "no_violation";
  for (const s of RESULT.segments) {
    if (t >= s.start_s && t < s.end_s) return s.state;
  }
  return RESULT.segments.length ? RESULT.segments[RESULT.segments.length - 1].state : "no_violation";
}

video.addEventListener("timeupdate", () => {
  if (!RESULT || !video.duration) return;
  const t = video.currentTime;
  const ratio = t / video.duration;
  playhead.style.left = ratio * 100 + "%";
  stTime.textContent = `${fmtTime(t)} / ${fmtTime(video.duration)}`;
  setStatus(currentSegmentState(t), t);
  checkVoiceTrigger(t);
});

// ====================== 浏览器语音告警 ======================
const VOICE_MSG = "注意，电动车请勿停放在消防通道，请移至指定停放点";
const voiceToggle = document.getElementById("voice-toggle");
const voiceSupported = "speechSynthesis" in window;
let voiceEnabled = voiceSupported;
let spokenAlerts = new Set();
let lastVoiceT = 0;

if (!voiceSupported) {
  voiceToggle.classList.remove("on");
  voiceToggle.textContent = "🔇 浏览器不支持语音";
  voiceToggle.disabled = true;
}

function pickZhVoice() {
  const vs = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  return vs.find((v) => (v.lang || "").toLowerCase().startsWith("zh")) || null;
}
if (voiceSupported && speechSynthesis.onvoiceschanged !== undefined) {
  speechSynthesis.onvoiceschanged = pickZhVoice;
}

function speak(text) {
  if (!voiceSupported || !voiceEnabled) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "zh-CN";
  const v = pickZhVoice();
  if (v) u.voice = v;
  u.rate = 1.0; u.pitch = 1.0; u.volume = 1.0;
  u.onstart = () => voiceToggle.classList.add("speaking");
  u.onend = () => voiceToggle.classList.remove("speaking");
  u.onerror = () => voiceToggle.classList.remove("speaking");
  speechSynthesis.speak(u);
}

function checkVoiceTrigger(t) {
  if (t < lastVoiceT - 0.4) spokenAlerts.clear();
  if (voiceEnabled && RESULT && RESULT.alerts) {
    RESULT.alerts.forEach((a, i) => {
      if (!spokenAlerts.has(i) && lastVoiceT <= a.time_seconds && t >= a.time_seconds) {
        spokenAlerts.add(i);
        speak(VOICE_MSG);
      }
    });
  }
  lastVoiceT = t;
}

voiceToggle.onclick = () => {
  if (!voiceSupported) return;
  voiceEnabled = !voiceEnabled;
  voiceToggle.classList.toggle("on", voiceEnabled);
  voiceToggle.textContent = voiceEnabled ? "🔊 语音告警 开" : "🔇 语音告警 关";
  if (voiceEnabled) {
    speak("语音告警已开启");
  } else {
    speechSynthesis.cancel();
    voiceToggle.classList.remove("speaking");
  }
};

video.addEventListener("seeking", () => { if (voiceSupported) speechSynthesis.cancel(); });

const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
function openLightbox(src) { lightboxImg.src = src; lightbox.classList.add("show"); }
lightbox.onclick = () => lightbox.classList.remove("show");

const btnReport = document.getElementById("btn-report");
const btnEmail = document.getElementById("btn-email");
const aaStatus = document.getElementById("aa-status");
const aaHint = document.getElementById("aa-hint");
let emailReady = false;

(async function initAlerting() {
  try {
    const s = await api("/api/alerting/status");
    emailReady = !!s.email;
  } catch (e) { emailReady = false; }
  if (!emailReady) {
    aaHint.innerHTML =
      '邮箱未配置 —— 复制 <code>config/alerting.example.yaml</code> 为 ' +
      '<code>config/alerting.yaml</code> 并填入 QQ 邮箱授权码后即可发送(详见 README)。';
  }
  if (RESULT) updateAlertActions(RESULT);
})();

function updateAlertActions(r) {
  const has = r && r.n_alerts > 0;
  btnReport.disabled = !has;
  btnEmail.disabled = !has || !emailReady;
  aaStatus.textContent = "";
  aaStatus.className = "aa-status";
  if (has && !emailReady) { btnEmail.title = "邮箱未配置"; }
}

function aaForm() {
  const fd = new FormData();
  fd.append("run", RESULT.run);
  fd.append("alert_idx", "0");
  fd.append("location", "演示点位 · 电动车停放区");
  return fd;
}

btnReport.onclick = async () => {
  aaStatus.className = "aa-status busy";
  aaStatus.textContent = "正在生成报告...";
  try {
    const r = await fetch("/api/report", { method: "POST", body: aaForm() });
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

btnEmail.onclick = async () => {
  aaStatus.className = "aa-status busy";
  aaStatus.textContent = "正在生成报告并发送邮件...";
  btnEmail.disabled = true;
  try {
    const r = await fetch("/api/alerting/send", { method: "POST", body: aaForm() });
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
    btnEmail.disabled = !emailReady;
  }
};

const drop = document.getElementById("drop");
const fileInput = document.createElement("input");
fileInput.type = "file";
fileInput.accept = "video/*";
let chosenFile = null;
const runBtn = document.getElementById("run-btn");

drop.onclick = () => fileInput.click();
fileInput.onchange = () => { if (fileInput.files[0]) pickFile(fileInput.files[0]); };
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => {
  e.preventDefault(); drop.classList.remove("over");
  if (e.dataTransfer.files[0]) pickFile(e.dataTransfer.files[0]);
};
function pickFile(f) {
  chosenFile = f;
  document.getElementById("drop-name").textContent = `已选择: ${f.name}`;
  runBtn.disabled = false;
}

runBtn.onclick = async () => {
  if (!chosenFile) return;
  const fd = new FormData();
  fd.append("file", chosenFile);
  fd.append("zone_roi", document.getElementById("roi").value.trim());
  fd.append("persist", document.getElementById("persist").value.trim() || "1.5");

  runBtn.disabled = true;
  const prog = document.getElementById("prog");
  const bar = document.getElementById("prog-bar");
  const stat = document.getElementById("up-status");
  prog.style.display = "block";
  stat.textContent = "上传中...";

  let job;
  try { job = await api("/api/ebike/analyze", { method: "POST", body: fd }); }
  catch (e) { stat.textContent = "上传失败: " + e.message; runBtn.disabled = false; return; }

  stat.textContent = "AI 分析中...";
  const poll = setInterval(async () => {
    let j;
    try { j = await api(`/api/jobs/${job.job_id}`); } catch (e) { return; }
    bar.style.width = Math.round((j.progress || 0) * 100) + "%";
    if (j.status === "done") {
      clearInterval(poll);
      stat.textContent = "✓ 分析完成";
      runBtn.disabled = false;
      document.querySelectorAll(".sample-chip").forEach((c) => c.classList.remove("active"));
      loadResult(job.run);
    } else if (j.status === "error") {
      clearInterval(poll);
      stat.textContent = "分析失败: " + (j.error || "");
      runBtn.disabled = false;
    }
  }, 600);
};
