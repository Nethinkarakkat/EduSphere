"""
Shared PDF utilities for EduSphere reports.
Provides consistent layout, styling, and configuration across all PDF exports.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, PageBreak
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
import os


def get_pdf_config():
    """
    Returns shared PDF configuration.
    Uses A4 portrait with consistent margins.
    """
    return {
        'pagesize': A4,
        'left_margin': 18,
        'right_margin': 18,
        'top_margin': 20,
        'bottom_margin': 20,
    }


def create_pdf_document(response):
    """
    Creates a SimpleDocTemplate with shared configuration.
    """
    config = get_pdf_config()
    doc = SimpleDocTemplate(
        response,
        pagesize=config['pagesize'],
        leftMargin=config['left_margin'],
        rightMargin=config['right_margin'],
        topMargin=config['top_margin'],
        bottomMargin=config['bottom_margin'],
        onFirstPage=add_page_number,
        onLaterPages=add_page_number
    )
    return doc


def add_page_number(canvas, doc):
    """Add page number to footer with total pages."""
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    page_num = canvas.getPageNumber()
    total_pages = getattr(doc, 'numPages', 1)
    canvas.drawCentredString(
        A4[0] / 2,
        10,
        f"Page {page_num} of {total_pages}"
    )
    canvas.restoreState()


def get_pdf_styles():
    """
    Returns shared PDF styles for consistent formatting.
    """
    styles = getSampleStyleSheet()
    
    # Wrap style for general text wrapping
    wrap_style = styles['Normal'].clone('wrap')
    wrap_style.fontSize = 10
    wrap_style.leading = 14
    wrap_style.textColor = colors.HexColor('#333333')
    wrap_style.wordWrap = 'LTR'
    wrap_style.splitLongWords = False
    
    # Name style - no wrapping, single line
    name_style = styles['Normal'].clone('name')
    name_style.fontSize = 10
    name_style.leading = 14
    name_style.textColor = colors.HexColor('#333333')
    name_style.wordWrap = 'LTR'
    name_style.splitLongWords = False
    name_style.alignment = 0  # Left align
    
    # Header style
    brand_style = styles['Normal'].clone('brand')
    brand_style.fontSize = 11
    brand_style.fontName = 'Helvetica-Bold'
    brand_style.textColor = colors.HexColor('#4f46e5')
    brand_style.alignment = 1
    brand_style.spaceAfter = 0
    
    # Title style
    title_style = styles['Normal'].clone('title')
    title_style.fontSize = 24
    title_style.fontName = 'Helvetica-Bold'
    title_style.textColor = colors.black
    title_style.alignment = 1
    title_style.leading = 28
    
    # Summary heading style
    summary_heading_style = styles['Normal'].clone('sumhead')
    summary_heading_style.fontSize = 18
    summary_heading_style.fontName = 'Helvetica-Bold'
    summary_heading_style.textColor = colors.black
    summary_heading_style.alignment = 0
    summary_heading_style.spaceBefore = 10
    summary_heading_style.spaceAfter = 8
    
    # Footer style
    footer_style = styles['Normal'].clone('footer')
    footer_style.fontSize = 8
    footer_style.textColor = colors.grey
    footer_style.alignment = 1
    
    return {
        'wrap': wrap_style,
        'name': name_style,
        'brand': brand_style,
        'title': title_style,
        'summary_heading': summary_heading_style,
        'footer': footer_style,
    }


def format_datetime(dt):
    """
    Formats datetime for PDF display on two lines.
    Returns: "DD Mon YYYY<br/>H:MM AM/PM" or "—" if None
    
    Handles both datetime objects and string representations.
    """
    if dt is None:
        return "—"
    
    # If it's a string, try to parse it first
    if isinstance(dt, str):
        try:
            # Try common datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(dt, fmt)
                    break
                except ValueError:
                    continue
        except Exception:
            # If parsing fails, return the original string
            return str(dt)
    
    # Now format the datetime object
    if hasattr(dt, 'strftime'):
        date_str = dt.strftime('%d %b %Y')  # 18 Jul 2026
        # Check if it has time component
        if hasattr(dt, 'hour') and (dt.hour != 0 or dt.minute != 0 or dt.second != 0):
            time_str = dt.strftime('%I:%M %p')  # 2:52 PM
            return f"{date_str}<br/>{time_str}"
        else:
            return date_str
    
    return str(dt)


def get_table_style(column_count):
    """
    Returns shared table style configuration.
    Applies consistent styling across all reports.
    """
    style_rules = [
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('LEFTPADDING', (0, 0), (-1, 0), 10),
        ('RIGHTPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Body styling
        ('LEFTPADDING', (0, 1), (-1, -1), 8),
        ('RIGHTPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    
    return TableStyle(style_rules)


def get_column_widths(report_type, doc_width=None):
    """
    Returns column width configuration for each report type.
    Widths are percentages of available page width.
    
    Args:
        report_type: Type of report ('users', 'activity', 'exam', etc.)
        doc_width: Available document width in points (optional)
    
    Returns list of column widths in points units.
    """
    # A4 width is approximately 595 points
    # With 18pt margins on each side, available width is ~559 points
    if doc_width is None:
        doc_width = 559  # Default A4 width with 18pt margins
    
    # Define column percentages for each report type
    if report_type == 'users':
        # Name: 18%, Email: 28%, Role: 10%, Status: 10%, Created At: 18%, Actions: 16%
        percentages = [0.18, 0.28, 0.10, 0.10, 0.18, 0.16]
    
    elif report_type == 'activity':
        # User: 16%, Role: 10%, Email: 32%, Action: 22%, Timestamp: 20%
        percentages = [0.16, 0.10, 0.32, 0.22, 0.20]
    
    elif report_type == 'exam':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Faculty: 15%, Score: 8%, Total: 8%, %: 6%, Result: 6%
        percentages = [0.18, 0.15, 0.12, 0.12, 0.15, 0.08, 0.08, 0.06, 0.06]
    
    elif report_type == 'faculty':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Score: 8%, Total: 8%, %: 6%, Result: 6%, Actions: 15%
        percentages = [0.18, 0.15, 0.12, 0.12, 0.08, 0.08, 0.06, 0.06, 0.15]
    
    elif report_type == 'student':
        # Exam: 20%, Subject: 15%, Date: 12%, Score: 8%, Total: 8%, %: 6%, Result: 6%, Actions: 25%
        percentages = [0.20, 0.15, 0.12, 0.08, 0.08, 0.06, 0.06, 0.25]
    
    elif report_type == 'analytics':
        # Exam: 18%, Classroom: 15%, Subject: 12%, Date: 12%, Attempts: 8%, Avg Score: 8%, Avg %: 8%, Max: 6%, Min: 6%, Total: 7%
        percentages = [0.18, 0.15, 0.12, 0.12, 0.08, 0.08, 0.08, 0.06, 0.06, 0.07]
    
    elif report_type == 'classroom':
        # Name: 20%, Registration: 15%, Email: 25%, Joined: 15%, Actions: 25%
        percentages = [0.20, 0.15, 0.25, 0.15, 0.25]
    
    elif report_type == 'integrity':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Flagged: 12%, Actions: 31%
        percentages = [0.18, 0.15, 0.12, 0.12, 0.12, 0.31]
    
    elif report_type == 'question_bank':
        # Question: 35%, Subject: 15%, Type: 10%, Marks: 8%, Difficulty: 10%, Actions: 22%
        percentages = [0.35, 0.15, 0.10, 0.08, 0.10, 0.22]
    
    else:
        # Default fallback
        percentages = [0.20] * 5
    
    # Calculate actual widths in points
    return [doc_width * pct for pct in percentages]


def create_header_table(title, logo_path=None):
    """
    Creates a standardized header table with centered logo, branding, and title.
    """
    styles = get_pdf_styles()
    
    if logo_path and os.path.exists(logo_path):
        logo = Image(logo_path, width=2.0*cm, height=2.0*cm)
        logo_cell = Table(
            [[logo], [Paragraph('EduSphere', styles['brand'])]],
            colWidths=[2.5*cm]
        )
        logo_cell.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('RIGHTPADDING', (0, 0), (0, -1), 0),
            ('TOPPADDING', (0, 0), (0, -1), 0),
            ('BOTTOMPADDING', (0, 0), (0, 0), 2),
            ('BOTTOMPADDING', (0, 1), (0, 1), 0),
        ]))
    else:
        logo_cell = Paragraph('EduSphere', styles['brand'])
    
    # Create a cohesive header block with logo/branding centered above title
    header_elements = [
        [logo_cell],
        [Paragraph(title, styles['title'])]
    ]
    
    hdr_table = Table(header_elements, colWidths=[18*cm])
    hdr_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    
    return hdr_table


def create_summary_table(summary_data):
    """
    Creates a standardized summary table with bordered box styling.
    summary_data should be a list of [label, value] pairs.
    """
    styles = get_pdf_styles()
    
    formatted_data = [["", label, value] for label, value in summary_data]
    formatted_data.append(["", "Generated:", datetime.now().strftime('%d %b %Y %H:%M')])
    
    summary_table = Table(formatted_data, colWidths=[2*cm, 4*cm, 6*cm])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 0), (1, -1), 12),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica'),
        ('FONTSIZE', (2, 0), (2, -1), 12),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#333333')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]))
    
    return summary_table


def apply_column_alignment(table_style, column_configs):
    """
    Applies column-specific alignment and word wrap settings.
    
    column_configs: list of dicts with keys:
        - 'align': 'LEFT', 'CENTER', or 'RIGHT'
        - 'wrap': True or False
    """
    for col_idx, config in enumerate(column_configs):
        align = config.get('align', 'LEFT')
        wrap = config.get('wrap', True)
        
        # Apply alignment to body rows (skip header row 0)
        table_style.add('ALIGN', (col_idx, 1), (col_idx, -1), align)
        
        # Apply word wrap to body rows
        table_style.add('WORDWRAP', (col_idx, 1), (col_idx, -1), wrap)
    
    return table_style
