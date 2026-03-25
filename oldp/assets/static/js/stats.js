// Case statistics: fetch API data, render bar charts on canvas, populate tables.
(function () {
  var config = {};
  // Translatable strings (defaults to English, overridden via config.strings)
  var S = {
    total: 'Total',
    cases: 'cases',
    date: 'Date',
    count: 'Count',
    name: 'Name',
    other: 'Other',
    errorLoading: 'Error loading statistics',
    selectState: 'Please select a state to view court statistics.',
    ly: 'ly'
  };
  var COLORS = [
    '#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8',
    '#6f42c1', '#fd7e14', '#20c997', '#e83e8c', '#6c757d',
    '#0056b3', '#1e7e34', '#c82333', '#d39e00'
  ];

  var StatsApp = {};
  window.StatsApp = StatsApp;

  StatsApp.init = function (cfg) {
    config = cfg;
    if (cfg.strings) {
      for (var k in cfg.strings) { if (cfg.strings.hasOwnProperty(k)) S[k] = cfg.strings[k]; }
    }
    // Pre-fill filters from URL query params
    var params = new URLSearchParams(window.location.search);
    var dateAfter = document.getElementById('stats-date-after');
    var dateBefore = document.getElementById('stats-date-before');
    var bucket = document.getElementById('stats-bucket');
    var state = document.getElementById('stats-state');

    if (params.get('date_after') && dateAfter) dateAfter.value = params.get('date_after');
    if (params.get('date_before') && dateBefore) dateBefore.value = params.get('date_before');
    if (params.get('bucket') && bucket) bucket.value = params.get('bucket');
    if (params.get('court__state') && state) state.value = params.get('court__state');

    var btn = document.getElementById('stats-apply-btn');
    if (btn) btn.addEventListener('click', function () { StatsApp.fetchAndRender(); });

    StatsApp.fetchAndRender();
  };

  StatsApp.setRange = function (months) {
    var dateAfter = document.getElementById('stats-date-after');
    var dateBefore = document.getElementById('stats-date-before');
    if (months === 0) {
      // All time
      dateAfter.value = '';
      dateBefore.value = '';
    } else {
      var today = new Date();
      var start = new Date(today);
      start.setMonth(start.getMonth() - months);
      dateAfter.value = start.toISOString().slice(0, 10);
      dateBefore.value = today.toISOString().slice(0, 10);
    }
    StatsApp.fetchAndRender();
  };

  function buildApiUrl() {
    var url = config.apiBaseUrl + config.apiEndpoint;
    var params = [];
    var dateAfter = document.getElementById('stats-date-after');
    var dateBefore = document.getElementById('stats-date-before');
    var bucket = document.getElementById('stats-bucket');
    var state = document.getElementById('stats-state');

    if (dateAfter && dateAfter.value) params.push('date_after=' + dateAfter.value);
    if (dateBefore && dateBefore.value) params.push('date_before=' + dateBefore.value);
    if (bucket && bucket.value) params.push('bucket=' + bucket.value);
    if (state && state.value) params.push('court__state=' + state.value);

    if (params.length) url += '?' + params.join('&');
    return url;
  }

  function updateDownloadLink(url) {
    var link = document.getElementById('stats-download-link');
    if (link) {
      link.href = url + (url.indexOf('?') >= 0 ? '&' : '?') + 'format=json';
    }
  }

  function show(id) { var el = document.getElementById(id); if (el) el.style.display = ''; }
  function hide(id) { var el = document.getElementById(id); if (el) el.style.display = 'none'; }

  StatsApp.fetchAndRender = function () {
    // by_court requires state
    if (config.pageKey === 'by_court') {
      var state = document.getElementById('stats-state');
      if (!state || !state.value) {
        hide('stats-loading');
        hide('stats-content');
        var err = document.getElementById('stats-error');
        if (err) {
          err.textContent = S.selectState;
          err.style.display = '';
        }
        return;
      }
    }

    hide('stats-error');
    hide('stats-content');
    show('stats-loading');

    var url = buildApiUrl();
    updateDownloadLink(url);

    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        hide('stats-loading');
        show('stats-content');

        var summary = document.getElementById('stats-summary');
        if (summary) {
          summary.textContent = S.total + ': ' + data.total.toLocaleString() + ' ' + S.cases;
          if (data.filters) {
            summary.textContent += ' (' + data.filters.date_after + ' – ' + data.filters.date_before + ', ' + data.filters.bucket + S.ly + ')';
          }
        }

        if (data.buckets) {
          renderOverviewChart(data);
          renderOverviewTable(data);
        } else if (data.results) {
          renderGroupedChart(data);
          renderGroupedTable(data);
        }
      })
      .catch(function (err) {
        hide('stats-loading');
        hide('stats-content');
        var errEl = document.getElementById('stats-error');
        if (errEl) {
          errEl.textContent = S.errorLoading + ': ' + err.message;
          errEl.style.display = '';
        }
      });
  };

  // ── Overview chart (single series) ──

  function renderOverviewChart(data) {
    var labels = data.buckets.map(function (b) { return b.date; });
    var values = data.buckets.map(function (b) { return b.count; });
    drawBarChart(labels, [{ label: S.cases, values: values, color: COLORS[0] }]);
    // No legend for single series
    var legend = document.getElementById('stats-legend');
    if (legend) legend.innerHTML = '';
  }

  function renderOverviewTable(data) {
    var container = document.getElementById('stats-table-container');
    if (!container) return;
    var html = '<table class="table table-striped table-hover table-sm">';
    html += '<thead><tr><th>' + esc(S.date) + '</th><th class="text-right">' + esc(S.count) + '</th></tr></thead><tbody>';
    data.buckets.forEach(function (b) {
      html += '<tr><td>' + esc(b.date) + '</td><td class="text-right">' + b.count.toLocaleString() + '</td></tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  // ── Grouped chart (stacked bars) ──

  function renderGroupedChart(data) {
    // Collect all unique dates across items
    var dateSet = {};
    data.results.forEach(function (item) {
      item.buckets.forEach(function (b) { dateSet[b.date] = true; });
    });
    var labels = Object.keys(dateSet).sort();

    // Build datasets (top items by total)
    var maxItems = 10;
    var datasets = [];
    var shown = data.results.slice(0, maxItems);
    shown.forEach(function (item, i) {
      var valMap = {};
      item.buckets.forEach(function (b) { valMap[b.date] = b.count; });
      datasets.push({
        label: item.name,
        color: COLORS[i % COLORS.length],
        values: labels.map(function (d) { return valMap[d] || 0; })
      });
    });

    // If more items, aggregate the rest as "Other"
    if (data.results.length > maxItems) {
      var otherMap = {};
      labels.forEach(function (d) { otherMap[d] = 0; });
      data.results.slice(maxItems).forEach(function (item) {
        item.buckets.forEach(function (b) { otherMap[b.date] = (otherMap[b.date] || 0) + b.count; });
      });
      datasets.push({
        label: S.other,
        color: '#adb5bd',
        values: labels.map(function (d) { return otherMap[d] || 0; })
      });
    }

    drawBarChart(labels, datasets);
    renderLegend(datasets);
  }

  function renderGroupedTable(data) {
    var container = document.getElementById('stats-table-container');
    if (!container) return;
    var html = '<table class="table table-striped table-hover table-sm">';
    html += '<thead><tr><th>' + esc(S.name) + '</th><th class="text-right">' + esc(S.total) + '</th></tr></thead><tbody>';
    data.results.forEach(function (item) {
      html += '<tr><td>' + esc(item.name) + '</td><td class="text-right">' + item.total.toLocaleString() + '</td></tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  // ── Legend ──

  function renderLegend(datasets) {
    var legend = document.getElementById('stats-legend');
    if (!legend) return;
    var html = '<div style="display: flex; flex-wrap: wrap; gap: 10px; font-size: 0.85rem;">';
    datasets.forEach(function (ds) {
      html += '<span><span style="display:inline-block;width:12px;height:12px;background:' + ds.color + ';margin-right:4px;border-radius:2px;"></span>' + esc(ds.label) + '</span>';
    });
    html += '</div>';
    legend.innerHTML = html;
  }

  // ── Canvas bar chart ──

  function drawBarChart(labels, datasets) {
    var canvas = document.getElementById('stats-chart');
    if (!canvas) return;
    var container = document.getElementById('stats-chart-container');

    var dpr = window.devicePixelRatio || 1;
    var width = container.clientWidth;
    var height = Math.min(400, Math.max(250, width * 0.4));

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';

    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    var pad = { top: 20, right: 20, bottom: 60, left: 60 };
    var chartW = width - pad.left - pad.right;
    var chartH = height - pad.top - pad.bottom;

    // Compute max stacked value
    var maxVal = 0;
    for (var i = 0; i < labels.length; i++) {
      var stackTotal = 0;
      datasets.forEach(function (ds) { stackTotal += ds.values[i] || 0; });
      if (stackTotal > maxVal) maxVal = stackTotal;
    }
    if (maxVal === 0) maxVal = 1;

    // Nice y-axis scale
    var yStep = niceStep(maxVal, 5);
    var yMax = Math.ceil(maxVal / yStep) * yStep;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Gridlines and y-axis labels
    ctx.strokeStyle = '#e9ecef';
    ctx.fillStyle = '#6c757d';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (var v = 0; v <= yMax; v += yStep) {
      var y = pad.top + chartH - (v / yMax) * chartH;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartW, y);
      ctx.stroke();
      ctx.fillText(formatNumber(v), pad.left - 8, y);
    }

    // Axes
    ctx.strokeStyle = '#6c757d';
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + chartH);
    ctx.lineTo(pad.left + chartW, pad.top + chartH);
    ctx.stroke();

    // Bars
    var barGroupWidth = chartW / labels.length;
    var barWidth = Math.max(2, barGroupWidth * 0.7);
    var barOffset = (barGroupWidth - barWidth) / 2;

    for (var i = 0; i < labels.length; i++) {
      var x = pad.left + i * barGroupWidth + barOffset;
      var stackY = pad.top + chartH;

      for (var d = 0; d < datasets.length; d++) {
        var val = datasets[d].values[i] || 0;
        var barH = (val / yMax) * chartH;
        if (barH < 1 && val > 0) barH = 1;

        ctx.fillStyle = datasets[d].color;
        ctx.fillRect(x, stackY - barH, barWidth, barH);
        stackY -= barH;
      }
    }

    // X-axis labels
    ctx.fillStyle = '#6c757d';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';

    var labelSkip = Math.max(1, Math.ceil(labels.length / (chartW / 50)));
    for (var i = 0; i < labels.length; i++) {
      if (i % labelSkip !== 0 && i !== labels.length - 1) continue;
      var x = pad.left + i * barGroupWidth + barGroupWidth / 2;
      var y = pad.top + chartH + 8;

      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(-Math.PI / 4);
      ctx.textAlign = 'right';
      ctx.fillText(labels[i], 0, 0);
      ctx.restore();
    }

    // Tooltip on hover
    setupTooltip(canvas, labels, datasets, pad, chartW, chartH, barGroupWidth, yMax);
  }

  function setupTooltip(canvas, labels, datasets, pad, chartW, chartH, barGroupWidth, yMax) {
    var tooltip = document.getElementById('stats-tooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.id = 'stats-tooltip';
      tooltip.style.cssText = 'position:absolute;background:rgba(0,0,0,0.85);color:#fff;padding:6px 10px;border-radius:4px;font-size:12px;pointer-events:none;display:none;z-index:10;white-space:nowrap;';
      canvas.parentElement.appendChild(tooltip);
    }

    canvas.onmousemove = function (e) {
      var rect = canvas.getBoundingClientRect();
      var mx = e.clientX - rect.left;
      var my = e.clientY - rect.top;

      var barIdx = Math.floor((mx - pad.left) / barGroupWidth);
      if (barIdx < 0 || barIdx >= labels.length || mx < pad.left || mx > pad.left + chartW || my < pad.top || my > pad.top + chartH) {
        tooltip.style.display = 'none';
        return;
      }

      var lines = ['<strong>' + esc(labels[barIdx]) + '</strong>'];
      var total = 0;
      datasets.forEach(function (ds) {
        var v = ds.values[barIdx] || 0;
        total += v;
        if (datasets.length > 1) {
          lines.push('<span style="color:' + ds.color + '">&#9632;</span> ' + esc(ds.label) + ': ' + v.toLocaleString());
        }
      });
      if (datasets.length === 1) {
        lines.push(total.toLocaleString() + ' ' + esc(S.cases));
      } else {
        lines.push('<strong>' + esc(S.total) + ': ' + total.toLocaleString() + '</strong>');
      }

      tooltip.innerHTML = lines.join('<br>');
      tooltip.style.display = '';
      tooltip.style.left = (mx + 12) + 'px';
      tooltip.style.top = (my - 10) + 'px';
    };

    canvas.onmouseleave = function () {
      tooltip.style.display = 'none';
    };
  }

  // ── Helpers ──

  function niceStep(maxVal, targetSteps) {
    var rough = maxVal / targetSteps;
    var mag = Math.pow(10, Math.floor(Math.log10(rough)));
    var norm = rough / mag;
    var step;
    if (norm <= 1) step = 1;
    else if (norm <= 2) step = 2;
    else if (norm <= 5) step = 5;
    else step = 10;
    return step * mag;
  }

  function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'K';
    return String(n);
  }

  function esc(s) {
    var el = document.createElement('span');
    el.textContent = s || '';
    return el.innerHTML;
  }

  // Responsive resize
  var resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { StatsApp.fetchAndRender(); }, 250);
  });
})();
