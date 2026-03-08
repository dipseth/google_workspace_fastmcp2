"""Feedback dashboard visualization for card patterns.

Renders a rich, dark-themed HTML dashboard with Chart.js visualizations
showing embedding vector statistics, DSL tree structure, and similar patterns
when a user submits card feedback.

All visualization is client-side via Chart.js CDN. No new Python dependencies.
"""

import html
import json


def render_dashboard_page(
    data: dict, feedback: str, feedback_type: str, message: str
) -> str:
    """Render the full feedback dashboard HTML page.

    Args:
        data: Enriched pattern data from FeedbackLoop.get_pattern_dashboard_data()
        feedback: "positive" or "negative"
        feedback_type: "content", "form", or ""
        message: Confirmation message to display

    Returns:
        Complete HTML string for the dashboard page.
    """
    payload = data.get("payload", {})
    vectors = data.get("vectors", {})
    similar = data.get("similar_patterns", [])
    symbol_map = data.get("symbol_map", {})

    # Safely serialize data for JS consumption
    # json.dumps escapes </script> by encoding < as \u003c
    js_data = json.dumps(
        {
            "cardId": data.get("card_id", ""),
            "payload": payload,
            "vectors": vectors,
            "similarPatterns": similar,
            "symbolMap": symbol_map,
            "feedback": feedback,
            "feedbackType": feedback_type,
        },
        default=str,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pattern Feedback Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>{_CSS}</style>
</head>
<body>
    {_section_header(message, feedback, feedback_type)}
    {_section_metadata(payload, data.get("card_id", ""), symbol_map)}
    <div class="two-col">
        {_section_dsl_tree(payload.get("card_description", ""))}
        {_section_radar_chart(vectors)}
    </div>
    {_section_activations(vectors)}
    {_section_similar(similar)}
    {_section_footer()}
    <script id="dash-data" type="application/json">{js_data}</script>
    <script>
    const DASH_DATA = JSON.parse(document.getElementById('dash-data').textContent);
    {_JS}
    </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_header(message: str, feedback: str, feedback_type: str) -> str:
    emoji = "\U0001f44d" if feedback == "positive" else "\U0001f44e"
    accent = "#4ade80" if feedback == "positive" else "#f87171"
    type_label = ""
    if feedback_type == "content":
        type_label = "Content feedback recorded"
    elif feedback_type == "form":
        type_label = "Layout feedback recorded"

    return f"""<header class="dash-header">
    <span class="header-emoji">{emoji}</span>
    <h1 style="color:{accent}">{_esc(message)}</h1>
    {f'<p class="type-label">{_esc(type_label)}</p>' if type_label else ""}
</header>"""


def _section_metadata(payload: dict, card_id: str, symbol_map: dict) -> str:
    desc = payload.get("card_description", "N/A")
    paths = payload.get("parent_paths", [])
    ts = payload.get("timestamp", "")
    content_fb = payload.get("content_feedback", "")
    form_fb = payload.get("form_feedback", "")

    paths_html = (
        ", ".join(f"<code>{_esc(p)}</code>" for p in paths[:5])
        if paths
        else "<em>none</em>"
    )

    fb_pills = ""
    if content_fb:
        c = "#4ade80" if content_fb == "positive" else "#f87171"
        fb_pills += f'<span class="pill" style="background:{c}20;color:{c}">content: {_esc(content_fb)}</span> '
    if form_fb:
        c = "#4ade80" if form_fb == "positive" else "#f87171"
        fb_pills += f'<span class="pill" style="background:{c}20;color:{c}">form: {_esc(form_fb)}</span>'

    return f"""<section class="card-surface">
    <h2>Pattern Metadata</h2>
    <div class="meta-grid">
        <div class="meta-item"><span class="meta-label">Card ID</span><code class="meta-value">{_esc(card_id[:12])}...</code></div>
        <div class="meta-item"><span class="meta-label">DSL</span><code class="meta-value dsl-code">{_esc(desc[:120])}</code></div>
        <div class="meta-item"><span class="meta-label">Components</span><span class="meta-value">{paths_html}</span></div>
        <div class="meta-item"><span class="meta-label">Timestamp</span><span class="meta-value">{_esc(ts[:19])}</span></div>
        <div class="meta-item"><span class="meta-label">Feedback</span><span class="meta-value">{fb_pills if fb_pills else "<em>pending</em>"}</span></div>
    </div>
</section>"""


def _section_dsl_tree(dsl_notation: str) -> str:
    return f"""<section class="card-surface">
    <h2>DSL Structure</h2>
    <div id="dsl-tree" class="dsl-tree-container" data-dsl="{_esc(dsl_notation)}"></div>
</section>"""


def _section_radar_chart(vectors: dict) -> str:
    if not vectors:
        return """<section class="card-surface"><h2>Embedding Vectors</h2><p class="empty">No vector data available</p></section>"""
    return """<section class="card-surface">
    <h2>Embedding Radar</h2>
    <div class="chart-wrapper"><canvas id="radarChart"></canvas></div>
</section>"""


def _section_activations(vectors: dict) -> str:
    rel = vectors.get("relationships", {})
    if not rel.get("top_activations"):
        return ""
    return """<section class="card-surface">
    <h2>Dimension Activation Profile</h2>
    <p class="chart-subtitle">Top-20 activated dimensions of the relationships vector (384d)</p>
    <div class="chart-wrapper chart-wide"><canvas id="activationsChart"></canvas></div>
</section>"""


def _section_similar(similar: list) -> str:
    if not similar:
        return """<section class="card-surface"><h2>Similar Patterns</h2><p class="empty">No similar patterns found</p></section>"""
    rows = ""
    for i, pat in enumerate(similar):
        score = pat.get("score", 0)
        pct = min(score * 100, 100)
        desc = pat.get("card_description", "N/A")
        cfb = pat.get("content_feedback", "")
        ffb = pat.get("form_feedback", "")
        fb_icon = ""
        if cfb == "positive" or ffb == "positive":
            fb_icon = '<span class="fb-icon positive">\u2713</span>'
        elif cfb == "negative" or ffb == "negative":
            fb_icon = '<span class="fb-icon negative">\u2717</span>'
        rows += f"""<div class="similar-row">
    <div class="similar-rank">#{i + 1}</div>
    <div class="similar-body">
        <code class="dsl-code">{_esc(desc[:100])}</code>
        <div class="score-bar-bg"><div class="score-bar" style="width:{pct:.0f}%"></div></div>
        <span class="score-label">{score:.4f}</span>
        {fb_icon}
    </div>
</div>"""
    return f"""<section class="card-surface">
    <h2>Similar Patterns</h2>
    <p class="chart-subtitle">5 nearest neighbors by relationships vector</p>
    <div id="similarContainer">{rows}</div>
</section>"""


def _section_footer() -> str:
    return '<footer class="dash-footer">You can close this window.</footer>'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _esc(text) -> str:
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
:root {
    --bg: #1a1a2e;
    --surface: rgba(255,255,255,0.05);
    --border: rgba(255,255,255,0.08);
    --text: #e0e0e0;
    --text-dim: #888;
    --green: #4ade80;
    --red: #f87171;
    --blue: #60a5fa;
    --purple: #a78bfa;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    background:var(--bg);color:var(--text);
    padding:24px;max-width:960px;margin:0 auto;
    line-height:1.5;
}
h1{font-size:1.3rem;font-weight:600}
h2{font-size:1rem;font-weight:600;margin-bottom:12px;color:var(--blue)}
code{font-family:'SF Mono',Monaco,Consolas,monospace;font-size:0.85em}
.dash-header{text-align:center;padding:24px 0 16px}
.header-emoji{font-size:48px;display:block;margin-bottom:8px}
.type-label{font-size:0.8rem;color:var(--text-dim);font-style:italic;margin-top:4px}
.card-surface{
    background:var(--surface);border:1px solid var(--border);
    border-radius:16px;padding:20px;margin:16px 0;
    box-shadow:0 4px 24px rgba(0,0,0,0.2);
}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:768px){.two-col{grid-template-columns:1fr}}
.meta-grid{display:grid;gap:8px}
.meta-item{display:flex;gap:12px;align-items:baseline}
.meta-label{font-size:0.8rem;color:var(--text-dim);min-width:90px;flex-shrink:0}
.meta-value{font-size:0.85rem}
.dsl-code{color:var(--purple);word-break:break-all}
.pill{
    display:inline-block;padding:2px 8px;border-radius:10px;
    font-size:0.75rem;font-weight:500;
}
.chart-wrapper{position:relative;width:100%;max-height:300px}
.chart-wide{max-height:220px}
.chart-subtitle{font-size:0.75rem;color:var(--text-dim);margin-bottom:8px}
.empty{color:var(--text-dim);font-style:italic;font-size:0.85rem}
/* DSL Tree */
.dsl-tree-container{padding:8px 0;overflow-x:auto}
.dsl-node{
    display:flex;flex-direction:column;gap:4px;
    padding-left:20px;border-left:2px solid var(--border);margin-left:4px;
}
.dsl-node:first-child{border-left:none;padding-left:0;margin-left:0}
.dsl-pill{
    display:inline-flex;align-items:center;gap:4px;
    padding:3px 10px;border-radius:8px;font-size:0.8rem;
    width:fit-content;font-family:monospace;
}
.dsl-pill .sym{font-weight:700;font-size:0.9rem}
.dsl-pill .count{
    background:rgba(255,255,255,0.15);border-radius:6px;
    padding:0 5px;font-size:0.7rem;margin-left:4px;
}
.dsl-pill.section{background:rgba(96,165,250,0.15);color:var(--blue)}
.dsl-pill.decorated{background:rgba(167,139,250,0.15);color:var(--purple)}
.dsl-pill.button{background:rgba(74,222,128,0.15);color:var(--green)}
.dsl-pill.grid{background:rgba(251,146,60,0.15);color:#fb923c}
.dsl-pill.carousel{background:rgba(236,72,153,0.15);color:#ec4899}
.dsl-pill.other{background:rgba(255,255,255,0.08);color:var(--text-dim)}
/* Similar patterns */
.similar-row{
    display:flex;align-items:center;gap:12px;
    padding:10px 0;border-bottom:1px solid var(--border);
}
.similar-row:last-child{border-bottom:none}
.similar-rank{font-size:0.8rem;color:var(--text-dim);min-width:24px}
.similar-body{flex:1;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.score-bar-bg{
    flex:1;min-width:80px;height:6px;background:rgba(255,255,255,0.08);
    border-radius:3px;overflow:hidden;
}
.score-bar{height:100%;background:var(--blue);border-radius:3px;transition:width 0.6s ease}
.score-label{font-size:0.75rem;color:var(--text-dim);min-width:50px}
.fb-icon{font-size:0.85rem}
.fb-icon.positive{color:var(--green)}
.fb-icon.negative{color:var(--red)}
.dash-footer{
    text-align:center;color:var(--text-dim);font-size:0.85rem;
    padding:24px 0 8px;
}
"""

# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS = """
(function(){
    const D = DASH_DATA;
    const V = D.vectors || {};

    // --- Radar Chart ---
    const radarEl = document.getElementById('radarChart');
    if (radarEl && Object.keys(V).length) {
        const labels = ['Norm', 'Mean (abs)', 'Max', 'Sparsity', 'Entropy'];
        const datasets = [];
        const colors = {
            components: {bg:'rgba(96,165,250,0.15)', border:'#60a5fa'},
            inputs:     {bg:'rgba(74,222,128,0.15)', border:'#4ade80'},
            relationships:{bg:'rgba(167,139,250,0.15)',border:'#a78bfa'}
        };

        // Collect raw values to compute per-axis max for normalization
        const axisMax = [0,0,0,0,0];
        for (const [name, s] of Object.entries(V)) {
            const raw = [s.norm||0, Math.abs(s.mean||0), s.max||0, s.sparsity||0, s.entropy||0];
            raw.forEach((v,i) => { if(v > axisMax[i]) axisMax[i] = v; });
        }
        // Normalize to 0-1 per axis
        for (const [name, s] of Object.entries(V)) {
            const raw = [s.norm||0, Math.abs(s.mean||0), s.max||0, s.sparsity||0, s.entropy||0];
            const normalized = raw.map((v,i) => axisMax[i] ? v/axisMax[i] : 0);
            const c = colors[name] || {bg:'rgba(255,255,255,0.1)',border:'#fff'};
            let label = name;
            if (s.token_count) label += ' (' + s.token_count + ' tokens)';
            datasets.push({
                label: label,
                data: normalized,
                backgroundColor: c.bg,
                borderColor: c.border,
                borderWidth: 2,
                pointRadius: 3,
                pointBackgroundColor: c.border
            });
        }
        new Chart(radarEl, {
            type: 'radar',
            data: {labels, datasets},
            options: {
                responsive: true, maintainAspectRatio: true,
                scales: {r:{
                    beginAtZero:true, max:1,
                    grid:{color:'rgba(255,255,255,0.06)'},
                    angleLines:{color:'rgba(255,255,255,0.06)'},
                    pointLabels:{color:'#888',font:{size:11}},
                    ticks:{display:false}
                }},
                plugins:{legend:{labels:{color:'#ccc',font:{size:11}}}}
            }
        });
    }

    // --- Activations Chart ---
    const actEl = document.getElementById('activationsChart');
    const rel = V.relationships;
    if (actEl && rel && rel.top_activations && rel.top_activations.length) {
        const acts = rel.top_activations;
        new Chart(actEl, {
            type: 'bar',
            data: {
                labels: acts.map(a => 'dim ' + a[0]),
                datasets: [{
                    data: acts.map(a => a[1]),
                    backgroundColor: acts.map(a => a[1] >= 0 ? 'rgba(167,139,250,0.6)' : 'rgba(248,113,113,0.6)'),
                    borderColor: acts.map(a => a[1] >= 0 ? '#a78bfa' : '#f87171'),
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true, maintainAspectRatio: false,
                plugins:{legend:{display:false}},
                scales:{
                    x:{grid:{color:'rgba(255,255,255,0.06)'},ticks:{color:'#888'}},
                    y:{grid:{display:false},ticks:{color:'#888',font:{size:10}}}
                }
            }
        });
        // Set explicit height based on bar count
        actEl.parentElement.style.height = Math.max(200, acts.length * 22) + 'px';
        actEl.parentElement.style.maxHeight = 'none';
    }

    // --- DSL Tree ---
    const treeEl = document.getElementById('dsl-tree');
    if (treeEl) {
        const dsl = treeEl.getAttribute('data-dsl') || '';
        treeEl.innerHTML = parseDSL(dsl);
    }

    function parseDSL(s) {
        if (!s) return '<span class="empty">No DSL notation</span>';
        // Symbol to class mapping
        const symClass = {
            '\\u00a7':'section','\\u03b4':'decorated','\\u0243':'button','\\u1d6c':'button',
            '\\u210a':'grid','\\u01f5':'grid','\\u25e6':'carousel','\\u25bc':'carousel',
            '\\u25b2':'other'
        };
        const symName = {};
        const sm = D.symbolMap || {};
        for (const [name, sym] of Object.entries(sm)) {
            symName[sym] = name;
        }

        function getClass(sym) {
            for (const [key, cls] of Object.entries(symClass)) {
                if (sym === key) return cls;
            }
            // Try matching by component name
            const name = (symName[sym] || '').toLowerCase();
            if (name.includes('section')) return 'section';
            if (name.includes('decorated')) return 'decorated';
            if (name.includes('button') || name.includes('chip')) return 'button';
            if (name.includes('grid')) return 'grid';
            if (name.includes('carousel')) return 'carousel';
            return 'other';
        }

        // Tokenize: symbols, [, ], numbers after x, commas
        const tokens = [];
        let i = 0;
        while (i < s.length) {
            const ch = s[i];
            if (ch === ' ' || ch === ',') { i++; continue; }
            if (ch === '[') { tokens.push({type:'open'}); i++; continue; }
            if (ch === ']') { tokens.push({type:'close'}); i++; continue; }
            if (ch === '\\u00d7' || ch === 'x' || ch === '*') {
                i++;
                let num = '';
                while (i < s.length && s[i] >= '0' && s[i] <= '9') { num += s[i]; i++; }
                if (num) tokens[tokens.length-1].count = parseInt(num);
                continue;
            }
            // It's a symbol character (possibly multi-byte)
            const cp = s.codePointAt(i);
            const sym = String.fromCodePoint(cp);
            tokens.push({type:'sym', sym: sym, name: symName[sym] || sym, cls: getClass(sym)});
            i += sym.length;
        }

        // Build HTML from tokens
        function buildHTML(idx) {
            let html = '';
            while (idx < tokens.length) {
                const t = tokens[idx];
                if (t.type === 'close') return {html, next: idx + 1};
                if (t.type === 'sym') {
                    const countBadge = t.count ? '<span class="count">\\u00d7' + t.count + '</span>' : '';
                    html += '<div class="dsl-pill ' + t.cls + '"><span class="sym">' + t.sym + '</span> ' + t.name + countBadge + '</div>';
                    idx++;
                    // Check for children
                    if (idx < tokens.length && tokens[idx].type === 'open') {
                        const child = buildHTML(idx + 1);
                        html += '<div class="dsl-node">' + child.html + '</div>';
                        idx = child.next;
                    }
                } else if (t.type === 'open') {
                    const child = buildHTML(idx + 1);
                    html += '<div class="dsl-node">' + child.html + '</div>';
                    idx = child.next;
                } else {
                    idx++;
                }
            }
            return {html, next: idx};
        }
        return buildHTML(0).html || '<span class="empty">Could not parse DSL</span>';
    }
})();
"""
