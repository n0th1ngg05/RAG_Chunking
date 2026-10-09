import os
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig_dir = Path("docs_assets")
fig_dir.mkdir(exist_ok=True)

# -------------------------------------------------------------
# CHART 4: Architecture Topology Diagram
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.axis('off')

# Boxes
def draw_box(x, y, w, h, title, subtitle, color, text_color='#ffffff'):
    box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                                  facecolor=color, edgecolor='#334155', linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h*0.6, title, ha='center', va='center', fontsize=11, fontweight='bold', color=text_color)
    ax.text(x + w/2, y + h*0.25, subtitle, ha='center', va='center', fontsize=8, color=text_color)

# Draw tiers
draw_box(0.5, 3.8, 2.2, 1.4, "Node.js Gateway", "Port 3000\nJWT + File Validation", "#1e3a8a")
draw_box(3.8, 3.8, 2.2, 1.4, "Redis Queue", "Port 6379\ningestion:jobs list", "#dc2626")
draw_box(7.1, 3.8, 2.4, 1.4, "Python Worker", "No Host Port\nDehyphenate, Chunk, Val", "#047857")

draw_box(1.5, 0.8, 3.0, 1.5, "PostgreSQL 16 + pgvector", "Port 5432 | VECTOR(768)\nRow-Level Security Active", "#334155")
draw_box(6.0, 0.8, 3.0, 1.5, "Ollama Local Inference", "Port 11434\nnomic-embed-text (768-dim)", "#4338ca")

# Arrows
arrow_props = dict(arrowstyle="->", lw=2, color="#0284c7")
ax.annotate("", xy=(3.8, 4.5), xytext=(2.7, 4.5), arrowprops=arrow_props)
ax.text(3.25, 4.7, "LPUSH", ha='center', fontsize=9, fontweight='bold', color='#0284c7')

ax.annotate("", xy=(7.1, 4.5), xytext=(6.0, 4.5), arrowprops=arrow_props)
ax.text(6.55, 4.7, "BRPOP", ha='center', fontsize=9, fontweight='bold', color='#0284c7')

# Downward arrows
ax.annotate("", xy=(2.5, 2.3), xytext=(1.6, 3.8), arrowprops=dict(arrowstyle="->", lw=1.5, color="#64748b"))
ax.text(1.3, 3.0, "RLS app_user", fontsize=8, color='#64748b')

ax.annotate("", xy=(7.0, 2.3), xytext=(7.8, 3.8), arrowprops=dict(arrowstyle="<->", lw=1.5, color="#64748b"))
ax.text(7.7, 3.0, "Embeddings HTTP", fontsize=8, color='#64748b')

ax.annotate("", xy=(4.5, 1.6), xytext=(7.1, 3.8), arrowprops=dict(arrowstyle="->", lw=1.5, color="#10b981"))
ax.text(6.2, 2.8, "BYPASSRLS\nPersist Vectors", fontsize=8, color='#10b981')

ax.set_title("DocStack Multi-Tier Topology & Data Flow Isolation", fontsize=13, fontweight='bold', pad=10)
plt.tight_layout()
chart4_path = fig_dir / "architecture_topology_diagram.png"
plt.savefig(chart4_path)
plt.close()
print("Saved Chart 4:", chart4_path)
