
import os
import re
import json
import zipfile
import shutil
import tempfile
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_PARAGRAPH_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from datetime import datetime
try:
    from .language_helpers import sanitize_arabic_sms_answer
except Exception:
    def sanitize_arabic_sms_answer(answer):
        return answer


# ========================== #
#      Arabic RTL Helpers    #
# ========================== #

def _ensure_run_arabic_font(run, font_name="Arial"):
    """Apply Arabic-compatible font settings to a run."""
    try:
        run.font.name = font_name
        r_pr = run._r.get_or_add_rPr()
        r_fonts = r_pr.rFonts
        if r_fonts is None:
            r_fonts = OxmlElement("w:rFonts")
            r_pr.append(r_fonts)
        r_fonts.set(qn("w:ascii"), font_name)
        r_fonts.set(qn("w:hAnsi"), font_name)
        r_fonts.set(qn("w:cs"), font_name)
        r_fonts.set(qn("w:eastAsia"), font_name)
    except Exception:
        pass


def _set_paragraph_rtl(paragraph, align_right=True):
    """Force a paragraph to behave as Arabic RTL in Microsoft Word."""
    try:
        if align_right:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        p_pr = paragraph._p.get_or_add_pPr()

        bidi = p_pr.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            p_pr.append(bidi)
        bidi.set(qn("w:val"), "1")

        jc = p_pr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            p_pr.append(jc)
        if align_right:
            jc.set(qn("w:val"), "right")

        for run in paragraph.runs:
            r_pr = run._r.get_or_add_rPr()
            rtl = r_pr.find(qn("w:rtl"))
            if rtl is None:
                rtl = OxmlElement("w:rtl")
                r_pr.append(rtl)
            rtl.set(qn("w:val"), "1")
            _ensure_run_arabic_font(run)
    except Exception:
        pass


def _set_cell_rtl(cell):
    """Force all paragraphs inside a table cell to RTL."""
    try:
        tc_pr = cell._tc.get_or_add_tcPr()
        text_direction = tc_pr.find(qn("w:textDirection"))
        if text_direction is None:
            text_direction = OxmlElement("w:textDirection")
            tc_pr.append(text_direction)
        text_direction.set(qn("w:val"), "rlTb")
    except Exception:
        pass

    for paragraph in cell.paragraphs:
        _set_paragraph_rtl(paragraph)


def _set_table_rtl(table):
    """Force table direction to RTL and align it to the right."""
    try:
        table.alignment = WD_TABLE_ALIGNMENT.RIGHT
        tbl_pr = table._tbl.tblPr
        bidi_visual = tbl_pr.find(qn("w:bidiVisual"))
        if bidi_visual is None:
            bidi_visual = OxmlElement("w:bidiVisual")
            tbl_pr.append(bidi_visual)
        bidi_visual.set(qn("w:val"), "1")
    except Exception:
        pass

    for row in table.rows:
        for cell in row.cells:
            _set_cell_rtl(cell)


def _force_document_rtl(document):
    """Safe final pass before saving: right-align Arabic DOCX content without editing the saved zip."""
    _set_document_rtl_settings(document)

    def force_p(paragraph):
        # Keep logo-only paragraphs centered/right as Word decides; all text paragraphs are RTL/right.
        if paragraph.runs and any((run.text or "").strip() for run in paragraph.runs):
            _set_paragraph_direction(paragraph, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
            for run in paragraph.runs:
                _set_run_font(run, font_name=ARABIC_FONT, lang_code="ar-SA")

    for paragraph in document.paragraphs:
        force_p(paragraph)

    for table in document.tables:
        _set_table_rtl(table)
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    force_p(paragraph)

    for section in document.sections:
        for paragraph in section.header.paragraphs:
            force_p(paragraph)
        for paragraph in section.footer.paragraphs:
            force_p(paragraph)
        for table in section.header.tables:
            _set_table_rtl(table)
        for table in section.footer.tables:
            _set_table_rtl(table)

def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in markdown_table_text.strip().splitlines() if '|' in line]
    if len(lines) < 2:
        doc.add_paragraph(markdown_table_text)
        return

    header_cells = [cell.strip() for cell in lines[0].split('|') if cell.strip()]
    table = doc.add_table(rows=1, cols=len(header_cells))
    hdr_cells = table.rows[0].cells
    for i, text in enumerate(header_cells):
        hdr_cells[i].text = text

    for line in lines[2:]:
        row_cells = [cell.strip() for cell in line.split('|') if cell.strip()]
        row = table.add_row().cells
        for i, text in enumerate(row_cells):
            row[i].text = text

# --- Basic Arabic/English paragraph handler ---
def add_wrapped_paragraph(doc, text):
    is_arabic_flag, fixed_text = is_arabic(text)
    p = doc.add_paragraph()
    lang_code = 'ar' if is_arabic_flag else 'en-US'

    # Inject direction control characters for mixed lines
    if is_arabic_flag and any(c.isascii() for c in text):
        fixed_text = f"\u202B{fixed_text}\u202C"  # RTL embedding
    elif not is_arabic_flag and any('\u0600' <= c <= '\u06FF' for c in text):
        fixed_text = f"\u202A{fixed_text}\u202C"  # LTR embedding

    if is_arabic_flag:
        p._element.get_or_add_pPr().set(qn('w:rtl'), '1')
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    set_paragraph_language(p, lang_code)
    run = p.add_run(fixed_text)
    set_run_language(run, lang_code)
    process_italic_and_bold(p)
    p.paragraph_format.space_after = Pt(10)


# --- SMS Formatters (placeholders) ---
# --- Style and layout ---
def add_colored_heading(doc, title):
    title = str(title or "")
    rtl = contains_arabic(title)

    p = doc.add_paragraph()

    if rtl:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        pPr = p._p.get_or_add_pPr()

        bidi = pPr.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            pPr.append(bidi)
        bidi.set(qn("w:val"), "1")

        jc = pPr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pPr.append(jc)
        jc.set(qn("w:val"), "right")
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    run = p.add_run(title)
    _set_run_font(
        run,
        font_name=ARABIC_FONT if rtl else ENGLISH_FONT,
        size=13,
        bold=True,
        color=RGBColor(0xFF, 0xFF, 0xFF),
        lang_code="ar-SA" if rtl else "en-US",
    )

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "2E75B6")
    p._element.get_or_add_pPr().append(shd)

    return p

def add_sms_list(doc, sms_text, numbered_sms=False):
    for line in sms_text.splitlines():
        if line.strip():
            doc.add_paragraph(line.strip(), style='ListNumber' if numbered_sms else 'ListBullet')

def arabic_sms_formatting(doc, sms_text):
    for line in sms_text.splitlines():
        if line.strip():
            para = doc.add_paragraph(line.strip())
            para._element.get_or_add_pPr().set(qn('w:rtl'), '1')
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            set_paragraph_language(para, 'ar')


# --- Main document generator ---
def generate_ai_docx(campaign_id, json_path, numbered_sms=False):
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    EXPORT_DIR = os.path.join(BASE_DIR, "exports", "docx")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    print(campaign_id, "has been created")

    print("📄 Loading JSON from:", json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    company_name= data.get('company_name', '[Not available]')
    company_url=data.get('company_url', '[Not available]')
    campaign_title=data.get('chain_campaign_title','SMS Marketing Campaign')
    # campaign_brief = data.get('campaign_brief', '[Not available]')

    sms_type=data.get('sms_type', 'smart')
    company_profile=data.get('company_profile', False)
    marketing_plan=data.get('marketing_plan', False)
    if company_profile==False or marketing_plan==False:
        output_path = os.path.join(EXPORT_DIR, f"{company_name[:-7]} - JorMall SMS.docx")
    else:
        output_path = os.path.join(EXPORT_DIR, f"{company_name} - JorMall SMS.docx")
    doc = Document()
    font = doc.styles['Normal'].font
    font.name = 'Arial'
    font.size = Pt(11)
    core_props = doc.core_properties
    core_props.author = "Central E-Commerce Ltd. (JorMall)"
    core_props.last_modified_by = "Central E-Commerce Ltd. (JorMall)"
    core_props.title = ""
    core_props.subject = ""
    core_props.comments = ""
    if company_profile==False and marketing_plan==False:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        
        # Determine campaign type based on SMS type
        if sms_type == "smart":
            campaign_title = "Smart Reach SMS Campaign"
            campaign_type = "Single SMS with Intelligent Targeting and Optimized Delivery"
        elif sms_type == "chain":
            campaign_title+= " – \nChain SMS Awareness Campaign"
            campaign_type='“Timed Messaging for Sustained Engagement and Higher Retention”'
        elif sms_type == "premium":
            campaign_title='Premium Multimedia Marketing Campaign'
            campaign_type = '“Integrated Creative Solutions Across All Channels”'
        elif sms_type == "personalized":
            campaign_title = "Personalized SMS Campaign"
            campaign_type = "Long-Format, Name-Based Messaging for Direct Customer Connection"
        elif sms_type == "lead":
            campaign_title = "Lead Collecting SMS Campaign"
            campaign_type = "Click-Based Engagement for Real-Time Interest Detection by Recipient"

        elif sms_type == "optin":
            campaign_title = "Opt-in/Opt-out SMS Compliance Campaign"
            campaign_type = "Consent-Based Messaging to Build Trust and Maintain TRC Compliance"
        else:
            campaign_type = "General Campaign"

        # Now pass it to the cover page function
        add_campaign_cover_page(
            doc,
            logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            campaign_title=campaign_title,
            client_name=company_name,
            campaign_type=campaign_type
        )


        if sms_type=="chain":
            add_chain_sms_section(doc)
        elif sms_type=="premium":
            add_premium_sms_section(doc)
            doc.add_section(WD_SECTION.NEW_PAGE)
        elif sms_type=="personalized":
            add_personalized_sms_section(doc)   
        elif sms_type=="optin":
            add_optin_sms_section(doc)
        elif sms_type=="lead":
            add_lead_sms_section(doc)
        else:
            pass


        if company_name != "[Not available]" and company_url != "[Not available]":
            doc.add_heading("SMS Marketing Campaign Report", 0)
            doc.add_paragraph(f"Company Name: {company_name}")
            doc.add_paragraph(f"Company Website: {company_url}")
        
        # if campaign_brief != "[Not available]":
        #     doc.add_paragraph(f"Campaign Brief: {campaign_brief}")


        
        header = doc.sections[0].header
        paragraph = header.paragraphs[0]
        try:
            logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png")
            paragraph.add_run().add_picture(logo_path, width=Inches(1.3))
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        except Exception as e:
            print("⚠️ Logo not found or failed to load:", e)
            paragraph.add_run("[الشعار غير متوفر]").bold = True
    elif company_profile:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        add_sales_profile_cover_page(
            doc,
            logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name
        )
    elif marketing_plan:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        add_marketing_plan_cover_page(
            doc,
            logo_path=os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name
        )
    else:
        pass

    for _, content in data.get("analysis", {}).items():

        header = content.get("header", "")
        answer = content.get("answer", "")
        message_index = content.get("message_index", "")
        pitch = content.get("pitch")
        delivery_date = content.get("delivery_date", datetime.today().strftime("%A, %d %B %Y"))
        delivery_time = content.get("delivery_time", "00:00")

        if sms_type == "premium":
            add_premium_intro_paragraph(doc, header)

        if sms_type == "chain":
            add_chain_message_page_arabic(doc, message_index, pitch, delivery_date, delivery_time)
            if header=="Target Audience":
                chain_messages = data.get("chain_messages", [])
                add_chain_summary(doc, "Chain SMS Campaign Summary", chain_messages)
        # Main heading
        add_colored_heading(doc, header)
        if marketing_plan:
            if header == "SMS Timing Strategy (Scheduling)":
                add_seasonal_sms_calendar(doc)
        if "English SMS Suggestions" in content.get("header", ""):
            add_wrapped_paragraph(doc, answer)
        elif "Arabic SMS Suggestions" in content.get("header", ""):
            arabic_sms_formatting(doc, answer)
        elif "|" in answer and "---" in answer:
            add_markdown_table(doc, answer)

        else:
            add_wrapped_paragraph(doc, answer)

    doc.add_section(WD_SECTION.NEW_PAGE)
    add_colored_heading(doc, "About JorMall SMS Service")
    add_jormall_sms_services_section(doc)
    section = doc.sections[0]
    footer = section.footer
    fpara = footer.paragraphs[0]
    fpara.text = (
        "JorMall Sales and Support Teams are always at your service,\n"
        "For any inquiries contact your account executive at JorMall or email to order.processing@jormall.com\n"
    )
    fpara.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fpara.style.font.size = Pt(9)

    try:
        print("💾 Saving DOCX to:", output_path)
        _force_document_rtl(doc)
        doc.save(output_path)
        print("✅ DOCX saved successfully.")
    except Exception as e:
        print("❌ Failed to save DOCX:", e)
        raise

    return output_path

# if __name__==("__main__"):
#     # Example usage
#     generate_ai_docx(
#         campaign_id="d4f37a7a-ae72-4d1c-807b-ec1958fd1952",
#         json_path="/Users/ai_engineer/Desktop/sales_chatbot_v9/exports/json/d4f37a7a-ae72-4d1c-807b-ec1958fd1952_analysis.json",
#         numbered_sms=False
#     )


# =====================================================================
# ARABIC DOCUMENT VERSION / RTL MARKDOWN SUPPORT
# This section intentionally overrides selected helpers and generate_ai_docx()
# so the same JSON structure can generate Arabic Word documents.
# =====================================================================

ARABIC_FONT = "Arial"
ENGLISH_FONT = "Arial"
JORMALL_BLUE = RGBColor(0x25, 0x75, 0xB6)
JORMALL_GRAY = RGBColor(0x44, 0x44, 0x44)


def contains_arabic(text):
    text = str(text or "")
    return any("\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F" or "\u08A0" <= c <= "\u08FF" for c in text)


def _set_run_font(run, font_name=ARABIC_FONT, size=None, bold=None, italic=None, color=None, lang_code="ar-SA"):
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if size is not None:
        run.font.size = Pt(size) if isinstance(size, (int, float)) else size
    if color is not None:
        run.font.color.rgb = color

    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.rFonts
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rFonts.set(qn("w:eastAsia"), font_name)
    rFonts.set(qn("w:cs"), font_name)
    set_run_language(run, lang_code)
    return run


def _set_paragraph_direction(paragraph, rtl=True, align=None, lang_code="ar-SA"):
    pPr = paragraph._element.get_or_add_pPr()
    if rtl:
        bidi = pPr.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            pPr.append(bidi)
        bidi.set(qn("w:val"), "1")
        # For bidi paragraphs, LibreOffice/Word render visual right alignment with w:jc="left".
        # This produces the actual on-page right alignment requested for Arabic text.
        if align == WD_ALIGN_PARAGRAPH.CENTER:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            jc_value = "center"
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            jc_value = "right"
        jc = pPr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pPr.append(jc)
        jc.set(qn("w:val"), jc_value)
        set_paragraph_language(paragraph, lang_code)
    else:
        paragraph.alignment = align if align is not None else WD_ALIGN_PARAGRAPH.LEFT
        jc = pPr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pPr.append(jc)
        jc.set(qn("w:val"), "left")
        set_paragraph_language(paragraph, "en-US")
    return paragraph


def _set_cell_rtl(cell, rtl=True):
    tcPr = cell._tc.get_or_add_tcPr()
    if rtl:
        text_dir = tcPr.find(qn("w:textDirection"))
        if text_dir is None:
            text_dir = OxmlElement("w:textDirection")
            tcPr.append(text_dir)
        text_dir.set(qn("w:val"), "rlTb")
    for p in cell.paragraphs:
        _set_paragraph_direction(p, rtl=rtl)


def _set_table_rtl(table):
    tblPr = table._tbl.tblPr
    bidi = tblPr.find(qn("w:bidiVisual"))
    if bidi is None:
        bidi = OxmlElement("w:bidiVisual")
        tblPr.append(bidi)
    bidi.set(qn("w:val"), "1")
    for row in table.rows:
        for cell in row.cells:
            _set_cell_rtl(cell, True)


def _add_inline_markdown_runs(paragraph, text, rtl=True):
    """Adds text to paragraph while preserving simple markdown: **bold**, *italic*."""
    lang_code = "ar-SA" if rtl else "en-US"
    font_name = ARABIC_FONT if rtl else ENGLISH_FONT
    tokens = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", str(text or ""))
    for token in tokens:
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, font_name=font_name, bold=True, lang_code=lang_code)
        elif token.startswith("*") and token.endswith("*"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, font_name=font_name, italic=True, lang_code=lang_code)
        else:
            run = paragraph.add_run(token)
            _set_run_font(run, font_name=font_name, lang_code=lang_code)


def _add_rtl_paragraph(doc, text="", bold=False, italic=False, size=11, color=None, align=WD_ALIGN_PARAGRAPH.RIGHT, style=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _set_paragraph_direction(p, rtl=True, align=align)
    if text:
        # Keep markdown if text includes ** or *.
        if "**" in str(text) or "*" in str(text):
            _add_inline_markdown_runs(p, text, rtl=True)
            for run in p.runs:
                if size:
                    run.font.size = Pt(size)
                if color:
                    run.font.color.rgb = color
                if bold:
                    run.bold = True
                if italic:
                    run.italic = True
        else:
            r = p.add_run(str(text))
            _set_run_font(r, font_name=ARABIC_FONT, size=size, bold=bold, italic=italic, color=color, lang_code="ar-SA")
    p.paragraph_format.space_after = Pt(8)
    return p


def _add_ltr_paragraph(doc, text="", bold=False, italic=False, size=11, color=None, align=WD_ALIGN_PARAGRAPH.LEFT, style=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _set_paragraph_direction(p, rtl=False, align=align)
    r = p.add_run(str(text or ""))
    _set_run_font(r, font_name=ENGLISH_FONT, size=size, bold=bold, italic=italic, color=color, lang_code="en-US")
    p.paragraph_format.space_after = Pt(8)
    return p


# Override: Arabic-aware markdown table formatter.
def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in str(markdown_table_text or "").strip().splitlines() if "|" in line]
    if len(lines) < 2:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    header_cells = [cell.strip() for cell in lines[0].split("|") if cell.strip()]
    if not header_cells:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    table = doc.add_table(rows=1, cols=len(header_cells))
    try:
        table.style = "Table Grid"
    except Exception:
        pass

    is_rtl_table = contains_arabic(markdown_table_text)
    if is_rtl_table:
        _set_table_rtl(table)

    hdr_cells = table.rows[0].cells
    for i, text in enumerate(header_cells):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        _set_paragraph_direction(p, rtl=is_rtl_table, align=WD_ALIGN_PARAGRAPH.RIGHT if is_rtl_table else WD_ALIGN_PARAGRAPH.LEFT)
        _add_inline_markdown_runs(p, text, rtl=is_rtl_table)
        for run in p.runs:
            run.bold = True

    for line in lines[2:]:
        row_cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        row = table.add_row().cells
        for i, text in enumerate(row_cells[:len(header_cells)]):
            row[i].text = ""
            p = row[i].paragraphs[0]
            _set_paragraph_direction(p, rtl=is_rtl_table, align=WD_ALIGN_PARAGRAPH.RIGHT if is_rtl_table else WD_ALIGN_PARAGRAPH.LEFT)
            _add_inline_markdown_runs(p, text, rtl=is_rtl_table)

    if is_rtl_table:
        _set_table_rtl(table)


# Override: Arabic-aware paragraph handler with markdown and RTL support.
def add_wrapped_paragraph(doc, text):
    text = str(text or "")
    if not text.strip():
        return

    # Split long answers into paragraphs, keep bullets readable.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        blocks = [text]

    for block in blocks:
        # Render markdown tables when a block is a markdown table.
        if "|" in block and "---" in block:
            add_markdown_table(doc, block)
            continue

        lines = block.splitlines()
        for line in lines:
            clean = line.strip()
            if not clean:
                continue

            bullet_match = re.match(r"^([-*•]|\d+[.)])\s+(.+)$", clean)
            is_rtl = contains_arabic(clean)
            if bullet_match:
                content = bullet_match.group(2).strip()
                style = "List Bullet"
                p = doc.add_paragraph(style=style)
                _set_paragraph_direction(p, rtl=is_rtl, align=WD_ALIGN_PARAGRAPH.RIGHT if is_rtl else WD_ALIGN_PARAGRAPH.LEFT)
                _add_inline_markdown_runs(p, content, rtl=is_rtl)
            else:
                if is_rtl:
                    p = doc.add_paragraph()
                    _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
                    _add_inline_markdown_runs(p, clean, rtl=True)
                else:
                    p = doc.add_paragraph()
                    _set_paragraph_direction(p, rtl=False, align=WD_ALIGN_PARAGRAPH.LEFT)
                    _add_inline_markdown_runs(p, clean, rtl=False)
            p.paragraph_format.space_after = Pt(8)


# Override: Arabic-aware colored heading.
def add_colored_heading(doc, title):
    title = str(title or "")
    rtl = contains_arabic(title)
    p = doc.add_paragraph()
    _set_paragraph_direction(p, rtl=rtl, align=WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT)
    run = p.add_run(title)
    _set_run_font(
        run,
        font_name=ARABIC_FONT if rtl else ENGLISH_FONT,
        size=13,
        bold=True,
        color=RGBColor(0xFF, 0xFF, 0xFF),
        lang_code="ar-SA" if rtl else "en-US",
    )
    p.paragraph_format.space_after = Pt(6)

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "2E75B6")
    p._element.get_or_add_pPr().append(shd)
    return p


# Override: Arabic SMS formatter with RTL and markdown support.
def arabic_sms_formatting(doc, sms_text):
    for line in str(sms_text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        p = doc.add_paragraph()
        _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _add_inline_markdown_runs(p, clean, rtl=True)
        p.paragraph_format.space_after = Pt(6)


def _today_arabic_date():
    # Keeps date numeric to avoid OS locale dependency.
    return datetime.today().strftime("%Y-%m-%d")


def add_campaign_cover_page_arabic(
    doc: Document,
    logo_path: str,
    campaign_title: str,
    client_name: str,
    campaign_type: str = "حملة رسائل قصيرة",
    campaign_date: str = None,
    prepared_by: str = "الشركة المركزية للتجارة الإلكترونية (جورمول)",
):
    if not campaign_date:
        campaign_date = _today_arabic_date()

    try:
        logo = doc.add_picture(logo_path, width=Inches(2.8))
        logo_paragraph = doc.paragraphs[-1]
        logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logo_paragraph.paragraph_format.space_after = Pt(10)
    except Exception:
        pass

    _add_rtl_paragraph(doc, campaign_title, bold=True, size=26, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph()
    _add_rtl_paragraph(doc, campaign_type, italic=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.paragraphs[-1].paragraph_format.space_after = Pt(40)
    _add_rtl_paragraph(doc, f"العميل: {client_name}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_rtl_paragraph(doc, f"إعداد: {prepared_by}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_rtl_paragraph(doc, f"التاريخ: {campaign_date}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_page_break()


def add_sales_profile_cover_page_arabic(
    doc: Document,
    logo_path: str,
    prospect_name: str,
    prepared_by: str = "الشركة المركزية للتجارة الإلكترونية (جورمول)",
    profile_title: str = "ملف المبيعات",
    tagline: str = "حلول تسويقية عملية تدعم الوصول والنتائج.",
):
    try:
        doc.add_picture(logo_path, width=Inches(2.8))
        p_logo = doc.paragraphs[-1]
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_logo.paragraph_format.space_after = Pt(8)
    except Exception:
        pass
    _add_rtl_paragraph(doc, profile_title, bold=True, size=26, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_rtl_paragraph(doc, tagline, italic=True, size=13, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_rtl_paragraph(doc, prospect_name, bold=True, size=18, align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph()
    _add_rtl_paragraph(doc, f"إعداد: {prepared_by}", size=11, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER)
    _add_rtl_paragraph(doc, "سري — للاستخدام الداخلي مع العملاء المحتملين.", size=9, color=RGBColor(0x77, 0x77, 0x77), align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_page_break()


def add_marketing_plan_cover_page_arabic(
    doc: Document,
    logo_path: str,
    prospect_name: str,
    prepared_by: str = "الشركة المركزية للتجارة الإلكترونية (جورمول)",
    profile_title: str = "خطة تسويقية",
    tagline: str = "حلول تسويقية قابلة للتنفيذ وتدعم النمو.",
):
    add_sales_profile_cover_page_arabic(doc, logo_path, prospect_name, prepared_by, profile_title, tagline)


def add_chain_sms_section_arabic(doc):
    """Arabic literal/concise translation of add_chain_sms_section()."""
    add_colored_heading(doc, "عن حملات الرسائل المتسلسلة")
    _add_rtl_paragraph(doc, "رسائل استراتيجية مجدولة لرفع التفاعل", bold=True, italic=True, size=12)

    add_colored_heading(doc, "نظرة عامة")
    add_wrapped_paragraph(
        doc,
        "تتكون حملات الرسائل المتسلسلة من رسائل مجدولة متعددة الخطوات تستهدف الجمهور نفسه. "
        "كل رسالة مصممة للتعريف أو التفاعل أو دفع المستلم لاتخاذ إجراء، مما يجعلها مناسبة لاستراتيجيات التواصل المرحلية."
    )
    add_wrapped_paragraph(
        doc,
        "**ينصح باستخدام روابط Bitly المختصرة لرفع التفاعل مع صفحات الهبوط أو الفيديوهات أو منشورات التواصل الاجتماعي.**"
    )

    add_colored_heading(doc, "الفوائد الرئيسية")
    for b in [
        "تفاعل أقوى مع الوقت",
        "تذكّر أفضل للرسالة من خلال التكرار",
        "إمكانية تقسيم العروض المعقدة",
        "توجيه المستلمين نحو الإجراء المطلوب عبر الرسائل",
        "تخصيص الرسائل حسب الشريحة",
    ]:
        _add_rtl_paragraph(doc, b, style="List Bullet")

    add_colored_heading(doc, "كفاءة الاستهداف")
    add_wrapped_paragraph(doc, "تزداد الفعالية عند استخدام قاعدة بيانات جورمول المقسمة. يمكن فلترة الحملات حسب:")
    for f in [
        "المنطقة مثل المحافظة أو اتجاه المدينة",
        "الخصائص الديموغرافية مثل العمر والجنس والدخل",
        "سلوك المستهلك مثل امتلاك السيارة أو الحالة العائلية",
    ]:
        _add_rtl_paragraph(doc, f, style="List Bullet")

    add_colored_heading(doc, "النتائج المتوقعة")
    for o in [
        "معدلات تفاعل أعلى مقارنة بالحملات ذات الرسالة الواحدة",
        "تذكّر أكبر للعلامة التجارية والعرض",
        "تحويل أقوى من خلال روابط قابلة للتتبع",
        "تتبع واضح للأداء في كل مرحلة",
    ]:
        _add_rtl_paragraph(doc, o, style="List Bullet")

    add_wrapped_paragraph(
        doc,
        "الرسائل المتسلسلة أسلوب عملي للوصول المنظم. وعند دعمها بالاستهداف المناسب تصبح أداة قوية لتحقيق نتائج قابلة للقياس."
    )
    doc.add_page_break()

def _parse_chain_dt_arabic(msg):
    if not isinstance(msg, dict):
        return None
    date_value = msg.get("date") or msg.get("delivery_date") or ""
    time_value = msg.get("time") or msg.get("delivery_time") or ""
    combined = f"{str(date_value).strip()} {str(time_value).strip()}".strip()
    for fmt in (
        "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M %p", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(combined, fmt)
        except Exception:
            continue
    return None


def _format_arabic_datetime(dt, date_only=False, time_only=False):
    if not dt:
        return "غير محدد"
    if date_only:
        return dt.strftime("%Y-%m-%d")
    if time_only:
        return dt.strftime("%H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def add_chain_summary_arabic(doc, title, chain_messages, chain_delivery_dates=None, chain_delivery_times=None):
    """Arabic mirror of the English chain summary: duration, dates, type, and message date/time only."""
    if not chain_messages:
        return
    valid_messages = []
    for msg in chain_messages:
        dt = _parse_chain_dt_arabic(msg if isinstance(msg, dict) else {})
        valid_messages.append((dt, msg))
    valid_messages.sort(key=lambda item: item[0] or datetime.max)
    first_dt = valid_messages[0][0]
    last_dt = valid_messages[-1][0]

    add_colored_heading(doc, title or "ملخص حملة الرسائل المتسلسلة")
    add_wrapped_paragraph(doc, "**مدة الحملة:**")
    add_wrapped_paragraph(doc, f"**تاريخ البداية:** {_format_arabic_datetime(first_dt, date_only=True)}")
    add_wrapped_paragraph(doc, f"**تاريخ النهاية:** {_format_arabic_datetime(last_dt, date_only=True)}")
    add_wrapped_paragraph(doc, f"**نوع الحملة:** رسائل متسلسلة ({len(valid_messages)} رسائل تقود إلى إجراء)")

    for i, (dt, msg) in enumerate(valid_messages, start=1):
        add_wrapped_paragraph(doc, f"**الرسالة {i}**")
        _add_rtl_paragraph(doc, f"التاريخ: {_format_arabic_datetime(dt, date_only=True)}", style="List Bullet")
        _add_rtl_paragraph(doc, f"الوقت: {_format_arabic_datetime(dt, time_only=True)}", style="List Bullet")

rendered_messages_arabic = set()

def add_chain_message_page_arabic(doc, message_index, pitch, delivery_date, delivery_time):
    if not message_index or message_index in rendered_messages_arabic:
        return
    rendered_messages_arabic.add(message_index)

    pitch_title = ""
    if isinstance(pitch, dict):
        pitch_title = pitch.get("pitch") or pitch.get("message") or pitch.get("text") or ""
    else:
        pitch_title = str(pitch or "")

    doc.add_page_break()
    _add_rtl_paragraph(doc, f"الرسالة {message_index}", bold=True, size=18, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    if pitch_title:
        _add_rtl_paragraph(doc, f"فكرة الرسالة: {pitch_title}", bold=True, size=12, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    if delivery_date:
        _add_rtl_paragraph(doc, f"تاريخ الإرسال: {delivery_date}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    if delivery_time:
        _add_rtl_paragraph(doc, f"وقت الإرسال: {delivery_time}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)


def add_premium_sms_section_arabic(doc):
    """Arabic literal/concise translation of add_premium_sms_section()."""
    add_colored_heading(doc, "عن حملات الرسائل المميزة")
    _add_rtl_paragraph(doc, "إبداع متعدد القنوات لتحقيق أثر أعلى", bold=True, italic=True, size=12)

    add_colored_heading(doc, "نظرة عامة")
    add_wrapped_paragraph(
        doc,
        "حملة الرسائل المميزة هي حل متكامل من جورمول يمكّن العملاء من تنفيذ حملات فعالة ومؤثرة باستخدام عناصر إبداعية متعددة المنصات. "
        "تركز الحملة على الحفاظ على هوية موحدة عبر القنوات لضمان تذكر أقوى للعلامة وتجربة أكثر سلاسة."
    )

    add_colored_heading(doc, "العناصر الإبداعية المشمولة")
    for item in [
        "اقتراحات رسائل SMS جذابة بالعربية والإنجليزية مع تصميم صفحة هبوط.",
        "نصوص إعلانات إذاعية للبث السريع.",
        "تصاميم وتعليقات لمنصات فيسبوك وإنستغرام وغيرها.",
        "نماذج تصميم للوحات الإعلانية.",
        "فيديو بصري قصير للريلز والقصص والإعلانات.",
    ]:
        _add_rtl_paragraph(doc, item, style="List Bullet")

    add_colored_heading(doc, "الفوائد الرئيسية")
    for b in [
        "هوية ورسالة موحدة عبر القنوات",
        "تذكر أعلى وأثر عاطفي أقوى",
        "مواد جاهزة للاستخدام توفر الوقت والتكلفة",
    ]:
        _add_rtl_paragraph(doc, b, style="List Bullet")

    add_colored_heading(doc, "استهداف ذكي مع رسائل غنية")
    add_wrapped_paragraph(doc, "عند دمجها مع تقسيم جمهور جورمول، تصبح الحملات المميزة أكثر فعالية. يمكن تخصيص الرسائل والتصاميم حسب:")
    for f in [
        "الموقع مثل المحافظة أو اتجاه عمان",
        "الخصائص الديموغرافية مثل العمر والدخل والجنس",
        "شرائح نمط الحياة مثل مشتري الفخامة والعائلات والشباب",
    ]:
        _add_rtl_paragraph(doc, f, style="List Bullet")

    add_wrapped_paragraph(
        doc,
        "حملات الرسائل المميزة مناسبة للعلامات التي تريد حضوراً واضحاً. ومع مواد إبداعية جاهزة للتعديل والاستخدام، تساعد هذه الحملات على جذب الانتباه ورفع الاستجابة وتعزيز الوجود عبر القنوات."
    )


def add_optin_sms_section_arabic(doc):
    """Arabic literal/concise translation of add_optin_sms_section()."""
    add_colored_heading(doc, "عن رسائل الاشتراك وإلغاء الاشتراك")
    _add_rtl_paragraph(doc, "رسائل مبنية على الموافقة لتعزيز الثقة والامتثال", bold=True, italic=True, size=12)

    add_colored_heading(doc, "نظرة عامة")
    add_wrapped_paragraph(
        doc,
        "تستخدم رسائل الاشتراك وإلغاء الاشتراك لإبلاغ المستلمين بوضوح بأنهم يتلقون رسائل من شركة محددة، مع منحهم خيار البقاء مشتركين أو الخروج من القائمة. "
        "هذه الرسائل مهمة للشفافية والثقة واحترام تفضيلات المستخدم إضافة إلى الامتثال لتعليمات هيئة تنظيم قطاع الاتصالات."
    )
    add_wrapped_paragraph(doc, "استخدام روابط Bitly في رسائل الاشتراك يساعد على قياس الاهتمام مع الحفاظ على الامتثال والخصوصية.")
    add_wrapped_paragraph(doc, "سيتم حفظ جميع سجلات الإرسال والردود لدى جورمول للرجوع إليها مستقبلاً.")

    add_colored_heading(doc, "الفوائد الرئيسية")
    for b in [
        "تلبية متطلبات الامتثال من خلال تعليمات إلغاء الاشتراك",
        "تحسين مصداقية العلامة وثقة المستهلك",
        "تعزيز جمع البيانات من خلال موافقة واضحة",
        "تقليل الشكاوى وطلبات إلغاء الاشتراك مستقبلاً",
        "إتاحة تقسيم المستخدمين المهتمين فعلياً",
    ]:
        _add_rtl_paragraph(doc, b, style="List Bullet")

    add_colored_heading(doc, "النتائج المتوقعة")
    for o in [
        "قوائم مشتركين أنظف وأكثر تفاعلاً",
        "عائد أعلى على الحملات المستقبلية",
        "تقليل مخاطر المخالفات التنظيمية",
        "تحسين تجربة العميل وتوافقها مع العلامة",
    ]:
        _add_rtl_paragraph(doc, o, style="List Bullet")

    add_wrapped_paragraph(
        doc,
        "رسائل الاشتراك ليست مجرد مطلب امتثال، بل أداة لبناء الثقة. وعندما يختار المستلمون البقاء، تصبح الحملات المستقبلية أكثر دقة وفعالية واحتراماً لتفضيلاتهم."
    )
    doc.add_page_break()


def add_personalized_sms_section_arabic(doc):
    """Arabic literal/concise translation of add_personalized_sms_section()."""
    add_colored_heading(doc, "عن الرسائل الشخصية")
    _add_rtl_paragraph(doc, "تواصل مباشر بالاسم لرفع التفاعل", bold=True, italic=True, size=12)

    add_colored_heading(doc, "نظرة عامة")
    add_wrapped_paragraph(
        doc,
        "تخاطب حملات الرسائل الشخصية كل مستلم باسمه باستخدام مقدمات مثل عزيزي [الاسم] لخلق تواصل مباشر وفردي. "
        "هذا الأسلوب يحسن الانتباه والاستجابة العاطفية ويجعل الرسالة أكثر ملاءمة وأهمية."
    )
    add_wrapped_paragraph(doc, "**هذه الرسائل متاحة فقط كرسائل طويلة: حتى 126 حرفاً بالعربية و160 حرفاً بالإنجليزية.**")

    add_colored_heading(doc, "الفوائد الرئيسية")
    for b in [
        "رفع الاستجابة من خلال مخاطبة المستلم بالاسم",
        "خلق نبرة إنسانية ومحترمة تعزز الثقة",
        "زيادة معدلات القراءة مقارنة بالرسائل العامة",
        "دعم الولاء وتجربة العميل المميزة",
        "تعزيز جودة البيانات من خلال استخدام الاسم الصحيح",
    ]:
        _add_rtl_paragraph(doc, b, style="List Bullet")

    add_colored_heading(doc, "الاستخدام والتسليم الذكي")
    add_wrapped_paragraph(doc, "تتوفر هذه الميزة فقط لقواعد البيانات التي تحتوي على أسماء أولى موثوقة. تكون الحملات الشخصية أكثر فعالية عند استخدامها مع:")
    for u in [
        "العروض عالية القيمة أو رسائل الولاء",
        "تذكير المواعيد أو الدعوات الخاصة",
        "حملات الوصول المميز أو متابعات خدمة العملاء",
    ]:
        _add_rtl_paragraph(doc, u, style="List Bullet")

    add_colored_heading(doc, "التقسيم والتخصيص")
    add_wrapped_paragraph(doc, "تعمل حملات الرسائل الشخصية بشكل أفضل عند استهدافها حسب:")
    for seg in [
        "الاسم الكامل مع جنس معروف لتخصيص النبرة",
        "حالة العميل مثل جديد أو عائد أو مميز",
        "تاريخ المنتج أو التفاعل السابق",
    ]:
        _add_rtl_paragraph(doc, seg, style="List Bullet")

    add_colored_heading(doc, "النتائج المتوقعة")
    for o in [
        "تفاعل ونقرات أعلى",
        "تحسين صورة العلامة واحترافيتها",
        "تقليل إلغاء الاشتراك والشكاوى",
        "أثر عاطفي إيجابي لدى المستلمين",
    ]:
        _add_rtl_paragraph(doc, o, style="List Bullet")

    add_wrapped_paragraph(
        doc,
        "التخصيص ليس مجرد ميزة، بل التزام بالملاءمة. وبمساندة جورمول، يمكن للعملاء الوصول إلى الأشخاص بالاسم وبالمحتوى المناسب مع الالتزام بحدود الصياغة والإرسال."
    )
    doc.add_page_break()


def add_lead_sms_section_arabic(doc):
    """Arabic literal/concise translation of add_lead_sms_section()."""
    add_colored_heading(doc, "عن رسائل جمع العملاء المهتمين")
    _add_rtl_paragraph(doc, "تتبع النقرات لتحديد العملاء المهتمين", bold=True, italic=True, size=12)

    add_colored_heading(doc, "نظرة عامة")
    add_wrapped_paragraph(
        doc,
        "صممت حملات رسائل جمع العملاء المهتمين لتحديد المستلمين المهتمين وتأهيلهم من خلال روابط Bitly فريدة لكل رقم. "
        "عند نقر المستخدم على الرابط، يربط النظام الاهتمام برقمه ويوفر معلومات متابعة دون الحاجة إلى رد أو نموذج."
    )
    add_wrapped_paragraph(doc, "**تحتوي كل رسالة على رابط Bitly فريد مرتبط برقم المستلم، مما يتيح تتبع الاهتمام بدقة لكل مستخدم.**")

    add_colored_heading(doc, "الفوائد الرئيسية")
    for b in [
        "تحديد المهتمين بالعرض فوراً",
        "تقليل التخمين وتحسين دقة الاستهداف",
        "عدم الحاجة إلى ردود أو نماذج من العملاء",
        "توفير معلومات فورية لمتابعة المبيعات",
        "تتبع مسار التحويل حسب سلوك المستلم",
    ]:
        _add_rtl_paragraph(doc, b, style="List Bullet")

    add_colored_heading(doc, "الاستخدامات المناسبة")
    for u in [
        "تتبع الاهتمام بإطلاق منتج",
        "تأكيد دعوات الفعاليات",
        "التفاعل مع خصم أو عرض محدود",
        "حملات متابعة للعملاء الدافئين",
    ]:
        _add_rtl_paragraph(doc, u, style="List Bullet")

    add_colored_heading(doc, "التكامل الذكي مع أدوات جورمول")
    add_wrapped_paragraph(
        doc,
        "تكون رسائل جمع العملاء المهتمين أكثر فعالية عند دمجها مع لوحات جورمول وأنظمة المتابعة. يمكن للنقرات المجمعة دعم التنبيهات أو الردود المخصصة أو حملات إعادة الاستهداف."
    )

    add_colored_heading(doc, "النتائج المتوقعة")
    for o in [
        "قياس دقيق لتفاعل الحملة",
        "قوائم متابعة أصغر وأكثر جودة",
        "وقت أقصر لتأهيل العملاء المحتملين",
        "عائد أفضل من خلال تواصل مركز",
    ]:
        _add_rtl_paragraph(doc, o, style="List Bullet")

    add_wrapped_paragraph(
        doc,
        "رسائل جمع العملاء المهتمين طريقة ذكية لمعرفة من يتفاعل. ومن خلال تتبع النقرات المرتبطة بكل رقم، تتحول الإرسالات العامة إلى اهتمام قابل للمتابعة."
    )

def add_premium_intro_paragraph_arabic(doc, header):
    mapping = {
        "Arabic SMS Suggestions": ("محتوى الرسائل القصيرة", "فيما يلي اقتراحات رسائل قصيرة مخصصة للحملة. ويمكن دعمها بصفحة هبوط للحفاظ على تجربة موحدة وقياس التفاعل."),
        "Social Media Caption": ("محتوى السوشال ميديا", "فيما يلي اقتراح محتوى مناسب للنشر على منصات التواصل الاجتماعي مع إمكانية مواءمة التصميم مع صفحة الهبوط والحملة."),
        "Radio Announcement Script": ("نص الإعلان الإذاعي", "يمكن توسيع الحملة عبر نصوص إذاعية قصيرة ومباشرة تتماشى مع هوية الحملة وتدفع الجمهور لاتخاذ إجراء."),
    }
    for key, (intro_header, intro_paragraph) in mapping.items():
        if key in str(header or ""):
            doc.add_page_break()
            add_colored_heading(doc, intro_header)
            add_wrapped_paragraph(doc, intro_paragraph)
            return


def add_jormall_sms_services_section_arabic(doc):
    """Arabic literal/concise translation of add_jormall_sms_services_section()."""
    add_wrapped_paragraph(
        doc,
        "جورمول من أبرز مزودي حلول الرسائل القصيرة الجماعية في الأردن، وتخدم قطاعات متعددة تشمل التجزئة والسيارات والرعاية الصحية والبنوك والحكومة والاتصالات. "
        "وبخبرة تمتد لأكثر من عقدين، تتخصص جورمول في تقديم حملات رسائل قصيرة عالية الجودة وموجهة حسب احتياجات كل عميل."
    )
    add_wrapped_paragraph(doc, "**تقدم خدمات الرسائل القصيرة لدينا:**")
    services = {
        "إرسال موثوق": "ضمان إرسال سريع ومضمون من خلال الربط المباشر مع شركات الاتصالات الرئيسية في الأردن.",
        "استهداف متقدم": "استخدام قواعد بيانات تضم أكثر من 7.5 مليون ملف مقسم، بما يتيح الاستهداف حسب الخصائص الديموغرافية والموقع والاهتمامات والسلوك الشرائي.",
        "حملات مخصصة": "تقديم محتوى رسائل بعدة لغات، بالعربية والإنجليزية، مصمم لرفع التفاعل والولاء والتحويل.",
        "تقارير فورية": "الوصول إلى تحليلات ومؤشرات أداء وإمكانات تتبع تساعد العملاء على قياس فعالية الحملة فوراً.",
        "امتثال تنظيمي": "الالتزام بتعليمات هيئة تنظيم قطاع الاتصالات لضمان إدارة الحملات بشكل مهني ومتوافق.",
        "دعم العملاء": "فريق دعم مخصص للمساعدة في إعداد الحملات وتحسينها ومتابعتها.",
    }
    for title, text in services.items():
        add_wrapped_paragraph(doc, f"**{title}:** {text}")
    add_wrapped_paragraph(
        doc,
        "**باختيار خدمة الرسائل القصيرة من جورمول، تعزز الشركات قدراتها في التواصل مع العملاء وتحقق انتشاراً أوسع ونتائج قابلة للقياس من خلال التسويق بالرسائل القصيرة.**"
    )
    return doc

def add_seasonal_sms_calendar_arabic(doc):
    add_colored_heading(doc, "تقويم الحملات الموسمية في الأردن")
    add_wrapped_paragraph(doc, "أهم المناسبات الوطنية والموسمية التي يمكن استخدامها في تخطيط حملات الرسائل القصيرة.")
    table_text = """
| الشهر | المناسبة أو الفكرة الرئيسية |
| --- | --- |
| كانون الثاني | بداية السنة والعروض الخاصة |
| شباط | حملات عيد الحب |
| آذار | عيد الأم وبداية الربيع ومناسبات رمضان حسب السنة |
| نيسان | حملات الربيع والفعاليات المجتمعية |
| أيار | عيد الاستقلال وعيد الأضحى حسب السنة |
| حزيران | حملات الصيف |
| تموز | عروض منتصف السنة |
| آب | العودة إلى المدارس والمولد النبوي حسب السنة |
| أيلول | إطلاقات الخريف وبرامج المجتمع |
| تشرين الأول | حملات ما قبل الشتاء |
| تشرين الثاني | الجمعة البيضاء وبداية عروض الشتاء |
| كانون الأول | عيد الميلاد ونهاية السنة |
"""
    add_markdown_table(doc, table_text)
    add_wrapped_paragraph(doc, "**ملاحظة:** يجب التأكد من تواريخ المناسبات الهجرية في كل سنة قبل جدولة الحملات.")
    doc.add_page_break()


def translate_header_to_arabic(header):
    header = str(header or "").strip()
    exact = {
        "Target Audience": "الجمهور المستهدف",
        "Campaign Objective": "هدف الحملة",
        "Campaign Strategy": "استراتيجية الحملة",
        "SMS Timing Strategy (Scheduling)": "استراتيجية توقيت الرسائل",
        "English SMS Suggestions": "English SMS Suggestions",
        "Arabic SMS Suggestions": "اقتراحات الرسائل العربية",
        "Landing Page Copy": "محتوى صفحة الهبوط",
        "Social Media Caption (English)": "تعليق السوشال ميديا",
        "Radio Announcement Script (English)": "نص الإعلان الإذاعي",
        "Budget Recommendation": "توصية الميزانية",
        "Follow-up Plan": "خطة المتابعة",
        "Expected Results": "النتائج المتوقعة",
        "About JorMall SMS Service": "عن خدمة الرسائل القصيرة من جورمول",
        "Chain SMS Campaign Summary": "ملخص حملة الرسائل المتسلسلة",
        "نبذة عن الشركة": "نبذة عن الشركة",
        "العرض التسويقي للحملة": "العرض التسويقي للحملة",
        "اقتراحات اليوم والوقت": "اقتراحات اليوم والوقت",
        "اقتراحات رسائل عربية إضافية - 160 حرفاً": "English SMS Suggestions - 160 Characters",
        "اقتراحات رسائل عربية عامية - 70 حرفاً": "اقتراحات رسائل عربية عامة - 70 حرفاً",
        "اقتراحات رسائل عربية رسمية - 70 حرفاً": "اقتراحات رسائل عربية تسويقية - 70 حرفاً",
        "اقتراحات رسائل عربية رسمية - 126 حرفاً": "اقتراحات رسائل عربية طويلة - 126 حرفاً",
        "منشور سوشال ميديا باللغة العربية": "منشور سوشال ميديا باللغة العربية",
        "نص إعلان إذاعي باللغة العربية": "نص إعلان إذاعي باللغة العربية",
        "نص حوار إذاعي باللغة العربية": "نص حوار إذاعي باللغة العربية",
        "رسالة إلغاء الاشتراك العربية": "رسالة إلغاء الاشتراك العربية",
    }
    if header in exact:
        return exact[header]
    replacements = [
        ("Target Audience", "الجمهور المستهدف"),
        ("Arabic SMS Suggestions", "اقتراحات الرسائل العربية"),
        ("English SMS Suggestions", "English SMS Suggestions"),
        ("SMS Suggestions", "اقتراحات الرسائل"),
        ("Campaign", "الحملة"),
        ("Strategy", "الاستراتيجية"),
        ("Analysis", "التحليل"),
        ("Plan", "الخطة"),
        ("Recommendation", "التوصية"),
    ]
    translated = header
    for old, new in replacements:
        translated = translated.replace(old, new)
    return translated


def _campaign_type_arabic(sms_type, original_title=""):
    if sms_type == "smart":
        return "حملة رسائل قصيرة ذكية", "رسالة واحدة مع استهداف ذكي وتوقيت محسّن"
    if sms_type == "chain":
        base = original_title or "حملة رسائل متسلسلة"
        return f"{base} - حملة توعية برسائل متسلسلة", "رسائل مجدولة لرفع التذكّر والتفاعل"
    if sms_type == "premium":
        return "حملة تسويقية متكاملة متعددة القنوات", "حلول إبداعية متكاملة عبر الرسائل والقنوات الرقمية"
    if sms_type == "personalized":
        return "حملة رسائل شخصية", "رسائل طويلة موجهة بالاسم لتعزيز التفاعل"
    if sms_type == "lead":
        return "حملة رسائل لجمع العملاء المهتمين", "تتبع النقرات لتحديد الاهتمام الحقيقي"
    if sms_type == "optin":
        return "حملة موافقة وإلغاء اشتراك", "رسائل شفافة لدعم الثقة والامتثال"
    return "حملة رسائل قصيرة", "حملة تسويقية عامة"




# =====================================================================
# STRICT ARABIC RTL OVERRIDES
# These overrides force the Arabic DOCX to behave as a true RTL document.
# They intentionally force ALL generated Arabic-document paragraphs/tables
# to RTL, even when a line contains English brand names, URLs, or numbers.
# =====================================================================

def _get_or_add_child(parent, tag):
    child = parent.find(qn(tag))
    if child is None:
        child = OxmlElement(tag)
        parent.append(child)
    return child


def _set_document_rtl_settings(document):
    """Set document-level defaults so Word opens the file as an Arabic RTL document."""
    try:
        settings = document.settings._element
        bidi = settings.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            settings.append(bidi)
        bidi.set(qn("w:val"), "1")

        theme_lang = settings.find(qn("w:themeFontLang"))
        if theme_lang is None:
            theme_lang = OxmlElement("w:themeFontLang")
            settings.append(theme_lang)
        theme_lang.set(qn("w:val"), "en-US")
        theme_lang.set(qn("w:eastAsia"), "en-US")
        theme_lang.set(qn("w:bidi"), "ar-SA")
    except Exception:
        pass

    try:
        styles = document.styles.element
        doc_defaults = _get_or_add_child(styles, "w:docDefaults")
        ppr_default = _get_or_add_child(doc_defaults, "w:pPrDefault")
        ppr = _get_or_add_child(ppr_default, "w:pPr")
        bidi = _get_or_add_child(ppr, "w:bidi")
        bidi.set(qn("w:val"), "1")
        jc = _get_or_add_child(ppr, "w:jc")
        jc.set(qn("w:val"), "right")

        rpr_default = _get_or_add_child(doc_defaults, "w:rPrDefault")
        rpr = _get_or_add_child(rpr_default, "w:rPr")
        rtl = _get_or_add_child(rpr, "w:rtl")
        rtl.set(qn("w:val"), "1")
        lang = _get_or_add_child(rpr, "w:lang")
        lang.set(qn("w:val"), "ar-SA")
        lang.set(qn("w:bidi"), "ar-SA")
        rfonts = _get_or_add_child(rpr, "w:rFonts")
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), ARABIC_FONT)
    except Exception:
        pass

    # Also make common paragraph/list styles RTL so bullets do not remain LTR.
    for style_name in ["Normal", "List Bullet", "List Number", "Heading 1", "Heading 2", "Heading 3"]:
        try:
            style = document.styles[style_name]
            ppr = style.element.get_or_add_pPr()
            bidi = ppr.find(qn("w:bidi"))
            if bidi is None:
                bidi = OxmlElement("w:bidi")
                ppr.append(bidi)
            bidi.set(qn("w:val"), "1")
            jc = ppr.find(qn("w:jc"))
            if jc is None:
                jc = OxmlElement("w:jc")
                ppr.append(jc)
            jc.set(qn("w:val"), "right")
        except Exception:
            pass


def _set_run_font(run, font_name=ARABIC_FONT, size=None, bold=None, italic=None, color=None, lang_code="ar-SA"):
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if size is not None:
        run.font.size = Pt(size) if isinstance(size, (int, float)) else size
    if color is not None:
        run.font.color.rgb = color

    try:
        run.font.name = font_name
        rPr = run._element.get_or_add_rPr()
        rtl = rPr.find(qn("w:rtl"))
        if rtl is None:
            rtl = OxmlElement("w:rtl")
            rPr.append(rtl)
        rtl.set(qn("w:val"), "1")

        rFonts = rPr.rFonts
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rFonts.set(qn(attr), font_name)

        lang = rPr.find(qn("w:lang"))
        if lang is None:
            lang = OxmlElement("w:lang")
            rPr.append(lang)
        lang.set(qn("w:val"), lang_code)
        lang.set(qn("w:bidi"), lang_code)
    except Exception:
        pass
    return run


def _set_paragraph_direction(paragraph, rtl=True, align=None, lang_code="ar-SA"):
    """Force Arabic-document paragraphs to true RTL with explicit Word right alignment."""
    pPr = paragraph._element.get_or_add_pPr()

    # Remove stale alignment created by earlier helper versions, then add a clean value.
    for child in list(pPr):
        if child.tag == qn("w:jc"):
            pPr.remove(child)

    bidi = pPr.find(qn("w:bidi"))
    if bidi is None:
        bidi = OxmlElement("w:bidi")
        pPr.append(bidi)
    bidi.set(qn("w:val"), "1")

    jc = OxmlElement("w:jc")
    pPr.append(jc)

    if align == WD_ALIGN_PARAGRAPH.CENTER:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        jc.set(qn("w:val"), "center")
    else:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        jc.set(qn("w:val"), "right")

    try:
        set_paragraph_language(paragraph, lang_code)
    except Exception:
        pass

    for run in paragraph.runs:
        _set_run_font(run, font_name=ARABIC_FONT, lang_code=lang_code)
    return paragraph


def _set_paragraph_rtl(paragraph, align_right=True):
    return _set_paragraph_direction(
        paragraph,
        rtl=True,
        align=WD_ALIGN_PARAGRAPH.RIGHT if align_right else paragraph.alignment,
        lang_code="ar-SA",
    )


def _set_cell_rtl(cell, rtl=True):
    # Do not use invalid Word textDirection values. Paragraph bidi + table bidiVisual is enough for horizontal Arabic.
    try:
        tcPr = cell._tc.get_or_add_tcPr()
        # Remove vertical textDirection if a previous version added an invalid value.
        for child in list(tcPr):
            if child.tag == qn("w:textDirection"):
                tcPr.remove(child)
    except Exception:
        pass
    for p in cell.paragraphs:
        _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)


def _set_table_rtl(table):
    try:
        table.alignment = WD_TABLE_ALIGNMENT.RIGHT
        tblPr = table._tbl.tblPr
        bidi = tblPr.find(qn("w:bidiVisual"))
        if bidi is None:
            bidi = OxmlElement("w:bidiVisual")
            tblPr.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass
    for row in table.rows:
        for cell in row.cells:
            _set_cell_rtl(cell, True)


def _force_document_rtl(document):
    """Final pass before saving: force all body/header/footer content to Arabic RTL and right aligned."""
    _set_document_rtl_settings(document)

    def force_p(paragraph):
        # The user requested all Arabic document text right-aligned; do not preserve center/left.
        _set_paragraph_direction(paragraph, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        for run in paragraph.runs:
            _set_run_font(run, font_name=ARABIC_FONT, lang_code="ar-SA")

    for paragraph in document.paragraphs:
        force_p(paragraph)

    for table in document.tables:
        _set_table_rtl(table)
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    force_p(paragraph)

    for section in document.sections:
        try:
            sectPr = section._sectPr
            text_direction = sectPr.find(qn("w:textDirection"))
            if text_direction is None:
                text_direction = OxmlElement("w:textDirection")
                sectPr.append(text_direction)
            text_direction.set(qn("w:val"), "rlTb")
        except Exception:
            pass
        for paragraph in section.header.paragraphs:
            force_p(paragraph)
        for paragraph in section.footer.paragraphs:
            force_p(paragraph)
        for table in section.header.tables:
            _set_table_rtl(table)
        for table in section.footer.tables:
            _set_table_rtl(table)


def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in str(markdown_table_text or "").strip().splitlines() if "|" in line]
    if len(lines) < 2:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    header_cells = [cell.strip() for cell in lines[0].split("|") if cell.strip()]
    if not header_cells:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    table = doc.add_table(rows=1, cols=len(header_cells))
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    _set_table_rtl(table)

    hdr_cells = table.rows[0].cells
    for i, text in enumerate(header_cells):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _add_inline_markdown_runs(p, text, rtl=True)
        for run in p.runs:
            run.bold = True

    for line in lines[2:]:
        row_cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        row = table.add_row().cells
        for i, text in enumerate(row_cells[:len(header_cells)]):
            row[i].text = ""
            p = row[i].paragraphs[0]
            _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _add_inline_markdown_runs(p, text, rtl=True)
    _set_table_rtl(table)


def add_wrapped_paragraph(doc, text):
    text = str(text or "")
    if not text.strip():
        return

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        blocks = [text]

    for block in blocks:
        if "|" in block and "---" in block:
            add_markdown_table(doc, block)
            continue

        lines = block.splitlines()
        for line in lines:
            clean = line.strip()
            if not clean:
                continue
            bullet_match = re.match(r"^([-*•]|\d+[.)])\s+(.+)$", clean)
            if bullet_match:
                clean = "• " + bullet_match.group(2).strip()
            p = doc.add_paragraph()
            _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _add_inline_markdown_runs(p, clean, rtl=True)
            p.paragraph_format.space_after = Pt(8)


def add_colored_heading(doc, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)

    # Keep the blue heading bar, but force the heading text itself to the right.
    pPr = p._element.get_or_add_pPr()
    for child in list(pPr):
        if child.tag == qn("w:jc"):
            pPr.remove(child)
    bidi = pPr.find(qn("w:bidi"))
    if bidi is None:
        bidi = OxmlElement("w:bidi")
        pPr.append(bidi)
    bidi.set(qn("w:val"), "1")
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "right")
    pPr.append(jc)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "2E75B6")
    pPr.append(shd)

    run = p.add_run(str(title or ""))
    _set_run_font(run, font_name=ARABIC_FONT, size=13, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), lang_code="ar-SA")
    return p


def arabic_sms_formatting(doc, sms_text):
    for line in str(sms_text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        p = doc.add_paragraph()
        _set_paragraph_direction(p, rtl=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _add_inline_markdown_runs(p, clean, rtl=True)
        p.paragraph_format.space_after = Pt(6)



def _patch_saved_docx_rtl_right_aligned(docx_path):
    """Patch saved OOXML so Word/LibreOffice cannot reopen Arabic docs as LTR/left."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    from xml.etree import ElementTree as ET
    ET.register_namespace('w', ns)
    q = lambda tag: '{%s}%s' % (ns, tag)

    def child(parent, tag):
        found = parent.find(q(tag))
        if found is None:
            found = ET.Element(q(tag))
            parent.append(found)
        return found

    tmp = str(docx_path) + '.rtl_tmp'
    with zipfile.ZipFile(docx_path, 'r') as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in ('word/document.xml', 'word/styles.xml', 'word/settings.xml') or re.match(r'word/(header|footer)\d+\.xml$', item.filename):
                try:
                    root = ET.fromstring(data)
                    # settings.xml document bidi
                    if item.filename == 'word/settings.xml':
                        bidi = child(root, 'bidi')
                        bidi.set(q('val'), '1')
                        theme = root.find(q('themeFontLang'))
                        if theme is None:
                            theme = ET.Element(q('themeFontLang'))
                            root.append(theme)
                        theme.set(q('bidi'), 'ar-SA')

                    # styles.xml defaults and styles
                    if item.filename == 'word/styles.xml':
                        for style in root.findall(q('style')):
                            pPr = child(style, 'pPr')
                            child(pPr, 'bidi').set(q('val'), '1')
                            child(pPr, 'jc').set(q('val'), 'right')
                        docDefaults = root.find(q('docDefaults'))
                        if docDefaults is None:
                            docDefaults = ET.Element(q('docDefaults'))
                            root.insert(0, docDefaults)
                        pPrDefault = child(docDefaults, 'pPrDefault')
                        pPr = child(pPrDefault, 'pPr')
                        child(pPr, 'bidi').set(q('val'), '1')
                        child(pPr, 'jc').set(q('val'), 'right')
                        rPrDefault = child(docDefaults, 'rPrDefault')
                        rPr = child(rPrDefault, 'rPr')
                        child(rPr, 'rtl').set(q('val'), '1')
                        lang = child(rPr, 'lang')
                        lang.set(q('val'), 'ar-SA')
                        lang.set(q('bidi'), 'ar-SA')

                    # document/header/footer paragraph and run direction
                    for p in root.iter(q('p')):
                        pPr = p.find(q('pPr'))
                        if pPr is None:
                            pPr = ET.Element(q('pPr'))
                            p.insert(0, pPr)
                        child(pPr, 'bidi').set(q('val'), '1')
                        child(pPr, 'jc').set(q('val'), 'right')
                    for r in root.iter(q('r')):
                        rPr = r.find(q('rPr'))
                        if rPr is None:
                            rPr = ET.Element(q('rPr'))
                            r.insert(0, rPr)
                        child(rPr, 'rtl').set(q('val'), '1')
                        lang = rPr.find(q('lang'))
                        if lang is None:
                            lang = ET.Element(q('lang'))
                            rPr.append(lang)
                        lang.set(q('bidi'), 'ar-SA')
                    for tbl in root.iter(q('tbl')):
                        tblPr = tbl.find(q('tblPr'))
                        if tblPr is None:
                            tblPr = ET.Element(q('tblPr'))
                            tbl.insert(0, tblPr)
                        child(tblPr, 'bidiVisual').set(q('val'), '1')
                    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                except Exception:
                    pass
            zout.writestr(item, data)
    os.replace(tmp, docx_path)

# Arabic default main document generator.
def generate_ai_docx(campaign_id, json_path, numbered_sms=False, language="ar"):
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    EXPORT_DIR = os.path.join(BASE_DIR, "exports", "docx")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    print(campaign_id, "Arabic DOCX has been created")

    print("📄 Loading JSON from:", json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    company_name = data.get("company_name", "[غير متوفر]")
    company_url = data.get("company_url", "[غير متوفر]")
    original_campaign_title = data.get("chain_campaign_title", "حملة رسائل قصيرة")
    sms_type = data.get("sms_type", "smart")
    company_profile = data.get("company_profile", False)
    marketing_plan = data.get("marketing_plan", False)

    safe_company = re.sub(r"[\\/:*?\"<>|]+", "-", str(company_name)).strip() or "JorMall"
    output_path = os.path.join(EXPORT_DIR, f"{safe_company} - JorMall Arabic SMS.docx")

    doc = Document()
    _set_document_rtl_settings(doc)
    normal_font = doc.styles["Normal"].font
    normal_font.name = ARABIC_FONT
    normal_font.size = Pt(11)

    core_props = doc.core_properties
    core_props.author = "Central E-Commerce Ltd. (JorMall)"
    core_props.last_modified_by = "Central E-Commerce Ltd. (JorMall)"
    core_props.title = ""
    core_props.subject = ""
    core_props.comments = ""

    section = doc.sections[0]
    section.different_first_page_header_footer = True

    logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png")

    if company_profile:
        add_sales_profile_cover_page_arabic(doc, logo_path=logo_path, prospect_name=company_name)
    elif marketing_plan:
        add_marketing_plan_cover_page_arabic(doc, logo_path=logo_path, prospect_name=company_name)
    else:
        campaign_title, campaign_type = _campaign_type_arabic(sms_type, original_campaign_title)
        add_campaign_cover_page_arabic(
            doc,
            logo_path=logo_path,
            campaign_title=campaign_title,
            client_name=company_name,
            campaign_type=campaign_type,
        )

        if sms_type == "chain":
            add_chain_sms_section_arabic(doc)
        elif sms_type == "premium":
            add_premium_sms_section_arabic(doc)
            doc.add_section(WD_SECTION.NEW_PAGE)
        elif sms_type == "personalized":
            add_personalized_sms_section_arabic(doc)
        elif sms_type == "optin":
            add_optin_sms_section_arabic(doc)
        elif sms_type == "lead":
            add_lead_sms_section_arabic(doc)

        if company_name != "[غير متوفر]" and company_url != "[غير متوفر]":
            add_colored_heading(doc, "تقرير حملة الرسائل القصيرة")
            add_wrapped_paragraph(doc, f"**اسم الشركة:** {company_name}")
            add_wrapped_paragraph(doc, f"**الموقع الإلكتروني:** {company_url}")

        # Header logo on following pages
        header = doc.sections[0].header
        paragraph = header.paragraphs[0]
        try:
            paragraph.add_run().add_picture(logo_path, width=Inches(1.3))
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        except Exception as e:
            print("⚠️ Logo not found or failed to load:", e)
            paragraph.add_run("[الشعار غير متوفر]").bold = True

    for _, content in data.get("analysis", {}).items():
        header = content.get("header", "")
        answer = content.get("answer", "")
        message_index = content.get("message_index", "")
        pitch = content.get("pitch") or {}
        delivery_date = content.get("delivery_date", datetime.today().strftime("%Y-%m-%d"))
        delivery_time = content.get("delivery_time", "00:00")

        if sms_type == "premium":
            add_premium_intro_paragraph_arabic(doc, header)

        if sms_type == "chain":
            # Keep existing chain message page formatter, but pass Arabic labels through heading after.
            add_chain_message_page_arabic(doc, message_index, pitch, delivery_date, delivery_time)
            if header == "Target Audience":
                chain_messages = data.get("chain_messages", [])
                add_chain_summary_arabic(doc, "ملخص حملة الرسائل المتسلسلة", chain_messages, data.get("chain_delivery_dates", []), data.get("chain_delivery_times", []))

        arabic_header = translate_header_to_arabic(header)
        add_colored_heading(doc, arabic_header)

        if marketing_plan and header == "SMS Timing Strategy (Scheduling)":
            add_seasonal_sms_calendar_arabic(doc)

        if "|" in str(answer) and "---" in str(answer):
            add_markdown_table(doc, answer)
        elif "Arabic SMS Suggestions" in str(header) or contains_arabic(answer):
            arabic_sms_formatting(doc, answer) if "SMS" in str(header) else add_wrapped_paragraph(doc, answer)
        else:
            add_wrapped_paragraph(doc, answer)

    doc.add_section(WD_SECTION.NEW_PAGE)
    add_colored_heading(doc, "عن خدمة الرسائل القصيرة من جورمول")
    add_jormall_sms_services_section_arabic(doc)

    footer = doc.sections[0].footer
    fpara = footer.paragraphs[0]
    _set_paragraph_direction(fpara, rtl=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    fpara.text = ""
    r = fpara.add_run(
        "فرق المبيعات والدعم في جورمول دائماً بخدمتكم.\n"
        "لأي استفسار، يرجى التواصل مع مسؤول الحساب أو عبر البريد الإلكتروني: order.processing@jormall.com\n"
    )
    _set_run_font(r, font_name=ARABIC_FONT, size=9, lang_code="ar-SA")

    try:
        print("💾 Saving Arabic DOCX to:", output_path)
        _force_document_rtl(doc)
        doc.save(output_path)
        #_patch_saved_docx_rtl_right_aligned(output_path)
        print("✅ Arabic DOCX saved successfully with RTL/right-aligned headings.")
    except Exception as e:
        print("❌ Failed to save Arabic DOCX:", e)
        raise

    return output_path

# =====================================================================
# CLEAN ARABIC DOCX GENERATOR OVERRIDE
# Generated Arabic files now mirror the English DOCX structure and use a
# translated copy of the English JSON. This avoids different meanings and
# fixes the messy RTL formatting.
# =====================================================================


def _clean_contains_arabic(text):
    text = str(text or "")
    return any("\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF" for ch in text)


def _clean_rtl_text(text):
    """Wrap mixed Arabic/Latin text so Word keeps visual order stable."""
    text = str(text or "")
    # Avoid duplicated bidi control marks if the model or previous version already inserted them.
    text = text.replace("\u202A", "").replace("\u202B", "").replace("\u202C", "").replace("\u200E", "").replace("\u200F", "")
    if _clean_contains_arabic(text):
        return "\u202B" + text + "\u202C"
    return text


def _clean_set_run_rtl(run, font_name=ARABIC_FONT, size=None, bold=None, italic=None, color=None):
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if size is not None:
        run.font.size = Pt(size) if isinstance(size, (int, float)) else size
    if color is not None:
        run.font.color.rgb = color
    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.rFonts
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font_name)
    rtl = rPr.find(qn("w:rtl"))
    if rtl is None:
        rtl = OxmlElement("w:rtl")
        rPr.append(rtl)
    rtl.set(qn("w:val"), "1")
    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "ar-SA")
    lang.set(qn("w:bidi"), "ar-SA")
    return run


def _clean_set_paragraph_rtl(paragraph, align=WD_ALIGN_PARAGRAPH.RIGHT):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if align == WD_ALIGN_PARAGRAPH.CENTER else WD_ALIGN_PARAGRAPH.RIGHT
    pPr = paragraph._p.get_or_add_pPr()
    # Remove old direction/alignment records so Word does not keep a stale left alignment.
    for child in list(pPr):
        if child.tag in {qn("w:jc"), qn("w:bidi")}:
            pPr.remove(child)
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center" if align == WD_ALIGN_PARAGRAPH.CENTER else "right")
    pPr.append(jc)
    try:
        set_paragraph_language(paragraph, "ar-SA")
    except Exception:
        pass
    for run in paragraph.runs:
        _clean_set_run_rtl(run)
    return paragraph


def _clean_set_doc_defaults(doc):
    try:
        settings = doc.settings._element
        bidi = settings.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            settings.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass
    try:
        normal = doc.styles["Normal"]
        normal.font.name = ARABIC_FONT
        normal.font.size = Pt(11)
        rPr = normal.element.get_or_add_rPr()
        rFonts = rPr.rFonts
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rFonts.set(qn(attr), ARABIC_FONT)
        # Right-align the Normal paragraph style for Arabic documents.
        pPr = normal.element.get_or_add_pPr()
        for child in list(pPr):
            if child.tag in {qn("w:jc"), qn("w:bidi")}:
                pPr.remove(child)
        bidi = OxmlElement("w:bidi")
        bidi.set(qn("w:val"), "1")
        pPr.append(bidi)
        jc = OxmlElement("w:jc")
        jc.set(qn("w:val"), "right")
        pPr.append(jc)
    except Exception:
        pass


def _clean_add_text(doc, text="", bold=False, italic=False, size=11, color=None, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=8):
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=align)
    if text:
        _clean_add_inline_runs(p, str(text), bold_all=bold, italic_all=italic, size=size, color=color)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _clean_add_inline_runs(paragraph, text, bold_all=False, italic_all=False, size=11, color=None):
    # Preserve the same simple markdown formatting used by the English generator.
    tokens = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", str(text or ""))
    for token in tokens:
        if token == "":
            continue
        bold = bold_all
        italic = italic_all
        clean = token
        if token.startswith("**") and token.endswith("**"):
            clean = token[2:-2]
            bold = True
        elif token.startswith("*") and token.endswith("*"):
            clean = token[1:-1]
            italic = True
        run = paragraph.add_run(_clean_rtl_text(clean))
        _clean_set_run_rtl(run, size=size, bold=bold, italic=italic, color=color)


def _clean_add_title(doc, text):
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    r = p.add_run(_clean_rtl_text(str(text or "")))
    _clean_set_run_rtl(r, size=24, bold=False, color=RGBColor(0x1F, 0x4E, 0x79))
    p.paragraph_format.space_after = Pt(14)
    # Underline/bottom border similar to Word heading style.
    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "2E75B6")
    pBdr.append(bottom)
    return p


def _clean_add_blue_heading(doc, title):
    # Match the English document's neat blue paragraph heading, but use RTL/right alignment.
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    r = p.add_run(_clean_rtl_text(str(title or "")))
    _clean_set_run_rtl(r, size=13, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    shd = pPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        pPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "2E75B6")
    return p


def add_colored_heading(doc, title):
    return _clean_add_blue_heading(doc, title)


def add_wrapped_paragraph(doc, text):
    text = str(text or "")
    if not text.strip():
        return
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()] or [text]
    for block in blocks:
        if "|" in block and "---" in block:
            add_markdown_table(doc, block)
            continue
        # Keep one paragraph per logical block, exactly like the English doc.
        # Line breaks inside the block are preserved but do not create messy oversized spacing.
        _clean_add_text(doc, block, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=8)


def arabic_sms_formatting(doc, sms_text):
    add_wrapped_paragraph(doc, sms_text)


def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in str(markdown_table_text or "").splitlines() if "|" in line]
    if len(lines) < 2:
        add_wrapped_paragraph(doc, markdown_table_text)
        return
    header_cells = [cell.strip() for cell in lines[0].split("|") if cell.strip()]
    if not header_cells:
        add_wrapped_paragraph(doc, markdown_table_text)
        return
    table = doc.add_table(rows=1, cols=len(header_cells))
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.RIGHT
    try:
        tblPr = table._tbl.tblPr
        bidi = tblPr.find(qn("w:bidiVisual"))
        if bidi is None:
            bidi = OxmlElement("w:bidiVisual")
            tblPr.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass
    rows = [header_cells]
    for line in lines[2:]:
        rows.append([cell.strip() for cell in line.split("|") if cell.strip()][:len(header_cells)])
    for ri, row_values in enumerate(rows):
        cells = table.rows[0].cells if ri == 0 else table.add_row().cells
        for i, value in enumerate(row_values):
            if i >= len(cells):
                break
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, value, bold_all=(ri == 0))
    return table

def _clean_cover_page_arabic(doc, logo_path, campaign_title, client_name, campaign_type, campaign_date=None, prepared_by="الشركة المركزية للتجارة الإلكترونية (جورمول)"):
    if campaign_date is None:
        campaign_date = datetime.today().strftime("%Y-%m-%d")
    try:
        doc.add_picture(logo_path, width=Inches(2.8))
        p_logo = doc.paragraphs[-1]
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_logo.paragraph_format.space_after = Pt(10)
    except Exception:
        pass
    _clean_add_text(doc, campaign_title, bold=True, size=24, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
    doc.add_paragraph()
    p_type = _clean_add_text(doc, campaign_type, italic=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)
    _clean_add_text(doc, f"العميل: {client_name}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    _clean_add_text(doc, f"إعداد: {prepared_by}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    _clean_add_text(doc, f"التاريخ: {campaign_date}", size=12, color=JORMALL_GRAY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    doc.add_page_break()


def _clean_add_simple_section(doc, title, subtitle, paragraphs=None, bullets=None):
    _clean_add_blue_heading(doc, title)
    if subtitle:
        _clean_add_text(doc, subtitle, bold=True, italic=True, size=12, space_after=8)
    for para in paragraphs or []:
        add_wrapped_paragraph(doc, para)
    for b in bullets or []:
        add_wrapped_paragraph(doc, f"- {b}")
    doc.add_page_break()


def _clean_add_intro_for_sms_type(doc, sms_type):
    """Use the full Arabic campaign explanations so Arabic/English documents stay content-equivalent."""
    if sms_type == "chain":
        add_chain_sms_section_arabic(doc)
    elif sms_type == "premium":
        add_premium_sms_section_arabic(doc)
    elif sms_type == "personalized":
        add_personalized_sms_section_arabic(doc)
    elif sms_type == "optin":
        add_optin_sms_section_arabic(doc)
    elif sms_type == "lead":
        add_lead_sms_section_arabic(doc)


def _clean_add_jormall_services_arabic(doc):
    _clean_add_blue_heading(doc, "عن خدمة الرسائل القصيرة من جورمول")
    add_wrapped_paragraph(doc, "جورمول من أبرز مزودي حلول الرسائل القصيرة الجماعية في الأردن، وتخدم قطاعات متعددة تشمل التجزئة والسيارات والرعاية الصحية والبنوك والحكومة والاتصالات. وبخبرة تمتد لأكثر من عقدين، تتخصص جورمول في تقديم حملات رسائل قصيرة عالية الجودة وموجهة حسب احتياجات كل عميل.")
    add_wrapped_paragraph(doc, "**تقدم خدمات الرسائل القصيرة لدينا:**")
    services = [
        ("إرسال موثوق", "ضمان إرسال سريع ومضمون من خلال الربط المباشر مع شركات الاتصالات الرئيسية في الأردن."),
        ("استهداف متقدم", "استخدام قواعد بيانات تضم أكثر من 7.5 مليون ملف مقسم، بما يتيح الاستهداف حسب الخصائص الديموغرافية والموقع والاهتمامات والسلوك الشرائي."),
        ("حملات مخصصة", "تقديم محتوى رسائل بالعربية والإنجليزية لرفع التفاعل والولاء والتحويل."),
        ("تقارير فورية", "الوصول إلى تحليلات ومؤشرات أداء تساعد العملاء على قياس فعالية الحملة."),
        ("امتثال تنظيمي", "الالتزام بتعليمات هيئة تنظيم قطاع الاتصالات لضمان إدارة الحملات بشكل مهني ومتوافق."),
        ("دعم العملاء", "فريق دعم مخصص للمساعدة في إعداد الحملات وتحسينها ومتابعتها."),
    ]
    for title, body in services:
        add_wrapped_paragraph(doc, f"**{title}:** {body}")
    add_wrapped_paragraph(doc, "**باختيار خدمة الرسائل القصيرة من جورمول، تعزز الشركات قدراتها في التواصل مع العملاء وتحقق انتشاراً أوسع ونتائج قابلة للقياس من خلال التسويق بالرسائل القصيرة.**")


def _clean_chain_message_page(doc, message_index, pitch, delivery_date, delivery_time):
    if not message_index:
        return
    doc.add_page_break()
    _clean_add_text(doc, f"الرسالة {message_index}", bold=True, size=13, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    if pitch:
        _clean_add_text(doc, f"فكرة الرسالة: {pitch}", bold=True, size=12, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    if delivery_date:
        _clean_add_text(doc, f"تاريخ الإرسال: {delivery_date}", bold=True, size=12, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)
    if delivery_time:
        _clean_add_text(doc, f"وقت الإرسال: {delivery_time}", bold=True, size=12, color=JORMALL_BLUE, align=WD_ALIGN_PARAGRAPH.CENTER)


def _clear_header(header):
    try:
        header.is_linked_to_previous = False
    except Exception:
        pass
    paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.space_after = Pt(3)
    return paragraph


def _add_jormall_logo_to_all_headers(doc, logo_path):
    """Keep the Arabic cover-page header blank and add the logo to every later page."""
    for section_index, section in enumerate(doc.sections):
        regular_paragraph = _clear_header(section.header)
        regular_paragraph.add_run().add_picture(logo_path, width=Inches(1.15))

        try:
            first_page_header = section.first_page_header
        except Exception:
            first_page_header = None

        if first_page_header is not None:
            first_paragraph = _clear_header(first_page_header)
            # The first document page is the cover page and must not repeat the logo.
            # Later section first pages retain the standard logo.
            if section_index > 0:
                first_paragraph.add_run().add_picture(logo_path, width=Inches(1.15))



def _clean_add_label_value(doc, label, value, bold_label=True, size=11, space_after=8):
    """Right-aligned Arabic label with a correctly ordered Arabic or LTR value."""
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    label_run = p.add_run(str(label or "") + ": ")
    _clean_set_run_rtl(label_run, size=size, bold=bold_label)
    value_text = str(value or "")
    if _clean_contains_arabic(value_text):
        value_run = p.add_run(value_text)
        _clean_set_run_rtl(value_run, size=size)
    else:
        # Directional embedding keeps URLs, trailing slashes, numbers and Latin names intact.
        value_run = p.add_run("\u202A" + value_text + "\u202C")
        _clean_set_run_ltr(value_run, size=size)
    p.paragraph_format.space_after = Pt(space_after)
    return p

def _normalize_arabic_doc_header(header, original_header=""):
    """Normalize known bilingual/static section titles in Arabic documents."""
    h = str(header or "").strip()
    o = str(original_header or "").strip()
    key = (o or h).lower()
    if "english sms suggestions" in key:
        return "English SMS Suggestions - 160 Characters"
    if "lead sms sample" in key or "نماذج رسائل lead sms" in h.lower():
        return "نماذج رسائل جمع العملاء المهتمين (عربي)"
    if "lead sms tracking workflow" in key or "آلية تنفيذ وتتبع lead sms" in h.lower():
        return "آلية تنفيذ وتتبع رسائل جمع العملاء المهتمين"
    return h


def _normalize_arabic_doc_answer(answer, header="", original_header=""):
    """Repair known legacy English Lead-SMS strings that leaked into Arabic reports."""
    text = str(answer or "")
    key = (str(original_header or "") or str(header or "")).lower()
    if "lead sms sample" in key:
        text = text.replace(
            "Implementation note: [رابط Bitly فريد] is replaced with a different Bitly link for each recipient when the campaign is prepared, allowing every click to be tied to the correct phone number.",
            "ملاحظة تنفيذية: يُستبدل [رابط Bitly فريد] برابط Bitly مختلف لكل مستلم عند تجهيز الحملة، حتى يمكن ربط كل نقرة برقم الهاتف الصحيح ومتابعة العملاء المهتمين بدقة."
        )
    if "lead sms tracking workflow" in key and not _clean_contains_arabic(text):
        legacy = {
            "1. Prepare the SMS and assign a unique Bitly link to each recipient.": "1. تجهيز الرسالة النصية وتعيين رابط Bitly فريد لكل مستلم.",
            "2. Send the campaign to the selected audience segment.": "2. إرسال الحملة إلى شريحة الجمهور المحددة.",
            "3. Record clicks and associate each click with the recipient phone number.": "3. تسجيل النقرات وربط كل نقرة برقم هاتف المستلم.",
            "4. Build a qualified follow-up list from recipients who showed interest.": "4. إنشاء قائمة متابعة مؤهلة من المستلمين الذين أظهروا اهتماماً.",
            "5. Use click behavior to improve targeting and subsequent follow-up campaigns.": "5. استخدام سلوك النقر لتحسين الاستهداف وحملات المتابعة اللاحقة.",
        }
        for old, new in legacy.items():
            text = text.replace(old, new)
    return text


def _last_paragraph_has_page_break(doc):
    if not doc.paragraphs:
        return False
    p = doc.paragraphs[-1]._p
    for br in p.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False


def _ensure_new_page(doc):
    """Start a major title on a fresh page without creating duplicate blank pages."""
    if not _last_paragraph_has_page_break(doc):
        doc.add_page_break()




# =====================================================================
# FINAL ARABIC DOCUMENT ALIGNMENT NORMALIZATION
# Every non-centered content paragraph in an Arabic-generated DOCX is
# physically RIGHT aligned. Arabic/mixed paragraphs are RTL; English-only
# runs (URLs, brands and the English 160-character suggestions) keep LTR
# reading order while remaining right aligned inside the Arabic document.
# Intentionally centered cover/footer elements are preserved.
# =====================================================================
def _force_final_arabic_right_alignment(document):
    def _set_style_right(style_name):
        try:
            style = document.styles[style_name]
            pPr = style.element.get_or_add_pPr()
            for child in list(pPr):
                if child.tag in {qn('w:jc'), qn('w:bidi'), qn('w:rtl')}:
                    pPr.remove(child)
            bidi = OxmlElement('w:bidi')
            bidi.set(qn('w:val'), '1')
            pPr.append(bidi)
            jc = OxmlElement('w:jc')
            jc.set(qn('w:val'), 'right')
            pPr.append(jc)
        except Exception:
            pass

    for style_name in ('Normal', 'List Bullet', 'List Number', 'Heading 1', 'Heading 2', 'Heading 3'):
        _set_style_right(style_name)

    def _paragraph_has_arabic(paragraph):
        return _clean_contains_arabic(''.join((run.text or '') for run in paragraph.runs))

    def _force_paragraph(paragraph):
        has_text = any((run.text or '').strip() for run in paragraph.runs)
        if not has_text:
            return

        # Preserve deliberate centered cover/title/footer blocks only.
        is_centered = paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if is_centered else WD_ALIGN_PARAGRAPH.RIGHT

        pPr = paragraph._element.get_or_add_pPr()
        for child in list(pPr):
            if child.tag in {qn('w:jc'), qn('w:bidi'), qn('w:rtl')}:
                pPr.remove(child)

        # Arabic/mixed content is true RTL. English-only text keeps LTR order,
        # but the physical paragraph alignment remains on the right.
        bidi = OxmlElement('w:bidi')
        bidi.set(qn('w:val'), '1' if _paragraph_has_arabic(paragraph) else '0')
        pPr.append(bidi)
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), 'center' if is_centered else 'right')
        pPr.append(jc)

        if _paragraph_has_arabic(paragraph):
            try:
                set_paragraph_language(paragraph, 'ar-SA')
            except Exception:
                pass

    for paragraph in document.paragraphs:
        _force_paragraph(paragraph)

    for table in document.tables:
        try:
            table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            tblPr = table._tbl.tblPr
            bidi = tblPr.find(qn('w:bidiVisual'))
            if bidi is None:
                bidi = OxmlElement('w:bidiVisual')
                tblPr.append(bidi)
            bidi.set(qn('w:val'), '1')
        except Exception:
            pass
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _force_paragraph(paragraph)

    for section in document.sections:
        for paragraph in section.header.paragraphs:
            _force_paragraph(paragraph)
        for paragraph in section.footer.paragraphs:
            _force_paragraph(paragraph)
        for table in section.header.tables:
            try:
                table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            except Exception:
                pass
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _force_paragraph(paragraph)
        for table in section.footer.tables:
            try:
                table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            except Exception:
                pass
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _force_paragraph(paragraph)


def _clean_add_jormall_ai_products_arabic(doc):
    _clean_add_text(
        doc,
        "تقدم جورمول منتجات ذكاء اصطناعي موجهة لأهداف أعمال محددة، وتحول المحتوى المعتمد من العميل إلى تجربة محادثة عملية تساعد المستخدم على الوصول إلى الإجراء المطلوب دون الخروج عن المعلومات المعتمدة.",
        size=11, space_after=8,
    )
    _clean_add_text(doc, "منتجات الذكاء الاصطناعي الحالية:", bold=True, size=11, space_after=5)
    items = [
        ("مساعد الحجوزات الذكي", "مساعد يركز على أسئلة الخدمات والمواعيد المعتمدة، يوجه طلبات الحجز، ويحول الحالات التي تحتاج تدخلاً بشرياً إلى القناة المحددة."),
        ("مساعد الحملات الذكي", "مساعد مخصص لحملة أو عرض أو فعالية أو إطلاق خدمة واحدة، يجيب من محتوى الحملة المعتمد ويوجه المستخدم إلى الإجراء المطلوب."),
        ("محتوى موثوق", "تعتمد الإجابات على معلومات العميل المعتمدة، ولا يتم تخمين التفاصيل غير المتوفرة أو الحساسة."),
        ("العربية والإنجليزية", "يمكن تجهيز المستندات وتجربة المساعد وفق لغة المشروع والمحتوى المعتمد."),
        ("التحسين المستمر", "تساعد مراجعة الأسئلة والفجوات في تحديد المحتوى الذي يحتاج إلى تحديث أو إضافة بعد اعتماد العميل."),
    ]
    for title, text in items:
        p = doc.add_paragraph(style='List Bullet')
        _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
        p.paragraph_format.space_after = Pt(3)
        r1 = p.add_run(title + ": ")
        _clean_set_run_rtl(r1, bold=True, size=11)
        r2 = p.add_run(text)
        _clean_set_run_rtl(r2, size=11)
    _clean_add_text(
        doc,
        "يتم إطلاق أي منتج بعد اعتماد العميل للمحتوى ومسار المحادثة وقواعد التحويل والروابط أو النماذج المستخدمة داخل التجربة.",
        bold=True, size=11, space_after=5,
    )


# Final override imported by app.py as generate_arabic_ai_docx.
def generate_ai_docx(campaign_id, json_path, numbered_sms=False, language="ar"):

    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    EXPORT_DIR = os.path.join(BASE_DIR, "exports", "docx")
    os.makedirs(EXPORT_DIR, exist_ok=True)

    print("📄 Loading translated Arabic JSON from:", json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    company_name = data.get("company_name", "[غير متوفر]")
    company_url = data.get("company_url", "[غير متوفر]")
    sms_type = data.get("sms_type", "smart")
    company_profile = data.get("company_profile", False)
    marketing_plan = data.get("marketing_plan", False)
    platform_benefits = data.get("platform_benefits", False)
    ai_product = data.get("ai_product", False)
    safe_company = re.sub(r'[\\/:*?"<>|]+', '-', str(company_name)).strip() or 'JorMall'
    if company_profile:
        output_name = f"{safe_company} - JorMall Arabic Profile Report.docx"
    elif marketing_plan:
        output_name = f"{safe_company} - JorMall Arabic Marketing Plan.docx"
    elif platform_benefits:
        output_name = f"{safe_company} - JorMall Arabic Platform Benefits.docx"
    elif ai_product:
        product_type = str(data.get("ai_product_type", "")).strip()
        product_label = "Reservation Chatbot" if product_type == "reservation_chatbot" else "Campaign Chatbot"
        output_name = f"{safe_company} - JorMall Arabic {product_label}.docx"
    else:
        output_name = f"{safe_company} - JorMall Arabic SMS.docx"
    output_path = os.path.join(EXPORT_DIR, output_name)

    doc = Document()
    _clean_set_doc_defaults(doc)
    core_props = doc.core_properties
    core_props.author = "Central E-Commerce Ltd. (JorMall)"
    core_props.last_modified_by = "Central E-Commerce Ltd. (JorMall)"
    core_props.title = ""
    core_props.subject = ""
    core_props.comments = ""

    section = doc.sections[0]
    section.different_first_page_header_footer = True
    logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png")

    if company_profile:
        _clean_cover_page_arabic(doc, logo_path, "تقرير الملف التعريفي", company_name, "حلول تسويقية عملية تدعم الوصول والنتائج")
        _clean_add_title(doc, "تقرير الملف التعريفي")
        _clean_add_text(doc, f"اسم الشركة: {company_name}", bold=True, size=12, space_after=4)
        source_value = data.get("company_source") or data.get("company_url") or "غير متوفر"
        _clean_add_text(doc, f"مصدر المعلومات: {source_value}", size=10, color=JORMALL_GRAY, space_after=14)
    elif marketing_plan:
        _clean_cover_page_arabic(doc, logo_path, "خطة تسويقية", company_name, "حلول تسويقية قابلة للتنفيذ وتدعم النمو")
        _clean_add_title(doc, "الخطة التسويقية")
        _clean_add_text(doc, f"اسم الشركة: {company_name}", bold=True, size=12, space_after=4)
        source_value = data.get("company_source") or data.get("company_url") or "غير متوفر"
        _clean_add_text(doc, f"مصدر المعلومات: {source_value}", size=10, color=JORMALL_GRAY, space_after=14)
    elif platform_benefits:
        _clean_cover_page_arabic(doc, logo_path, "فوائد المنصة", company_name, "حلول رسائل جورمول المصممة بما يناسب قطاع العميل")
        _clean_add_title(doc, "فوائد منصة جورمول")
        _clean_add_text(doc, f"اسم الشركة: {company_name}", bold=True, size=12, space_after=4)
        industry_value = data.get("industry") or "غير متوفر"
        try:
            from .platform_benefits_generation import INDUSTRY_AR
            industry_value = INDUSTRY_AR.get(industry_value, industry_value)
        except Exception:
            pass
        _clean_add_text(doc, f"القطاع: {industry_value}", size=10, color=JORMALL_GRAY, space_after=4)
        source_value = data.get("company_source") or data.get("company_url") or "غير متوفر"
        _clean_add_text(doc, f"مصدر المعلومات: {source_value}", size=10, color=JORMALL_GRAY, space_after=14)
    elif ai_product:
        product_type = str(data.get("ai_product_type", "")).strip()
        product_title = "مساعد الحجوزات الذكي" if product_type == "reservation_chatbot" else "مساعد الحملات الذكي"
        tagline = (
            "محادثات ذكية تساعد العميل على الانتقال من الاستفسار إلى طلب الحجز"
            if product_type == "reservation_chatbot"
            else "مساعد مخصص لحملة أو عرض أو فعالية أو إطلاق خدمة واحدة"
        )
        _clean_cover_page_arabic(doc, logo_path, product_title, company_name, tagline)
        _clean_add_title(doc, product_title)
        _clean_add_text(doc, f"اسم الشركة: {company_name}", bold=True, size=12, space_after=4)
        source_value = data.get("company_source") or data.get("company_url") or "غير متوفر"
        _clean_add_text(doc, f"مصدر المعلومات: {source_value}", size=10, color=JORMALL_GRAY, space_after=14)
    else:
        campaign_title, campaign_type = _campaign_type_arabic(sms_type, data.get("chain_campaign_title_ar") or data.get("chain_campaign_title", ""))
        _clean_cover_page_arabic(doc, logo_path, campaign_title, company_name, campaign_type)
        _clean_add_intro_for_sms_type(doc, sms_type)

        # Major document titles always start on a fresh page, matching the other reports.
        _ensure_new_page(doc)
        _clean_add_title(doc, "تقرير حملة الرسائل القصيرة")
        _clean_add_label_value(doc, "اسم الشركة", company_name, space_after=10)
        _clean_add_label_value(doc, "الموقع الإلكتروني", company_url, space_after=14)

    rendered_chain_pages = set()
    chain_messages_ar = data.get("chain_messages_ar") or []
    raw_analysis = data.get("analysis") or {}
    if isinstance(raw_analysis, str):
        try:
            raw_analysis = json.loads(raw_analysis)
        except (json.JSONDecodeError, TypeError):
            raw_analysis = {"تحليل الحملة": raw_analysis}
    if isinstance(raw_analysis, list):
        raw_analysis = {f"القسم {i}": item for i, item in enumerate(raw_analysis, start=1)}
    if not isinstance(raw_analysis, dict):
        raw_analysis = {"تحليل الحملة": str(raw_analysis or "")}

    for key, content in raw_analysis.items():
        if isinstance(content, str):
            content = {"header": str(key), "answer": content}
        elif not isinstance(content, dict):
            content = {"header": str(key), "answer": str(content or "")}

        header = content.get("header", "")
        answer = content.get("answer", "")
        original_header = content.get("original_header", header)
        header = _normalize_arabic_doc_header(header, original_header)
        answer = _normalize_arabic_doc_answer(answer, header, original_header)
        message_index = content.get("message_index", "")
        pitch = content.get("pitch_ar") or content.get("pitch") or ""
        delivery_date = content.get("delivery_date", datetime.today().strftime("%Y-%m-%d"))
        delivery_time = content.get("delivery_time", "00:00")

        # Remove the old Arabic-only extra 160-char section from Arabic documents.
        # The correct replacement is the real English SMS Suggestions section.
        if _is_legacy_arabic_extra_160_header(header) or _is_legacy_arabic_extra_160_header(original_header):
            continue

        if sms_type == "chain" and message_index and message_index not in rendered_chain_pages:
            idx = int(message_index) - 1 if str(message_index).isdigit() else None
            page_pitch = chain_messages_ar[idx] if idx is not None and idx < len(chain_messages_ar) else pitch
            _clean_chain_message_page(doc, message_index, page_pitch, delivery_date, delivery_time)
            rendered_chain_pages.add(message_index)

        # Premium intro pages follow the English order but stay concise.
        if sms_type == "premium" and original_header in {
            "Arabic SMS Suggestions (Formal) – 126 Characters [2 Messages]",
            "Social Media Caption (English)",
            "Radio Announcement Script (English)",
        }:
            pass

        if not (_is_english_sms_header(header) or _is_english_sms_header(original_header)) and "اقتراحات رسائل عربية" in str(header):
            answer = sanitize_arabic_sms_answer(answer)

        _clean_add_blue_heading(doc, header)
        if company_profile or marketing_plan or platform_benefits or ai_product:
            _render_client_insight_markdown(doc, answer)
        elif "|" in str(answer) and "---" in str(answer):
            add_markdown_table(doc, answer)
        elif _is_english_sms_header(header) or _is_english_sms_header(original_header):
            add_ltr_paragraph(doc, answer)
        else:
            add_wrapped_paragraph(doc, answer)

    doc.add_section(WD_SECTION.NEW_PAGE)
    if ai_product:
        _clean_add_blue_heading(doc, "عن منتجات الذكاء الاصطناعي من جورمول")
        _clean_add_jormall_ai_products_arabic(doc)
    else:
        _clean_add_jormall_services_arabic(doc)

    footer = doc.sections[0].footer
    fpara = footer.paragraphs[0]
    fpara.text = ""
    _clean_set_paragraph_rtl(fpara, align=WD_ALIGN_PARAGRAPH.CENTER)
    r = fpara.add_run("فرق المبيعات والدعم في جورمول دائماً بخدمتكم.\nلأي استفسار، يرجى التواصل مع مسؤول الحساب أو عبر البريد الإلكتروني: order.processing@jormall.com\n")
    _clean_set_run_rtl(r, size=9)

    # Add the JorMall logo to the header of every page/section after all
    # sections are created, including the final About JorMall page.
    _add_jormall_logo_to_all_headers(doc, logo_path)

    print("💾 Saving clean Arabic DOCX to:", output_path)
    _force_final_arabic_right_alignment(doc)
    doc.save(output_path)
    print("✅ Clean Arabic DOCX saved successfully.")
    return output_path

# =====================================================================
# FINAL FORMAT PARITY OVERRIDES
# Keep this block LAST. It makes the Arabic DOCX use the same visible
# markdown/style rules as the English DOCX: Normal 11pt Arial, blue 13pt
# white bold headings, same paragraph spacing, real bullets for markdown
# bullet lines, and markdown **bold** / *italic*. Arabic remains RTL and
# right-aligned.
# =====================================================================

def _fmt_is_bullet_line(line):
    return re.match(r"^\s*([-*•]|\d+[.)])\s+(.+?)\s*$", str(line or ""))


def _clean_rtl_text(text):
    """Clean bidi control chars; let Word paragraph bidi handle direction."""
    text = str(text or "")
    return text.replace("\u202A", "").replace("\u202B", "").replace("\u202C", "").replace("\u200E", "").replace("\u200F", "")


def _clean_set_run_rtl(run, font_name=ARABIC_FONT, size=None, bold=None, italic=None, color=None):
    if bold is not None:
        run.bold = bold
        # Word treats Arabic as complex-script text. w:b alone can make the
        # Bold button appear active while the Arabic glyphs remain visually
        # regular. Set both standard and complex-script bold explicitly.
        rPr_for_bold = run._element.get_or_add_rPr()
        for tag_name in ("w:b", "w:bCs"):
            node = rPr_for_bold.find(qn(tag_name))
            if node is None:
                node = OxmlElement(tag_name)
                rPr_for_bold.append(node)
            node.set(qn("w:val"), "1" if bold else "0")
    if italic is not None:
        run.italic = italic
        rPr_for_italic = run._element.get_or_add_rPr()
        for tag_name in ("w:i", "w:iCs"):
            node = rPr_for_italic.find(qn(tag_name))
            if node is None:
                node = OxmlElement(tag_name)
                rPr_for_italic.append(node)
            node.set(qn("w:val"), "1" if italic else "0")
    if size is not None:
        resolved_size = Pt(size) if isinstance(size, (int, float)) else size
        run.font.size = resolved_size
        # Keep the complex-script size synchronized with the visible font size.
        try:
            half_points = str(int(round(resolved_size.pt * 2)))
            rPr_for_size = run._element.get_or_add_rPr()
            sz_cs = rPr_for_size.find(qn("w:szCs"))
            if sz_cs is None:
                sz_cs = OxmlElement("w:szCs")
                rPr_for_size.append(sz_cs)
            sz_cs.set(qn("w:val"), half_points)
        except Exception:
            pass
    if color is not None:
        run.font.color.rgb = color

    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()

    rFonts = rPr.rFonts
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font_name)

    rtl = rPr.find(qn("w:rtl"))
    if rtl is None:
        rtl = OxmlElement("w:rtl")
        rPr.append(rtl)
    rtl.set(qn("w:val"), "1")

    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "ar-SA")
    lang.set(qn("w:bidi"), "ar-SA")
    return run


def _clean_set_paragraph_rtl(paragraph, align=WD_ALIGN_PARAGRAPH.RIGHT):
    """RTL paragraph helper that mirrors the English doc's styling but right aligned."""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if align == WD_ALIGN_PARAGRAPH.CENTER else WD_ALIGN_PARAGRAPH.RIGHT
    pPr = paragraph._p.get_or_add_pPr()

    for child in list(pPr):
        if child.tag in {qn("w:jc"), qn("w:bidi")}:
            pPr.remove(child)

    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)

    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center" if align == WD_ALIGN_PARAGRAPH.CENTER else "right")
    pPr.append(jc)

    try:
        set_paragraph_language(paragraph, "ar-SA")
    except Exception:
        pass

    for run in paragraph.runs:
        _clean_set_run_rtl(run)
    return paragraph


def _clean_set_doc_defaults(doc):
    """Arabic document defaults that visually match the English DOCX body."""
    try:
        settings = doc.settings._element
        bidi = settings.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            settings.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass

    for style_name in ["Normal", "List Bullet", "List Number"]:
        try:
            style = doc.styles[style_name]
            style.font.name = ARABIC_FONT
            style.font.size = Pt(11)
            rPr = style.element.get_or_add_rPr()
            rFonts = rPr.rFonts
            if rFonts is None:
                rFonts = OxmlElement("w:rFonts")
                rPr.append(rFonts)
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rFonts.set(qn(attr), ARABIC_FONT)
            pPr = style.element.get_or_add_pPr()
            for child in list(pPr):
                if child.tag in {qn("w:jc"), qn("w:bidi")}:
                    pPr.remove(child)
            bidi = OxmlElement("w:bidi")
            bidi.set(qn("w:val"), "1")
            pPr.append(bidi)
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), "right")
            pPr.append(jc)
        except Exception:
            pass


def _split_bidi_segments(text):
    """Split mixed Arabic/Latin text into directional runs without reordering brands/URLs."""
    text = str(text or "")
    if not text:
        return []

    def strong_dir(ch):
        code = ord(ch)
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0x08A0 <= code <= 0x08FF):
            return "rtl"
        if ch.isascii() and (ch.isalpha() or ch.isdigit()):
            return "ltr"
        return None

    segments = []
    current = []
    current_dir = None
    pending_neutral = []
    for ch in text:
        direction = strong_dir(ch)
        if direction is None:
            pending_neutral.append(ch)
            continue
        if current_dir is None:
            current_dir = direction
            current.extend(pending_neutral)
            pending_neutral = []
            current.append(ch)
            continue
        if direction == current_dir:
            current.extend(pending_neutral)
            pending_neutral = []
            current.append(ch)
        else:
            # Spaces/punctuation between scripts travel with the preceding segment.
            current.extend(pending_neutral)
            pending_neutral = []
            if current:
                segments.append((current_dir, "".join(current)))
            current = [ch]
            current_dir = direction
    current.extend(pending_neutral)
    if current:
        segments.append((current_dir or "rtl", "".join(current)))
    return segments


def _clean_add_inline_runs(paragraph, text, bold_all=False, italic_all=False, size=11, color=None):
    """Render markdown with true RTL Arabic plus stable LTR brands, URLs, emails and numbers."""
    text = _clean_rtl_text(text)
    tokens = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", str(text or ""))
    for token in tokens:
        if token == "":
            continue
        bold = bold_all
        italic = italic_all
        visible = token
        if token.startswith("**") and token.endswith("**"):
            visible = token[2:-2]
            bold = True
        elif token.startswith("*") and token.endswith("*"):
            visible = token[1:-1]
            italic = True

        for direction, segment in _split_bidi_segments(visible):
            if not segment:
                continue
            run = paragraph.add_run(segment)
            if direction == "ltr":
                _clean_set_run_ltr(run, size=size, bold=bold, italic=italic, color=color)
            else:
                _clean_set_run_rtl(run, size=size, bold=bold, italic=italic, color=color)


def _clean_add_text(doc, text="", bold=False, italic=False, size=11, color=None, align=WD_ALIGN_PARAGRAPH.RIGHT, space_after=10, style=None):
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=align)
    if text:
        _clean_add_inline_runs(p, text, bold_all=bold, italic_all=italic, size=size, color=color)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _clean_add_bullet(doc, text, numbered=False):
    style = "List Number" if numbered else "List Bullet"
    p = doc.add_paragraph(style=style)
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _clean_add_inline_runs(p, text, size=11)
    # English List Bullet paragraphs are compact; avoid oversized Arabic gaps.
    p.paragraph_format.space_after = Pt(0)
    return p


def _clean_add_title(doc, text):
    # Mirrors doc.add_heading(..., 0) visual weight used in the English file.
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    r = p.add_run(_clean_rtl_text(str(text or "")))
    _clean_set_run_rtl(r, size=26, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
    p.paragraph_format.space_after = Pt(14)

    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)
    for child in list(pBdr):
        if child.tag == qn("w:bottom"):
            pBdr.remove(child)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "2E75B6")
    pBdr.append(bottom)
    return p


def _clean_add_blue_heading(doc, title):
    # Exact match to English add_colored_heading: blue fill, white Arial 13pt bold.
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    r = p.add_run(_clean_rtl_text(str(title or "")))
    _clean_set_run_rtl(r, size=13, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True

    pPr = p._p.get_or_add_pPr()
    for child in list(pPr):
        if child.tag == qn("w:shd"):
            pPr.remove(child)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "2E75B6")
    pPr.append(shd)
    return p


def add_colored_heading(doc, title):
    return _clean_add_blue_heading(doc, title)


def add_wrapped_paragraph(doc, text):
    """Arabic equivalent of the English paragraph renderer, with markdown and bullets preserved."""
    text = str(text or "")
    if not text.strip():
        return

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()] or [text]
    for block in blocks:
        if "|" in block and "---" in block:
            add_markdown_table(doc, block)
            continue

        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        # If a block is markdown bullets/numbering, render real Word bullets.
        if lines and all(_fmt_is_bullet_line(ln) for ln in lines):
            for ln in lines:
                m = _fmt_is_bullet_line(ln)
                marker = m.group(1)
                content = m.group(2).strip()
                _clean_add_bullet(doc, content, numbered=bool(re.match(r"\d+[.)]", marker)))
            continue

        # Otherwise preserve line breaks in one paragraph like the English generator.
        p = doc.add_paragraph()
        _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _clean_add_inline_runs(p, "\n".join(lines), size=11)
        p.paragraph_format.space_after = Pt(10)


def arabic_sms_formatting(doc, sms_text):
    """Match English Arabic-SMS rendering: one clean right-aligned paragraph per SMS line."""
    for line in str(sms_text or "").splitlines():
        clean = line.strip()
        if clean:
            p = doc.add_paragraph()
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, clean, size=11)
            p.paragraph_format.space_after = Pt(6)


def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in str(markdown_table_text or "").splitlines() if "|" in line]
    if len(lines) < 2:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    header_cells = [cell.strip() for cell in lines[0].split("|") if cell.strip()]
    if not header_cells:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    table = doc.add_table(rows=1, cols=len(header_cells))
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.RIGHT
    try:
        tblPr = table._tbl.tblPr
        bidi = tblPr.find(qn("w:bidiVisual"))
        if bidi is None:
            bidi = OxmlElement("w:bidiVisual")
            tblPr.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass

    rows = [header_cells]
    for line in lines[2:]:
        rows.append([cell.strip() for cell in line.split("|") if cell.strip()][:len(header_cells)])

    for ri, row_values in enumerate(rows):
        cells = table.rows[0].cells if ri == 0 else table.add_row().cells
        for i, value in enumerate(row_values):
            if i >= len(cells):
                break
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, value, bold_all=(ri == 0), size=11)
            p.paragraph_format.space_after = Pt(0)
    return table


def _clean_add_simple_section(doc, title, subtitle, paragraphs=None, bullets=None):
    _clean_add_blue_heading(doc, title)
    if subtitle:
        _clean_add_text(doc, subtitle, bold=True, italic=True, size=12, space_after=8)
    for para in paragraphs or []:
        add_wrapped_paragraph(doc, para)
    for b in bullets or []:
        _clean_add_bullet(doc, b)
    doc.add_page_break()

# Final Arabic body renderer: clean right alignment, real list spacing, and mixed-script safety.
def add_wrapped_paragraph(doc, text):
    text = str(text or "")
    if not text.strip():
        return

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()] or [text]
    for block in blocks:
        if "|" in block and "---" in block:
            add_markdown_table(doc, block)
            continue

        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        normal_buffer = []

        def flush_normal():
            if not normal_buffer:
                return
            p = doc.add_paragraph()
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, "\n".join(normal_buffer), size=11)
            p.paragraph_format.space_after = Pt(10)
            normal_buffer.clear()

        for ln in lines:
            m = _fmt_is_bullet_line(ln)
            if not m:
                normal_buffer.append(ln)
                continue
            flush_normal()
            marker = m.group(1)
            content = m.group(2).strip()
            # Manual markers are more reliable than Word's LTR list definitions for Arabic.
            p = doc.add_paragraph()
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            prefix = f"{marker} " if re.match(r"\d+[.)]", marker) else "• "
            _clean_add_inline_runs(p, prefix + content, size=11)
            p.paragraph_format.left_indent = Pt(0)
            p.paragraph_format.right_indent = Pt(14)
            p.paragraph_format.first_line_indent = Pt(-10)
            p.paragraph_format.space_after = Pt(3)
        flush_normal()

# Final RTL alignment override.
# Arabic body text is explicitly RIGHT aligned in both python-docx and OOXML.
# Mixed English/URL runs are handled separately as LTR runs without changing
# the paragraph's physical right alignment.
def _clean_set_paragraph_rtl(paragraph, align=WD_ALIGN_PARAGRAPH.RIGHT):
    if align == WD_ALIGN_PARAGRAPH.CENTER:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        jc_value = "center"
    else:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        jc_value = "right"

    pPr = paragraph._p.get_or_add_pPr()
    for child in list(pPr):
        if child.tag in {qn("w:jc"), qn("w:bidi")}:
            pPr.remove(child)

    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1")
    pPr.append(bidi)

    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), jc_value)
    pPr.append(jc)

    try:
        set_paragraph_language(paragraph, "ar-SA")
    except Exception:
        pass
    for run in paragraph.runs:
        _clean_set_run_rtl(run)
    return paragraph


# Keep the English 160-character SMS section readable inside Arabic DOCX files.
def _is_english_sms_header(header):
    return "english sms suggestions" in str(header or "").lower()


def _is_legacy_arabic_extra_160_header(header):
    return str(header or "").strip() == "اقتراحات رسائل عربية إضافية - 160 حرفاً"


def _clean_set_run_ltr(run, font_name=ENGLISH_FONT, size=None, bold=None, italic=None, color=None):
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if size is not None:
        run.font.size = Pt(size) if isinstance(size, (int, float)) else size
    if color is not None:
        run.font.color.rgb = color

    run.font.name = font_name
    rPr = run._element.get_or_add_rPr()

    rFonts = rPr.rFonts
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font_name)

    # Explicitly avoid RTL on the English-only SMS suggestion runs.
    rtl = rPr.find(qn("w:rtl"))
    if rtl is None:
        rtl = OxmlElement("w:rtl")
        rPr.append(rtl)
    rtl.set(qn("w:val"), "0")

    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "en-US")
    lang.set(qn("w:bidi"), "en-US")
    return run


def _clean_set_paragraph_ltr(paragraph, align=WD_ALIGN_PARAGRAPH.LEFT):
    paragraph.alignment = align
    pPr = paragraph._p.get_or_add_pPr()
    for child in list(pPr):
        if child.tag in {qn("w:jc"), qn("w:bidi")}:
            pPr.remove(child)

    # Explicitly mark the paragraph as non-bidi. Removing w:bidi is not
    # enough in some Word/LibreOffice Arabic document contexts because the
    # direction can be inherited from defaults.
    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "0")
    pPr.append(bidi)

    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "left" if align == WD_ALIGN_PARAGRAPH.LEFT else "center")
    pPr.append(jc)
    try:
        set_paragraph_language(paragraph, "en-US")
    except Exception:
        pass
    for run in paragraph.runs:
        _clean_set_run_ltr(run)
    return paragraph


def _clean_add_inline_runs_ltr(paragraph, text, bold_all=False, italic_all=False, size=11, color=None):
    tokens = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", str(text or ""))
    for token in tokens:
        if token == "":
            continue
        bold = bold_all
        italic = italic_all
        visible = token
        if token.startswith("**") and token.endswith("**"):
            visible = token[2:-2]
            bold = True
        elif token.startswith("*") and token.endswith("*"):
            visible = token[1:-1]
            italic = True
        run = paragraph.add_run(visible)
        _clean_set_run_ltr(run, size=size, bold=bold, italic=italic, color=color)


def add_ltr_paragraph(doc, text):
    text = str(text or "")
    if not text.strip():
        return
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()] or [text]
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        p = doc.add_paragraph()
        _clean_set_paragraph_ltr(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        _clean_add_inline_runs_ltr(p, "\n".join(lines), size=11)
        p.paragraph_format.space_after = Pt(10)


# =====================================================================
# CLIENT INSIGHTS ARABIC REPORT RENDERER
# Used only by Arabic Profile Reports and Marketing Plans. It turns mixed
# Markdown (headings, paragraphs, bullets, numbering and tables) into real
# Word structure instead of leaving Markdown characters visible.
# =====================================================================

def _client_insight_set_cell_margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for margin_name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn(f"w:{margin_name}"))
        if node is None:
            node = OxmlElement(f"w:{margin_name}")
            tcMar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _client_insight_shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)


def _client_insight_add_heading(doc, text, level=2):
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return None
    size = 14 if level <= 2 else 12
    color = RGBColor(0x1F, 0x4E, 0x79) if level <= 2 else RGBColor(0x36, 0x53, 0x6D)
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _clean_add_inline_runs(p, clean, bold_all=True, size=size, color=color)
    p.paragraph_format.space_before = Pt(7 if level <= 2 else 4)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    if level <= 2:
        pPr = p._p.get_or_add_pPr()
        pBdr = pPr.find(qn("w:pBdr"))
        if pBdr is None:
            pBdr = OxmlElement("w:pBdr")
            pPr.append(pBdr)
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "2")
        bottom.set(qn("w:color"), "B8D5EA")
        pBdr.append(bottom)
    return p


def _client_insight_add_body(doc, lines):
    clean_lines = [str(line or "").strip() for line in lines if str(line or "").strip()]
    if not clean_lines:
        return None
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    for index, line in enumerate(clean_lines):
        if index:
            p.add_run().add_break()
        _clean_add_inline_runs(p, line, size=11)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.12
    return p


def _client_insight_add_list_item(doc, text, numbered=False, number=None):
    clean = str(text or "").strip()
    if not clean:
        return None
    # Manual visible marker is more reliable than Word's LTR list numbering for
    # mixed Arabic/English content, while remaining a real separate list item.
    marker = f"{number}. " if numbered and number else ("• " if not numbered else "")
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _clean_add_inline_runs(p, marker + clean, size=11)
    p.paragraph_format.left_indent = Inches(0.08)
    p.paragraph_format.right_indent = Inches(0.16)
    p.paragraph_format.first_line_indent = Inches(-0.08)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.08
    return p


def _client_insight_add_table(doc, table_lines):
    lines = [str(line or "").strip() for line in table_lines if "|" in str(line or "")]
    if len(lines) < 2:
        return _client_insight_add_body(doc, table_lines)

    def cells_from(line):
        value = line.strip().strip("|")
        return [cell.strip() for cell in value.split("|")]

    headers = cells_from(lines[0])
    if not headers:
        return _client_insight_add_body(doc, table_lines)

    data_lines = lines[1:]
    if data_lines and all(re.fullmatch(r"\s*:?-{3,}:?\s*", c or "") for c in cells_from(data_lines[0])):
        data_lines = data_lines[1:]
    rows = [cells_from(line) for line in data_lines]

    table = doc.add_table(rows=1, cols=len(headers))
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.RIGHT
    table.autofit = True
    tblPr = table._tbl.tblPr
    bidi = tblPr.find(qn("w:bidiVisual"))
    if bidi is None:
        bidi = OxmlElement("w:bidiVisual")
        tblPr.append(bidi)
    bidi.set(qn("w:val"), "1")

    all_rows = [headers] + rows
    for row_index, values in enumerate(all_rows):
        cells = table.rows[0].cells if row_index == 0 else table.add_row().cells
        for cell_index, cell in enumerate(cells):
            value = values[cell_index] if cell_index < len(values) else ""
            cell.text = ""
            _client_insight_set_cell_margins(cell)
            if row_index == 0:
                _client_insight_shade_cell(cell, "2E75B6")
            elif row_index % 2 == 0:
                _client_insight_shade_cell(cell, "F2F7FB")
            p = cell.paragraphs[0]
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(
                p,
                value,
                bold_all=(row_index == 0),
                size=10.5,
                color=RGBColor(0xFF, 0xFF, 0xFF) if row_index == 0 else None,
            )
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(3)
    return table


def _render_client_insight_markdown(doc, text):
    raw = _clean_rtl_text(str(text or "")).replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"^\s*```(?:markdown|md|text)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```\s*$", "", raw)
    lines = raw.split("\n")
    paragraph_buffer = []
    index = 0

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            _client_insight_add_body(doc, paragraph_buffer)
            paragraph_buffer = []

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            flush_paragraph()
            index += 1
            continue
        if re.fullmatch(r"[-_]{3,}", line):
            flush_paragraph()
            index += 1
            continue

        # Markdown table: header row followed by a separator row.
        if "|" in line and index + 1 < len(lines) and "|" in lines[index + 1] and "---" in lines[index + 1]:
            flush_paragraph()
            table_lines = [line, lines[index + 1].strip()]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index].strip())
                index += 1
            _client_insight_add_table(doc, table_lines)
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading_match:
            flush_paragraph()
            _client_insight_add_heading(doc, heading_match.group(2), level=len(heading_match.group(1)))
            index += 1
            continue

        # Standalone bold line is treated as a subsection heading.
        bold_heading = re.fullmatch(r"\*\*(.+?)\*\*:?", line)
        if bold_heading and len(bold_heading.group(1)) <= 90:
            flush_paragraph()
            _client_insight_add_heading(doc, bold_heading.group(1), level=3)
            index += 1
            continue

        bullet_match = re.match(r"^[-*•]\s+(.+)$", line)
        if bullet_match:
            flush_paragraph()
            _client_insight_add_list_item(doc, bullet_match.group(1), numbered=False)
            index += 1
            continue

        number_match = re.match(r"^(\d+)[.)]\s+(.+)$", line)
        if number_match:
            flush_paragraph()
            _client_insight_add_list_item(doc, number_match.group(2), numbered=True, number=number_match.group(1))
            index += 1
            continue

        # Label/value lines such as **Objective:** ... deserve their own row.
        if re.match(r"^\*\*[^*]{1,70}:\*\*", line) or re.match(r"^[^:：]{1,45}[:：]\s+", line):
            flush_paragraph()
            _client_insight_add_body(doc, [line])
            index += 1
            continue

        paragraph_buffer.append(line)
        index += 1

    flush_paragraph()


# =====================================================================
# FINAL CLEAN RTL/LTR LAYOUT OVERRIDES (2026-07-19)
# IMPORTANT: In RTL paragraphs use logical `start` alignment, not w:jc=right.
# This renders physically on the RIGHT in Word-compatible RTL layout and avoids
# the left-shift produced by combining bidi=1 with right alignment.
# Pure English blocks embedded in Arabic documents remain LTR/left for readability.
# =====================================================================

def _set_logical_paragraph_alignment(paragraph, *, rtl=True, centered=False):
    """Set direction + logical alignment in OOXML without bidi/alignment conflicts."""
    pPr = paragraph._p.get_or_add_pPr()
    for child in list(pPr):
        if child.tag in {qn("w:jc"), qn("w:bidi")}:
            pPr.remove(child)

    bidi = OxmlElement("w:bidi")
    bidi.set(qn("w:val"), "1" if rtl else "0")
    pPr.append(bidi)

    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center" if centered else "start")
    pPr.append(jc)

    # Avoid python-docx re-writing jc as physical left/right after the OOXML fix.
    if centered:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # Re-assert because setting paragraph.alignment writes w:jc.
        pPr = paragraph._p.get_or_add_pPr()
        jc_node = pPr.find(qn("w:jc"))
        if jc_node is not None:
            jc_node.set(qn("w:val"), "center")
    else:
        paragraph.alignment = None
        pPr = paragraph._p.get_or_add_pPr()
        jc_node = pPr.find(qn("w:jc"))
        if jc_node is None:
            jc_node = OxmlElement("w:jc")
            pPr.append(jc_node)
        jc_node.set(qn("w:val"), "start")

    try:
        set_paragraph_language(paragraph, "ar-SA" if rtl else "en-US")
    except Exception:
        pass
    return paragraph


def _clean_set_paragraph_rtl(paragraph, align=WD_ALIGN_PARAGRAPH.RIGHT):
    centered = align == WD_ALIGN_PARAGRAPH.CENTER
    _set_logical_paragraph_alignment(paragraph, rtl=True, centered=centered)
    for run in paragraph.runs:
        # Do not force Latin-only runs RTL; preserve stable brands/URLs/numbers.
        if _clean_contains_arabic(run.text or ""):
            _clean_set_run_rtl(run)
        else:
            _clean_set_run_ltr(run)
    return paragraph


def _clean_set_paragraph_ltr(paragraph, align=WD_ALIGN_PARAGRAPH.LEFT):
    centered = align == WD_ALIGN_PARAGRAPH.CENTER
    _set_logical_paragraph_alignment(paragraph, rtl=False, centered=centered)
    for run in paragraph.runs:
        _clean_set_run_ltr(run)
    return paragraph


def _clean_set_doc_defaults(doc):
    """Stable Arabic defaults: RTL + logical start (physical right)."""
    try:
        settings = doc.settings._element
        bidi = settings.find(qn("w:bidi"))
        if bidi is None:
            bidi = OxmlElement("w:bidi")
            settings.append(bidi)
        bidi.set(qn("w:val"), "1")
    except Exception:
        pass

    for style_name in ["Normal", "List Bullet", "List Number", "Heading 1", "Heading 2", "Heading 3"]:
        try:
            style = doc.styles[style_name]
            style.font.name = ARABIC_FONT
            if style_name in {"Normal", "List Bullet", "List Number"}:
                style.font.size = Pt(11)
            rPr = style.element.get_or_add_rPr()
            rFonts = rPr.rFonts
            if rFonts is None:
                rFonts = OxmlElement("w:rFonts")
                rPr.append(rFonts)
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rFonts.set(qn(attr), ARABIC_FONT)
            pPr = style.element.get_or_add_pPr()
            for child in list(pPr):
                if child.tag in {qn("w:jc"), qn("w:bidi")}:
                    pPr.remove(child)
            bidi = OxmlElement("w:bidi")
            bidi.set(qn("w:val"), "1")
            pPr.append(bidi)
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), "start")
            pPr.append(jc)
        except Exception:
            pass


def _clean_add_bullet(doc, text, numbered=False):
    """RTL-safe manual list item; avoids Word's LTR list-marker positioning."""
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    marker = "1. " if numbered else "• "
    # Numbered source lines are normally handled by client-insight renderer; this
    # fallback intentionally uses a simple marker rather than unstable list styles.
    _clean_add_inline_runs(p, marker + str(text or ""), size=11)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.08
    return p


def _client_insight_add_list_item(doc, text, numbered=False, number=None):
    clean = str(text or "").strip()
    if not clean:
        return None
    marker = f"{number}. " if numbered and number else "• "
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _clean_add_inline_runs(p, marker + clean, size=11)
    # Keep the whole list on the RTL start edge. Avoid left/hanging indents that
    # previously made bullets look detached and shifted toward the left.
    p.paragraph_format.left_indent = None
    p.paragraph_format.right_indent = Inches(0.08)
    p.paragraph_format.first_line_indent = None
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.08
    return p


def _normalize_arabic_client_insight_labels(text):
    """Translate structural English labels that sometimes leak from model output."""
    value = str(text or "")
    replacements = [
        (r"\bSMS\s+Content\s+Sample\b", "نموذج محتوى رسالة قصيرة"),
        (r"\bDate\s*&\s*Time\b", "التاريخ والوقت"),
        (r"\bTime\s*&\s*Date\b", "التاريخ والوقت"),
        (r"\bObjective\b", "الهدف"),
        (r"\bContent\s+in\s+English\b", "المحتوى بالإنجليزية"),
        (r"\bContent\s+in\s+Arabic\b", "المحتوى بالعربية"),
        (r"\bTarget\s+Audience\b", "الجمهور المستهدف"),
        (r"\bAudience\s+Target\b", "الجمهور المستهدف"),
        (r"\bRecommendations\b", "التوصيات"),
        (r"\bDescription\b", "الوصف"),
        (r"\bSummary\b", "الملخص"),
        (r"SMS\s+Timing\s+Strategy\s*\(\s*Scheduling\s*\)", "استراتيجية توقيت وجدولة الرسائل القصيرة"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


# Wrap the existing Markdown renderer so existing structure is retained while
# leaked English field labels are normalized before layout.
_render_client_insight_markdown_pre_clean_20260719 = _render_client_insight_markdown

def _render_client_insight_markdown(doc, text):
    return _render_client_insight_markdown_pre_clean_20260719(
        doc, _normalize_arabic_client_insight_labels(text)
    )


def _force_final_arabic_right_alignment(document):
    """Final direction normalization using logical start alignment.

    Arabic/mixed paragraphs -> RTL + start = physical right.
    Pure English paragraphs -> LTR + start = physical left.
    Intentional centered cover/footer paragraphs stay centered.
    """
    def has_arabic(paragraph):
        return _clean_contains_arabic("".join((run.text or "") for run in paragraph.runs))

    def normalize_paragraph(paragraph):
        if not any((run.text or "").strip() for run in paragraph.runs):
            return
        pPr = paragraph._p.get_or_add_pPr()
        jc = pPr.find(qn("w:jc"))
        is_centered = (jc is not None and jc.get(qn("w:val")) == "center")
        rtl = has_arabic(paragraph)
        _set_logical_paragraph_alignment(paragraph, rtl=rtl, centered=is_centered)
        for run in paragraph.runs:
            if rtl and _clean_contains_arabic(run.text or ""):
                _clean_set_run_rtl(run)
            else:
                _clean_set_run_ltr(run)

    for paragraph in document.paragraphs:
        normalize_paragraph(paragraph)

    for table in document.tables:
        try:
            table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            tblPr = table._tbl.tblPr
            bidi = tblPr.find(qn("w:bidiVisual"))
            if bidi is None:
                bidi = OxmlElement("w:bidiVisual")
                tblPr.append(bidi)
            bidi.set(qn("w:val"), "1")
        except Exception:
            pass
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    normalize_paragraph(paragraph)

    for section in document.sections:
        for paragraph in section.header.paragraphs:
            normalize_paragraph(paragraph)
        for paragraph in section.footer.paragraphs:
            normalize_paragraph(paragraph)
        for table in list(section.header.tables) + list(section.footer.tables):
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        normalize_paragraph(paragraph)


# =====================================================================
# ABSOLUTE FINAL ARABIC DOCUMENT ALIGNMENT OVERRIDE
# Arabic-generated documents are physically right aligned throughout.
# Arabic/mixed paragraphs use RTL + logical start (right). Pure English
# paragraphs keep LTR reading order but use physical right alignment.
# Centered cover/footer blocks remain centered.
# =====================================================================
def _force_final_arabic_right_alignment(document):
    def _has_arabic(paragraph):
        return _clean_contains_arabic("".join((run.text or "") for run in paragraph.runs))

    def _normalize(paragraph):
        if not any((run.text or "").strip() for run in paragraph.runs):
            return
        pPr = paragraph._p.get_or_add_pPr()
        jc0 = pPr.find(qn("w:jc"))
        centered = jc0 is not None and jc0.get(qn("w:val")) == "center"
        rtl = _has_arabic(paragraph)
        for child in list(pPr):
            if child.tag in {qn("w:jc"), qn("w:bidi")} :
                pPr.remove(child)
        bidi = OxmlElement("w:bidi")
        bidi.set(qn("w:val"), "1" if rtl else "0")
        pPr.append(bidi)
        jc = OxmlElement("w:jc")
        if centered:
            jc.set(qn("w:val"), "center")
        elif rtl:
            jc.set(qn("w:val"), "start")
        else:
            jc.set(qn("w:val"), "right")
        pPr.append(jc)
        # Do not assign paragraph.alignment here: python-docx would rewrite/remove
        # the logical w:jc value. The OOXML above is the authoritative alignment.
        for run in paragraph.runs:
            if _clean_contains_arabic(run.text or ""):
                _clean_set_run_rtl(run)
            else:
                _clean_set_run_ltr(run)

    for paragraph in document.paragraphs:
        _normalize(paragraph)
    for table in document.tables:
        try:
            table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            tblPr = table._tbl.tblPr
            bidi = tblPr.find(qn("w:bidiVisual"))
            if bidi is None:
                bidi = OxmlElement("w:bidiVisual")
                tblPr.append(bidi)
            bidi.set(qn("w:val"), "1")
        except Exception:
            pass
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _normalize(paragraph)
    for section in document.sections:
        for paragraph in section.header.paragraphs:
            _normalize(paragraph)
        for paragraph in section.footer.paragraphs:
            _normalize(paragraph)
        for table in list(section.header.tables) + list(section.footer.tables):
            try:
                table.alignment = WD_TABLE_ALIGNMENT.RIGHT
            except Exception:
                pass
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _normalize(paragraph)

# =====================================================================
# FINAL ARABIC MARKDOWN BODY RENDERER
# Removes visible Markdown markers and gives Arabic campaign sections the
# same clean hierarchy used by the English renderer.
# =====================================================================
def _add_arabic_subheading(doc, text, level=2):
    p = doc.add_paragraph()
    _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
    p.paragraph_format.space_before = Pt(7 if level <= 2 else 4)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    _clean_add_inline_runs(
        p,
        str(text or '').strip(),
        bold_all=True,
        size=12 if level <= 2 else 11,
        color=RGBColor(0x2E, 0x75, 0xB6) if level <= 2 else RGBColor(0x33, 0x33, 0x33),
    )
    return p


def add_wrapped_paragraph(doc, text):
    """Render Arabic/mixed Markdown cleanly with no visible #/* markers."""
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not raw.strip():
        return

    # Whole Markdown tables are handled as one block.
    if '|' in raw and '---' in raw:
        add_markdown_table(doc, raw)
        return

    pending_blank = False
    for raw_line in raw.split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue

        m_heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if m_heading:
            _add_arabic_subheading(doc, m_heading.group(2), level=len(m_heading.group(1)))
            pending_blank = False
            continue

        m_bullet = re.match(r'^(\s*)[-*•]\s+(.+)$', line)
        if m_bullet:
            p = doc.add_paragraph()
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, '• ' + m_bullet.group(2).strip(), size=11)
            p.paragraph_format.right_indent = Inches(0.08)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.08
            pending_blank = False
            continue

        m_num = re.match(r'^(\s*)(\d+)[.)]\s+(.+)$', line)
        if m_num:
            p = doc.add_paragraph()
            _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
            _clean_add_inline_runs(p, f'{m_num.group(2)}. {m_num.group(3).strip()}', size=11)
            p.paragraph_format.right_indent = Inches(0.04)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.08
            pending_blank = False
            continue

        p = doc.add_paragraph()
        _clean_set_paragraph_rtl(p, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _clean_add_inline_runs(p, stripped, size=11)
        p.paragraph_format.space_after = Pt(7 if pending_blank else 5)
        p.paragraph_format.line_spacing = 1.12
        pending_blank = False

# English-only sections embedded in Arabic documents keep LTR reading order,
# use real bullets/numbering, and are moved to the document's right edge by
# the final alignment normalizer.
def add_ltr_paragraph(doc, text):
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    if not raw.strip():
        return
    pending_blank = False
    for raw_line in raw.split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue
        m_heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if m_heading:
            p = doc.add_paragraph()
            _clean_set_paragraph_ltr(p, align=WD_ALIGN_PARAGRAPH.LEFT)
            _clean_add_inline_runs_ltr(p, m_heading.group(2), bold_all=True,
                                       size=12 if len(m_heading.group(1)) <= 2 else 11,
                                       color=RGBColor(0x2E, 0x75, 0xB6))
            p.paragraph_format.space_after = Pt(5)
            pending_blank = False
            continue
        m_bullet = re.match(r'^(\s*)[-*•]\s+(.+)$', line)
        if m_bullet:
            p = doc.add_paragraph()
            _clean_set_paragraph_ltr(p, align=WD_ALIGN_PARAGRAPH.LEFT)
            _clean_add_inline_runs_ltr(p, '• ' + m_bullet.group(2).strip(), size=11)
            p.paragraph_format.space_after = Pt(3)
            pending_blank = False
            continue
        m_num = re.match(r'^(\s*)(\d+)[.)]\s+(.+)$', line)
        if m_num:
            p = doc.add_paragraph()
            _clean_set_paragraph_ltr(p, align=WD_ALIGN_PARAGRAPH.LEFT)
            _clean_add_inline_runs_ltr(p, f'{m_num.group(2)}. {m_num.group(3).strip()}', size=11)
            p.paragraph_format.space_after = Pt(4)
            pending_blank = False
            continue
        p = doc.add_paragraph()
        _clean_set_paragraph_ltr(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        _clean_add_inline_runs_ltr(p, stripped, size=11)
        p.paragraph_format.space_after = Pt(7 if pending_blank else 5)
        pending_blank = False
