/* Графики Dashboard и страницы «Статистика» на Chart.js.
   Данные приходят из <script id="chart-data" type="application/json">; цвета берутся из CSS-переменных темы. */
(function () {
  "use strict";

  var dataNode = document.getElementById("chart-data");
  if (!dataNode || typeof Chart === "undefined") return;
  var payload = JSON.parse(dataNode.textContent);
  var live = [];

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function toneColor(tone) {
    return token("--sn-" + tone);
  }

  function palette() {
    return { text: token("--sn-text"), muted: token("--sn-muted"), line: token("--sn-line"), surface: token("--sn-surface") };
  }

  function hasData(values) {
    return values.some(function (value) { return value > 0; });
  }

  function baseOptions(colors) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 350 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: colors.text, titleColor: colors.surface, bodyColor: colors.surface, padding: 10, cornerRadius: 8, displayColors: true }
      }
    };
  }

  function axes(colors, extra) {
    var scales = {
      x: { grid: { display: false }, border: { color: colors.line }, ticks: { color: colors.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
      y: { beginAtZero: true, grid: { color: colors.line }, border: { display: false }, ticks: { color: colors.muted, precision: 0 } }
    };
    return Object.assign(scales, extra || {});
  }

  var builders = {
    categories: function (canvas, colors) {
      var block = payload.categories;
      var centre = {
        id: "centre",
        afterDraw: function (chart) {
          var box = chart.chartArea;
          var ctx = chart.ctx;
          var total = block.values.reduce(function (sum, value) { return sum + value; }, 0);
          ctx.save();
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = colors.text;
          ctx.font = "700 30px Onest, sans-serif";
          ctx.fillText(String(total), (box.left + box.right) / 2, (box.top + box.bottom) / 2 - 8);
          ctx.fillStyle = colors.muted;
          ctx.font = "500 12px Onest, sans-serif";
          ctx.fillText("проверок", (box.left + box.right) / 2, (box.top + box.bottom) / 2 + 16);
          ctx.restore();
        }
      };
      var options = baseOptions(colors);
      options.cutout = "68%";
      options.plugins.legend = { display: true, position: "bottom", labels: { color: colors.text, usePointStyle: true, pointStyle: "rectRounded", padding: 16, font: { family: "Onest", size: 13 } } };
      options.interaction = { mode: "nearest", intersect: true };
      return {
        type: "doughnut",
        data: { labels: block.labels, datasets: [{ data: block.values, backgroundColor: block.tones.map(toneColor), borderColor: colors.surface, borderWidth: 3, hoverOffset: 4 }] },
        options: options,
        plugins: [centre],
        values: block.values
      };
    },

    "daily-line": function (canvas, colors) {
      var block = payload.daily;
      var line = colors.text;
      var area = canvas.getContext("2d").createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 300);
      area.addColorStop(0, line + "40");
      area.addColorStop(1, line + "00");
      var options = baseOptions(colors);
      options.scales = axes(colors);
      return {
        type: "line",
        data: { labels: block.labels, datasets: [{ label: "Проверок", data: block.totals, borderColor: line, backgroundColor: area, fill: true, borderWidth: 2.5, cubicInterpolationMode: "monotone", pointRadius: 0, pointHoverRadius: 5, pointHoverBackgroundColor: line }] },
        options: options,
        values: block.totals
      };
    },

    "daily-stack": function (canvas, colors) {
      var block = payload.daily;
      var options = baseOptions(colors);
      options.scales = axes(colors, {
        x: { stacked: true, grid: { display: false }, border: { color: colors.line }, ticks: { color: colors.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
        y: { stacked: true, beginAtZero: true, grid: { color: colors.line }, border: { display: false }, ticks: { color: colors.muted, precision: 0 } }
      });
      return {
        type: "bar",
        data: {
          labels: block.labels,
          datasets: block.series.map(function (item) {
            return { label: item.label, data: item.values, backgroundColor: toneColor(item.tone), borderRadius: 3, borderSkipped: false, maxBarThickness: 22 };
          })
        },
        options: options,
        values: block.totals
      };
    },

    levels: function (canvas, colors) {
      var block = payload.levels;
      var options = baseOptions(colors);
      options.indexAxis = "y";
      options.scales = axes(colors, {
        x: { beginAtZero: true, grid: { color: colors.line }, border: { display: false }, ticks: { color: colors.muted, precision: 0 } },
        y: { grid: { display: false }, border: { display: false }, ticks: { color: colors.text, font: { family: "Onest", size: 13 } } }
      });
      return {
        type: "bar",
        data: { labels: block.labels, datasets: [{ label: "Проверок", data: block.values, backgroundColor: block.tones.map(toneColor), borderRadius: 6, borderSkipped: false, maxBarThickness: 28 }] },
        options: options,
        values: block.values
      };
    }
  };

  function render() {
    live.forEach(function (chart) { chart.destroy(); });
    live = [];
    Chart.defaults.font.family = "Onest, sans-serif";
    var colors = palette();
    document.querySelectorAll("[data-chart]").forEach(function (box) {
      var build = builders[box.dataset.chart];
      var canvas = box.querySelector("canvas");
      if (!build || !canvas) return;
      var config = build(canvas, colors);
      box.classList.toggle("is-empty", !hasData(config.values));
      live.push(new Chart(canvas, config));
    });
  }

  render();
  document.addEventListener("sn:theme", render);
})();
