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
  document.getElementById("stat-online").innerHTML = `${online}<small> 项</small>`;
  document.getElementById("mod-count").textContent =
    `${online} 项已上线 / 共 ${modules.length} 项规划`;

  const matrix = document.getElementById("matrix");
  modules.forEach((m, i) => {
    const isOnline = m.status === "online";
    const card = document.createElement(isOnline && m.href ? "a" : "div");
    if (isOnline && m.href) card.href = m.href;
    card.className =
      "mod-card bracket reveal " + (isOnline ? "is-online" : "is-planned");
    card.style.animationDelay = `${0.1 + i * 0.08}s`;

    const metrics = (m.metrics || [])
      .map(
        (x) =>
          `<div class="m"><div class="v">${x.value}</div><div class="k">${x.label}</div></div>`
      )
      .join("");

    card.innerHTML = `
      <div class="row">
        <span class="idx">0${i + 1}</span>
        <span class="sep" style="flex:1"></span>
        <span class="badge ${isOnline ? "online" : "planned"}">
          <span class="d"></span>${isOnline ? "已上线" : "规划中"}
        </span>
      </div>
      <h3>${m.name}</h3>
      <div class="tagline">${m.tagline}</div>
      ${isOnline ? `<div class="mod-metrics">${metrics}</div>` : ""}
      ${
        isOnline
          ? `<span class="enter">进入演示 <span class="arr">→</span></span>`
          : `<div class="soon">敬请期待</div>`
      }
    `;
    matrix.appendChild(card);
  });
})();
