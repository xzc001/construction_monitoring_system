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
