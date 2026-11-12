/**
 * Interactive SVG Charts: Combined Line + Bar (combo), Bars-only, and Trend Line-only + Hover Tooltips.
 */

import { esc } from "../api.js";

export function renderTrafficChart(series, valueKey = "requests", secondaryKey = "errors", height = 200, mode = "combo") {
  if (!series || series.length === 0) {
    return `<p style="color:var(--text-muted);font-size:13px;">No traffic recorded yet.</p>`;
  }

  const width = 640;
  const padX = 36;
  const padY = 26;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;
  const maxVal = Math.max(5, ...series.map((d) => Number(d[valueKey] || 0)));
  const barW = Math.min(34, Math.max(14, plotW / series.length - 18));

  const points = series.map((item, idx) => {
    const val = Number(item[valueKey] || 0);
    const errVal = Number(item[secondaryKey] || 0);
    const cx = padX + (plotW / series.length) * (idx + 0.5);
    const y = padY + plotH - (val / maxVal) * plotH;
    return { item, val, errVal, cx, y, shortDate: String(item.date || "").slice(5) };
  });

  const gridLines = [0.25, 0.5, 0.75, 1]
    .map((frac) => {
      const gy = padY + plotH - frac * plotH;
      return `<line x1="${padX}" y1="${gy}" x2="${width - padX}" y2="${gy}" stroke="rgba(255,255,255,0.07)" stroke-dasharray="3,4" />`;
    })
    .join("");

  const showBars = mode === "bar" || mode === "combo";
  const showLine = mode === "line" || mode === "combo";

  const barsMarkup = showBars
    ? points
        .map((p, idx) => {
          const barH = Math.max(3, (p.val / maxVal) * plotH);
          const errH = p.errVal > 0 ? Math.max(2, (p.errVal / maxVal) * plotH) : 0;
          const y = padY + plotH - barH;
          const errY = padY + plotH - errH;
          return `
            <g class="chart-hover-target" data-tip="${esc(p.item.date)}: ${p.val} reqs (${p.errVal} errors)" data-cx="${p.cx}" data-cy="${y}">
              <rect class="svg-bar-rect" style="animation-delay:${idx * 0.04}s" x="${p.cx - barW / 2}" y="${y}" width="${barW}" height="${barH}" rx="6" fill="url(#betaBarGrad)" opacity="${mode === "combo" ? "0.82" : "0.95"}"></rect>
              ${errH > 0 ? `<rect x="${p.cx - barW / 2}" y="${errY}" width="${barW}" height="${errH}" rx="4" fill="#f43f5e" opacity="0.9"></rect>` : ""}
            </g>`;
        })
        .join("")
    : "";

  let lineMarkup = "";
  if (showLine) {
    const polylinePts = points.map((p) => `${p.cx},${p.y}`).join(" ");
    const areaPts = `${points[0].cx},${padY + plotH} ${polylinePts} ${points[points.length - 1].cx},${padY + plotH}`;
    lineMarkup = `
      ${mode === "line" ? `<polygon points="${areaPts}" fill="url(#betaAreaGrad)" />` : ""}
      <polyline class="svg-line-path" points="${polylinePts}" fill="none" stroke="${mode === "combo" ? "#ffffff" : "#f1f1f1"}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      ${points
        .map(
          (p) => `
          <g class="chart-hover-target" data-tip="${esc(p.item.date)}: ${p.val} reqs (${p.errVal} errors)" data-cx="${p.cx}" data-cy="${p.y}">
            <circle cx="${p.cx}" cy="${p.y}" r="4.5" fill="#0f0f0f" stroke="${mode === "combo" ? "#ffffff" : "#f1f1f1"}" stroke-width="2.5" style="cursor:pointer;" />
          </g>`
        )
        .join("")}
    `;
  }

  const labelsMarkup = points
    .map(
      (p) => `
        <text x="${p.cx}" y="${height - 4}" text-anchor="middle" fill="#717171" font-size="11">${esc(p.shortDate)}</text>
        <text x="${p.cx}" y="${Math.max(12, p.y - 9)}" text-anchor="middle" fill="#f1f1f1" font-weight="600" font-size="11">${p.val}</text>
      `
    )
    .join("");

  return `
    <div class="chart-box" data-chart-wrap="true">
      <div class="chart-tooltip"></div>
      <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="API Usage Line & Bar Chart">
        <defs>
          <linearGradient id="betaBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f1f1f1" />
            <stop offset="100%" stop-color="#383838" />
          </linearGradient>
          <linearGradient id="betaAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(255, 255, 255, 0.22)" />
            <stop offset="100%" stop-color="rgba(255, 255, 255, 0.01)" />
          </linearGradient>
        </defs>
        ${gridLines}
        <line x1="${padX}" y1="${padY + plotH}" x2="${width - padX}" y2="${padY + plotH}" stroke="rgba(255,255,255,0.12)" />
        ${barsMarkup}
        ${lineMarkup}
        ${labelsMarkup}
      </svg>
    </div>
  `;
}

export function bindChartTooltips(root) {
  root.querySelectorAll('[data-chart-wrap="true"]').forEach((wrap) => {
    const tip = wrap.querySelector(".chart-tooltip");
    const svg = wrap.querySelector("svg");
    if (!tip || !svg) return;

    wrap.querySelectorAll(".chart-hover-target").forEach((el) => {
      el.addEventListener("mouseenter", () => {
        const cx = Number(el.getAttribute("data-cx"));
        const cy = Number(el.getAttribute("data-cy"));
        const rect = svg.getBoundingClientRect();
        const xPct = (cx / 640) * rect.width;
        const yPct = (cy / Number(svg.getAttribute("height") || 200)) * rect.height;
        tip.textContent = el.getAttribute("data-tip") || "";
        tip.style.left = `${xPct}px`;
        tip.style.top = `${yPct}px`;
        tip.classList.add("visible");
      });
      el.addEventListener("mouseleave", () => {
        tip.classList.remove("visible");
      });
    });
  });
}
