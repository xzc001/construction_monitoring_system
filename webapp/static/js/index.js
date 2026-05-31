// 首页: 渲染能力矩阵
(async function () {
  let modules = [];
  try {
    modules = await api("/api/modules");
  } catch (e) {
    document.getElementById("matrix").innerHTML =
      `<p class="dim">无法加载模块清单: ${e.message}</p>`;
    return;
  }

  const online = modules.filter((m) => m.status === "online").length;
  const ready = modules.filter((m) => m.status === "ready").length;
  document.getElementById("stat-online").innerHTML = `${online}<small> 项</small>`;
  document.getElementById("mod-count").textContent =
    `${online} 项已上线${ready ? ` · ${ready} 项模型就绪` : ""} / 共 ${modules.length} 项`;

  const matrix = document.getElementById("matrix");
  modules.forEach((m, i) => {
    const isOnline = m.status === "online";
    const isReady = m.status === "ready";
    const clickable = (isOnline || isReady) && m.href;
    const card = document.createElement(clickable ? "a" : "div");
    if (clickable) card.href = m.href;
    card.className =
      "mod-card bracket reveal " +
      (isOnline ? "is-online" : isReady ? "is-ready" : "is-planned");
    card.style.animationDelay = `${0.1 + i * 0.08}s`;

    const metrics = (m.metrics || [])
      .map(
        (x) =>
          `<div class="m"><div class="v">${x.value}</div><div class="k">${x.label}</div></div>`
      )
      .join("");

    const badge = isOnline
      ? `<span class="badge online"><span class="d"></span>已上线</span>`
      : isReady
      ? `<span class="badge ready"><span class="d"></span>模型就绪</span>`
      : `<span class="badge planned"><span class="d"></span>规划中</span>`;

    const footer = isOnline
      ? `<span class="enter">进入演示 <span class="arr">→</span></span>`
      : isReady
      ? `<span class="enter">上传视频试用 <span class="arr">→</span></span>`
      : `<div class="soon">敬请期待</div>`;

    card.innerHTML = `
      <div class="row">
        <span class="idx">0${i + 1}</span>
        <span class="sep" style="flex:1"></span>
        ${badge}
      </div>
      <h3>${m.name}</h3>
      <div class="tagline">${m.tagline}</div>
      ${isOnline || isReady ? `<div class="mod-metrics">${metrics}</div>` : ""}
      ${footer}
    `;
    matrix.appendChild(card);
  });
})();
