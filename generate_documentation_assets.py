import os
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

# Set aesthetic style
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig_dir = Path("docs_assets")
fig_dir.mkdir(exist_ok=True)

# -------------------------------------------------------------
# CHART 1: Stage Timings Breakdown (PDF vs DOCX)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
stages = [
    "Text Extraction",
    "Structure Parsing",
    "Section Chunking",
    "Chunk Validation",
    "Embedding Gen",
    "DB Persistence"
]
pdf_timings = [0.14, 0.001, 0.001, 0.001, 0.61, 0.05]
docx_timings = [0.04, 0.001, 0.001, 0.12, 10.07, 0.10]

x = np.arange(len(stages))
width = 0.35

rects1 = ax.bar(x - width/2, pdf_timings, width, label='Run 1: CV-2.pdf (8 chunks, 335KB)', color='#0ea5e9')
rects2 = ax.bar(x + width/2, docx_timings, width, label='Run 2: EDS_n0th1ng.docx (38 chunks, 28KB)', color='#10b981')

ax.set_ylabel('Execution Time (Seconds)', fontsize=11, fontweight='bold')
ax.set_title('Pipeline Stage Timings Comparison: PDF vs DOCX Reference Runs', fontsize=13, fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(stages, rotation=15, ha='right', fontsize=10)
ax.legend(frameon=True, facecolor='#f8fafc', edgecolor='#cbd5e1')
ax.grid(axis='y', linestyle='--', alpha=0.7)

# Add value labels
for rect in rects1:
    h = rect.get_height()
    if h > 0.01:
        ax.annotate(f'{h:.2f}s', xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)

for rect in rects2:
    h = rect.get_height()
    if h > 0.01:
        ax.annotate(f'{h:.2f}s', xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8, fontweight='bold')

plt.tight_layout()
chart1_path = fig_dir / "stage_timings_comparison.png"
plt.savefig(chart1_path)
plt.close()
print("Saved Chart 1:", chart1_path)

# -------------------------------------------------------------
# CHART 2: Latency Composition: Queue vs Worker vs Upload E2E
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 4.5), dpi=300)
runs = ["Run 1: CV-2.pdf (PDF)", "Run 2: EDS_n0th1ng.docx (DOCX)"]
queue_waits = [0.001, 0.000]
worker_times = [0.80, 10.35]
upload_buffering = [0.874 - 0.80, 10.439 - 10.35]

p1 = ax.barh(runs, worker_times, label='Python Worker Processing', color='#6366f1', height=0.45)
p2 = ax.barh(runs, upload_buffering, left=worker_times, label='Node Gateway & Network Transit', color='#f59e0b', height=0.45)

ax.set_xlabel('Total End-to-End Duration (Seconds)', fontsize=11, fontweight='bold')
ax.set_title('Turnaround Latency: Worker Pipeline vs Gateway Overhead', fontsize=13, fontweight='bold', pad=15)
ax.legend(loc='lower right', frameon=True, facecolor='#f8fafc')
ax.grid(axis='x', linestyle='--', alpha=0.7)

for i, total in enumerate([0.874, 10.439]):
    ax.text(total + 0.15, i, f'Total: {total:.3f}s', va='center', fontweight='bold', fontsize=10, color='#1e293b')

ax.set_xlim(0, 12)
plt.tight_layout()
chart2_path = fig_dir / "worker_vs_e2e_breakdown.png"
plt.savefig(chart2_path)
plt.close()
print("Saved Chart 2:", chart2_path)

# -------------------------------------------------------------
# CHART 3: Percentage Latency Distribution (Pie / Donut)
# -------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5), dpi=300)

# PDF Distribution
labels1 = ['Embedding (70%)', 'Extraction (16%)', 'Database (6%)', 'Gateway/Other (8%)']
sizes1 = [0.61, 0.14, 0.05, 0.074]
colors1 = ['#10b981', '#0ea5e9', '#8b5cf6', '#cbd5e1']
wedges1, _, autotexts1 = ax1.pie(sizes1, labels=labels1, autopct='%1.1f%%', startangle=140,
                                  colors=colors1, wedgeprops=dict(width=0.4, edgecolor='w'))
ax1.set_title('Run 1: PDF (8 Chunks)\nTotal: 0.874s', fontsize=11, fontweight='bold')

# DOCX Distribution
labels2 = ['Embedding (96.5%)', 'Validation (1.2%)', 'DB (1.0%)', 'Other (1.3%)']
sizes2 = [10.07, 0.12, 0.10, 0.149]
colors2 = ['#10b981', '#f59e0b', '#8b5cf6', '#cbd5e1']
wedges2, _, autotexts2 = ax2.pie(sizes2, labels=labels2, autopct='%1.1f%%', startangle=140,
                                  colors=colors2, wedgeprops=dict(width=0.4, edgecolor='w'))
ax2.set_title('Run 2: DOCX (38 Chunks)\nTotal: 10.439s', fontsize=11, fontweight='bold')

plt.suptitle('Subsystem Latency Budget: Local Embeddings Dominate Medium Documents', fontsize=13, fontweight='bold', y=0.98)
plt.tight_layout()
chart3_path = fig_dir / "throughput_latency_distribution.png"
plt.savefig(chart3_path)
plt.close()
print("Saved Chart 3:", chart3_path)
