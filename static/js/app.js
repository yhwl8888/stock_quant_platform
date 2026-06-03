let currentCode = '';
let klineData = [];
let chart = null;
let indicatorsData = null;
    let activeIndicators = ['ma5', 'ma10', 'ma20', 'ma60'];
let isLoading = false;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    chart = echarts.init(document.getElementById('kline-chart'), 'dark');
    await loadStrategies();
    setupEventListeners();
    handleResize();
});

async function loadStrategies() {
    try {
        const resp = await fetch('/api/strategies');
        const data = await resp.json();
        const select = document.getElementById('btStrategy');
        select.innerHTML = '';
        for (const [key, strategy] of Object.entries(data)) {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = strategy.name;
            option.title = strategy.desc;
            select.appendChild(option);
        }
    } catch (e) {
        console.error('加载策略失败:', e);
    }
}

function setupEventListeners() {
    document.getElementById('searchBtn').addEventListener('click', async () => {
        const results = document.getElementById('searchResults');
        if (results.classList.contains('show') && results.children.length > 0) {
            results.children[0].click();
        } else {
            await doSearch();
            const r = document.getElementById('searchResults');
            if (r.classList.contains('show') && r.children.length > 0) {
                r.children[0].click();
            }
        }
    });
    document.getElementById('searchInput').addEventListener('keydown', async e => {
        if (e.key === 'Enter') {
            const results = document.getElementById('searchResults');
            if (results.classList.contains('show') && results.children.length > 0) {
                results.children[0].click();
            } else {
                await doSearch();
                const r = document.getElementById('searchResults');
                if (r.classList.contains('show') && r.children.length > 0) {
                    r.children[0].click();
                }
            }
        }
    });
    document.getElementById('searchInput').addEventListener('input', debounce(doSearch, 300));

    document.querySelectorAll('.indicator-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const group = tab.dataset.group;
            const ind = tab.dataset.indicator;

            if (group === 'boll') {
                const bollInds = ['boll_upper', 'boll_middle', 'boll_lower'];
                const wasActive = tab.classList.contains('active');
                tab.classList.toggle('active');
                bollInds.forEach(b => {
                    if (wasActive) {
                        activeIndicators = activeIndicators.filter(i => i !== b);
                    } else {
                        if (!activeIndicators.includes(b)) activeIndicators.push(b);
                    }
                });
            } else {
                tab.classList.toggle('active');
                if (tab.classList.contains('active')) {
                    if (!activeIndicators.includes(ind)) activeIndicators.push(ind);
                } else {
                    activeIndicators = activeIndicators.filter(i => i !== ind);
                }
            }
            renderChart();
        });
    });

    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });

    document.getElementById('backtestBtn').addEventListener('click', runBacktest);
    document.getElementById('optimizeBtn').addEventListener('click', runOptimize);
    document.getElementById('walkforwardBtn').addEventListener('click', runWalkforward);
    document.getElementById('scanBtn').addEventListener('click', runScan);
    document.getElementById('scanPool').addEventListener('change', e => {
        document.getElementById('scanCustomBox').style.display = e.target.value === '__custom__' ? 'block' : 'none';
    });
    populateScanStrategies();
}

function handleResize() {
    window.addEventListener('resize', () => { if (chart) chart.resize(); });
}

function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

async function doSearch() {
    const q = document.getElementById('searchInput').value.trim();
    if (!q) return;
    const results = document.getElementById('searchResults');
    results.innerHTML = '<div class="spinner">搜索中...</div>';
    results.classList.add('show');
    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        results.innerHTML = '';
        if (data.data && data.data.length > 0) {
            data.data.forEach(item => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.innerHTML = `<span class="search-result-code">${item.code}</span><span class="search-result-name">${item.name}</span>`;
                div.addEventListener('click', () => {
                    document.getElementById('searchInput').value = `${item.code}`;
                    results.classList.remove('show');
                    loadStock(item.code);
                });
                results.appendChild(div);
            });
            results.classList.add('show');
        } else if (/^\d{4,6}$/.test(q)) {
            results.classList.remove('show');
            loadStock(q.padStart(6, '0'));
        } else {
            results.innerHTML = '<div class="search-result-item" style="color:var(--text-muted);cursor:default">未找到匹配股票，请输入完整代码或名称</div>';
            results.classList.add('show');
        }
    } catch (e) {
        results.classList.remove('show');
        console.error(e);
    }
}

// Close search results on outside click
document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-box')) {
        document.getElementById('searchResults').classList.remove('show');
    }
});

async function loadStock(code) {
    currentCode = code;
    isLoading = true;
    document.getElementById('searchResults').classList.remove('show');
    document.getElementById('stockName').textContent = '加载中...';
    document.getElementById('q-price').innerHTML = '<div class="spinner"></div>';
    document.getElementById('scoreCircle').textContent = '--';
    document.getElementById('scoreSignal').textContent = '加载中';
    document.getElementById('srDisplay').innerHTML = '<div class="spinner"></div>';
    document.getElementById('backtestResults').innerHTML = '';

    const results = await Promise.allSettled([
        fetch(`/api/quote/${code}`),
        fetch(`/api/kline/${code}?days=250`),
        fetch(`/api/analysis/${code}`),
        fetch(`/api/indicators/${code}`),
    ]);

    const [quoteResult, klineResult, analysisResult, indicatorsResult] = results;

    if (klineResult.status === 'fulfilled') {
        try {
            const kline = await klineResult.value.json();
            if (kline && kline.data && kline.data.length > 0) {
                klineData = kline.data;
                renderChart();
                renderATRInfo();
            } else if (kline && kline.error) {
                showError('kline-chart', kline.error);
            } else {
                showError('kline-chart', '暂无K线数据');
            }
        } catch { /* ignore */ }
    } else {
        showError('kline-chart', 'K线数据加载失败');
    }

    if (quoteResult.status === 'fulfilled') {
        try {
            const quote = await quoteResult.value.json();
            if (quote && quote.price) {
                document.getElementById('stockName').textContent = `${code} ${quote.name || ''}`;
                renderQuote(quote);
            }
        } catch { /* ignore */ }
    }

    if (analysisResult.status === 'fulfilled') {
        try {
            const analysis = await analysisResult.value.json();
            if (analysis && analysis.总分 !== undefined) renderAnalysis(analysis);
        } catch { /* ignore */ }
    }

    if (indicatorsResult.status === 'fulfilled') {
        try {
            const indicators = await indicatorsResult.value.json();
            if (indicators) {
                indicatorsData = indicators;
                renderSupportResistance(indicators);
                renderATRInfo();
            }
        } catch { /* ignore */ }
    }

    isLoading = false;
}

function renderQuote(quote) {
    const isUp = quote.change_pct >= 0;
    const cls = isUp ? 'price-up' : 'price-down';
    const sign = isUp ? '+' : '';

    document.getElementById('q-price').innerHTML = `<div class="quote-value ${cls}">${quote.price.toFixed(2)}</div>`;
    document.getElementById('q-change').innerHTML =
        `<div class="quote-value ${cls}">${sign}${quote.change_pct.toFixed(2)}%</div>`;
    document.getElementById('q-open').innerHTML = `<div class="quote-value">${quote.open.toFixed(2)}</div>`;
    document.getElementById('q-high').innerHTML = `<div class="quote-value ${cls}">${quote.high.toFixed(2)}</div>`;
    document.getElementById('q-low').innerHTML = `<div class="quote-value ${cls}">${quote.low.toFixed(2)}</div>`;
    document.getElementById('q-volume').innerHTML = `<div class="quote-value">${(quote.volume / 10000).toFixed(0)}万</div>`;
    document.getElementById('q-pre-close').innerHTML = `<div class="quote-value">${quote.pre_close.toFixed(2)}</div>`;
}

function renderAnalysis(analysis) {
    const total = analysis.总分;
    const signal = analysis.信号中文;

    let scoreCls = 'score-neutral';
    let signalCls = 'signal-neutral';
    if (signal === '强买入' || signal === '弱买入') {
        scoreCls = 'score-buy';
        signalCls = 'signal-buy';
    } else if (signal === '强卖出' || signal === '弱卖出') {
        scoreCls = 'score-sell';
        signalCls = 'signal-sell';
    }

    document.getElementById('scoreCircle').className = `score-circle ${scoreCls}`;
    document.getElementById('scoreCircle').textContent = total;
    document.getElementById('scoreSignal').className = `signal-badge ${signalCls}`;
    document.getElementById('scoreSignal').textContent = signal;

    const dims = [
        { key: '趋势', item: analysis.趋势 },
        { key: '超买超卖', item: analysis.超买超卖 },
        { key: '量价分析', item: analysis.量价分析 },
        { key: '运动与位置', item: analysis.运动与位置 },
    ];

    const container = document.getElementById('dimensionScores');
    container.innerHTML = dims.map(d => {
        const pct = d.item.max > 0 ? (d.item.score / d.item.max * 100) : 0;
        const color = pct >= 60 ? '#22c55e' : pct >= 40 ? '#eab308' : '#ef4444';
        return `
            <div class="dimension-item fade-in">
                <div class="dim-name">${d.key}</div>
                <div class="dim-score" style="color:${color}">${d.item.score}/${d.item.max}</div>
                <div class="dim-bar"><div class="dim-bar-fill" style="width:${pct}%;background:${color}"></div></div>
            </div>
        `;
    }).join('');

    // Show detail tooltips
    document.querySelectorAll('.dimension-item').forEach((el, i) => {
        el.title = dims[i].item.details ? Object.values(dims[i].item.details).map(v => v.desc).join('\n') : '';
    });
}

function renderSupportResistance(data) {
    const supports = data.support || [];
    const resistances = data.resistance || [];

    let html = '<div class="sr-display">';
    if (supports.length > 0) {
        html += supports.map(s => `<div class="sr-item sr-support">支撑 ${s}</div>`).join('');
    }
    if (resistances.length > 0) {
        html += resistances.map(r => `<div class="sr-item sr-resistance">阻力 ${r}</div>`).join('');
    }
    html += '</div>';
    document.getElementById('srDisplay').innerHTML = html;
}

function renderATRInfo() {
    if (!indicatorsData || !indicatorsData.atr) return;
    const atrVals = indicatorsData.atr.filter(v => v !== null);
    if (atrVals.length === 0) return;
    const currentATR = atrVals[atrVals.length - 1];
    const lastClose = klineData.length > 0 ? klineData[klineData.length - 1].close : 0;

    document.getElementById('atrValue').textContent = currentATR.toFixed(2);
    document.getElementById('atrStop').textContent = (lastClose - 2 * currentATR).toFixed(2);
    document.getElementById('atrTake').textContent = (lastClose + 3 * currentATR).toFixed(2);
}

function renderChart() {
    if (!klineData || klineData.length === 0 || !chart) return;

    const dates = klineData.map(d => d.date);
    const closes = klineData.map(d => d.close);
    const opens = klineData.map(d => d.open);
    const highs = klineData.map(d => d.high);
    const lows = klineData.map(d => d.low);
    const volumes = klineData.map(d => d.volume);

    const series = [];
    const legendData = [];

    // Candlestick
    series.push({
        name: 'K线',
        type: 'candlestick',
        data: klineData.map(d => [d.open, d.close, d.low, d.high]),
        itemStyle: {
            color: '#22c55e', color0: '#ef4444',
            borderColor: '#22c55e', borderColor0: '#ef4444',
        },
    });
    legendData.push('K线');

    // Indicator lines
    if (indicatorsData) {
        activeIndicators.forEach(ind => {
            const values = indicatorsData[ind];
            if (!values) return;
            const validData = values.map((v, i) => v !== null && v !== undefined ? [dates[i], v] : null)
                .filter(v => v !== null);

            let name = ind.toUpperCase();
            let color = '#3b82f6';
            if (ind === 'ma5') { name = 'MA5'; color = '#f59e0b'; }
            if (ind === 'ma10') { name = 'MA10'; color = '#3b82f6'; }
            if (ind === 'ma20') { name = 'MA20'; color = '#8b5cf6'; }
            if (ind === 'ma60') { name = 'MA60'; color = '#ec4899'; }
            if (ind === 'boll_upper') { name = 'BOLL上'; color = '#06b6d4'; }
            if (ind === 'boll_middle') { name = 'BOLL中'; color = '#22d3ee'; }
            if (ind === 'boll_lower') { name = 'BOLL下'; color = '#0891b2'; }
            if (ind === 'rsi') { name = 'RSI'; color = '#a855f7'; }
            if (ind === 'kdj_j') { name = 'KDJ-J'; color = '#14b8a6'; }

            legendData.push(name);
            const isIndicator = ind === 'rsi' || ind === 'kdj_j';
            series.push({
                name, type: 'line', data: validData,
                smooth: true, symbol: 'none',
                lineStyle: { width: 1.5, color },
                yAxisIndex: isIndicator ? 2 : 0,
                xAxisIndex: isIndicator ? 2 : 0,
            });
        });
    }

    // Volume
    const volumeData = volumes.map((v, i) => [dates[i], v, closes[i] >= opens[i] ? 1 : -1]);
    legendData.push('成交量');
    series.push({
        name: '成交量', type: 'bar',
        data: volumeData,
        xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: p => p.data[2] > 0 ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)' },
    });

    // MACD bar (on sub-chart with volume)
    if (indicatorsData && indicatorsData.macd_hist) {
        const macdData = indicatorsData.macd_hist
            .map((v, i) => v !== null && v !== undefined ? [dates[i], v] : null)
            .filter(v => v !== null);
        series.push({
            name: 'MACD', type: 'bar',
            data: macdData,
            xAxisIndex: 1, yAxisIndex: 1,
            itemStyle: { color: p => p.data[1] >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)' },
        });
        legendData.push('MACD');
    }

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(17, 24, 39, 0.9)',
            borderColor: 'rgba(255,255,255,0.1)',
            textStyle: { color: '#e2e8f0' },
        },
        legend: {
            data: legendData,
            textStyle: { color: '#94a3b8', fontSize: 11 },
            top: 0,
        },
        grid: [
            { left: '5%', right: '5%', top: '10%', height: '46%' },
            { left: '5%', right: '5%', top: '60%', height: '15%' },
            { left: '5%', right: '5%', top: '78%', height: '14%' },
        ],
        xAxis: [
            {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
                axisLabel: { color: '#64748b', fontSize: 10 },
                splitLine: { show: false },
                gridIndex: 0,
            },
            {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
                axisLabel: { show: false },
                gridIndex: 1,
            },
            {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
                axisLabel: { show: false },
                gridIndex: 2,
            },
        ],
        yAxis: [
            {
                scale: true,
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)', type: 'dashed' } },
                axisLabel: { color: '#64748b', fontSize: 10 },
                gridIndex: 0,
            },
            {
                scale: true,
                splitLine: { show: false },
                axisLabel: { color: '#64748b', fontSize: 10 },
                gridIndex: 1,
            },
            {
                scale: true,
                splitLine: { show: false },
                axisLabel: { color: '#64748b', fontSize: 10 },
                gridIndex: 2,
            },
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1, 2], start: Math.max(0, 100 - 30), end: 100 },
            {
                type: 'slider',
                xAxisIndex: [0, 1, 2],
                start: Math.max(0, 100 - 30),
                end: 100,
                bottom: '2%',
                borderColor: 'rgba(255,255,255,0.1)',
                backgroundColor: 'rgba(17,24,39,0.8)',
                dataBackground: {
                    areaStyle: { color: 'rgba(59,130,246,0.1)' },
                    lineStyle: { color: 'rgba(59,130,246,0.3)' },
                },
                selectedDataBackground: {
                    areaStyle: { color: 'rgba(59,130,246,0.2)' },
                    lineStyle: { color: 'rgba(59,130,246,0.5)' },
                },
                textStyle: { color: '#64748b' },
            },
        ],
        series,
    };

    chart.setOption(option, true);
}

function showError(elementId, msg) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = `<div class="error-box">${msg}</div>`;
}

async function runBacktest() {
    if (!currentCode) {
        alert('请先搜索并选择一只股票');
        return;
    }
    if (isLoading) return;

    const capital = parseFloat(document.getElementById('btCapital').value) || 10000;
    const tradeDays = parseInt(document.getElementById('btDays').value) || 60;
    const atrStop = parseFloat(document.getElementById('btStop').value) || 2.0;
    const atrTake = parseFloat(document.getElementById('btTake').value) || 3.0;
    const strategy = document.getElementById('btStrategy').value;

    document.getElementById('backtestResults').innerHTML = '<div class="spinner">回测计算中...</div>';

    try {
        const resp = await fetch('/api/backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: currentCode,
                capital,
                trade_days: tradeDays,
                atr_stop: atrStop,
                atr_take: atrTake,
                strategy: strategy,
                days: Math.max(tradeDays + 100, 250),
            }),
        });
        
        if (!resp.ok) {
            throw new Error(`服务器错误: ${resp.status}`);
        }
        
        const text = await resp.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            throw new Error(`响应解析失败: ${text.substring(0, 100)}`);
        }

        if (data.error) {
            document.getElementById('backtestResults').innerHTML = `<div class="error-box">${data.error}</div>`;
            return;
        }

        let html = `<div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:8px">策略: ${strategy}</div>`;
        if ((data.total_trades || 0) === 0) {
            html += `<div class="error-box" style="background:rgba(245,158,11,0.1);border-color:rgba(245,158,11,0.3);color:#f59e0b;margin-bottom:8px">
                ⚠️ 回测窗口内策略未触发任何交易。所有指标均为初始值。<br>
                <span style="font-size:0.8rem;color:var(--text-muted)">建议：增加回测天数、放宽策略阈值（如 RSI 超卖线提高），或点击"参数优化"自动搜索可用参数组合。</span>
            </div>`;
        }
        html += '<div class="metrics-grid">';
        const metrics = [
            { label: '初始资金', value: `¥${data.initial_capital?.toLocaleString()}` },
            { label: '期末资金', value: `¥${data.final_capital?.toLocaleString()}` },
            { label: '总收益率', value: data.total_return_str || `${data.total_return}%` },
            { label: '胜率', value: data.win_rate_str || `${data.win_rate}%` },
            { label: '夏普比率', value: data.sharpe_ratio },
            { label: '最大回撤', value: data.max_drawdown_str || `${data.max_drawdown}%` },
            { label: '盈亏比', value: data.win_loss_ratio },
            { label: '利润因子', value: data.profit_factor },
            { label: '交易次数', value: data.total_trades },
        ];
        metrics.forEach(m => {
            const color = m.label === '总收益率' ? (data.total_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') :
                         m.label === '最大回撤' ? 'var(--accent-red)' : 'var(--text-primary)';
            html += `
                <div class="metric-item">
                    <div class="metric-label">${m.label}</div>
                    <div class="metric-value" style="color:${color}">${m.value}</div>
                </div>
            `;
        });
        html += '</div>';

        // Trades table
        const sellTrades = (data.trades || []).filter(t => t.action === 'sell');
        if (sellTrades.length > 0) {
            html += '<h4 style="margin-top:16px;margin-bottom:8px;color:var(--text-secondary)">交易明细</h4>';
            html += '<div style="max-height:200px;overflow-y:auto">';
            html += '<table style="width:100%;font-size:0.85rem;border-collapse:collapse">';
            html += '<tr style="color:var(--text-muted)"><th style="padding:6px 8px;text-align:left">方向</th><th style="padding:6px 8px;text-align:left">价格</th><th style="padding:6px 8px;text-align:left">盈亏</th><th style="padding:6px 8px;text-align:left">原因</th></tr>';
            sellTrades.forEach(t => {
                const pnl = t.pnl || 0;
                const pnlCls = pnl >= 0 ? 'price-up' : 'price-down';
                html += `<tr><td style="padding:4px 8px">${t.reason || '卖出'}</td><td style="padding:4px 8px">${t.price?.toFixed(2)}</td><td style="padding:4px 8px" class="${pnlCls}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</td><td style="padding:4px 8px">${t.reason || '-'}</td></tr>`;
            });
            html += '</table></div>';
        }

        document.getElementById('backtestResults').innerHTML = html;
    } catch (e) {
        document.getElementById('backtestResults').innerHTML = `<div style="color:var(--accent-red)">回测请求失败: ${e.message}</div>`;
    }
}

async function runOptimize() {
    if (!currentCode) {
        alert('请先搜索并选择一只股票');
        return;
    }
    if (isLoading) return;

    const capital = parseFloat(document.getElementById('btCapital').value) || 10000;
    const tradeDays = parseInt(document.getElementById('btDays').value) || 60;
    const strategy = document.getElementById('btStrategy').value;

    document.getElementById('optimizeResults').innerHTML = '<div class="spinner">参数搜索中...</div>';
    document.getElementById('backtestResults').innerHTML = '';

    try {
        const resp = await fetch('/api/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: currentCode,
                capital,
                trade_days: tradeDays,
                strategy: strategy,
                metric: 'sharpe_ratio',
                days: Math.max(tradeDays + 100, 250),
            }),
        });
        
        if (!resp.ok) {
            throw new Error(`服务器错误: ${resp.status}`);
        }
        
        const text = await resp.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            throw new Error(`响应解析失败: ${text.substring(0, 100)}`);
        }

        if (data.error) {
            document.getElementById('optimizeResults').innerHTML = `<div class="error-box">${data.error}</div>`;
            return;
        }

        let html = `<div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:8px">策略: ${strategy} | 共扫描 ${data.tested}/${data.total_combinations} 种参数组合</div>`;

        const allZero = data.top && data.top.length > 0 && data.top.every(t => (t.metrics?.total_trades || 0) === 0);
        const noResults = !data.top || data.top.length === 0;
        if (allZero || noResults) {
            html += `<div class="error-box" style="background:rgba(245,158,11,0.1);border-color:rgba(245,158,11,0.3);color:#f59e0b;margin-bottom:8px">
                ⚠️ 所有参数组合在当前回测窗口内均未触发交易。<br>
                <span style="font-size:0.8rem;color:var(--text-muted)">建议：增加回测天数（如 120-250），或换一只波动更大的股票测试该策略。</span>
            </div>`;
        }

        if (data.best) {
            html += '<h4 style="color:var(--accent-green);margin-bottom:8px">🏆 最优参数（样本内 IS）</h4>';
            html += '<div class="metrics-grid">';
            const bestParams = data.best_params || {};
            for (const [k, v] of Object.entries(bestParams)) {
                html += `<div class="metric-item"><div class="metric-label">${k}</div><div class="metric-value" style="font-size:0.9rem">${v}</div></div>`;
            }
            html += '</div>';
            html += '<div class="metrics-grid" style="margin-top:8px">';
            const bestMetrics = data.best.metrics || {};
            for (const [k, v] of Object.entries(bestMetrics)) {
                if (v === null || v === undefined) continue;
                const val = typeof v === 'number' ? (k.includes('return') || k.includes('rate') || k.includes('drawdown') ? `${v.toFixed(2)}%` : v.toFixed(4)) : v;
                html += `<div class="metric-item"><div class="metric-label">${k}</div><div class="metric-value" style="font-size:0.9rem">${val}</div></div>`;
            }
            html += '</div>';
        }

        if (data.oos) {
            const oos = data.oos;
            const isRet = data.best?.metrics?.total_return ?? 0;
            const degBadge = data.overfit_warning
                ? `<span style="background:rgba(239,68,68,0.15);color:#ef4444;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px">⚠ 疑似过拟合</span>`
                : (data.degradation_pct !== null && data.degradation_pct > 0
                    ? `<span style="background:rgba(245,158,11,0.15);color:#f59e0b;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px">降级 ${data.degradation_pct}%</span>`
                    : `<span style="background:rgba(34,197,94,0.15);color:#22c55e;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px">✓ OOS 稳健</span>`);
            html += `<h4 style="color:var(--accent-cyan);margin-top:16px;margin-bottom:8px">🧪 样本外验证（OOS，最后 ${Math.round((data.oos_ratio||0.2)*100)}% 数据 / ${oos.trade_days} 天）${degBadge}</h4>`;
            html += '<div class="metrics-grid">';
            const oosFields = [
                { k: 'total_return', label: 'OOS 收益率', fmt: v => `${v.toFixed(2)}%`, color: oos.total_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
                { k: 'sharpe_ratio', label: 'OOS 夏普', fmt: v => v.toFixed(2), color: oos.sharpe_ratio >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
                { k: 'max_drawdown', label: 'OOS 回撤', fmt: v => `${v.toFixed(2)}%`, color: 'var(--accent-red)' },
                { k: 'win_rate', label: 'OOS 胜率', fmt: v => `${v.toFixed(2)}%` },
                { k: 'total_trades', label: 'OOS 交易', fmt: v => `${v}笔` },
                { k: 'final_capital', label: 'OOS 终值', fmt: v => `¥${v.toLocaleString()}` },
            ];
            oosFields.forEach(f => {
                const val = oos[f.k];
                if (val === null || val === undefined) return;
                html += `<div class="metric-item"><div class="metric-label">${f.label}</div><div class="metric-value" style="font-size:0.9rem;color:${f.color || 'var(--text-primary)'}">${f.fmt(val)}</div></div>`;
            });
            html += '</div>';
            if (data.overfit_warning) {
                html += `<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:8px 12px;margin-top:8px;font-size:0.8rem;color:#fca5a5">
                    ⚠ 警告：样本内表现亮眼但样本外明显劣化，最优参数可能仅是历史数据的偶然拟合。<br>
                    <span style="color:var(--text-muted)">建议：用"Walk-Forward 验证"做多窗口稳健性测试，或换更宽参数网格再扫一次。</span>
                </div>`;
            }
        }

        if (data.top && data.top.length > 1) {
            html += '<h4 style="color:var(--text-secondary);margin-top:16px;margin-bottom:8px">📊 Top 10 排名</h4>';
            html += '<div style="max-height:300px;overflow-y:auto;font-size:0.8rem">';
            html += '<table style="width:100%;border-collapse:collapse">';
            html += '<tr style="color:var(--text-muted)"><th style="padding:4px 6px;text-align:left">#</th><th style="padding:4px 6px;text-align:left">参数</th><th style="padding:4px 6px;text-align:right">夏普</th><th style="padding:4px 6px;text-align:right">收益</th><th style="padding:4px 6px;text-align:right">回撤</th></tr>';
            data.top.forEach((item, idx) => {
                const paramsStr = Object.entries(item.params).map(([k, v]) => `${k}=${v}`).join(' ');
                const m = item.metrics;
                html += `<tr style="border-bottom:1px solid var(--border-glass)"><td style="padding:4px 6px">${idx + 1}</td><td style="padding:4px 6px;color:var(--text-muted)">${paramsStr}</td><td style="padding:4px 6px;text-align:right;color:${item.score > 1 ? 'var(--accent-green)' : 'var(--accent-red)'}">${item.score.toFixed(2)}</td><td style="padding:4px 6px;text-align:right">${m.total_return.toFixed(2)}%</td><td style="padding:4px 6px;text-align:right;color:var(--accent-red)">${m.max_drawdown.toFixed(2)}%</td></tr>`;
            });
            html += '</table></div>';
        }

        document.getElementById('optimizeResults').innerHTML = html;
    } catch (e) {
        document.getElementById('optimizeResults').innerHTML = `<div style="color:var(--accent-red)">参数优化失败: ${e.message}</div>`;
    }
}


async function runWalkforward() {
    if (!currentCode) { alert('请先搜索并选择一只股票'); return; }
    if (isLoading) return;

    const capital = parseFloat(document.getElementById('btCapital').value) || 10000;
    const strategy = document.getElementById('btStrategy').value;
    const container = document.getElementById('walkforwardResults');
    container.innerHTML = '<div class="spinner">Walk-Forward 滚动验证中（多窗口扫描，需 1-3 分钟）...</div>';

    try {
        const resp = await fetch('/api/walkforward', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: currentCode, capital, strategy,
                days: 500, n_windows: 4, train_ratio: 0.67, metric: 'sharpe_ratio',
            }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data.error) { container.innerHTML = `<div class="error-box">${data.error}</div>`; return; }

        const s = data.summary || {};
        const isOk = s.oos_return_avg >= 0 && s.oos_sharpe_avg >= 0;
        const judge = isOk
            ? `<span style="background:rgba(34,197,94,0.15);color:#22c55e;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px">✓ 跨窗口稳健</span>`
            : `<span style="background:rgba(239,68,68,0.15);color:#ef4444;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-left:8px">⚠ 样本外失效</span>`;

        let html = `<h4 style="color:var(--accent-cyan);margin-bottom:8px">🧪 Walk-Forward 多窗口验证（${data.n_windows} 窗口）${judge}</h4>`;
        html += '<div class="metrics-grid">';
        const summFields = [
            { k: 'is_return_avg', label: 'IS 收益均值', fmt: v => `${v.toFixed(2)}%`, color: s.is_return_avg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
            { k: 'oos_return_avg', label: 'OOS 收益均值', fmt: v => `${v.toFixed(2)}%`, color: s.oos_return_avg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
            { k: 'is_sharpe_avg', label: 'IS 夏普均值', fmt: v => v.toFixed(2) },
            { k: 'oos_sharpe_avg', label: 'OOS 夏普均值', fmt: v => v.toFixed(2), color: s.oos_sharpe_avg >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' },
            { k: 'oos_total_trades', label: 'OOS 总交易', fmt: v => `${v}笔` },
            { k: 'degradation_pct', label: 'IS→OOS 降级', fmt: v => `${v.toFixed(2)}%`, color: s.degradation_pct > 0 ? 'var(--accent-yellow)' : 'var(--accent-green)' },
        ];
        summFields.forEach(f => {
            const v = s[f.k];
            if (v === null || v === undefined) return;
            html += `<div class="metric-item"><div class="metric-label">${f.label}</div><div class="metric-value" style="font-size:0.9rem;color:${f.color || 'var(--text-primary)'}">${f.fmt(v)}</div></div>`;
        });
        html += '</div>';

        html += '<h4 style="margin-top:16px;margin-bottom:8px;color:var(--text-secondary)">📊 各窗口明细</h4>';
        html += '<div style="overflow-x:auto"><table style="width:100%;font-size:0.78rem;border-collapse:collapse">';
        html += '<tr style="color:var(--text-muted)"><th style="padding:4px 6px;text-align:left">窗口</th><th style="padding:4px 6px;text-align:right">IS 收益</th><th style="padding:4px 6px;text-align:right">IS 夏普</th><th style="padding:4px 6px;text-align:right">OOS 收益</th><th style="padding:4px 6px;text-align:right">OOS 夏普</th><th style="padding:4px 6px;text-align:right">OOS 胜率</th><th style="padding:4px 6px;text-align:right">OOS 回撤</th><th style="padding:4px 6px;text-align:right">交易</th></tr>';
        (data.windows || []).forEach(w => {
            const oosColor = w.oos_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            html += `<tr style="border-bottom:1px solid var(--border-glass)">
                <td style="padding:4px 6px">W${w.window}</td>
                <td style="padding:4px 6px;text-align:right">${w.is_return.toFixed(2)}%</td>
                <td style="padding:4px 6px;text-align:right">${w.is_sharpe.toFixed(2)}</td>
                <td style="padding:4px 6px;text-align:right;color:${oosColor}">${w.oos_return.toFixed(2)}%</td>
                <td style="padding:4px 6px;text-align:right;color:${oosColor}">${w.oos_sharpe.toFixed(2)}</td>
                <td style="padding:4px 6px;text-align:right">${w.oos_win_rate.toFixed(2)}%</td>
                <td style="padding:4px 6px;text-align:right;color:var(--accent-red)">${w.oos_max_dd.toFixed(2)}%</td>
                <td style="padding:4px 6px;text-align:right">${w.oos_trades}</td>
            </tr>`;
        });
        html += '</table></div>';

        if (!isOk) {
            html += `<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:8px 12px;margin-top:10px;font-size:0.8rem;color:#fca5a5">
                ⚠ 多个窗口 OOS 表现劣化，该策略/参数不具备跨时段稳健性，<b>不建议实盘</b>。
            </div>`;
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div style="color:var(--accent-red)">Walk-Forward 失败: ${e.message}</div>`;
    }
}


async function populateScanStrategies() {
    try {
        const resp = await fetch('/api/strategies');
        const data = await resp.json();
        const select = document.getElementById('scanStrategy');
        select.innerHTML = '';
        for (const [key, strat] of Object.entries(data)) {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = strat.name;
            select.appendChild(opt);
        }
    } catch (e) { console.error('加载扫描策略失败:', e); }
}


async function runScan() {
    const strategy = document.getElementById('scanStrategy').value;
    const pool = document.getElementById('scanPool').value;
    const minScore = parseInt(document.getElementById('scanMinScore').value) || 0;
    const days = parseInt(document.getElementById('scanDays').value) || 200;
    const container = document.getElementById('scanResults');

    const body = { strategy, min_score: minScore, days };
    if (pool === '__custom__') {
        const raw = document.getElementById('scanCustomCodes').value.trim();
        const codes = raw.split(/[,，\s]+/).map(c => c.trim()).filter(Boolean);
        if (!codes.length) { container.innerHTML = '<div class="error-box">请输入至少一个股票代码</div>'; return; }
        body.codes = codes;
    } else {
        body.pool = pool;
    }

    container.innerHTML = '<div class="spinner">扫描中… 每只股票需拉取 K 线数据，4 线程并行。<br><span style="font-size:0.8rem;color:var(--text-muted)">预设池约 10-30 秒，动态市场池（500 只采样）约 60-90 秒。</span></div>';
    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const txt = await resp.text();
            container.innerHTML = `<div class="error-box">扫描失败: ${txt.substring(0,200)}</div>`;
            return;
        }
        const data = await resp.json();
        if (data.error) { container.innerHTML = `<div class="error-box">${data.error}</div>`; return; }

        const hits = data.hits || [];
        const ranked = data.ranked || [];

        const skipped = data.skipped || 0;
        let html = `<div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:8px">
            池容量 ${data.pool_size} · 有效扫描 ${data.scanned} · 跳过 ${skipped} (停牌/退市/无效)
            · 信号命中 <b style="color:var(--accent-cyan)">${hits.length}</b> 只
        </div>`;

        if (hits.length > 0) {
            html += '<h4 style="color:var(--accent-green);margin-top:12px;margin-bottom:6px">🟢 策略信号命中 (' + strategy + ')</h4>';
            html += '<table style="width:100%;font-size:0.85rem;border-collapse:collapse">';
            html += '<tr style="color:var(--text-muted)"><th style="padding:6px 8px;text-align:left">代码</th><th style="padding:6px 8px;text-align:right">现价</th><th style="padding:6px 8px;text-align:right">总分</th><th style="padding:6px 8px;text-align:left">评分信号</th><th style="padding:6px 8px;text-align:right">止损</th><th style="padding:6px 8px;text-align:right">止盈</th><th style="padding:6px 8px;text-align:left">操作</th></tr>';
            hits.forEach(h => {
                const tagCls = h.signal_label?.includes('买入') ? 'tag-buy' : h.signal_label?.includes('卖出') ? 'tag-sell' : 'tag-watch';
                html += `<tr style="border-bottom:1px solid var(--border-glass);background:rgba(34,197,94,0.04)">
                    <td style="padding:6px 8px;font-weight:600">${h.code}</td>
                    <td style="padding:6px 8px;text-align:right">${h.price}</td>
                    <td style="padding:6px 8px;text-align:right;color:${h.total_score >= 60 ? 'var(--accent-green)' : 'var(--accent-yellow)'}">${h.total_score}</td>
                    <td style="padding:6px 8px"><span class="tag ${tagCls}">${h.signal_label || '-'}</span> <span class="tag tag-buy" style="font-size:0.7rem;margin-left:4px">策略触发</span></td>
                    <td style="padding:6px 8px;text-align:right;color:var(--accent-red)">${h.stop_price ?? '-'}</td>
                    <td style="padding:6px 8px;text-align:right;color:var(--accent-green)">${h.take_price ?? '-'}</td>
                    <td style="padding:6px 8px"><a href="#" data-code="${h.code}" class="scan-load-link" style="color:var(--accent-cyan);text-decoration:none">分析 →</a></td>
                </tr>`;
            });
            html += '</table>';
        }

        if (ranked.length > 0) {
            html += `<h4 style="color:var(--text-secondary);margin-top:16px;margin-bottom:6px">📋 全池排名（按综合评分降序）<span style="font-size:0.75rem;color:var(--text-muted);font-weight:400"> — 带 <span class="tag tag-buy" style="font-size:0.65rem">策略触发</span> 标签的已被当前策略选中</span></h4>`;
            html += '<div style="max-height:400px;overflow-y:auto"><table style="width:100%;font-size:0.85rem;border-collapse:collapse">';
            html += '<tr style="color:var(--text-muted);position:sticky;top:0;background:var(--bg-card)"><th style="padding:6px 8px;text-align:left">#</th><th style="padding:6px 8px;text-align:left">代码</th><th style="padding:6px 8px;text-align:right">现价</th><th style="padding:6px 8px;text-align:right">总分</th><th style="padding:6px 8px;text-align:left">评分信号</th><th style="padding:6px 8px;text-align:right">趋势</th><th style="padding:6px 8px;text-align:right">量价</th><th style="padding:6px 8px;text-align:left">操作</th></tr>';
            ranked.forEach((h, idx) => {
                const tagCls = h.signal_label?.includes('买入') ? 'tag-buy' : h.signal_label?.includes('卖出') ? 'tag-sell' : 'tag-watch';
                const stratTriggered = h.signal_triggered ? '<span class="tag tag-buy" style="font-size:0.65rem;margin-left:4px">策略触发</span>' : '';
                const bgStyle = h.signal_triggered ? 'background:rgba(34,197,94,0.04)' : '';
                html += `<tr style="border-bottom:1px solid var(--border-glass);${bgStyle}">
                    <td style="padding:6px 8px;color:var(--text-muted)">${idx + 1}</td>
                    <td style="padding:6px 8px;font-weight:600">${h.code}</td>
                    <td style="padding:6px 8px;text-align:right">${h.price}</td>
                    <td style="padding:6px 8px;text-align:right;color:${h.total_score >= 60 ? 'var(--accent-green)' : 'var(--accent-yellow)'}">${h.total_score}</td>
                    <td style="padding:6px 8px"><span class="tag ${tagCls}">${h.signal_label || '-'}</span>${stratTriggered}</td>
                    <td style="padding:6px 8px;text-align:right">${h.trend_score ?? '-'}</td>
                    <td style="padding:6px 8px;text-align:right">${h.volume_score ?? '-'}</td>
                    <td style="padding:6px 8px"><a href="#" data-code="${h.code}" class="scan-load-link" style="color:var(--accent-cyan);text-decoration:none">分析 →</a></td>
                </tr>`;
            });
            html += '</table></div>';
        }
        container.innerHTML = html;
        container.querySelectorAll('.scan-load-link').forEach(a => {
            a.addEventListener('click', e => {
                e.preventDefault();
                const code = a.dataset.code;
                document.getElementById('searchInput').value = code;
                loadStock(code);
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });
        });
    } catch (e) {
        container.innerHTML = `<div style="color:var(--accent-red)">扫描请求失败: ${e.message}</div>`;
    }
}
