"""Render a CCPM schedule as a standalone interactive network graph HTML.

The Gantt chart shows WHEN tasks happen; this view shows WHY — the
dependency structure. One self-contained HTML file with the graph data
embedded as JSON and vis-network loaded from a CDN: no build step, no local
server — open it in any browser to zoom, pan, drag nodes, and click a node
to inspect task details in the sidebar.

Color code matches the Gantt: critical chain firebrick, feeding chains
colored, buffers gold/khaki with dashed borders (buffer attachments are
dashed edges — they are not work; slippage consumes them), other tasks grey,
zero-duration milestones as diamonds. Non-FS links carry an SS/FF/SF label.

Pass the input tasks (`tasks=` / `--tasks tasks.csv`) to enrich each task
node with its realistic duration estimate — schedule.csv only carries the
scheduled (optimal) duration, and reviewing the optimal/realistic balance is
exactly what teams do in front of this view.

Library API:  render_network_html(schedule, title=..., tasks=...) -> str
              write_network_html(schedule, path, title=..., tasks=...)
CLI:          ccpm-scheduler graph schedule.csv project-network.html
                  [--tasks tasks.csv]
"""
from __future__ import annotations

import json

from . import io
from .model import Schedule, as_int

CRITICAL_COLOR = "#b22222"          # firebrick, as on the Gantt
OTHER_COLOR = "#9e9e9e"
PB_COLOR = "#ffd700"                # gold
FB_COLOR = "#f0e68c"                # khaki
# matplotlib tab10 hues in the Gantt's feeding-chain order (red family
# excluded - reserved for the critical chain)
FEEDING_PALETTE = ["#2ca02c", "#1f77b4", "#9467bd", "#8c564b",
                   "#e377c2", "#bcbd22", "#17becf", "#ff7f0e"]


def _node_style(row, feed_color):
    if row.type == "project_buffer":
        return PB_COLOR, "#8a7500", True, "box"
    if row.type == "feeding_buffer":
        return FB_COLOR, "#8a8250", True, "box"
    if row.duration == 0:
        return "#ffffff", "#333333", False, "diamond"
    if row.chain == "critical":
        return CRITICAL_COLOR, "#7a1717", False, "box"
    if row.chain in feed_color:
        return feed_color[row.chain], "#555555", False, "box"
    return OTHER_COLOR, "#616161", False, "box"


def _estimates(tasks):
    """task id -> realistic duration (whole days), for tasks that have one."""
    if tasks is None:
        return {}
    if hasattr(tasks, "tasks"):     # a Network is fine too
        tasks = tasks.tasks
    out = {}
    for t in tasks:
        if t.realistic_duration in (None, ""):
            continue
        try:
            out[t.id] = as_int(t.realistic_duration)
        except ValueError:
            continue
    return out


def _graph_data(schedule: Schedule, critical_label, tasks=None):
    rows = schedule.rows
    realistic = _estimates(tasks)
    feeding_chains = sorted({r.chain for r in rows
                             if r.chain.startswith("feeding")})
    feed_color = {c: FEEDING_PALETTE[i % len(FEEDING_PALETTE)]
                  for i, c in enumerate(feeding_chains)}

    ids = {r.id for r in rows}
    nodes, edges = [], []
    for r in rows:
        background, border, dashed_border, shape = _node_style(r, feed_color)
        dark = r.chain == "critical" and r.type == "task"
        r_realistic = realistic.get(r.id) if r.type == "task" else None
        title = f"{r.name}: day {r.start} – {r.finish} ({r.duration}d)"
        if r_realistic is not None:
            title = (f"{r.name}: day {r.start} – {r.finish} "
                     f"({r.duration}d optimal, {r_realistic}d realistic)")
        nodes.append({
            "id": r.id,
            "label": f"{r.id}\n{r.name}" if r.name and r.name != r.id else r.id,
            "shape": shape,
            "color": {"background": background, "border": border,
                      "highlight": {"background": background,
                                    "border": "#000000"}},
            "font": {"color": "#ffffff" if dark else "#1a1a1a"},
            "shapeProperties": {"borderDashes": [4, 3] if dashed_border
                                else False},
            "borderWidth": 2 if r.type != "task" else 1,
            "title": title,
            # inspector payload (vis passes unknown fields through)
            "data": {
                "name": r.name, "type": r.type, "chain": r.chain,
                "start": r.start, "finish": r.finish,
                "duration": r.duration,
                "realistic": r_realistic,
                "resources": r.resource_ids.replace(";", ", "),
                "predecessors": r.predecessor_ids.replace(";", "; "),
                "url": r.url,
            },
        })
        for link in io.parse_links(r.predecessor_ids, buffer_links=True):
            if link.pred_id not in ids:
                continue
            buffer_link = link.type in ("PB", "FB")
            label = "" if link.type in ("FS", "PB", "FB") else link.type
            if link.lag:
                label += f"{link.lag:+d}"
            edges.append({
                "from": link.pred_id, "to": r.id, "arrows": "to",
                "dashes": [6, 4] if buffer_link else False,
                "color": {"color": "#666666" if buffer_link else "#404040"},
                "width": 1.5,
                **({"label": label} if label else {}),
            })

    legend = []
    if any(r.chain == "critical" and r.type == "task" for r in rows):
        legend.append({"color": CRITICAL_COLOR, "label": critical_label})
    for c in feeding_chains:
        legend.append({"color": feed_color[c], "label": f"Feeding chain {c.split('-', 1)[1]}"})
    if any(r.type == "task" and r.chain == "none" for r in rows):
        legend.append({"color": OTHER_COLOR, "label": "Other task"})
    if any(r.type == "project_buffer" for r in rows):
        legend.append({"color": PB_COLOR, "label": "Project buffer"})
    if any(r.type == "feeding_buffer" for r in rows):
        legend.append({"color": FB_COLOR, "label": "Feeding buffer"})

    pb = next((r for r in rows if r.type == "project_buffer"), None)
    cc = [r for r in rows if r.chain == "critical" and r.type == "task"]
    summary = ""
    if cc:
        summary = (f"Critical chain: {len(cc)} tasks, "
                   f"{sum(r.duration for r in cc)} working days")
    if pb:
        summary += (f"{' — ' if summary else ''}project buffer "
                    f"{pb.duration}d — promised completion: day {pb.finish}")

    return {"nodes": nodes, "edges": edges, "legend": legend,
            "summary": summary}


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>__TITLE__ — project network</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
           Helvetica, Arial, sans-serif; margin: 0; display: flex;
           flex-direction: column; height: 100vh; }
    #header { padding: 10px 16px; border-bottom: 1px solid #ddd;
              background: #ffffff; }
    #header h1 { margin: 0; font-size: 1.1rem; color: #222; }
    #header .summary { color: #666; font-size: 0.85rem; margin-top: 2px; }
    #main { flex: 1; display: flex; min-height: 0; }
    #network-container { flex: 1; height: 100%; background: #f8f9fa; }
    #sidebar { width: 320px; padding: 16px; border-left: 1px solid #ddd;
               background: #ffffff; overflow-y: auto; }
    #sidebar h2 { margin-top: 0; font-size: 1rem; color: #333; }
    .detail-label { font-weight: bold; color: #666; margin-top: 10px;
                    font-size: 0.8rem; }
    .detail-value { color: #222; font-size: 0.9rem; word-break: break-word; }
    #task-details { display: none; }
    #placeholder-text { color: #888; font-style: italic; font-size: 0.9rem; }
    #legend { margin-top: 20px; border-top: 1px solid #eee; padding-top: 10px; }
    .legend-item { display: flex; align-items: center; margin: 4px 0;
                   font-size: 0.8rem; color: #444; }
    .legend-swatch { width: 14px; height: 14px; border-radius: 3px;
                     margin-right: 8px; border: 1px solid #999;
                     flex: none; }
    #controls { margin-top: 16px; border-top: 1px solid #eee;
                padding-top: 10px; }
    #controls button { font-size: 0.8rem; padding: 4px 10px;
                       margin-right: 6px; cursor: pointer; }
  </style>
</head>
<body>
  <div id="header">
    <h1>__TITLE__</h1>
    <div class="summary" id="summary"></div>
  </div>
  <div id="main">
    <div id="network-container"></div>
    <div id="sidebar">
      <h2>Task inspector</h2>
      <div id="placeholder-text">Click a node to view task details.
        Drag nodes, scroll to zoom, drag the background to pan.</div>
      <div id="task-details">
        <div class="detail-label">Task</div>
        <div id="detail-name" class="detail-value"></div>
        <div class="detail-label">Type / chain</div>
        <div id="detail-type" class="detail-value"></div>
        <div class="detail-label">Schedule</div>
        <div id="detail-schedule" class="detail-value"></div>
        <div class="detail-label" id="label-estimates">Estimates</div>
        <div id="detail-estimates" class="detail-value"></div>
        <div class="detail-label">Resources</div>
        <div id="detail-resources" class="detail-value"></div>
        <div class="detail-label">Predecessors</div>
        <div id="detail-preds" class="detail-value"></div>
        <div class="detail-label">Link</div>
        <div id="detail-url" class="detail-value"></div>
      </div>
      <div id="legend"></div>
      <div id="controls">
        <button id="btn-fit">Fit view</button>
        <button id="btn-layout">Free layout</button>
      </div>
    </div>
  </div>

  <script>
    const GRAPH = __DATA__;

    document.getElementById('summary').innerText = GRAPH.summary;

    const legendBox = document.getElementById('legend');
    for (const item of GRAPH.legend) {
      const row = document.createElement('div');
      row.className = 'legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = item.color;
      const label = document.createElement('span');
      label.innerText = item.label;
      row.appendChild(swatch);
      row.appendChild(label);
      legendBox.appendChild(row);
    }

    const nodes = new vis.DataSet(GRAPH.nodes);
    const edges = new vis.DataSet(GRAPH.edges);
    const container = document.getElementById('network-container');

    const hierarchical = {
      layout: { hierarchical: { enabled: true, direction: 'LR',
                                sortMethod: 'directed',
                                levelSeparation: 180, nodeSpacing: 70 } },
      physics: { enabled: false },
      nodes: { widthConstraint: { maximum: 170 },
               margin: { top: 8, bottom: 8, left: 10, right: 10 } },
      edges: { font: { size: 10, color: '#555555', strokeWidth: 4,
                       strokeColor: '#f8f9fa' },
               smooth: { type: 'cubicBezier',
                         forceDirection: 'horizontal', roundness: 0.4 } },
      interaction: { hover: true, navigationButtons: true, keyboard: true },
    };
    const free = {
      layout: { hierarchical: { enabled: false } },
      physics: { enabled: true,
                 barnesHut: { springLength: 160, gravitationalConstant: -4000 } },
      nodes: hierarchical.nodes,
      edges: { ...hierarchical.edges, smooth: { type: 'dynamic' } },
      interaction: hierarchical.interaction,
    };

    const network = new vis.Network(container, { nodes, edges }, hierarchical);
    let freeMode = false;

    document.getElementById('btn-fit').addEventListener('click',
      () => network.fit({ animation: true }));
    document.getElementById('btn-layout').addEventListener('click', (e) => {
      freeMode = !freeMode;
      network.setOptions(freeMode ? free : hierarchical);
      e.target.innerText = freeMode ? 'Hierarchical layout' : 'Free layout';
      network.fit({ animation: true });
    });

    network.on('click', (params) => {
      const details = document.getElementById('task-details');
      const placeholder = document.getElementById('placeholder-text');
      if (params.nodes.length === 0) {
        details.style.display = 'none';
        placeholder.style.display = 'block';
        return;
      }
      const d = nodes.get(params.nodes[0]).data;
      placeholder.style.display = 'none';
      details.style.display = 'block';
      document.getElementById('detail-name').innerText =
        `${params.nodes[0]} — ${d.name}`;
      document.getElementById('detail-type').innerText =
        `${d.type.replace('_', ' ')} / ${d.chain}`;
      document.getElementById('detail-schedule').innerText =
        `day ${d.start} → ${d.finish} (${d.duration} working days)`;
      const hasRealistic = d.realistic !== null && d.realistic !== undefined;
      document.getElementById('label-estimates').style.display =
        hasRealistic ? 'block' : 'none';
      const estimatesBox = document.getElementById('detail-estimates');
      estimatesBox.style.display = hasRealistic ? 'block' : 'none';
      if (hasRealistic) {
        const cut = d.realistic > 0
          ? Math.round(100 * (1 - d.duration / d.realistic)) : 0;
        estimatesBox.innerText =
          `optimal ${d.duration}d · realistic ${d.realistic}d` +
          (cut > 0 ? ` (${cut}% safety pooled into buffers)` : '');
      }
      document.getElementById('detail-resources').innerText =
        d.resources || '—';
      document.getElementById('detail-preds').innerText =
        d.predecessors || '— (start task)';
      const urlBox = document.getElementById('detail-url');
      urlBox.innerHTML = '';
      if (d.url) {
        const a = document.createElement('a');
        a.href = d.url; a.target = '_blank'; a.rel = 'noopener';
        a.innerText = d.url;
        urlBox.appendChild(a);
      } else {
        urlBox.innerText = '—';
      }
    });
  </script>
</body>
</html>
"""


def render_network_html(schedule: Schedule, title="CCPM Schedule",
                        critical_label="Critical chain", tasks=None) -> str:
    """The complete standalone HTML document as a string.

    `tasks` (a list of Task or a Network) enriches task nodes with their
    realistic duration estimates in the tooltip and inspector."""
    data = _graph_data(schedule, critical_label, tasks)
    # </ would end the inline <script> early if a name/url contained it
    payload = json.dumps(data, indent=2).replace("</", "<\\/")
    safe_title = (title.replace("&", "&amp;").replace("<", "&lt;")
                  .replace(">", "&gt;"))
    return (_TEMPLATE.replace("__TITLE__", safe_title)
            .replace("__DATA__", payload))


def write_network_html(schedule: Schedule, path, title="CCPM Schedule",
                       critical_label="Critical chain", tasks=None):
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_network_html(schedule, title, critical_label, tasks))
