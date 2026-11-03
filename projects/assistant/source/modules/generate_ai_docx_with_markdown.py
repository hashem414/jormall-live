
import os
import re
import json
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_PARAGRAPH_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from datetime import datetime
def add_campaign_cover_page(
    doc: Document,
    logo_path: str,
    campaign_title: str,
    client_name: str,
    campaign_type: str = "SMS Campaign",
    campaign_date: str = None,
    prepared_by: str = "Central E-Commerce Ltd. (JorMall)"
):
    if not campaign_date:
        campaign_date = datetime.today().strftime("%A, %B %d, %Y")
    # 1. Insert Logo
    logo = doc.add_picture(logo_path, width=Inches(2.8))
    logo_paragraph = doc.paragraphs[-1]
    logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_paragraph.paragraph_format.space_after = Pt(10)  # Reduce space after logo

    # 2. Campaign Title
    title_para = doc.add_paragraph()
    title_run = title_para.add_run(campaign_title)
    title_run.font.name = "Arial"
    title_run.font.size = Pt(26)
    title_run.bold = True
    title_run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.paragraph_format.space_after = Pt(6)

    
    doc.add_paragraph()  # This inserts a blank line

    # 3. Campaign Type
    type_para = doc.add_paragraph()
    type_run = type_para.add_run(campaign_type)
    type_run.font.name = "Arial"
    type_run.font.size = Pt(14)
    type_run.italic = True
    type_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    type_para.paragraph_format.space_after = Pt(40)

    # 4. Client Name
    client_para = doc.add_paragraph()
    client_run = client_para.add_run(f"Client: {client_name}")
    client_run.font.name = "Arial"
    client_run.font.size = Pt(12)
    client_run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    client_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    client_para.paragraph_format.space_after = Pt(4)

    # 5. Prepared By
    prep_para = doc.add_paragraph()
    prep_run = prep_para.add_run(f"Prepared by: {prepared_by}")
    prep_run.font.name = "Arial"
    prep_run.font.size = Pt(12)
    prep_run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    prep_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    prep_para.paragraph_format.space_after = Pt(4)

    # 6. Date
    date_para = doc.add_paragraph()
    date_run = date_para.add_run(f"Date: {campaign_date}")
    date_run.font.name = "Arial"
    date_run.font.size = Pt(12)
    date_run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 7. Page Break
    doc.add_page_break()
def add_sales_profile_cover_page(
    doc: Document,
    logo_path: str,
    prospect_name: str,
    industry: str = "",
    phone: str = "",
    email: str = "",
    prepared_by: str = "JorMall Central E-Commerce",
    profile_title: str = "Sales Profile",
    tagline: str = "Solutions that convert. Expertise you can trust."
):
    """
    Creates a clean, printable Sales Profile cover page with logo, title,
    prospect details, AE info, and meeting date. Adds a page break at the end.
    """


    # 1) Logo
    logo = doc.add_picture(logo_path, width=Inches(2.8))
    p_logo = doc.paragraphs[-1]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_logo.paragraph_format.space_after = Pt(8)

    # 2) Main Title
    p_title = doc.add_paragraph()
    r_title = p_title.add_run(profile_title)
    r_title.font.name = "Arial"
    r_title.font.size = Pt(26)
    r_title.bold = True
    r_title.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)  # JorMall blue
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(4)

    # 3) Tagline / Subtitle
    p_tag = doc.add_paragraph()
    r_tag = p_tag.add_run(tagline)
    r_tag.font.name = "Arial"
    r_tag.font.size = Pt(13)
    r_tag.italic = True
    p_tag.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_tag.paragraph_format.space_after = Pt(28)

    # 4) Prospect Name (prominent)
    p_client = doc.add_paragraph()
    r_client = p_client.add_run(prospect_name)
    r_client.font.name = "Arial"
    r_client.font.size = Pt(18)
    r_client.bold = True
    p_client.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_client.paragraph_format.space_after = Pt(2)

    # 5) Prospect meta (industry / location)
    # p_meta = doc.add_paragraph()
    # meta_text = " • ".join([t for t in [industry] if t])
    # if meta_text:
    #     r_meta = p_meta.add_run(meta_text)
    #     r_meta.font.name = "Arial"
    #     r_meta.font.size = Pt(11.5)
    #     r_meta.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    #     p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    #     p_meta.paragraph_format.space_after = Pt(24)
    # else:
    #     p_meta.paragraph_format.space_after = Pt(12)

    # 6) Info box (Prospect / Meeting / AE)
    # Using a single-column table with subtle background to create a card
    # table = doc.add_table(rows=6, cols=2)
    # table.autofit = True

    # # Light gray background for header cells
    # def _cell_text(cell, text, bold=False):
    #     run = cell.paragraphs[0].add_run(text)
    #     run.font.name = "Arial"
    #     run.font.size = Pt(11.5)
    #     run.bold = bold
    #
    # rows = [
    #     ("Prospect", prospect_name),
    #     ("Industry", industry),
    #     ("Contact", " / ".join([t for t in [phone, email] if t])),
    # # ]
    #
    # for i, (label, value) in enumerate(rows):
    #     left, right = table.rows[i].cells
    #     _cell_text(left, f"{label}:", bold=True)
    #     _cell_text(right, value if value else "-")

    # Space before/after table using surrounding paragraphs
    p_before = doc.add_paragraph()
    p_before.paragraph_format.space_before = Pt(6)
    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_after = Pt(14)

    # 7) Prepared by + Date footer block (centered)
    p_prep = doc.add_paragraph()
    r_prep = p_prep.add_run(f"Prepared by: {prepared_by}")
    r_prep.font.name = "Arial"
    r_prep.font.size = Pt(11)
    r_prep.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    p_prep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_prep.paragraph_format.space_after = Pt(2)



    # 8) Confidential note (small, gray)
    p_conf = doc.add_paragraph()
    r_conf = p_conf.add_run("Confidential — For internal use with prospective clients.")
    r_conf.font.name = "Arial"
    r_conf.font.size = Pt(9)
    r_conf.font.color.rgb = RGBColor(0x77, 0x77, 0x77)
    p_conf.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 9) Page break to start body
    doc.add_page_break()
def add_marketing_plan_cover_page(
    doc: Document,
    logo_path: str,
    prospect_name: str,
    industry: str = "",
    phone: str = "",
    email: str = "",
    prepared_by: str = "JorMall Central E-Commerce",
    profile_title: str = "Marketing Plan",
    tagline: str = "Solutions that convert. Expertise you can trust."
):
    """
    prospect details, AE info, and meeting date. Adds a page break at the end.
    """


    # 1) Logo
    logo = doc.add_picture(logo_path, width=Inches(2.8))
    p_logo = doc.paragraphs[-1]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_logo.paragraph_format.space_after = Pt(8)

    # 2) Main Title
    p_title = doc.add_paragraph()
    r_title = p_title.add_run(profile_title)
    r_title.font.name = "Arial"
    r_title.font.size = Pt(26)
    r_title.bold = True
    r_title.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)  # JorMall blue
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(4)

    # 3) Tagline / Subtitle
    p_tag = doc.add_paragraph()
    r_tag = p_tag.add_run(tagline)
    r_tag.font.name = "Arial"
    r_tag.font.size = Pt(13)
    r_tag.italic = True
    p_tag.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_tag.paragraph_format.space_after = Pt(28)

    # 4) Prospect Name (prominent)
    p_client = doc.add_paragraph()
    r_client = p_client.add_run(prospect_name)
    r_client.font.name = "Arial"
    r_client.font.size = Pt(18)
    r_client.bold = True
    p_client.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_client.paragraph_format.space_after = Pt(2)

    # 5) Prospect meta (industry / location)
    # p_meta = doc.add_paragraph()
    # meta_text = " • ".join([t for t in [industry] if t])
    # if meta_text:
    #     r_meta = p_meta.add_run(meta_text)
    #     r_meta.font.name = "Arial"
    #     r_meta.font.size = Pt(11.5)
    #     r_meta.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    #     p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    #     p_meta.paragraph_format.space_after = Pt(24)
    # else:
    #     p_meta.paragraph_format.space_after = Pt(12)

    # 6) Info box (Prospect / Meeting / AE)
    # Using a single-column table with subtle background to create a card
    # table = doc.add_table(rows=6, cols=2)
    # table.autofit = True

    # # Light gray background for header cells
    # def _cell_text(cell, text, bold=False):
    #     run = cell.paragraphs[0].add_run(text)
    #     run.font.name = "Arial"
    #     run.font.size = Pt(11.5)
    #     run.bold = bold
    #
    # rows = [
    #     ("Prospect", prospect_name),
    #     ("Industry", industry),
    #     ("Contact", " / ".join([t for t in [phone, email] if t])),
    # # ]
    #
    # for i, (label, value) in enumerate(rows):
    #     left, right = table.rows[i].cells
    #     _cell_text(left, f"{label}:", bold=True)
    #     _cell_text(right, value if value else "-")

    # Space before/after table using surrounding paragraphs
    p_before = doc.add_paragraph()
    p_before.paragraph_format.space_before = Pt(6)
    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_after = Pt(14)

    # 7) Prepared by + Date footer block (centered)
    p_prep = doc.add_paragraph()
    r_prep = p_prep.add_run(f"Prepared by: {prepared_by}")
    r_prep.font.name = "Arial"
    r_prep.font.size = Pt(11)
    r_prep.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    p_prep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_prep.paragraph_format.space_after = Pt(2)

    # 8) Page break to start body
    doc.add_page_break()
def add_chain_sms_section(doc):
    # Title
    title = doc.add_heading("About Chain SMS Campaigns", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle
    subtitle = doc.add_paragraph("Strategic, Timed Messaging for Better Engagement")
    subtitle.runs[0].bold = True
    subtitle.runs[0].italic = True

    # Definition
    doc.add_heading("Overview", level=2)
    paragraph = doc.add_paragraph()
    paragraph.add_run("Chain SMS campaigns consist of scheduled, multi-step messages targeting the ").bold = False
    paragraph.add_run("same audience").bold = True
    paragraph.add_run(". Each message is designed to inform, engage, or prompt action, making it ideal for phased communication strategies.").bold = False

    bitly_paragraph = doc.add_paragraph()
    bitly_paragraph.add_run(
        "Using Bitly-shortened links is highly recommended to boost engagement with landing pages, videos, or social posts."
    ).bold = True
    # Benefits
    doc.add_heading("Key Benefits", level=2)
    benefits = [
        "Stronger engagement over time",
        "Better message retention through repetition",
        "Ability to break down complex offers",
        "Guided recipient actions across messages",
        "Customized messaging by segment"
    ]
    for b in benefits:
        doc.add_paragraph(f"{b}", style="List Bullet")

    # Targeting
    doc.add_heading("Targeted Efficiency", level=2)
    doc.add_paragraph(
        "Effectiveness increases when using JorMall’s segmented database. Campaigns can be filtered by:"
    )
    filters = [
        "Region (e.g., governorate, city direction)",
        "Demographics (age, gender, income)",
        "Consumer behaviors (e.g., car ownership, family status)"
    ]
    for f in filters:
        doc.add_paragraph(f"{f}", style="List Bullet")

    # Results
    doc.add_heading("Expected Outcomes", level=2)
    outcomes = [
        "Higher engagement rates vs. single-message campaigns",
        "Greater recall and brand familiarity",
        "Stronger conversion with trackable links",
        "Clear performance tracking at each stage"
    ]
    for o in outcomes:
        doc.add_paragraph(f"{o}", style="List Bullet")

    # Closing
    doc.add_paragraph(
        "Chain SMS is a results-driven approach to structured outreach. When supported by targeted data, "
        "it becomes a powerful tool for measurable and sustained campaign success."
    )
   

def _parse_chain_datetime(date_value, time_value):
    """Parse common HTML/legacy date and time formats without failing document creation."""
    date_text = str(date_value or "").strip()
    time_text = str(time_value or "").strip()
    if not date_text:
        return None

    combined = f"{date_text} {time_text}".strip()
    formats = (
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M %p",
        "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %I:%M %p",
        "%d-%m-%Y %H:%M", "%d-%m-%Y %I:%M %p",
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _normalize_chain_summary_messages(chain_messages, chain_delivery_dates=None, chain_delivery_times=None):
    """Return canonical Chain SMS objects regardless of the JSON version used."""
    if not chain_messages:
        return []
    if isinstance(chain_messages, (str, dict)):
        chain_messages = [chain_messages]
    if not isinstance(chain_messages, list):
        chain_messages = list(chain_messages) if chain_messages else []

    dates = chain_delivery_dates if isinstance(chain_delivery_dates, list) else []
    times = chain_delivery_times if isinstance(chain_delivery_times, list) else []
    normalized = []
    for index, item in enumerate(chain_messages):
        fallback_date = dates[index] if index < len(dates) else ""
        fallback_time = times[index] if index < len(times) else ""
        if isinstance(item, dict):
            pitch = item.get("pitch") or item.get("message") or item.get("text") or ""
            date_value = item.get("date") or item.get("delivery_date") or fallback_date
            time_value = item.get("time") or item.get("delivery_time") or fallback_time
        else:
            pitch = str(item or "")
            date_value = fallback_date
            time_value = fallback_time
        normalized.append({
            "pitch": str(pitch or "").strip(),
            "date": str(date_value or "").strip(),
            "time": str(time_value or "").strip(),
            "datetime": _parse_chain_datetime(date_value, time_value),
            "order": index,
        })
    return normalized


def add_chain_summary(doc, title, chain_messages, chain_delivery_dates=None, chain_delivery_times=None):
    """Add a Chain SMS summary without assuming every message is a dictionary."""
    messages = _normalize_chain_summary_messages(
        chain_messages, chain_delivery_dates, chain_delivery_times
    )
    if not messages:
        return

    # Valid dated messages are sorted chronologically; undated messages keep input order.
    sorted_msgs = sorted(
        messages,
        key=lambda msg: (msg["datetime"] is None, msg["datetime"] or datetime.max, msg["order"]),
    )
    dated = [msg for msg in sorted_msgs if msg["datetime"] is not None]
    start_dt = dated[0]["datetime"] if dated else None
    end_dt = dated[-1]["datetime"] if dated else None

    add_colored_heading(doc, title)

    p = doc.add_paragraph()
    p.add_run("Campaign Duration: ").bold = True
    if start_dt and end_dt:
        duration_days = max((end_dt.date() - start_dt.date()).days + 1, 1)
        p.add_run(f"{duration_days} day" + ("s" if duration_days != 1 else ""))
    else:
        p.add_run("Not specified")

    p = doc.add_paragraph()
    p.add_run("Start Date: ").bold = True
    p.add_run(start_dt.strftime("%A, %B %d, %Y") if start_dt else "Not specified")

    p = doc.add_paragraph()
    p.add_run("End Date: ").bold = True
    p.add_run(end_dt.strftime("%A, %B %d, %Y") if end_dt else "Not specified")

    p = doc.add_paragraph()
    p.add_run("Campaign Type: ").bold = True
    p.add_run(f"Chain SMS ({len(sorted_msgs)} messages leading to action)")

    for i, msg in enumerate(sorted_msgs, start=1):
        dt = msg["datetime"]
        msg_title = doc.add_paragraph()
        msg_title.add_run(f"Message {i}").bold = True

        p = doc.add_paragraph(style="List Bullet")
        p.add_run("Date: ").bold = True
        p.add_run(dt.strftime("%A, %B %d, %Y") if dt else (msg["date"] or "Not specified"))

        p = doc.add_paragraph(style="List Bullet")
        p.add_run("Time: ").bold = True
        if dt and msg["time"]:
            p.add_run(dt.strftime("%I:%M %p").lstrip("0"))
        else:
            p.add_run(msg["time"] or "Not specified")


rendered_messages = set()

def add_chain_message_page(doc, message_index, pitch, delivery_date, delivery_time):
    """
    Adds a new page with the message title and delivery date (centered, bold, blue).
    Runs only once per message.
    """
    if not message_index or (message_index in rendered_messages):
        return

    rendered_messages.add(message_index)

    # Extract the pitch safely. Chain generators store it as a string, while
    # some legacy JSON files store an object. Both shapes are valid.
    if isinstance(pitch, dict):
        pitch_title = pitch.get('pitch') or pitch.get('message') or pitch.get('text') or ''
    else:
        pitch_title = str(pitch or '')
    delivery_date_text = f"Delivery Date: {delivery_date}" if delivery_date else ""
    delivery_time_text = f"Delivery Time: {delivery_time}" if delivery_time else ""
    # Add new page
    doc.add_page_break()

    # Add message title
    title_paragraph = doc.add_paragraph()
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_paragraph.add_run(f"Message {message_index}")
    title_run.bold = True
    title_run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)

    # Add message pitch
    pitch_paragraph = doc.add_paragraph()
    pitch_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pitch_run = pitch_paragraph.add_run(f"Message Pitch: {pitch_title}")
    pitch_run.bold = True
    pitch_run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)
    
    # Add delivery date (if available)
    if delivery_date_text:
        date_paragraph = doc.add_paragraph()
        date_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_run = date_paragraph.add_run(delivery_date_text)
        date_run.bold = True
        date_run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)
        
    # Add delivery date (if available)
    if delivery_time_text:
        date_paragraph = doc.add_paragraph()
        date_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_run = date_paragraph.add_run(delivery_time_text)
        date_run.bold = True
        date_run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)

def add_premium_sms_section(doc):
    # Title
    title = doc.add_heading("About Premium SMS Campaigns", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle
    subtitle = doc.add_paragraph("Multi-Channel Creativity for Maximum Impact")
    subtitle.runs[0].bold = True
    subtitle.runs[0].italic = True

    # Definition
    doc.add_heading("Overview", level=2)
    doc.add_paragraph(
        """A Premium SMS campaign is an integrated solution provided by JorMall, enabling customers to execute highly effective and impactful campaigns with creative, multi-platform elements. It emphasizes maintaining a consistent "one-look" identity across all channels, ensuring stronger brand recognition and seamless customer experiences."""        
    )

    # Components Included
    doc.add_heading("Included Creative Elements", level=2)
    components = [
        "Engaging SMS text suggestions (Arabic & English) with a landing page design.",
        "Radio commercial scripts for quick audio broadcast.",
        "Visual design and captions for Facebook, Instagram, etc.",
        "Visual design previews for billboards.",
        "Visual graphic video for social media  reels, stories, and ads."
        ]
    for c in components:
        doc.add_paragraph(f"{c}", style="List Bullet")

    # Benefits
    doc.add_heading("Key Benefits", level=2)
    benefits = [
        "Premium branding and message consistency across channels",
        "Higher recall and stronger emotional impact",
        "Ready-to-use materials save time and cost"
        ]
    for b in benefits:
        doc.add_paragraph(f"{b}", style="List Bullet")

    # Targeting
    doc.add_heading("Smart Targeting with Rich Messaging", level=2)
    doc.add_paragraph(
        "When paired with JorMall’s audience segmentation, Premium Campaigns are even more effective. "
        "Messages and visuals can be tailored by:"
    )
    filters = [
        "Location (governorate, Amman direction)",
        "Demographics (age group, income, gender)",
        "Lifestyle segments (luxury buyers, families, youth, etc.)"
    ]
    for f in filters:
        doc.add_paragraph(f"{f}", style="List Bullet")


    # Closing
    doc.add_paragraph(
        "Premium SMS Campaigns are ideal for brands looking to make a statement. With creative assets designed for immediate use and customization, "
        "these campaigns offer a powerful way to drive attention, boost response, and elevate brand presence across all channels."
    )
def add_premium_intro_paragraph(doc, header):
    # Define mapping of headers to intro content
    intro_mapping = {
        "Arabic SMS Suggestions (Formal) – 126 Characters [2 Messages]": (
            "SMS Content",
            "Provided below are 3 tailored SMS suggestions in both Arabic and English. "
            "JorMall will also deliver a landing page design to complement these messages "
            "and ensure a unified campaign experience."
        ),
        "Social Media Caption (English)": (
            "Social Media Content",
            "Provided below is a creative caption suggestion tailored for social media platforms. "
            "JorMall will also adapt the landing page design from the SMS campaign to fit social media formats "
            "and create a short 15 seconds promotional video to enhance engagement."
        ),
        "Radio Announcement Script (English)": (
            "On-street Platforms",
            "This campaign extends its reach through impactful on-street platforms, including billboard designs and radio scripts "
            "in both Arabic and English. The billboard visuals will align with the campaign’s identity, while the radio scripts—offered in both "
            "dialogue and one-way formats—are crafted to capture attention and drive immediate action."
        )
    }

    # Check if header is in mapping
    if header in intro_mapping:
        doc.add_page_break()
        intro_header, intro_paragraph = intro_mapping[header]
        # Add blue bold heading
        p = doc.add_paragraph()
        run = p.add_run(intro_header)
        run.bold = True
        run.font.size = Pt(13)
        run.font.color.rgb = RGBColor(0x25, 0x75, 0xB6)  # Blue (#2575b6)
        # Add intro paragraph
        add_wrapped_paragraph(doc, intro_paragraph)



def add_optin_sms_section(doc):
    # Title
    title = doc.add_heading("About Opt-in/Opt-out Messages", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle
    subtitle = doc.add_paragraph("Consent-Driven Messaging for Trust and Compliance")
    subtitle.runs[0].bold = True
    subtitle.runs[0].italic = True

    # Overview
    doc.add_heading("Overview", level=2)
    doc.add_paragraph(
        "Opt-in/Opt-out SMS messages are used to clearly inform recipients that they are receiving SMS messages from a specific company "
        "and provide them with the option to stay subscribed or exit the list. These messages are essential for maintaining transparency, "
        "enhancing trust, and respecting user preferences in addition to compliance with TRC rules."
    )
    doc.add_paragraph(
        "Using Bitly links in opt-in messages helps track interest while remaining compliant, enabling insights without breaching privacy."
    )
     # Logging and Compliance Note
    doc.add_paragraph(
        "All sending and reply records will be stored by JorMall for future references."
    )
    # Key Benefits
    doc.add_heading("Key Benefits", level=2)
    benefits = [
        "Fulfills TRC compliance by offering opt-out instructions",
        "Improves brand credibility and consumer trust",
        "Strengthens data collection through informed consent",
        "Reduces future complaints and opt-out spam flags",
        "Enables segmentation of truly interested users"
    ]
    for b in benefits:
        doc.add_paragraph(f"{b}", style="List Bullet")

    # Expected Outcomes
    doc.add_heading("Expected Outcomes", level=2)
    outcomes = [
        "Clean and responsive SMS subscriber lists",
        "Higher return on future campaign efforts",
        "Reduced risk of regulatory violations",
        "Improved customer experience and brand alignment"
    ]
    for o in outcomes:
        doc.add_paragraph(f"{o}", style="List Bullet")

    # Final Paragraph
    doc.add_paragraph(
        "Opt-in messages aren’t just a compliance requirement — they’re a trust-building strategy. "
        "When recipients choose to stay, your future campaigns become more targeted, efficient, and respectful of user preferences."
    )


def add_personalized_sms_section(doc):
    # Title
    title = doc.add_heading("About Personalized SMS Messages", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle
    subtitle = doc.add_paragraph("Direct, Name-Based Messaging for Stronger Engagement")
    subtitle.runs[0].bold = True
    subtitle.runs[0].italic = True

    # Overview
    doc.add_heading("Overview", level=2)
    doc.add_paragraph(
        'Personalized SMS campaigns address each recipient by name, using introductions like '
        '"Dear [Name]" to create a direct, one-to-one connection. This approach significantly improves the '
        'emotional response and attention rate of the recipient, making the message feel relevant and important.'
    )

    bitly_paragraph = doc.add_paragraph()
    bitly_paragraph.add_run(
        "These personalized messages are available exclusively as long-format SMS — up to 126 characters in Arabic and 160 characters in English."
    ).bold = True

    # Key Benefits
    doc.add_heading("Key Benefits", level=2)
    benefits = [
        "Boosts response by directly addressing the recipient by name",
        "Creates a human, respectful tone that enhances brand trust",
        "Increases open and read rates compared to generic messages",
        "Helps build loyalty and a premium customer experience",
        "Reinforces data quality through accurate name usage"
    ]
    for b in benefits:
        doc.add_paragraph(f"{b}", style="List Bullet")

    # Smart Use and Delivery
    doc.add_heading("Smart Use and Delivery", level=2)
    doc.add_paragraph(
        "This feature is only available for databases that contain reliable first-name data. Personalized campaigns are most effective when paired with:"
    )
    usage = [
        "High-value offers or loyalty messages",
        "Appointment reminders or private invitations",
        "VIP access campaigns or customer service follow-ups"
    ]
    for u in usage:
        doc.add_paragraph(f"{u}", style="List Bullet")

    # Segmentation and Customization
    doc.add_heading("Segmentation and Customization", level=2)
    doc.add_paragraph("Personalized SMS campaigns work best when targeted by:")
    segments = [
        "Full name with known gender (to tailor tone)",
        "Customer status (new, returning, VIP)",
        "Product history or past engagement"
    ]
    for s in segments:
        doc.add_paragraph(f"{s}", style="List Bullet")

    # Expected Outcomes
    doc.add_heading("Expected Outcomes", level=2)
    outcomes = [
        "Higher engagement and click-through rates",
        "Improved perception of brand professionalism",
        "Lower opt-out and complaint rates",
        "Positive emotional resonance with recipients"
    ]
    for o in outcomes:
        doc.add_paragraph(f"{o}", style="List Bullet")

    # Closing Paragraph
    doc.add_paragraph(
        "Personalization is not just a feature — it’s a commitment to relevance. With JorMall’s support, "
        "clients can reach people by name, with the tone and content that matters most — in full compliance with format and delivery limits."
    )

def add_lead_sms_section(doc):
    # Title
    title = doc.add_heading("About Lead SMS Messages", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Subtitle
    subtitle = doc.add_paragraph("Click-Based Tracking for Lead Identification")
    subtitle.runs[0].bold = True
    subtitle.runs[0].italic = True

    # Overview
    doc.add_heading("Overview", level=2)
    doc.add_paragraph(
        "Lead SMS campaigns are designed to identify and qualify interested recipients by embedding unique Bitly links for each phone number. "
        "When a user clicks the link, the system instantly associates that interest with their number — providing real-time lead intelligence without requiring replies or forms."
    )

    bitly_paragraph = doc.add_paragraph()
    bitly_paragraph.add_run(
        "Each SMS contains a unique Bitly link tied to the recipient’s number, enabling precise tracking of interest per user."
    ).bold = True

    # Key Benefits
    doc.add_heading("Key Benefits", level=2)
    benefits = [
        "Instantly identifies who is interested in the offer",
        "Eliminates guesswork and improves targeting precision",
        "No need for customer replies or form submissions",
        "Enables real-time feedback for sales follow-up",
        "Tracks conversion funnels by recipient behavior"
    ]
    for b in benefits:
        doc.add_paragraph(f"{b}", style="List Bullet")

    # Use Cases
    doc.add_heading("Ideal Use Cases", level=2)
    use_cases = [
        "Product launch interest tracking",
        "Event invitation confirmations",
        "Discount or limited-time offer engagement",
        "Follow-up campaigns to warm leads"
    ]
    for u in use_cases:
        doc.add_paragraph(f"{u}", style="List Bullet")

    # Integration
    doc.add_heading("Smart Integration with JorMall Tools", level=2)
    doc.add_paragraph(
        "Lead SMS is most effective when paired with JorMall's dashboards and follow-up systems. "
        "Collected clicks can trigger alerts, custom replies, or personalized re-targeting campaigns."
    )

    # Expected Outcomes
    doc.add_heading("Expected Outcomes", level=2)
    outcomes = [
        "Accurate measurement of campaign engagement",
        "Smaller, high-quality follow-up lists",
        "Shorter lead qualification time",
        "Better ROI through focused communication"
    ]
    for o in outcomes:
        doc.add_paragraph(f"{o}", style="List Bullet")

    # Closing
    doc.add_paragraph(
        "Lead SMS is a smart, silent way to know who’s listening. By tracking clicks tied to each phone number, "
        "you turn anonymous broadcasts into traceable interest — without requiring a single word in return."
    )



def add_jormall_sms_services_section(doc):
    """Insert a styled JorMall SMS Services section into an existing docx.Document"""

    # Intro paragraph
    intro = doc.add_paragraph(
        "JorMall is Jordan's leading provider of Bulk SMS solutions, serving diverse sectors including "
        "retail, automotive, healthcare, banking, government, and telecommunications. "
        "With over two decades of proven expertise, JorMall specializes in delivering high-quality, "
        "targeted SMS campaigns tailored to each client’s unique business needs."
    )
    intro.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    intro.paragraph_format.line_spacing = 1.5
    intro.runs[0].font.size = Pt(11)

    # Section Header
    p_head = doc.add_paragraph()
    p_head.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    p_head.paragraph_format.line_spacing = 1.5
    head = p_head.add_run("Our SMS services offer:")
    head.bold = True
    head.font.size = Pt(11)

    # Services list
    services = {
        "Reliable Delivery": "Ensuring rapid and guaranteed delivery rates through direct connections with major telecom operators in Jordan.",
        "Advanced Targeting": "Utilizing comprehensive databases of over 7.5 million segmented profiles, allowing precise targeting based on demographics, location, interests, and purchasing behavior.",
        "Customized Campaigns": "Providing multilingual SMS content (Arabic and English) crafted to enhance customer engagement, brand loyalty, and conversion rates.",
        "Real-Time Reporting": "Access detailed analytics, performance metrics, and tracking capabilities, enabling clients to measure campaign effectiveness instantly.",
        "Regulatory Compliance": "Adhering strictly to all Jordanian Telecommunications Regulatory Commission (TRC) guidelines, ensuring your campaigns are fully compliant and professionally managed.",
        "Customer Support": "Dedicated support team available to assist with campaign setup, optimization, and ongoing management.",
    }

    for header, text in services.items():
        p = doc.add_paragraph(style="List Bullet")
        p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.space_after = Pt(3)

        run_header = p.add_run(header + ": ")
        run_header.bold = True
        run_header.font.name = "Arial"
        run_header.font.size = Pt(11)

        run_text = p.add_run(text)
        run_text.font.name = "Arial"
        run_text.font.size = Pt(11)

    # Closing
    closing = doc.add_paragraph(
        "By choosing JorMall SMS service, businesses enhance their customer communication capabilities, "
        "achieve greater market penetration, and drive measurable results through strategic SMS marketing."
    )
    closing.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
    closing.paragraph_format.line_spacing = 1.5
    closing.runs[0].bold = True
    closing.runs[0].font.size = Pt(11)

    return doc

def add_jormall_ai_products_section(doc):
    """Insert a concise JorMall AI Products overview for generated AI product documents."""
    intro = doc.add_paragraph(
        "JorMall AI Products turn approved company information into focused customer-facing assistants designed for a specific business objective. "
        "The product is configured around the client's approved content, expected customer questions, and the action the company wants the customer to complete."
    )
    _format_english_paragraph(intro, space_after=8)

    p_head = doc.add_paragraph()
    _format_english_paragraph(p_head, space_after=5, keep_with_next=True)
    run = p_head.add_run("Current AI product options:")
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(11)

    products = {
        "Reservation Chatbot": "A booking-focused assistant that answers approved service and appointment questions, guides booking requests, and hands off cases that require staff action.",
        "Campaign Chatbot": "A focused assistant for one campaign, offer, event, or service launch that answers campaign-approved questions and directs customers to the intended campaign action.",
        "Grounded Content": "Responses are based on client-approved information. Missing or sensitive details should be handled through an approved human or official channel rather than guessed.",
        "Arabic and English": "Documents and customer experiences can be prepared around the approved language requirements of the project.",
        "Continuous Improvement": "Conversation questions and gaps can be reviewed to identify where the approved knowledge base needs refinement."
    }
    for title, text in products.items():
        p = doc.add_paragraph(style="List Bullet")
        _format_english_paragraph(p, space_after=3)
        p.paragraph_format.left_indent = Inches(0.28)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        r1 = p.add_run(title + ": ")
        r1.bold = True
        r1.font.name = "Arial"
        r1.font.size = Pt(11)
        r2 = p.add_run(text)
        r2.font.name = "Arial"
        r2.font.size = Pt(11)

    closing = doc.add_paragraph(
        "Each AI product should be launched only after the client approves the knowledge, customer journey, handoff rules, and any links or forms used by the assistant."
    )
    _format_english_paragraph(closing, space_after=5)
    if closing.runs:
        closing.runs[0].bold = True
    return doc


def add_seasonal_sms_calendar(doc):
    # ===== Title =====
    title = doc.add_heading("Seasonal SMS Calendar (Jordan) – 2026/2027", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # ===== Intro (generalized) =====
    intro = doc.add_paragraph(
        "Key national, cultural, and seasonal moments mapped to each month for planning SMS campaigns."
    )
    intro.runs[0].italic = True

    # ===== Table summary only =====
    doc.add_heading("Monthly Occasions Summary (2026/2027)", level=2)
    table = doc.add_table(rows=1, cols=2)
    try:
        table.style = "Light List Accent 1"
    except Exception:
        pass

    # Header
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Month"
    hdr_cells[1].text = "Primary Occasion / Theme"

    # Table items
    items = [
        ("January", "New Year Greetings & Special Announcements"),
        ("February", "Valentine’s Day Engagements"),
        ("March", "Mother’s Day (March 21), Spring Kick-off, Ramadan & Eid al-Fitr (dates vary annually)"),
        ("April", "Spring Campaigns & Community Events"),
        ("May", "Independence Day (May 25), Eid al-Adha (dates vary annually)"),
        ("June", "Summer Engagement Campaigns"),
        ("July", "Mid-Year Highlights & Announcements"),
        ("August", "Back to School (Education, Finance, Family Focus); Prophet’s Birthday (Mawlid)"),
        ("September", "Autumn Launches & Community Programs"),
        ("October", "Pre-Winter Announcements"),
        ("November", "Black Friday & Early Winter Initiatives"),
        ("December", "Christmas & End-of-Year Reflections"),
    ]

    for month, occasion in items:
        row_cells = table.add_row().cells
        row_cells[0].text = month
        row_cells[1].text = occasion

    # ===== Movable Islamic occasions note (covers Eid al-Adha & Prophet’s Birthday) =====
    note = doc.add_paragraph()
    run = note.add_run(
        "Movable Islamic Occasions (Hijri calendar — verify dates each year): "
        "Ramadan, Eid al-Fitr, Eid al-Adha, and Prophet Muhammad’s Birthday (Mawlid)."
    )
    run.italic = True

    # ===== Closing line =====
    doc.add_paragraph(
        "Campaigns should be tailored to Islamic holiday periods, national events, "
        "local community activities, and specific organization objectives."
    )
    # Page break (optional)
    doc.add_page_break()

# --- Utility: Detect Arabic ---
def is_arabic(text):
    return any('\u0600' <= c <= '\u06FF' for c in text), text

# --- Utility: Set language tags ---
def set_run_language(run, lang_code):
    rPr = run._element.get_or_add_rPr()
    for el in rPr.findall('.//w:lang', namespaces={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}):
        rPr.remove(el)
    lang = OxmlElement('w:lang')
    lang.set(qn('w:val'), lang_code)
    rPr.append(lang)

def set_paragraph_language(paragraph, lang_code):
    pPr = paragraph._element.get_or_add_pPr()
    for el in pPr.findall('.//w:lang', namespaces={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}):
        pPr.remove(el)
    lang_tag = OxmlElement('w:lang')
    lang_tag.set(qn('w:val'), lang_code)
    lang_tag.set(qn('w:eastAsia'), lang_code)
    lang_tag.set(qn('w:bidi'), lang_code)
    pPr.append(lang_tag)

# --- Markdown-style formatting processor ---
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")


def _set_run_direction(run, rtl=False):
    """Set run-level bidi without changing the paragraph direction."""
    rPr = run._element.get_or_add_rPr()
    for tag_name in ("rtl",):
        for el in rPr.findall(f'.//w:{tag_name}', namespaces={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}):
            rPr.remove(el)
    if rtl:
        rtl_el = OxmlElement('w:rtl')
        rtl_el.set(qn('w:val'), '1')
        rPr.append(rtl_el)


def _add_directional_text_run(paragraph, text, *, bold=False, italic=False):
    """Add text as LTR/RTL runs while keeping English documents left aligned."""
    if not text:
        return
    # Split on Arabic vs non-Arabic spans. This prevents one Arabic phrase from
    # flipping an otherwise English paragraph to RTL.
    spans = re.split(r'([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF][\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\s\u064B-\u065F\u0670\u06D6-\u06ED،؛؟٪0-9%.,!?:()\-–—\'\"]*)', text)
    for span in spans:
        if not span:
            continue
        rtl = bool(_ARABIC_CHAR_RE.search(span))
        run = paragraph.add_run(span)
        run.bold = bold
        run.italic = italic
        run.font.name = 'Arial'
        run.font.size = Pt(11)
        set_run_language(run, 'ar' if rtl else 'en-US')
        _set_run_direction(run, rtl=rtl)


def _add_inline_markdown(paragraph, text):
    """Render **bold** and *italic* without leaking Markdown markers."""
    # Supports the simple Markdown emitted by the application's prompts.
    tokens = re.split(r'(\*\*.+?\*\*|(?<!\*)\*[^*]+?\*(?!\*))', str(text or ''))
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            _add_directional_text_run(paragraph, token[2:-2], bold=True)
        elif token.startswith('*') and token.endswith('*'):
            _add_directional_text_run(paragraph, token[1:-1], italic=True)
        else:
            _add_directional_text_run(paragraph, token)


def process_italic_and_bold(para):
    """Backward-compatible inline Markdown cleanup for existing callers."""
    new_text = "".join(run.text for run in para.runs)
    para.clear()
    _add_inline_markdown(para, new_text)


def _format_english_paragraph(paragraph, *, left_indent=0, first_line_indent=0, space_after=5, keep_with_next=False):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = paragraph.paragraph_format
    pf.left_indent = Inches(left_indent) if left_indent else None
    pf.first_line_indent = Inches(first_line_indent) if first_line_indent else None
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.line_spacing = 1.15
    pf.keep_with_next = keep_with_next
    set_paragraph_language(paragraph, 'en-US')
    # Explicitly remove paragraph-level RTL if it was inherited/copied.
    pPr = paragraph._element.get_or_add_pPr()
    for rtl in pPr.findall('.//w:rtl', namespaces={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}):
        pPr.remove(rtl)


def _add_english_subheading(doc, text, level=2):
    p = doc.add_paragraph()
    _format_english_paragraph(p, space_after=5, keep_with_next=True)
    p.paragraph_format.space_before = Pt(7 if level <= 2 else 4)
    r = p.add_run(text.strip())
    r.font.name = 'Arial'
    r.bold = True
    r.font.size = Pt(12 if level <= 2 else 11)
    r.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6) if level <= 2 else RGBColor(0x33, 0x33, 0x33)
    set_run_language(r, 'en-US')
    return p


def _add_english_bullet(doc, text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    _format_english_paragraph(p, space_after=3)
    # Use consistent compact hanging indents instead of raw hyphens.
    left = 0.28 + (0.24 * max(0, level))
    p.paragraph_format.left_indent = Inches(left)
    p.paragraph_format.first_line_indent = Inches(-0.18)
    _add_inline_markdown(p, text.strip())
    return p


def _add_english_numbered_item(doc, number, text, level=0):
    p = doc.add_paragraph()
    _format_english_paragraph(p, space_after=5)
    left = 0.02 + (0.24 * max(0, level))
    p.paragraph_format.left_indent = Inches(left)
    p.paragraph_format.first_line_indent = Inches(0)
    r = p.add_run(f'{number}. ')
    r.bold = True
    r.font.name = 'Arial'
    r.font.size = Pt(11)
    set_run_language(r, 'en-US')
    _add_inline_markdown(p, text.strip())
    return p


# --- Markdown table formatter ---
def add_markdown_table(doc, markdown_table_text):
    lines = [line.strip() for line in str(markdown_table_text or '').strip().splitlines() if '|' in line]
    if len(lines) < 2:
        add_wrapped_paragraph(doc, markdown_table_text)
        return

    header_cells = [cell.strip() for cell in lines[0].strip('|').split('|')]
    table = doc.add_table(rows=1, cols=len(header_cells))
    table.alignment = 0  # left
    try:
        table.style = 'Light Shading Accent 1'
    except Exception:
        pass

    hdr_cells = table.rows[0].cells
    for i, text in enumerate(header_cells):
        hdr_cells[i].text = ''
        p = hdr_cells[i].paragraphs[0]
        _format_english_paragraph(p, space_after=0)
        r = p.add_run(re.sub(r'\*\*', '', text))
        r.bold = True
        r.font.name = 'Arial'
        r.font.size = Pt(10.5)

    for line in lines[2:]:
        if re.match(r'^\s*\|?\s*:?-{3,}', line):
            continue
        values = [cell.strip() for cell in line.strip('|').split('|')]
        row = table.add_row().cells
        for i in range(len(header_cells)):
            text = values[i] if i < len(values) else ''
            row[i].text = ''
            p = row[i].paragraphs[0]
            _format_english_paragraph(p, space_after=0)
            _add_inline_markdown(p, text)

    # Small breathing room after tables.
    spacer = doc.add_paragraph()
    _format_english_paragraph(spacer, space_after=3)


# --- English document body renderer ---
def add_wrapped_paragraph(doc, text):
    """
    Render model output into clean English DOCX paragraphs.

    Important: an English document remains LTR/left-aligned even if individual
    lines contain Arabic translations. Arabic is handled at run level only.
    """
    raw = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    lines = raw.split('\n')
    pending_blank = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            pending_blank = True
            continue

        # Markdown headings: remove visible # markers and style them properly.
        m_heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if m_heading:
            level = len(m_heading.group(1))
            _add_english_subheading(doc, m_heading.group(2), level=level)
            pending_blank = False
            continue

        # Markdown/list bullets, including nested "Example" / "Description" items.
        m_bullet = re.match(r'^(\s*)[-*•]\s+(.+)$', line)
        if m_bullet:
            leading = len(m_bullet.group(1).replace('\t', '    '))
            level = 1 if leading >= 1 else 0
            _add_english_bullet(doc, m_bullet.group(2), level=level)
            pending_blank = False
            continue

        # Numbered sections remain explicit and consistently left aligned.
        m_num = re.match(r'^(\s*)(\d+)[.)]\s+(.+)$', line)
        if m_num:
            leading = len(m_num.group(1).replace('\t', '    '))
            level = 1 if leading >= 2 else 0
            _add_english_numbered_item(doc, m_num.group(2), m_num.group(3), level=level)
            pending_blank = False
            continue

        p = doc.add_paragraph()
        _format_english_paragraph(p, space_after=7 if pending_blank else 5)
        _add_inline_markdown(p, stripped)
        pending_blank = False

# --- SMS Formatters (placeholders) ---
# --- Style and layout ---
def add_colored_heading(doc, title):
    p = doc.add_paragraph()
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(13)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True

    rPr = run._element.get_or_add_rPr()
    color = OxmlElement('w:color')
    color.set(qn('w:val'), 'FFFFFF')
    rPr.append(color)

    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), 'Arial')
    rFonts.set(qn('w:hAnsi'), 'Arial')
    rFonts.set(qn('w:eastAsia'), 'Arial')
    rFonts.set(qn('w:cs'), 'Arial')
    rPr.append(rFonts)

    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '26')
    rPr.append(sz)

    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), '2E75B6')
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




# =====================================================================
# FINAL DOCUMENT ALIGNMENT NORMALIZATION
# English generated documents must remain physically LTR/LEFT aligned.
# Intentionally centered cover-page/footer elements are preserved.
# Arabic text inside an English document stays readable through run-level
# direction, but it does not flip the paragraph or document to the right.
# =====================================================================
def _force_final_english_left_alignment(document):
    def _set_style_left(style_name):
        try:
            style = document.styles[style_name]
            pPr = style.element.get_or_add_pPr()
            for child in list(pPr):
                if child.tag in {qn('w:jc'), qn('w:bidi'), qn('w:rtl')}:
                    pPr.remove(child)
            bidi = OxmlElement('w:bidi')
            bidi.set(qn('w:val'), '0')
            pPr.append(bidi)
            jc = OxmlElement('w:jc')
            jc.set(qn('w:val'), 'left')
            pPr.append(jc)
        except Exception:
            pass

    for style_name in ('Normal', 'List Bullet', 'List Number', 'Heading 1', 'Heading 2', 'Heading 3'):
        _set_style_left(style_name)

    def _force_paragraph(paragraph):
        has_text = any((run.text or '').strip() for run in paragraph.runs)
        if not has_text:
            return

        # Covers, deliberate title blocks and footers may stay centered.
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER:
            return

        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pPr = paragraph._element.get_or_add_pPr()
        for child in list(pPr):
            if child.tag in {qn('w:jc'), qn('w:bidi'), qn('w:rtl')}:
                pPr.remove(child)
        bidi = OxmlElement('w:bidi')
        bidi.set(qn('w:val'), '0')
        pPr.append(bidi)
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), 'left')
        pPr.append(jc)
        try:
            set_paragraph_language(paragraph, 'en-US')
        except Exception:
            pass

    for paragraph in document.paragraphs:
        _force_paragraph(paragraph)

    for table in document.tables:
        try:
            table.alignment = 0  # LEFT
            tblPr = table._tbl.tblPr
            bidi = tblPr.find(qn('w:bidiVisual'))
            if bidi is not None:
                tblPr.remove(bidi)
        except Exception:
            pass
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _force_paragraph(paragraph)

    for section in document.sections:
        # An English document should never inherit a section-level RTL direction.
        try:
            sectPr = section._sectPr
            for child in list(sectPr):
                if child.tag == qn('w:textDirection'):
                    sectPr.remove(child)
        except Exception:
            pass
        for paragraph in section.header.paragraphs:
            _force_paragraph(paragraph)
        for paragraph in section.footer.paragraphs:
            _force_paragraph(paragraph)
        for table in section.header.tables:
            try:
                table.alignment = 0
            except Exception:
                pass
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _force_paragraph(paragraph)
        for table in section.footer.tables:
            try:
                table.alignment = 0
            except Exception:
                pass
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        _force_paragraph(paragraph)



def _last_paragraph_has_page_break_en(doc):
    if not doc.paragraphs:
        return False
    for br in doc.paragraphs[-1]._p.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False

def _remove_trailing_page_break_only_paragraphs_en(doc):
    """Remove redundant page-break-only paragraphs before a pageBreakBefore title.

    A standalone break can be pushed onto the next page when the previous page is full,
    creating an accidental blank page. The title-level page break is layout-safe.
    """
    while doc.paragraphs:
        p = doc.paragraphs[-1]
        text = ''.join(r.text or '' for r in p.runs).strip()
        has_page_break = any(br.get(qn("w:type")) == "page" for br in p._p.iter(qn("w:br")))
        if text or not has_page_break:
            break
        p._element.getparent().remove(p._element)

def _add_major_report_title_en(doc, title):
    _remove_trailing_page_break_only_paragraphs_en(doc)
    p = doc.add_heading(title, 0)
    p.paragraph_format.page_break_before = True
    p.paragraph_format.keep_with_next = True
    return p

# --- Main document generator ---
def generate_ai_docx(campaign_id, json_path, numbered_sms=False):
    # This set is module-global for helper compatibility; clear it for every new
    # document so one request cannot suppress pages in a later campaign.
    rendered_messages.clear()
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
    platform_benefits=data.get('platform_benefits', False)
    ai_product=data.get('ai_product', False)
    safe_company = re.sub(r'[\/:*?"<>|]+', '-', str(company_name)).strip() or 'JorMall'
    if company_profile:
        output_path = os.path.join(EXPORT_DIR, f"{safe_company} - JorMall Profile Report.docx")
    elif marketing_plan:
        output_path = os.path.join(EXPORT_DIR, f"{safe_company} - JorMall Marketing Plan.docx")
    elif platform_benefits:
        output_path = os.path.join(EXPORT_DIR, f"{safe_company} - JorMall Platform Benefits.docx")
    elif ai_product:
        product_type = str(data.get('ai_product_type', '')).strip()
        product_label = 'Reservation Chatbot' if product_type == 'reservation_chatbot' else 'Campaign Chatbot'
        output_path = os.path.join(EXPORT_DIR, f"{safe_company} - JorMall {product_label}.docx")
    else:
        campaign_company = safe_company[:-7] if safe_company.lower().endswith(" jordan") else safe_company
        output_path = os.path.join(EXPORT_DIR, f"{campaign_company} - JorMall SMS.docx")
    doc = Document()
    normal_style = doc.styles['Normal']
    font = normal_style.font
    font.name = 'Arial'
    font.size = Pt(11)
    normal_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.space_after = Pt(5)
    core_props = doc.core_properties
    core_props.author = "Central E-Commerce Ltd. (JorMall)"
    core_props.last_modified_by = "Central E-Commerce Ltd. (JorMall)"
    core_props.title = ""
    core_props.subject = ""
    core_props.comments = ""
    if company_profile==False and marketing_plan==False and platform_benefits==False and ai_product==False:
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
            _add_major_report_title_en(doc, "SMS Marketing Campaign Report")
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
            paragraph.add_run("[Logo missing]").bold = True
    elif company_profile:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        add_sales_profile_cover_page(
            doc,
            logo_path = os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name,
            profile_title="Profile Report"
        )
    elif marketing_plan:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        add_marketing_plan_cover_page(
            doc,
            logo_path=os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name
        )
    elif platform_benefits:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        industry = str(data.get("industry", "")).strip()
        tagline = "JorMall SMS solutions tailored to your industry."
        if industry:
            tagline = f"JorMall SMS solutions tailored to the {industry} industry."
        add_marketing_plan_cover_page(
            doc,
            logo_path=os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name,
            profile_title="Platform Benefits",
            tagline=tagline,
        )
    elif ai_product:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        product_type = str(data.get('ai_product_type', '')).strip()
        product_label = 'Reservation Chatbot' if product_type == 'reservation_chatbot' else 'Campaign Chatbot'
        tagline = (
            'AI-guided customer conversations designed to support booking requests.'
            if product_type == 'reservation_chatbot'
            else 'A focused AI assistant for one campaign, offer, event, or service launch.'
        )
        add_marketing_plan_cover_page(
            doc,
            logo_path=os.path.join(BASE_DIR, "assets", "images", "logo_25.png"),
            prospect_name=company_name,
            profile_title=product_label,
            tagline=tagline,
        )
    else:
        pass

    raw_analysis = data.get("analysis", {})
    if isinstance(raw_analysis, str):
        try:
            raw_analysis = json.loads(raw_analysis)
        except (json.JSONDecodeError, TypeError):
            raw_analysis = {"Campaign Analysis": raw_analysis}
    if isinstance(raw_analysis, list):
        raw_analysis = {f"Section {i}": item for i, item in enumerate(raw_analysis, start=1)}
    if not isinstance(raw_analysis, dict):
        raw_analysis = {"Campaign Analysis": str(raw_analysis or "")}

    for key, content in raw_analysis.items():
        if isinstance(content, str):
            content = {"header": str(key), "answer": content}
        elif not isinstance(content, dict):
            content = {"header": str(key), "answer": str(content or "")}

        header = content.get("header", "")
        answer = content.get("answer", "")
        message_index = content.get("message_index", "")
        pitch = content.get("pitch")
        delivery_date = content.get("delivery_date", datetime.today().strftime("%A, %d %B %Y"))
        delivery_time = content.get("delivery_time", "00:00")

        if sms_type == "premium":
            add_premium_intro_paragraph(doc, header)

        if sms_type == "chain":
            add_chain_message_page(doc, message_index, pitch, delivery_date, delivery_time)
            if header=="Target Audience":
                chain_messages = data.get("chain_messages", [])
                add_chain_summary(doc, "Chain SMS Campaign Summary", chain_messages, data.get("chain_delivery_dates", []), data.get("chain_delivery_times", []))
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
    if ai_product:
        add_colored_heading(doc, "About JorMall AI Products")
        add_jormall_ai_products_section(doc)
    else:
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
        _force_final_english_left_alignment(doc)
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
