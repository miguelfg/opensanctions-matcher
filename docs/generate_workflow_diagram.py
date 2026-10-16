#!/usr/bin/env python3
"""Generate the opensanctions-matcher skill workflow diagram."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(14, 18))
ax.set_xlim(0, 14)
ax.set_ylim(0, 18)
ax.axis("off")
fig.patch.set_facecolor("#ffffff")
ax.set_facecolor("#ffffff")

# Color palette — vivid strokes, light fills, dark text for white background
C = {
    "user":    "#1d4ed8",   # blue
    "ai":      "#7c3aed",   # purple
    "cache":   "#b45309",   # amber-dark
    "index":   "#047857",   # emerald-dark
    "search":  "#0e7490",   # cyan-dark
    "fuzzy":   "#c2410c",   # orange-dark
    "enrich":  "#4338ca",   # indigo-dark
    "result":  "#15803d",   # green-dark
    "no":      "#b91c1c",   # red-dark
    "yes":     "#15803d",   # green-dark
    "text":    "#1e293b",   # near-black for labels
    "subtext": "#475569",   # slate for sublabels
    "arrow":   "#64748b",   # slate arrows
    "title":   "#0f172a",   # almost black title
}

def box(ax, x, y, w, h, label, sublabel, color, radius=0.35):
    rect = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad=0.05,rounding_size={radius}",
        linewidth=2.0, edgecolor=color,
        facecolor=color + "18",   # very light tint — always visible on white
        zorder=3,
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.12 if sublabel else 0), label,
            ha="center", va="center", fontsize=10, fontweight="bold",
            color=color, zorder=4)
    if sublabel:
        ax.text(x, y - 0.28, sublabel,
                ha="center", va="center", fontsize=7.5,
                color=C["subtext"], zorder=4)

def diamond(ax, x, y, w, h, label, color):
    dx, dy = w / 2, h / 2
    pts = [(x, y + dy), (x + dx, y), (x, y - dy), (x - dx, y)]
    poly = plt.Polygon(pts, closed=True,
                       linewidth=2.0, edgecolor=color,
                       facecolor=color + "18", zorder=3)
    ax.add_patch(poly)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=9, fontweight="bold", color=color, zorder=4)

def arrow(ax, x1, y1, x2, y2, label="", color="#64748b"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.5, mutation_scale=14),
                zorder=2)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.15, my, label, ha="left", va="center",
                fontsize=8, color=color, zorder=5)

def side_arrow(ax, x1, y1, x2, y2, label="", color="#64748b"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.5, mutation_scale=14,
                                connectionstyle="arc3,rad=0.0"),
                zorder=2)
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.15,
                label, ha="center", va="bottom",
                fontsize=8, color=color, zorder=5)

def diag_return(ax, from_x, from_y, to_x, to_y, color):
    """Diagonal arrow from bottom-right corner of source box to right edge of target."""
    ax.annotate("", xy=(to_x, to_y), xytext=(from_x, from_y),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.5, mutation_scale=14),
                zorder=2)

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(7, 17.4, "OpenSanctions Matcher — Skill Workflow",
        ha="center", va="center", fontsize=15, fontweight="bold",
        color=C["title"])
ax.text(7, 17.0, "AI-driven sanctions screening with FTS5 + fuzzy matching",
        ha="center", va="center", fontsize=9, color=C["subtext"])

# ── Nodes (x=7 centre column, y top-to-bottom) ────────────────────────────────
# 1. User Input
box(ax, 7, 16.2, 5.0, 0.7, "User Input", "wallet · person · company · IBAN · vessel", C["user"])

# 2. Classify Target
box(ax, 7, 15.2, 4.2, 0.7, "Classify Target Type",
    "AI detects type & suggests datasets", C["ai"])

# 3. Dataset Selection
box(ax, 7, 14.2, 4.2, 0.7, "Select Dataset(s)",
    "us_ofac_sdn · il_mod_crypto · peps · …", C["ai"])

# 4. Cache check diamond
diamond(ax, 7, 13.1, 4.0, 0.9, "Cached locally?", C["cache"])

# 4a. Download (right branch)
box(ax, 11.0, 13.1, 3.0, 0.7, "Download Dataset",
    "OpenSanctions bulk export", C["cache"])

# 5. FTS5 index check diamond
diamond(ax, 7, 11.9, 4.0, 0.9, "FTS5 index built?", C["index"])

# 5a. Build index (right branch)
box(ax, 11.0, 11.9, 3.0, 0.7, "Build FTS5 Index",
    ".fts5.db · unicode61 tokeniser", C["index"])

# 6. Search Layer 1
box(ax, 7, 10.7, 4.8, 0.7, "Layer 1: FTS5 Full-Text Search",
    "names.txt · BM25 ranking · phrase / prefix / exact", C["search"])

# 7. Fuzzy check diamond
diamond(ax, 7, 9.6, 4.0, 0.9, "--fuzzy flag set?", C["fuzzy"])

# 7a. Fuzzy pass (right branch)
box(ax, 11.0, 9.6, 3.0, 0.7, "Fuzzy Pass",
    "rapidfuzz WRatio · dedup vs FTS5", C["fuzzy"])

# 8. Phase 2: Enrich
box(ax, 7, 8.4, 4.8, 0.7, "Phase 2: Enrich Hits",
    "targets.simple.csv · entities.ftm.json", C["enrich"])

# 9. Match found diamond
diamond(ax, 7, 7.3, 4.0, 0.9, "Match found?", C["result"])

# 10a. Structured Result (left branch — yes)
box(ax, 3.0, 7.3, 3.2, 0.7, "Structured Result",
    "FtM schema · risk tags · exit 0", C["result"])

# 10b. No Match (right branch — no)
box(ax, 11.0, 7.3, 3.0, 0.7, "No Match Found",
    "clean · exit 2", C["no"])

# ── Arrows ────────────────────────────────────────────────────────────────────
arrow(ax, 7, 15.85, 7, 15.55, color=C["arrow"])   # input → classify
arrow(ax, 7, 14.85, 7, 14.55, color=C["arrow"])   # classify → select
arrow(ax, 7, 13.85, 7, 13.55, color=C["arrow"])   # select → cache?

# cache no (down)
arrow(ax, 7, 12.65, 7, 12.25, "", C["index"])
ax.text(7.15, 12.45, "yes", fontsize=8, color=C["yes"])

# cache yes (right → download)
side_arrow(ax, 9.0, 13.1, 9.5, 13.1, "", C["cache"])
ax.text(9.05, 13.25, "no", fontsize=8, color=C["no"])
# download → diagonal from bottom-right corner to FTS5 index diamond right tip
diag_return(ax, from_x=12.5, from_y=12.75, to_x=9.0, to_y=11.9, color=C["cache"])

# index no (down)
arrow(ax, 7, 11.45, 7, 11.05, "", C["search"])
ax.text(7.15, 11.25, "yes", fontsize=8, color=C["yes"])

# index yes (right → build)
side_arrow(ax, 9.0, 11.9, 9.5, 11.9, "", C["index"])
ax.text(9.05, 12.05, "no", fontsize=8, color=C["no"])
# build FTS5 index → diagonal from bottom-right corner to Layer 1 box right edge
diag_return(ax, from_x=12.5, from_y=11.55, to_x=9.4, to_y=10.7, color=C["index"])

# search → fuzzy?
arrow(ax, 7, 10.35, 7, 10.05)

# fuzzy no (down)
arrow(ax, 7, 9.15, 7, 8.75, "", C["enrich"])
ax.text(7.15, 8.95, "no", fontsize=8, color=C["no"])

# fuzzy yes (right → fuzzy pass)
side_arrow(ax, 9.0, 9.6, 9.5, 9.6, "", C["fuzzy"])
ax.text(9.05, 9.75, "yes", fontsize=8, color=C["yes"])
# fuzzy pass → diagonal from bottom-right corner to Phase 2 Enrich box right edge
diag_return(ax, from_x=12.5, from_y=9.25, to_x=9.4, to_y=8.4, color=C["fuzzy"])

# enrich → match?
arrow(ax, 7, 8.05, 7, 7.75)

# match yes (left)
ax.annotate("", xy=(4.6, 7.3), xytext=(5.0, 7.3),
            arrowprops=dict(arrowstyle="-|>", color=C["result"],
                            lw=1.5, mutation_scale=14), zorder=2)
ax.text(4.75, 7.45, "yes", fontsize=8, color=C["yes"])

# match no (right)
ax.annotate("", xy=(9.5, 7.3), xytext=(9.0, 7.3),
            arrowprops=dict(arrowstyle="-|>", color=C["no"],
                            lw=1.5, mutation_scale=14), zorder=2)
ax.text(9.05, 7.45, "no", fontsize=8, color=C["no"])

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    ("User / Input",         C["user"]),
    ("AI Classification",    C["ai"]),
    ("Cache / Download",     C["cache"]),
    ("FTS5 Index",           C["index"]),
    ("Search",               C["search"]),
    ("Fuzzy Matching",       C["fuzzy"]),
    ("Enrichment",           C["enrich"]),
    ("Result",               C["result"]),
]
for i, (label, color) in enumerate(legend_items):
    px = 0.6 + (i % 4) * 3.3
    py = 6.1 - (i // 4) * 0.55
    rect = FancyBboxPatch((px, py - 0.18), 0.35, 0.36,
                          boxstyle="round,pad=0.03",
                          facecolor=color + "55", edgecolor=color,
                          linewidth=1.2, zorder=3)
    ax.add_patch(rect)
    ax.text(px + 0.5, py, label, va="center", fontsize=8,
            color=C["text"], zorder=4)

ax.plot([0.4, 13.6], [5.3, 5.3], color=C["subtext"], lw=0.5, alpha=0.4)

plt.tight_layout(pad=0.3)
out = "workflow_diagram.png"
plt.savefig(out, dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print(f"Saved: {out}")
