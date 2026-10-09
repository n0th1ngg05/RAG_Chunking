import re
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas that performs a two-pass calculation for 'Page X of Y' footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # Skip decorations on cover page
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Running header
        self.drawString(54, 755, "DOCSTACK ENTERPRISE — TECHNICAL ARCHITECTURE & PERFORMANCE SPECIFICATION")
        self.setFont("Helvetica", 8)
        self.drawRightString(558, 755, "CONFIDENTIAL & PROPRIETARY")
        
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 747, 558, 747)

        # Running footer
        self.line(54, 45, 558, 45)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(54, 34, "DocStack v2.0.0-PROD | Document Chunking & Vector Retrieval Engine")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 34, page_str)
        self.restoreState()


def build_pdf():
    pdf_filename = "DocStack_System_Documentation_and_Metrics.pdf"
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0f172a") # Dark Slate
    accent_blue = colors.HexColor("#0284c7")   # Deep Sky Blue
    accent_green = colors.HexColor("#059669")  # Emerald
    text_dark = colors.HexColor("#1e293b")     # Body Text Slate
    code_bg = colors.HexColor("#f1f5f9")       # Light Slate
    border_color = colors.HexColor("#e2e8f0")

    styles.add(ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=primary_color,
        alignment=0,
        spaceAfter=12
    ))

    styles.add(ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=13,
        leading=18,
        textColor=accent_blue,
        spaceAfter=24
    ))

    styles.add(ParagraphStyle(
        'CoverMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#475569")
    ))

    styles.add(ParagraphStyle(
        'DocH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=17,
        leading=22,
        textColor=primary_color,
        spaceBefore=18,
        spaceAfter=10,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'DocH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=accent_blue,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'DocH3',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=text_dark,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        'DocBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=text_dark,
        leftIndent=15,
        spaceAfter=4
    ))

    styles.add(ParagraphStyle(
        'DocCodeBlock',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
        backColor=code_bg,
        borderColor=border_color,
        borderWidth=0.5,
        borderPadding=6,
        spaceBefore=6,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        'DocCallout',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
        backColor=colors.HexColor("#eff6ff"),
        borderColor=colors.HexColor("#93c5fd"),
        borderWidth=1,
        borderPadding=8,
        spaceBefore=8,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=text_dark
    ))

    styles.add(ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    ))

    story = []

    # -------------------------------------------------------------
    # COVER PAGE
    # -------------------------------------------------------------
    story.append(Spacer(1, 40))
    story.append(Paragraph("DocStack Enterprise Document Ingestion & Chunking System", styles['CoverTitle']))
    story.append(Paragraph("Complete Technical Architecture, Implementation Manual & Performance Telemetry Specification", styles['CoverSubtitle']))
    story.append(HRFlowable(width="100%", thickness=3, color=accent_blue, spaceBefore=0, spaceAfter=20))

    meta_text = """
    <b>Document Version:</b> 2.0.0-PROD<br/>
    <b>Classification:</b> Enterprise Architectural Specification & SRE Operations Guide<br/>
    <b>Target Platform:</b> Bare-Metal & Multi-Container Docker Compose Stack<br/>
    <b>Primary Components:</b> Node.js (Gateway), Python 3.11 (Worker), Redis (Queue), PostgreSQL 16 + pgvector, Ollama (Embeddings)<br/>
    <b>Security Model:</b> PostgreSQL Kernel Row-Level Security (RLS) + JWT HS256 + Zero External Egress<br/>
    <b>Telemetry Instrumentation:</b> Monotonic Monitored Timestamps & Permanent JSONB Metrics Engine<br/>
    <b>Date:</b> October 2026
    """
    story.append(Paragraph(meta_text, styles['CoverMeta']))
    story.append(Spacer(1, 30))

    # Architecture Overview Graphic on Cover Page
    arch_chart = Path("docs_assets/architecture_topology_diagram.png")
    if arch_chart.exists():
        story.append(Paragraph("<b>System Topology Architecture</b>", styles['DocH3']))
        story.append(Image(str(arch_chart), width=500, height=250))
        story.append(Spacer(1, 15))

    story.append(PageBreak())

    # -------------------------------------------------------------
    # READ AND PARSE MARKDOWN
    # -------------------------------------------------------------
    md_path = Path("SYSTEM_DOCUMENTATION.md")
    content = md_path.read_text(encoding="utf-8")

    lines = content.split("\n")
    in_code_block = False
    code_lines = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        # Handle Code Blocks
        if stripped.startswith("```"):
            if in_code_block:
                # Flush code block
                code_text = "<br/>".join([c.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") for c in code_lines])
                if code_text.strip():
                    story.append(Paragraph(code_text, styles['DocCodeBlock']))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # Handle Tables
        if "|" in line and not stripped.startswith("#"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if parts and not all(p == "" or set(p) <= set("-: ") for p in parts):
                in_table = True
                table_rows.append(parts)
                continue
            elif all(set(p) <= set("-: ") for p in parts if p):
                continue
        else:
            if in_table:
                # Flush table
                if table_rows:
                    formatted_table = []
                    # Header
                    head = [Paragraph(f"<b>{c}</b>", styles['TableHead']) for c in table_rows[0]]
                    formatted_table.append(head)
                    for r in table_rows[1:]:
                        row = [Paragraph(c.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles['TableCell']) for c in r]
                        formatted_table.append(row)
                    
                    t = Table(formatted_table, repeatRows=1)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (-1, -1), 6),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ]))
                    story.append(Spacer(1, 4))
                    story.append(t)
                    story.append(Spacer(1, 8))
                in_table = False
                table_rows = []

        # Skip main markdown title since we have a custom cover page
        if stripped.startswith("# DocStack Enterprise") or stripped.startswith("## Complete Technical"):
            continue

        # Headers
        if stripped.startswith("# "):
            h_text = stripped[2:].strip()
            story.append(Paragraph(h_text, styles['DocH1']))
            story.append(HRFlowable(width="100%", thickness=1, color=accent_blue, spaceBefore=2, spaceAfter=8))
            continue
        elif stripped.startswith("## "):
            h_text = stripped[3:].strip()
            story.append(Paragraph(h_text, styles['DocH2']))
            continue
        elif stripped.startswith("### "):
            h_text = stripped[4:].strip()
            story.append(Paragraph(h_text, styles['DocH3']))

            # Hook Charts into Chapter 15!
            if "15.2 Initial Reference Processing Runs" in h_text:
                chart1 = Path("docs_assets/stage_timings_comparison.png")
                if chart1.exists():
                    story.append(Spacer(1, 6))
                    story.append(Image(str(chart1), width=490, height=245))
                    story.append(Spacer(1, 6))
            elif "15.3 Cross-Format Comparative Dynamics" in h_text:
                chart2 = Path("docs_assets/worker_vs_e2e_breakdown.png")
                chart3 = Path("docs_assets/throughput_latency_distribution.png")
                if chart2.exists():
                    story.append(Spacer(1, 6))
                    story.append(Image(str(chart2), width=480, height=270))
                    story.append(Spacer(1, 6))
                if chart3.exists():
                    story.append(Spacer(1, 6))
                    story.append(Image(str(chart3), width=480, height=216))
                    story.append(Spacer(1, 6))
            continue
        elif stripped.startswith("#### "):
            h_text = stripped[5:].strip()
            story.append(Paragraph(f"<b>{h_text}</b>", styles['DocH3']))
            continue

        # Horizontal Rule
        if stripped == "---":
            story.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceBefore=8, spaceAfter=8))
            continue

        # Callouts / Quotes
        if stripped.startswith("> "):
            callout_text = stripped[2:].replace("[!NOTE]", "<b>NOTE:</b>").replace("[!WARNING]", "<b>WARNING:</b>").replace("[!IMPORTANT]", "<b>IMPORTANT:</b>")
            story.append(Paragraph(callout_text, styles['DocCallout']))
            continue

        # Bullet points
        if stripped.startswith("- ") or stripped.startswith("* "):
            bullet_text = stripped[2:].replace("**", "<b>").replace("**", "</b>")
            # Handle inline markdown bolding
            parts = re.split(r'\*\*(.*?)\*\*', stripped[2:])
            if len(parts) > 1:
                formatted = ""
                for idx, p in enumerate(parts):
                    if idx % 2 == 1:
                        formatted += f"<b>{p}</b>"
                    else:
                        formatted += p
                story.append(Paragraph(f"• {formatted}", styles['DocBullet']))
            else:
                story.append(Paragraph(f"• {stripped[2:]}", styles['DocBullet']))
            continue

        # Standard Paragraphs
        if stripped:
            # Inline bold formatting
            parts = re.split(r'\*\*(.*?)\*\*', stripped)
            if len(parts) > 1:
                formatted = ""
                for idx, p in enumerate(parts):
                    if idx % 2 == 1:
                        formatted += f"<b>{p}</b>"
                    else:
                        formatted += p
                story.append(Paragraph(formatted, styles['DocBody']))
            else:
                story.append(Paragraph(stripped, styles['DocBody']))

    # Build the document with two-pass canvas
    print("Compiling PDF document with ReportLab...")
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF: {pdf_filename} ({Path(pdf_filename).stat().st_size} bytes)")

if __name__ == "__main__":
    build_pdf()
