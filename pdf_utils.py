"""
Shared PDF utilities for EduSphere reports.
Provides consistent layout, styling, and configuration across all PDF exports.
"""

from reportlab.lib.pagesizes import landscape, A4, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
from datetime import datetime
import os


def get_pdf_config():
    """
    Returns shared PDF configuration.
    Uses landscape Letter for maximum width (better than A4 landscape).
    """
    # Landscape Letter provides more width than landscape A4
    # Letter landscape: 11.69 x 8.27 inches
    # A4 landscape: 11.69 x 8.27 inches (similar, but Letter is slightly wider)
    
    return {
        'pagesize': landscape(letter),
        'left_margin': 20,
        'right_margin': 20,
        'top_margin': 30,
        'bottom_margin': 25,
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
        bottomMargin=config['bottom_margin']
    )
    return doc


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
    Returns: "YYYY-MM-DD<br/>HH:MM:SS" or "—" if None
    
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
        date_str = dt.strftime('%Y-%m-%d')
        # Check if it has time component
        if hasattr(dt, 'hour') and (dt.hour != 0 or dt.minute != 0 or dt.second != 0):
            time_str = dt.strftime('%H:%M:%S')
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


def get_column_widths(report_type):
    """
    Returns column width configuration for each report type.
    Widths are percentages of available page width.
    
    Returns list of column widths in cm units.
    """
    # Landscape Letter width is approximately 28 cm (11 inches)
    # With 20pt margins on each side, available width is ~26 cm
    # We use cm units for consistency
    
    if report_type == 'users':
        # Name: 18%, Email: 28%, Role: 10%, Status: 10%, Created At: 18%, Actions: 16%
        return [4.7*cm, 7.3*cm, 2.6*cm, 2.6*cm, 4.7*cm, 4.1*cm]
    
    elif report_type == 'activity':
        # User: 16%, Role: 10%, Email: 25%, Action: 29%, Timestamp: 20%
        return [4.2*cm, 2.6*cm, 6.5*cm, 7.5*cm, 5.2*cm]
    
    elif report_type == 'exam':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Faculty: 15%, Score: 8%, Total: 8%, %: 6%, Result: 6%
        return [4.7*cm, 3.9*cm, 3.1*cm, 3.1*cm, 3.9*cm, 2.1*cm, 2.1*cm, 1.6*cm, 1.6*cm]
    
    elif report_type == 'faculty':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Score: 8%, Total: 8%, %: 6%, Result: 6%, Actions: 15%
        return [4.7*cm, 3.9*cm, 3.1*cm, 3.1*cm, 2.1*cm, 2.1*cm, 1.6*cm, 1.6*cm, 3.9*cm]
    
    elif report_type == 'student':
        # Exam: 20%, Subject: 15%, Date: 12%, Score: 8%, Total: 8%, %: 6%, Result: 6%, Actions: 25%
        return [5.2*cm, 3.9*cm, 3.1*cm, 2.1*cm, 2.1*cm, 1.6*cm, 1.6*cm, 6.5*cm]
    
    elif report_type == 'analytics':
        # Exam: 18%, Classroom: 15%, Subject: 12%, Date: 12%, Attempts: 8%, Avg Score: 8%, Avg %: 8%, Max: 6%, Min: 6%, Total: 7%
        return [4.7*cm, 3.9*cm, 3.1*cm, 3.1*cm, 2.1*cm, 2.1*cm, 2.1*cm, 1.6*cm, 1.6*cm, 1.8*cm]
    
    elif report_type == 'classroom':
        # Name: 20%, Registration: 15%, Email: 25%, Joined: 15%, Actions: 25%
        return [5.2*cm, 3.9*cm, 6.5*cm, 3.9*cm, 6.5*cm]
    
    elif report_type == 'integrity':
        # Student: 18%, Exam: 15%, Subject: 12%, Date: 12%, Flagged: 12%, Actions: 31%
        return [4.7*cm, 3.9*cm, 3.1*cm, 3.1*cm, 3.1*cm, 8.1*cm]
    
    elif report_type == 'question_bank':
        # Question: 35%, Subject: 15%, Type: 10%, Marks: 8%, Difficulty: 10%, Actions: 22%
        return [9.1*cm, 3.9*cm, 2.6*cm, 2.1*cm, 2.6*cm, 5.7*cm]
    
    else:
        # Default fallback
        return [3.0*cm] * 5


def create_header_table(title, logo_path=None):
    """
    Creates a standardized header table with logo and title.
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
    
    hdr_table = Table(
        [["", Paragraph(title, styles['title']), logo_cell]],
        colWidths=[3.5*cm, 11*cm, 3.5*cm]
    )
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    
    return hdr_table


def create_summary_table(summary_data):
    """
    Creates a standardized summary table.
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
