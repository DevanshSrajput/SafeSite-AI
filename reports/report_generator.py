import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, Image, PageBreak)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

SCREENSHOTS_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

PRIMARY_COLOR = HexColor('#E63946')
DARK_COLOR = HexColor('#1D3557')
LIGHT_BG = HexColor('#F1FAEE')


def generate_report(violations, start_date, end_date):
    """Generate a PDF incident report and return it as bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            topMargin=30*mm, bottomMargin=20*mm,
                            leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'],
                                  fontSize=24, textColor=DARK_COLOR,
                                  spaceAfter=12)
    subtitle_style = ParagraphStyle('ReportSubtitle', parent=styles['Normal'],
                                     fontSize=12, textColor=grey,
                                     spaceAfter=20, alignment=TA_CENTER)
    heading_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'],
                                    fontSize=14, textColor=DARK_COLOR,
                                    spaceBefore=16, spaceAfter=8)
    normal_style = styles['Normal']

    elements = []

    # --- Title Page ---
    elements.append(Spacer(1, 40*mm))
    elements.append(Paragraph('SafeSite AI', title_style))
    elements.append(Paragraph('Incident Report', ParagraphStyle(
        'SubTitle2', parent=styles['Title'], fontSize=18,
        textColor=PRIMARY_COLOR, spaceAfter=8)))
    elements.append(Paragraph(
        f'Period: {start_date} to {end_date}', subtitle_style))
    elements.append(Paragraph(
        f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', subtitle_style))
    elements.append(Spacer(1, 20*mm))

    # --- Summary Statistics ---
    total = len(violations)
    type_counts = {}
    zone_counts = {}
    for v in violations:
        vtype = v['violation_type']
        type_counts[vtype] = type_counts.get(vtype, 0) + 1
        zname = v.get('zone_name', '')
        if zname:
            zone_counts[zname] = zone_counts.get(zname, 0) + 1

    elements.append(Paragraph('Summary', heading_style))

    summary_data = [['Metric', 'Value']]
    summary_data.append(['Total Violations', str(total)])
    for vtype, count in type_counts.items():
        summary_data.append([f'  {vtype}', str(count)])
    if zone_counts:
        summary_data.append(['', ''])
        summary_data.append(['Zone Breakdown', ''])
        for zname, count in zone_counts.items():
            summary_data.append([f'  {zname}', str(count)])

    summary_table = Table(summary_data, colWidths=[120*mm, 40*mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
        ('GRID', (0, 0), (-1, -1), 0.5, grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 10*mm))

    # --- Detailed Violations ---
    elements.append(Paragraph('Violation Details', heading_style))

    for i, v in enumerate(violations):
        elements.append(Spacer(1, 4*mm))

        # Violation header
        entry_data = [
            ['#', str(i + 1), 'Type', v['violation_type']],
            ['Time', v['timestamp'], 'Zone', v.get('zone_name', 'N/A') or 'N/A'],
            ['Confidence', f"{v.get('confidence_score', 0):.1%}", '', ''],
        ]
        entry_table = Table(entry_data, colWidths=[20*mm, 55*mm, 20*mm, 55*mm])
        entry_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.3, grey),
            ('BACKGROUND', (0, 0), (0, -1), LIGHT_BG),
            ('BACKGROUND', (2, 0), (2, -1), LIGHT_BG),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(entry_table)

        # Screenshot if available
        screenshot = v.get('screenshot_path', '')
        if screenshot:
            img_path = os.path.join(SCREENSHOTS_BASE, screenshot)
            if os.path.exists(img_path):
                try:
                    img = Image(img_path, width=140*mm, height=80*mm)
                    img.hAlign = 'CENTER'
                    elements.append(Spacer(1, 2*mm))
                    elements.append(img)
                except Exception:
                    pass

        # Page break every 3 violations to keep it tidy
        if (i + 1) % 3 == 0 and i < total - 1:
            elements.append(PageBreak())

    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
