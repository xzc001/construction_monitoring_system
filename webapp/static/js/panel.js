// 配电箱模块页逻辑
const video = document.getElementById("video");
const timeline = document.getElementById("timeline");
const playhead = document.getElementById("playhead");
const statusbar = document.getElementById("statusbar");
const stText = document.getElementById("st-text");
const stDesc = document.getElementById("st-desc");
const stTime = document.getElementById("st-time");

let RESULT = null;

const STATE_META = {
  closed:          { cls: "s-closed",     text: "门已关 · 合规",       desc: "配电箱门处于关闭状态,符合安全规范" },
  open_attended:   { cls: "s-attended",   text: "维修中 · 人员值守",   desc: "门已打开,但有人员在场操作 —— 判定为合规作业,不告警" },
  open_unattended: { cls: "s-unattended", text: "无人值守 · 门未关",   desc: "门持续敞开且周边无人 —— 触电隐患,已触发告警!" },
};

// ---------- 加载样本 ----------
(async function init() {
  let samples = [];
  try { samples = await api("/api/samples"); } catch (e) { return; }
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

// ---------- 渲染某次结果 ----------
async function loadResult(run) {
  let r;
  try { r = await api(`/api/result/${run}`); } catch (e) { return; }
  RESULT = r;

  video.src = r.video_url;
  video.load();

  // 重置语音播报状态(换样本/重载视频)
  if (typeof spokenAlerts !== "undefined") { spokenAlerts.clear(); lastVoiceT = 0; }
  if (window.speechSynthesis) speechSynthesis.cancel();

  // 指标
  document.getElementById("m-dur").textContent = r.duration_s ?? "--";
  const mAlert = document.getElementById("m-alert");
  mAlert.textContent = r.n_alerts;
  mAlert.classList.toggle("alert", r.n_alerts > 0);
  document.getElementById("m-res").textContent = r.width ? `${r.width}×${r.height}` : "--";
  document.getElementById("m-elapsed").textContent = r.elapsed_seconds ? r.elapsed_seconds + "s" : "--";
  document.getElementById("tl-end").textContent = fmtTime(r.duration_s);

  renderTimeline(r);
  renderAlerts(r);
  setStatus(r.segments.length ? r.segments[0].state : "closed", 0);
  updateAlertActions(r);
}

// ---------- 时间轴 ----------
function renderTimeline(r) {
  // 清掉旧 seg / tick, 保留 playhead
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

// 点击时间轴跳转
timeline.onclick = (e) => {
  if (!RESULT || !video.duration) return;
  const rect = timeline.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  video.currentTime = ratio * video.duration;
};

// ---------- 告警卡片 ----------
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
        <div class="t">⚠ 配电箱无人值守</div>
        <div class="d">触发时刻 ${fmtTime(a.time_seconds)} (${a.time_seconds}s) · 事件 #${a.track_id}</div>
      </div>`;
    const img = card.querySelector("img");
    if (img) img.onclick = () => openLightbox(a.screenshot_url);
    list.appendChild(card);
    // 卡片点击跳到该时刻
    card.querySelector(".meta").onclick = () => { if (video.duration) video.currentTime = a.time_seconds; };
  });
}

// ---------- 状态联动 ----------
function setStatus(state, t) {
  const m = STATE_META[state] || STATE_META.closed;
  statusbar.className = "statusbar " + m.cls;
  stText.textContent = m.text;
  stDesc.textContent = m.desc;
}

function currentSegmentState(t) {
  if (!RESULT) return "closed";
  for (const s of RESULT.segments) {
    if (t >= s.start_s && t < s.end_s) return s.state;
  }
  return RESULT.segments.length ? RESULT.segments[RESULT.segments.length - 1].state : "closed";
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
const VOICE_MSG = "注意，请关闭配电箱";
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

// 预加载中文语音(部分浏览器异步加载)
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

// 播放进度跨过告警时刻 → 播报一次(回放/拖回会重置)
function checkVoiceTrigger(t) {
  if (t < lastVoiceT - 0.4) spokenAlerts.clear();   // 拖回 / 重播
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
    speak("语音告警已开启");   // 同时借用户手势"解锁"浏览器语音权限
  } else {
    speechSynthesis.cancel();
    voiceToggle.classList.remove("speaking");
  }
};

// 拖动进度条 / 切换样本时, 取消正在进行的播报
video.addEventListener("seeking", () => { if (voiceSupported) speechSynthesis.cancel(); });

// ---------- 灯箱 ----------
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
function openLightbox(src) { lightboxImg.src = src; lightbox.classList.add("show"); }
lightbox.onclick = () => lightbox.classList.remove("show");

// 告警动作(报告/邮件/自动发送)逻辑见 common.js

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
  fd.append("panel_roi", document.getElementById("roi").value.trim());
  fd.append("persist", document.getElementById("persist").value.trim() || "1.5");

  runBtn.disabled = true;
  const prog = document.getElementById("prog");
  const bar = document.getElementById("prog-bar");
  const stat = document.getElementById("up-status");
  prog.style.display = "block";
  stat.textContent = "上传中...";

  let job;
  try { job = await api("/api/panel/analyze", { method: "POST", body: fd }); }
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
      // 取消样本高亮, 载入新结果
      document.querySelectorAll(".sample-chip").forEach((c) => c.classList.remove("active"));
      loadResult(job.run);
    } else if (j.status === "error") {
      clearInterval(poll);
      stat.textContent = "分析失败: " + (j.error || "");
      runBtn.disabled = false;
    }
  }, 600);
};
