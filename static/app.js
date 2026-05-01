let selectedCode = '';
let selectedName = '';
let stockCache = [];
let currentDays = 90;
const history = JSON.parse(localStorage.getItem('analysisHistory') || '[]');

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

renderHistory();
loadStockCache();

async function loadStockCache() {
  try {
    stockCache = await (await fetch('/api/v1/stock/stocks')).json();
  } catch (e) {}
}

function filterStocks(q) {
  if (!q || !stockCache.length) return [];
  const l = q.toLowerCase();
  return stockCache.filter(s => s.code.includes(l) || s.name.toLowerCase().includes(l)).slice(0, 10);
}

function setupSearch(inputEl, dropdownEl) {
  inputEl.addEventListener('input', () => {
    const q = inputEl.value.trim();
    if (/^\d{6}$/.test(q)) {
      const m = stockCache.find(s => s.code === q);
      selectStock(q, m ? m.name : '');
      return dropdownEl.classList.remove('show');
    }
    if (!q) { dropdownEl.classList.remove('show'); if (!selectedCode) $('#analyzeBtn').disabled = true; return; }
    renderDropdown(dropdownEl, filterStocks(q));
  });
  inputEl.addEventListener('focus', () => {
    const q = inputEl.value.trim();
    if (q && !/^\d{6}$/.test(q)) { const m = filterStocks(q); if (m.length) renderDropdown(dropdownEl, m); }
  });
  inputEl.addEventListener('blur', () => setTimeout(() => dropdownEl.classList.remove('show'), 200));
  inputEl.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    dropdownEl.classList.remove('show');
    if (selectedCode) { $('#analyzeBtn').click(); }
    else if (/^\d{6}$/.test(inputEl.value.trim())) { selectStock(inputEl.value.trim(), ''); $('#analyzeBtn').click(); }
  });
}

function renderDropdown(el, items) {
  if (!items.length) { el.classList.remove('show'); return; }
  el.innerHTML = items.map(s =>
    `<div class="search-dropdown-item" data-code="${s.code}" data-name="${s.name}">
      <span class="s-code">${s.code}</span><span>${s.name}</span></div>`
  ).join('');
  el.querySelectorAll('.search-dropdown-item').forEach(it =>
    it.addEventListener('mousedown', () => { selectStock(it.dataset.code, it.dataset.name); el.classList.remove('show'); })
  );
  el.classList.add('show');
}

function selectStock(code, name) {
  selectedCode = code; selectedName = name;
  $('#mainSearch').value = `${code} ${name}`;
  $('#sidebarSearch').value = `${code} ${name}`;
  $('#analyzeBtn').disabled = false;
}

setupSearch($('#mainSearch'), $('#mainDropdown'));
setupSearch($('#sidebarSearch'), $('#sidebarDropdown'));

$('#analyzeBtn').addEventListener('click', () => { if (selectedCode) startAnalysis(selectedCode, selectedName); });

async function startAnalysis(code, name) {
  $('#progressArea').classList.remove('hidden');
  $('#resultsArea').classList.add('hidden');
  $('#emptyState').classList.add('hidden');
  $('#analyzeBtn').disabled = true;
  resetProgress();

  try {
    const { task_id } = await fetch('/api/v1/analysis/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code })
    }).then(r => r.json());

    const sse = new EventSource(`/api/v1/analysis/status/${task_id}`);
    let done = false;
    sse.addEventListener('status', async (e) => {
      const t = JSON.parse(e.data);
      updateProgress(t.status);
      if (t.status === 'completed' && !done) { done = true; sse.close(); await onComplete(code, name, t.result); }
      else if (t.status === 'failed' && !done) { done = true; sse.close(); alert('分析失败: ' + (t.error || '')); $('#progressArea').classList.add('hidden'); $('#emptyState').classList.remove('hidden'); }
    });
    sse.onerror = () => sse.close();
  } catch (e) { alert('请求失败'); $('#progressArea').classList.add('hidden'); }
}

function resetProgress() {
  $$('.progress-step').forEach(s => s.classList.remove('active', 'done'));
  $('#progressText').textContent = '正在准备...';
}

function updateProgress(status) {
  const steps = ['collecting', 'analyzing', 'training', 'predicting'];
  const idx = steps.indexOf(status);
  $$('.progress-step').forEach(s => {
    const si = steps.indexOf(s.dataset.step);
    s.classList.remove('active', 'done');
    if (si < idx) s.classList.add('done');
    if (si === idx) s.classList.add('active');
  });
  $('#progressText').textContent = { collecting: '采集数据', analyzing: '计算指标', training: '训练模型', predicting: '生成预测' }[status] || status;
}

async function onComplete(code, name, result) {
  $('#progressArea').classList.add('hidden');
  $('#resultsArea').classList.remove('hidden');
  $('#analyzeBtn').disabled = false;

  renderCoreResult(code, name, result);

  try {
    const res = await fetch(`/api/v1/stocks/${code}/full`);
    const full = await res.json();
    renderProfile(full.profile || {});
    renderPlatform(full.platform || {});
    renderSentiment(full.sentiment || {});
    renderResearch(full.research || []);
    renderNews(full.news || []);
    loadChart(code);
    loadPatience(code);
    loadFinancials(code);
  } catch (e) {}
}

function renderCoreResult(code, name, result) {
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].code === code && history[i].date === result.date) { history.splice(i, 1); break; }
  }
  history.unshift({ code, name, trend: result.trend, confidence: result.confidence, date: result.date });
  if (history.length > 50) history.pop();
  localStorage.setItem('analysisHistory', JSON.stringify(history));
  renderHistory();

  let tl = t => t === 'up' ? '看涨' : t === 'down' ? '看跌' : '横盘';

  $('#statsRow').innerHTML = `
    <div class="stat-card"><div class="label">当前价格</div><div class="value">${result.latest_price?.toFixed(2) || '--'}</div></div>
    <div class="stat-card"><div class="label">趋势预测</div><div class="value ${result.trend}">${tl(result.trend)}</div></div>
    <div class="stat-card"><div class="label">置信度</div><div class="value">${(result.confidence * 100).toFixed(1)}%</div></div>
    <div class="stat-card"><div class="label">分析日期</div><div class="value" style="font-size:1rem;">${result.date}</div></div>`;

  let sug = '<div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;">操作建议</div>';
  if (result.trend === 'up') sug += '<div style="font-size:1.5rem;font-weight:700;color:var(--up-color);">买入</div>';
  else if (result.trend === 'down') sug += '<div style="font-size:1.5rem;font-weight:700;color:var(--down-color);">卖出/观望</div>';
  else sug += '<div style="font-size:1.5rem;font-weight:700;color:var(--text-muted);">观望</div>';
  sug += `<div style="margin-top:12px;font-size:0.8rem;color:var(--text-muted);">模型: ${result.model}</div>`;
  $('#suggestionCard').innerHTML = sug;

  let tr = '<div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;">关键指标</div>';
  tr += _row('MA5', result.latest_ma5?.toFixed(2));
  tr += _row('RSI(14)', result.latest_rsi?.toFixed(1));
  tr += _row('MACD DIF', result.latest_macd_dif?.toFixed(3));
  tr += _row('MACD BAR', result.latest_macd_bar?.toFixed(3));
  $('#trendCard').innerHTML = tr;

  _drawGauge(result.confidence);

  const p = result.latest_price || 0;
  if (p > 0) {
    $('#stratIdeal').textContent = (p * 0.95).toFixed(2);
    $('#stratSecond').textContent = (p * 0.97).toFixed(2);
    $('#stratStop').textContent = (p * 0.92).toFixed(2);
    $('#stratTarget').textContent = (p * 1.10).toFixed(2);
  }

  const bc = (result.latest_macd_bar || 0) > 0 ? 'var(--up-color)' : 'var(--down-color)';
  $('#indicatorsRow').innerHTML = `
    <div class="indicator"><span class="ind-name">MA5</span><span class="ind-value">${result.latest_ma5?.toFixed(2) || '--'}</span></div>
    <div class="indicator"><span class="ind-name">RSI(14)</span><span class="ind-value">${result.latest_rsi?.toFixed(1) || '--'}</span></div>
    <div class="indicator"><span class="ind-name">MACD DIF</span><span class="ind-value">${result.latest_macd_dif?.toFixed(3) || '--'}</span></div>
    <div class="indicator"><span class="ind-name">MACD BAR</span><span class="ind-value" style="color:${bc}">${result.latest_macd_bar?.toFixed(3) || '--'}</span></div>`;
}

function _row(label, val) {
  return `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);"><span style="color:var(--text-muted);">${label}</span><span>${val || '--'}</span></div>`;
}

function _drawGauge(val) {
  $('#gaugeCard').innerHTML = `<svg viewBox="0 0 200 120" style="width:100%;">
    <g transform="translate(100,100)">
      <circle class="gauge-bg" cx="0" cy="0" r="70" stroke-width="12" stroke-dasharray="220 440"/>
      <circle class="gauge-fill" cx="0" cy="0" r="70" stroke-width="12" stroke="${val > 0.6 ? '#ef4444' : val > 0.4 ? '#f59e0b' : '#64748b'}" stroke-dasharray="${val * 220} 440" filter="url(#glow)"/>
    </g>
    <text x="100" y="85" text-anchor="middle" class="gauge-text">${(val * 100).toFixed(0)}%</text>
    <text x="100" y="105" text-anchor="middle" class="gauge-label">置信度</text>
    <defs><filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
  </svg>`;
}

function renderProfile(d) {
  $('#profIndustry').textContent = d.industry || '--';
  $('#profTotalMv').textContent = d.total_mv || '--';
  $('#profPE').textContent = d.pe || '--';
  $('#profPB').textContent = d.pb || '--';
  $('#profListed').textContent = d.listed_date || '--';
  $('#indName').textContent = d.industry || '--';
  if (d.industry_change_pct && d.industry_change_pct !== '--') {
    const v = parseFloat(d.industry_change_pct);
    $('#indChange').textContent = d.industry_change_pct + '%';
    $('#indChange').style.color = v > 0 ? 'var(--up-color)' : v < 0 ? 'var(--down-color)' : '';
  }
}

function renderPlatform(d) {
  if (d.em_hot_rank) $('#platHot').textContent = d.em_hot_rank;
  if (d.main_5d_net) { $('#platFlow').textContent = d.main_5d_net; $('#platFlow').style.color = d.main_5d_net.startsWith('-') ? 'var(--down-color)' : 'var(--up-color)'; }
  if (d.xq_followers) $('#platXq').textContent = d.xq_followers;
}

function renderSentiment(d) {
  if (d.north_hold_value) $('#northValue').textContent = d.north_hold_value;
  if (d.north_10d_change_pct) { $('#northTrend').textContent = d.north_10d_change_pct; $('#northTrend').style.color = d.north_10d_change_pct.startsWith('+') ? 'var(--up-color)' : 'var(--down-color)'; }
  if (d.fund_count) $('#fundCount').textContent = d.fund_count + '家';
  if (d.market_north_5d) { $('#marketNorth').textContent = d.market_north_5d; $('#marketNorth').style.color = d.market_north_5d.startsWith('+') ? 'var(--up-color)' : 'var(--down-color)'; }
}

function renderResearch(items) {
  if (!items.length) { $('#researchList').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">暂无研报</div>'; return; }
  $('#researchList').innerHTML = items.map(r => `
    <div style="padding:8px 0; border-bottom:1px solid var(--border-subtle);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
        <span style="font-size:0.75rem; color:var(--accent-blue);">${r.org}</span>
        <span style="font-size:0.7rem; color:var(--text-muted);">${r.date}</span>
      </div>
      <div style="font-size:0.8rem; color:var(--text-primary); line-height:1.4;">${r.title}</div>
      <span style="font-size:0.7rem; padding:1px 6px; border-radius:4px; background:${r.rating && (r.rating.includes('买入')||r.rating.includes('增持'))?'rgba(239,68,68,0.1)':'rgba(100,116,139,0.1)'}; color:${r.rating && (r.rating.includes('买入')||r.rating.includes('增持'))?'var(--up-color)':'var(--text-muted)'};">${r.rating || ''}</span>
    </div>`).join('');
}

function renderNews(items) {
  if (!items.length) { $('#newsList').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">暂无资讯</div>'; return; }
  $('#newsList').innerHTML = items.map(n => `
    <div style="padding:8px 0; border-bottom:1px solid var(--border-subtle);">
      <div style="font-size:0.7rem; color:var(--text-muted); margin-bottom:2px;">${n.time}</div>
      <div style="font-size:0.8rem; color:var(--text-primary); line-height:1.4;">${n.title}</div>
    </div>`).join('');
}

function loadChart(code) {
  $('#chartContainer').innerHTML = `<div class="loading-overlay" data-lazy="kline" style="cursor:pointer;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5"><rect x="3" y="3" width="18" height="18" rx="3"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
    <span>点击加载K线图</span></div>`;
}

function loadPatience(code) {
  $('#patienceChart').innerHTML = `<div class="loading-overlay" data-lazy="patience" style="cursor:pointer;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    <span>点击加载资金耐心图</span></div>`;
}

function loadFinancials(code) {
  $('#finChart').innerHTML = `<div class="loading-overlay" data-lazy="financials" style="cursor:pointer;">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5"><rect x="3" y="12" width="3" height="9" rx="1"/><rect x="10" y="7" width="3" height="14" rx="1"/><rect x="17" y="3" width="3" height="18" rx="1"/></svg>
    <span>点击加载财务</span></div>`;
  $('#roeChart').innerHTML = `<div class="loading-overlay" data-lazy="financials" style="cursor:pointer;">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
    <span>点击加载ROE</span></div>`;
}

let _plotlyLoading = false;
async function ensurePlotly() {
  if (typeof Plotly !== 'undefined') return;
  if (_plotlyLoading) { await new Promise(r => setTimeout(r, 100)); return ensurePlotly(); }
  _plotlyLoading = true;
  return new Promise(resolve => {
    const s = document.createElement('script');
    s.src = '/static/plotly.min.js';
    s.onload = () => { _plotlyLoading = false; resolve(); };
    document.head.appendChild(s);
  });
}

async function renderKline(code) {
  const c = $('#chartContainer');
  c.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
  await ensurePlotly();
  try {
    const d = await (await fetch(`/api/v1/stocks/${code}/chart?days=${currentDays}`)).json();
    if (d.error) { c.innerHTML = '<div class="loading-overlay"><span>暂无数据</span></div>'; return; }
    const traces = [{
      type: 'candlestick', name: 'K线', x: d.dates, open: d.open, high: d.high, low: d.low, close: d.close,
      increasing: { line: { color: '#ef4444' } }, decreasing: { line: { color: '#10b981' } }, yaxis: 'y'
    }];
    if (d.ma_5?.some(v => v)) traces.push({ type: 'scatter', mode: 'lines', name: 'MA5', x: d.dates, y: d.ma_5, line: { color: '#f59e0b', width: 1 }, yaxis: 'y' });
    if (d.ma_20?.some(v => v)) traces.push({ type: 'scatter', mode: 'lines', name: 'MA20', x: d.dates, y: d.ma_20, line: { color: '#8b5cf6', width: 1 }, yaxis: 'y' });
    if (d.volume?.some(v => v > 0)) {
      const colors = d.close.map((cl, i) => i > 0 && cl >= d.close[i - 1] ? '#ef4444' : '#10b981');
      traces.push({ type: 'bar', name: '成交量', x: d.dates, y: d.volume, marker: { color: colors }, yaxis: 'y2', opacity: 0.3 });
    }
    Plotly.newPlot(c, traces, {
      paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#94a3b8', size: 10 },
      xaxis: { gridcolor: 'rgba(255,255,255,0.04)', type: 'date' },
      yaxis: { title: '价格', gridcolor: 'rgba(255,255,255,0.04)', side: 'right' },
      yaxis2: { title: '成交量', overlaying: 'y', side: 'left', showgrid: false },
      margin: { l: 10, r: 50, t: 10, b: 30 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, dragmode: 'pan'
    }, { responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false });
  } catch (e) { c.innerHTML = '<div class="loading-overlay"><span>加载失败</span></div>'; }
}

async function _renderPatience(code) {
  const c = $('#patienceChart');
  c.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
  await ensurePlotly();
  try {
    const d = await (await fetch(`/api/v1/stocks/${code}/patience`)).json();
    if (d.irm_rate) $('#irmBadge').textContent = '回复率' + d.irm_rate;
    const traces = [];
    if (d.holders?.length) traces.push({ type: 'scatter', mode: 'lines+markers', name: '股东人数', x: d.holders.map(h => h.date), y: d.holders.map(h => h.count), line: { color: '#8b5cf6', width: 2 }, marker: { size: 4 }, yaxis: 'y' });
    if (d.turnover?.length) traces.push({ type: 'scatter', mode: 'lines', name: '换手率', x: d.turnover.slice(-60).map(t => t.date), y: d.turnover.slice(-60).map(t => t.value), line: { color: 'rgba(6,182,212,0.4)', width: 1, dash: 'dot' }, yaxis: 'y2' });
    if (d.irm_monthly?.length) traces.push({ type: 'bar', name: '董秘提问', x: d.irm_monthly.map(m => m.month), y: d.irm_monthly.map(m => m.count), marker: { color: 'rgba(245,158,11,0.3)' }, yaxis: 'y3' });
    Plotly.newPlot(c, traces, {
      paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#94a3b8', size: 9 },
      xaxis: { gridcolor: 'rgba(255,255,255,0.04)' }, yaxis: { title: '股东人数', gridcolor: 'rgba(255,255,255,0.04)', side: 'right' },
      yaxis2: { title: '换手率', overlaying: 'y', side: 'left', showgrid: false },
      yaxis3: { title: '提问', overlaying: 'y', anchor: 'free', position: 0.05, showgrid: false },
      margin: { l: 50, r: 50, t: 10, b: 30 }, legend: { orientation: 'h', y: 1.2 }
    }, { responsive: true, displayModeBar: false, displaylogo: false });
  } catch (e) { c.innerHTML = '<div class="loading-overlay"><span>加载失败</span></div>'; }
}

async function renderFinancials(code) {
  await ensurePlotly();
  const d = await (await fetch(`/api/v1/stocks/${code}/financials`)).json();

  const t1 = [];
  if (d.revenue?.length) t1.push({ type: 'bar', name: '营收(亿)', x: d.revenue.map(r => r.date), y: d.revenue.map(r => r.value), marker: { color: 'rgba(59,130,246,0.4)' }, yaxis: 'y' });
  if (d.profit?.length) t1.push({ type: 'scatter', mode: 'lines+markers', name: '净利润(亿)', x: d.profit.map(r => r.date), y: d.profit.map(r => r.value), line: { color: '#10b981', width: 2 }, marker: { size: 5 }, yaxis: 'y2' });
  Plotly.newPlot('finChart', t1, {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#94a3b8', size: 9 },
    xaxis: { gridcolor: 'rgba(255,255,255,0.04)' }, yaxis: { title: '营收(亿)', gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis2: { title: '净利润(亿)', overlaying: 'y', side: 'right', showgrid: false },
    margin: { l: 50, r: 50, t: 10, b: 30 }, legend: { orientation: 'h', y: 1.15 }
  }, { responsive: true, displayModeBar: false, displaylogo: false });

  const t2 = [];
  if (d.roe?.length) t2.push({ type: 'scatter', mode: 'lines+markers', name: 'ROE(%)', x: d.roe.map(r => r.date), y: d.roe.map(r => r.value), line: { color: '#f59e0b', width: 2 }, marker: { size: 5 }, yaxis: 'y' });
  if (d.valuation?.length) t2.push({ type: 'scatter', mode: 'lines', name: '市值(亿)', x: d.valuation.slice(-120).map(r => r.date), y: d.valuation.slice(-120).map(r => r.value), line: { color: 'rgba(6,182,212,0.3)', width: 1 }, yaxis: 'y2' });
  Plotly.newPlot('roeChart', t2, {
    paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#94a3b8', size: 9 },
    xaxis: { gridcolor: 'rgba(255,255,255,0.04)' }, yaxis: { title: 'ROE(%)', gridcolor: 'rgba(255,255,255,0.04)' },
    yaxis2: { title: '市值(亿)', overlaying: 'y', side: 'right', showgrid: false },
    margin: { l: 50, r: 50, t: 10, b: 30 }, legend: { orientation: 'h', y: 1.15 }
  }, { responsive: true, displayModeBar: false, displaylogo: false });
}

document.addEventListener('click', (e) => {
  const lazy = e.target.closest('[data-lazy]');
  if (!lazy || !selectedCode) return;
  const type = lazy.dataset.lazy;
  if (type === 'kline') renderKline(selectedCode);
  else if (type === 'patience') _renderPatience(selectedCode);
  else if (type === 'financials') renderFinancials(selectedCode);
});

document.addEventListener('click', (e) => {
  if (!e.target.classList.contains('chart-range-btn')) return;
  $$('.chart-range-btn').forEach(b => { b.classList.remove('active'); b.style.borderColor = 'var(--border-card)'; b.style.background = 'transparent'; b.style.color = 'var(--text-secondary)'; });
  e.target.classList.add('active');
  e.target.style.borderColor = 'var(--accent-blue)'; e.target.style.background = 'rgba(59,130,246,0.12)'; e.target.style.color = 'var(--accent-blue)';
  currentDays = +e.target.dataset.days;
  if (selectedCode) loadChart(selectedCode);
});

function renderHistory() {
  const list = $('#historyList');
  if (!history.length) { list.innerHTML = '<li style="color:var(--text-muted);font-size:0.8rem;padding:8px 12px;">暂无记录</li>'; return; }
  list.innerHTML = history.map((h, i) => `
    <li class="history-item" data-idx="${i}" style="position:relative;">
      <span class="code" style="cursor:pointer;">${h.code}</span><span class="name" style="cursor:pointer;flex:1;">${h.name || ''}</span>
      <span class="trend ${h.trend}" style="cursor:pointer;">${h.trend === 'up' ? '看涨' : h.trend === 'down' ? '看跌' : '横盘'}</span>
      <button class="del-btn" data-idx="${i}" style="opacity:0;position:absolute;right:4px;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:0.8rem;padding:2px 4px;">x</button>
    </li>`).join('');
  list.querySelectorAll('.history-item .code, .history-item .name, .history-item .trend').forEach(el => {
    el.addEventListener('click', (e) => {
      const h = history[e.target.closest('.history-item').dataset.idx];
      selectStock(h.code, h.name);
      startAnalysis(h.code, h.name);
    });
  });
  list.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('mouseenter', () => item.querySelector('.del-btn').style.opacity = '1');
    item.addEventListener('mouseleave', () => item.querySelector('.del-btn').style.opacity = '0');
  });
  list.querySelectorAll('.del-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      history.splice(btn.dataset.idx, 1);
      localStorage.setItem('analysisHistory', JSON.stringify(history));
      renderHistory();
    });
  });
}

function clearHistory() {
  history.length = 0;
  localStorage.removeItem('analysisHistory');
  renderHistory();
}

$$('.mode-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    $$('.mode-tab').forEach(t => { t.classList.remove('active'); t.style.background = 'transparent'; t.style.color = 'var(--text-secondary)'; t.style.fontWeight = '500'; });
    tab.classList.add('active'); tab.style.background = 'rgba(59,130,246,0.15)'; tab.style.color = 'var(--accent-blue)'; tab.style.fontWeight = '600';
    const m = tab.dataset.mode;
    if (m === 'single') { $('#singleSearchSection').classList.remove('hidden'); $('#screenPanel').classList.add('hidden'); $('#macroPanel').classList.add('hidden'); $('#resultsArea').classList.add('hidden'); $('#progressArea').classList.add('hidden'); if (!selectedCode) $('#emptyState').classList.remove('hidden'); }
    else if (m === 'macro') { $('#singleSearchSection').classList.add('hidden'); $('#screenPanel').classList.add('hidden'); $('#macroPanel').classList.remove('hidden'); $('#resultsArea').classList.add('hidden'); $('#emptyState').classList.add('hidden'); loadMacro(); }
    else { $('#singleSearchSection').classList.add('hidden'); $('#macroPanel').classList.add('hidden'); $('#screenPanel').classList.remove('hidden'); $('#resultsArea').classList.add('hidden'); $('#emptyState').classList.add('hidden'); loadStrategies(); }
  });
});

async function loadStrategies() {
  try {
    const list = await (await fetch('/api/v1/screen/strategies')).json();
    $('#strategySelect').innerHTML = list.map(s => `<option value="${s.name}">${s.name} (${s.category}) - ${s.description}</option>`).join('');
  } catch (e) { $('#strategySelect').innerHTML = '<option value="">加载失败</option>'; }
}

$('#screenBtn').addEventListener('click', async () => {
  const strat = $('#strategySelect').value;
  if (!strat) return;
  $('#screenBtn').disabled = true;
  $('#screenProgress').classList.remove('hidden');
  $('#screenResults').classList.add('hidden');
  try {
    const data = await fetch('/api/v1/screen/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strategy: strat })
    }).then(r => r.json());
    if (data.error) { alert('选股失败: ' + data.error); return; }
    $('#screenMeta').textContent = `${data.strategy} | ${data.snapshot_source} | ${data.snapshot_count}只 -> 初筛${data.after_filter_count}只 -> 精选${data.picks_count}只`;
    $('#screenTableBody').innerHTML = data.picks.map(p => `
      <tr style="border-bottom:1px solid var(--border-subtle);cursor:pointer;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'"
          onclick="selectStock('${p.code}','${p.name}');document.querySelectorAll('.mode-tab')[0].click();startAnalysis('${p.code}','${p.name}')">
        <td style="padding:10px 12px;font-family:monospace;color:var(--accent-blue);">${p.code}</td>
        <td style="padding:10px 12px;">${p.name}</td>
        <td style="padding:10px 12px;text-align:right;">${p.price?.toFixed(2) || '--'}</td>
        <td style="padding:10px 12px;text-align:right;color:${(p.change_pct||0)>0?'var(--up-color)':'var(--down-color)'};">${p.change_pct != null ? p.change_pct.toFixed(2)+'%' : '--'}</td>
        <td style="padding:10px 12px;text-align:right;">${p.pe_ratio?.toFixed(1) || '--'}</td>
        <td style="padding:10px 12px;text-align:right;">${p.pb_ratio?.toFixed(2) || '--'}</td>
        <td style="padding:10px 12px;text-align:right;font-weight:600;">${p.final_score}</td>
        <td style="padding:10px 12px;color:var(--text-muted);font-size:0.8rem;">${p.industry || ''}</td>
      </tr>`).join('');
    $('#screenResults').classList.remove('hidden');
  } catch (e) { alert('选股失败'); }
  finally { $('#screenBtn').disabled = false; $('#screenProgress').classList.add('hidden'); }
});

async function loadMacro() {
  const el = $('#macroIndicators');
  el.innerHTML = '<div style="grid-column:1/6;text-align:center;padding:20px;"><div class="spinner"></div></div>';
  loadHeadlines();
  try {
    const d = await (await fetch('/api/v1/macro/overview')).json();
    if (d.error) { el.innerHTML = '<span style="color:var(--text-muted);">加载失败</span>'; return; }
    const items = [
      { label: 'PMI制造业', val: d.pmi_manufacturing, color: parseFloat(d.pmi_manufacturing) >= 50 ? 'var(--accent-cyan)' : 'var(--text-muted)' },
      { label: 'CPI同比', val: d.cpi_yoy, sub: d.cpi_date },
      { label: 'LPR 1Y/5Y', val: (d.lpr_1y || '') + ' / ' + (d.lpr_5y || ''), sub: d.lpr_date },
      { label: 'M2同比', val: d.m2_yoy },
      { label: '美联储利率', val: d.fed_rate, sub: d.fed_date },
      { label: '美债10Y', val: d.us_10y_yield || '--' },
    ];
    el.innerHTML = items.map(i => `
      <div style="text-align:center;padding:8px;">
        <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;">${i.label}</div>
        <div style="font-size:1.1rem;font-weight:700;${i.color ? 'color:'+i.color+';' : ''}">${i.val || '--'}</div>
        ${i.sub ? `<div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px;">${i.sub}</div>` : ''}
      </div>`).join('');
  } catch (e) { el.innerHTML = '<span style="color:var(--text-muted);">加载失败</span>'; }
}

async function loadHeadlines() {
  const el = $('#headlinesList');
  el.innerHTML = '<div style="text-align:center;padding:12px;"><div class="spinner"></div></div>';
  try {
    const kw = ($('#newsKeyword')?.value || '').trim();
    const url = kw ? `/api/v1/news/headlines?q=${encodeURIComponent(kw)}` : '/api/v1/news/headlines';
    const data = await (await fetch(url)).json();
    if (!data.length) { el.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;padding:12px;">暂无资讯</div>'; return; }
    el.innerHTML = data.map(n => `
      <div style="padding:6px 0;border-bottom:1px solid var(--border-subtle);display:flex;gap:8px;">
        <span style="font-size:0.65rem;color:var(--text-muted);min-width:60px;">${n.time}</span>
        <span style="font-size:0.8rem;color:var(--text-primary);">${n.title}</span>
      </div>`).join('');
  } catch (e) { el.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;padding:12px;">加载失败</div>'; }
}
