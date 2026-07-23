from __future__ import annotations

import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Optional, Union

from compliance_engine import ComplianceReport, Criterion, Gap


def md_to_html(md_text: str) -> str:
    import markdown2
    return markdown2.markdown(md_text, extras=["tables"])


def generate_html(report: ComplianceReport) -> str:
    html_commentary = md_to_html(report.commentary)
    total_count = len(report.criteria)
    compliant_count = sum(1 for c in report.criteria if c.status == "compliant")
    partial_count = sum(1 for c in report.criteria if c.status == "partial")
    non_compliant_count = sum(1 for c in report.criteria if c.status == "non_compliant")
    not_checked_count = sum(1 for c in report.criteria if c.status == "not_checked")

    compliant_pct = (compliant_count / total_count * 100) if total_count else 0
    partial_pct = (partial_count / total_count * 100) if total_count else 0
    noncomp_pct = (non_compliant_count / total_count * 100) if total_count else 0
    unchecked_pct = (not_checked_count / total_count * 100) if total_count else 0

    score_tier = "strong"
    score_label = "Strong Compliance"
    score_color = "#10B981"
    if report.overall_score < 40:
        score_tier = "atrisk"
        score_label = "Action Required"
        score_color = "#F43F5E"
    elif report.overall_score < 70:
        score_tier = "conditional"
        score_label = "Gaps Remain"
        score_color = "#F59E0B"

    # Status pill rendering helper
    def status_pill(status: str) -> str:
        mapping = {
            "compliant": ("pill-compliant", "✔ Compliant"),
            "partial": ("pill-partial", "⚠ Partial"),
            "non_compliant": ("pill-noncompliant", "✘ Non-Compliant"),
            "not_checked": ("pill-unchecked", "🔍 Not Checked"),
        }
        cls, label = mapping.get(status.lower(), ("pill-unchecked", "🔍 Not Checked"))
        return f'<span class="pill {cls}">{label}</span>'

    # Severity tag helper
    def severity_tag(severity: str) -> str:
        sev = severity.lower()
        mapping = {
            "critical": ("tag-critical", "☢ Critical"),
            "high": ("tag-high", "⚠ High"),
            "medium": ("tag-medium", "✦ Medium"),
            "low": ("tag-low", "ℹ Low"),
        }
        cls, label = mapping.get(sev, ("tag-low", "ℹ Low"))
        return f'<span class="sev-tag {cls}">{label}</span>'

    # Build Gaps Register Rows
    gaps_cards = []
    for g in report.gaps:
        gaps_cards.append(f"""
        <div class="gap-card">
            <div class="gap-header">
                <span class="gap-id">{g.id}</span>
                {severity_tag(g.severity)}
                <span class="gap-link">Linked: {g.criterion_id}</span>
            </div>
            <div class="gap-body">
                {g.description}
            </div>
        </div>""")
    gaps_content = "\n".join(gaps_cards) if gaps_cards else '<div class="empty-state">No gaps identified during compliance check.</div>'

    # Build Criteria Registry Comparison Layout Rows
    criteria_cards = []
    for c in report.criteria:
        # Normalize fields
        rfp_clause = c.rfp_clause_num if c.rfp_clause_num != "N/A" else ""
        rfp_clause_disp = f"{rfp_clause} &middot; {c.rfp_clause_name}" if rfp_clause and c.rfp_clause_name != "N/A" else (rfp_clause or c.rfp_clause_name or "N/A")
        
        comp_disp = ""
        if c.status == "compliant" or c.status == "partial":
            comp_clause = c.comp_clause_num if c.comp_clause_num != "N/A" else ""
            comp_disp = f"{comp_clause} &middot; {c.comp_clause_name}" if comp_clause and c.comp_clause_name != "N/A" else (comp_clause or c.comp_clause_name or "Proposal Extract")
        
        evidence_html = ""
        if c.evidence:
            evidence_html = f"""
            <div class="evidence-quote-box">
                <div class="quote-header">COMPLIANCE EVIDENCE</div>
                <div class="quote-text">"{c.evidence}"</div>
            </div>"""

        notes_html = ""
        if c.notes:
            notes_html = f"""
            <div class="notes-box">
                <strong>Analysis Notes:</strong> {c.notes}
            </div>"""

        criteria_cards.append(f"""
        <div class="comparison-card status-{c.status.lower()}">
            <!-- Header Row -->
            <div class="card-header">
                <div class="header-left">
                    <span class="criterion-id">{c.id}</span>
                    <span class="meta-section">{c.rfp_section}</span>
                </div>
                <div class="header-right">
                    {status_pill(c.status)}
                </div>
            </div>

            <!-- Comparison Columns -->
            <div class="comparison-grid">
                <!-- Left: RFP Requirement -->
                <div class="column-rfp">
                    <div class="col-meta-header">RFP REQUIREMENT</div>
                    <div class="clause-banner">
                        <span class="icon-chip">📄</span>
                        <span class="clause-title">{rfp_clause_disp}</span>
                        <span class="page-chip">Page {c.rfp_page}</span>
                    </div>
                    <div class="requirement-text">{c.rfp_clause_text}</div>
                </div>

                <!-- Right: Submission Match -->
                <div class="column-submission">
                    <div class="col-meta-header">SUBMISSION VERDICT & EXCERPTS</div>
                    {f'''
                    <div class="clause-banner sub-banner missing-banner">
                        <span class="icon-chip">❌</span>
                        <span class="clause-title">Not Found in Submission Documents</span>
                        <span class="page-chip">RFP Ref: Page {c.rfp_page}</span>
                    </div>
                    ''' if c.status == "non_compliant" else f'''
                    <div class="clause-banner sub-banner">
                        <span class="icon-chip">📄</span>
                        <span class="clause-title">Skipped / Unable to Verify</span>
                        <span class="page-chip">RFP Ref: Page {c.rfp_page}</span>
                    </div>
                    ''' if c.status == "not_checked" else f'''
                    <div class="clause-banner sub-banner">
                        <span class="icon-chip">📁</span>
                        <span class="clause-title truncate">{c.comp_doc_name}</span>
                        <span class="clause-title">{comp_disp}</span>
                        <span class="page-chip">Page {c.comp_page}</span>
                    </div>
                    '''}
                    
                    {evidence_html}
                    {notes_html}
                    
                    {f'<div class="empty-evidence-message">No matching compliance evidence was found in the submission folder.</div>' if c.status == "non_compliant" else ""}
                    {f'<div class="empty-evidence-message">Skipped or unable to verify page matches due to text quality.</div>' if c.status == "not_checked" else ""}
                </div>
            </div>
        </div>""")
    criteria_content = "\n".join(criteria_cards)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report.rfp_title} — Premium Compliance Report</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,600;0,800;1,600&display=swap');

    :root {{
        --font-title: 'Outfit', -apple-system, sans-serif;
        --font-body: 'Outfit', -apple-system, sans-serif;
        
        /* Stratum AI Design System Palette */
        --bg-body: #F1F4EE;
        --bg-paper: #FFFFFF;
        --bg-slate: #EFEFEF;
        --border-color: #E0E5DC;
        
        --text-dark: #0B090A;
        --text-muted: #4A5568;
        --text-light: #718096;
        
        --accent-lime: #CCF458;
        --accent-forest: #34970D;
        
        --color-compliant: #34970D;
        --bg-compliant: #F4FCE8;
        --border-compliant: #CCF458;
        
        --color-partial: #D97706;
        --bg-partial: #FFFBEB;
        --border-partial: #FCD34D;
        
        --color-noncompliant: #E63946;
        --bg-noncompliant: #FFF0F2;
        --border-noncompliant: #FFB3BA;
        
        --color-unchecked: #64748B;
        --bg-unchecked: #F8FAFC;
        --border-unchecked: #E2E8F0;

        --shadow-sm: 0 4px 20px -2px rgba(11, 9, 10, 0.04);
        --shadow-md: 0 10px 30px -4px rgba(11, 9, 10, 0.06);
    }}

    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    body.dark {{
        --bg-body: #090D16;
        --bg-paper: #111827;
        --bg-slate: #1F2937;
        --border-color: #374151;
        
        --text-dark: #F9FAFB;
        --text-muted: #D1D5DB;
        --text-light: #9CA3AF;
        
        --bg-compliant: #064E3B;
        --border-compliant: #047857;
        
        --bg-partial: #78350F;
        --border-partial: #B45309;
        
        --bg-noncompliant: #7F1D1D;
        --border-noncompliant: #B91C1C;
        
        --bg-unchecked: #1F2937;
        --border-unchecked: #4B5563;
    }}

    body {{
        font-family: var(--font-body);
        font-size: 18px;
        background-color: var(--bg-body);
        color: var(--text-dark);
        line-height: 1.6;
        padding: 40px 24px;
    }}

    /* Scorecard Commentary Table & Markdown Styling */
    .metrics-card table {{
        width: 100%;
        border-collapse: collapse;
        margin: 24px 0;
        font-size: 1.1rem;
    }}
    .metrics-card th, .metrics-card td {{
        padding: 16px 20px;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
    }}
    .metrics-card th {{
        font-weight: 700;
        font-size: 1.15rem;
        background-color: var(--bg-slate);
        color: var(--text-dark);
    }}
    .metrics-card p {{
        margin-bottom: 16px;
        font-size: 1.1rem;
        line-height: 1.7;
        color: var(--text-dark);
    }}
    .metrics-card h3, .metrics-card h4 {{
        margin-top: 28px;
        margin-bottom: 12px;
        font-weight: 800;
        font-size: 1.6rem;
        color: var(--text-dark);
    }}
    .metrics-card ul, .metrics-card ol {{
        margin-left: 28px;
        margin-bottom: 20px;
        font-size: 1.1rem;
        color: var(--text-dark);
    }}
    .metrics-card li {{
        margin-bottom: 8px;
        line-height: 1.6;
    }}

    .container {{
        max-width: 1200px;
        margin: 0 auto;
    }}

    /* Cover Header Styling */
    .report-header {{
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        color: #FFFFFF;
        padding: 48px;
        border-radius: 20px;
        box-shadow: var(--shadow-md);
        margin-bottom: 32px;
        position: relative;
        overflow: hidden;
    }}

    .header-accent {{
        position: absolute;
        top: -50px;
        right: -50px;
        width: 250px;
        height: 250px;
        background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
        border-radius: 50%;
    }}

    .project-tag {{
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.15em;
        font-weight: 700;
        color: #38BDF8;
        margin-bottom: 12px;
        display: inline-block;
    }}

    .report-title {{
        font-family: var(--font-title);
        font-size: 2.5rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 8px;
    }}

    .report-subtitle {{
        font-size: 1.1rem;
        font-weight: 300;
        color: #94A3B8;
        margin-bottom: 24px;
    }}

    .header-meta-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 20px;
        border-top: 1px solid #334155;
        padding-top: 24px;
    }}

    .meta-item {{
        display: flex;
        flex-direction: column;
    }}

    .meta-item .meta-label {{
        font-size: 0.75rem;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
    }}

    .meta-item .meta-value {{
        font-size: 0.95rem;
        font-weight: 500;
        color: #F1F5F9;
    }}

    /* Dashboard Tabs */
    .tabs-bar {{
        display: flex;
        gap: 8px;
        background-color: #E2E8F0;
        padding: 6px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: var(--shadow-sm);
    }}

    .tab-btn {{
        background: none;
        border: none;
        padding: 12px 24px;
        font-family: var(--font-body);
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--text-muted);
        cursor: pointer;
        border-radius: 8px;
        transition: all 0.2s ease;
        flex: 1;
        text-align: center;
    }}

    .tab-btn:hover {{
        color: var(--text-dark);
    }}

    .tab-btn.active {{
        background-color: #FFFFFF;
        color: var(--text-dark);
        box-shadow: var(--shadow-sm);
    }}

    .tab-pane {{
        display: none;
    }}

    .tab-pane.active {{
        display: block;
    }}

    /* Scorecard layout */
    .scorecard-grid {{
        display: grid;
        grid-template-columns: 1fr 2fr;
        gap: 32px;
        margin-bottom: 32px;
    }}

    .score-circle-card {{
        background-color: #FFFFFF;
        border-radius: 16px;
        padding: 40px;
        box-shadow: var(--shadow-md);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        border: 1px solid var(--border-color);
        text-align: center;
    }}

    .score-number {{
        font-size: 5rem;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 8px;
    }}

    .score-badge {{
        font-size: 0.85rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.1em;
        padding: 6px 16px;
        border-radius: 20px;
        background-color: #F1F5F9;
        margin-bottom: 16px;
    }}

    .score-badge.strong {{ color: var(--color-compliant); background-color: var(--bg-compliant); }}
    .score-badge.conditional {{ color: var(--color-partial); background-color: var(--bg-partial); }}
    .score-badge.atrisk {{ color: var(--color-noncompliant); background-color: var(--bg-noncompliant); }}

    .score-explain {{
        font-size: 0.9rem;
        color: var(--text-muted);
    }}

    .metrics-card {{
        background-color: #FFFFFF;
        border-radius: 16px;
        padding: 32px;
        box-shadow: var(--shadow-md);
        border: 1px solid var(--border-color);
    }}

    .metric-bar-row {{
        margin-bottom: 20px;
    }}

    .metric-info {{
        display: flex;
        justify-content: space-between;
        margin-bottom: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }}

    .bar-outer {{
        background-color: #E2E8F0;
        height: 12px;
        border-radius: 6px;
        overflow: hidden;
    }}

    .bar-inner {{
        height: 100%;
        border-radius: 6px;
        width: 0%;
        transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    .bar-compliant {{ background-color: var(--color-compliant); }}
    .bar-partial {{ background-color: var(--color-partial); }}
    .bar-noncompliant {{ background-color: var(--color-noncompliant); }}
    .bar-unchecked {{ background-color: var(--color-unchecked); }}

    /* Comparison Card */
    .comparison-card {{
        background-color: #FFFFFF;
        border-radius: 16px;
        padding: 24px;
        box-shadow: var(--shadow-md);
        border: 1px solid var(--border-color);
        margin-bottom: 24px;
        position: relative;
        border-left: 6px solid var(--border-unchecked);
        transition: transform 0.15s ease;
    }}

    .comparison-card:hover {{
        transform: translateY(-2px);
    }}

    .comparison-card.status-compliant {{ border-left-color: var(--color-compliant); }}
    .comparison-card.status-partial {{ border-left-color: var(--color-partial); }}
    .comparison-card.status-non_compliant {{ border-left-color: var(--color-noncompliant); }}

    .card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 14px;
        margin-bottom: 20px;
    }}

    .header-left {{
        display: flex;
        align-items: center;
        gap: 12px;
    }}

    .criterion-id {{
        font-family: var(--font-title);
        font-weight: 800;
        font-size: 1.3rem;
        background-color: #F1F5F9;
        color: var(--text-dark);
        padding: 6px 14px;
        border-radius: 8px;
    }}

    .meta-section {{
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--text-light);
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}

    .pill {{
        font-size: 0.9rem;
        font-weight: 800;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        padding: 8px 16px;
        border-radius: 20px;
        box-shadow: var(--shadow-sm);
    }}

    .pill-compliant {{ background-color: var(--bg-compliant); color: var(--color-compliant); }}
    .pill-partial {{ background-color: var(--bg-partial); color: var(--color-partial); }}
    .pill-noncompliant {{ background-color: var(--bg-noncompliant); color: var(--color-noncompliant); }}
    .pill-unchecked {{ background-color: var(--bg-unchecked); color: var(--color-unchecked); }}

    /* Grid layout */
    .comparison-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
    }}

    .column-rfp, .column-submission {{
        display: flex;
        flex-direction: column;
    }}

    .column-rfp {{
        border-right: 1px solid var(--border-color);
        padding-right: 24px;
    }}

    .col-meta-header {{
        font-size: 0.85rem;
        font-weight: 800;
        color: var(--text-light);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 8px;
    }}

    .clause-banner {{
        display: flex;
        align-items: center;
        gap: 8px;
        background-color: var(--bg-slate);
        border: 1px solid var(--border-color);
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 12px;
        font-size: 0.95rem;
        font-weight: 600;
    }}

    .clause-banner.sub-banner {{
        background-color: #F0FDF4;
        border-color: #DCFCE7;
        color: #15803D;
    }}

    .comparison-card.status-partial .clause-banner.sub-banner {{
        background-color: #FFFBEB;
        border-color: #FEF3C7;
        color: #B45309;
    }}

    .icon-chip {{ font-size: 1.1rem; }}
    .clause-title {{ flex: 1; }}
    .truncate {{
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 160px;
    }}

    .page-chip {{
        background-color: #FFFFFF;
        border: 1px solid var(--border-color);
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 700;
    }}

    .requirement-text {{
        font-size: 1.15rem;
        color: var(--text-dark);
        line-height: 1.7;
    }}

    /* Quotes and Evidences */
    .evidence-quote-box {{
        background-color: var(--bg-compliant);
        border: 1px solid var(--border-compliant);
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
        position: relative;
    }}

    .comparison-card.status-partial .evidence-quote-box {{
        background-color: var(--bg-partial);
        border-color: var(--border-partial);
    }}

    .quote-header {{
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin-bottom: 6px;
    }}

    .quote-text {{
        font-family: var(--font-body);
        font-size: 1.1rem;
        font-style: normal;
        font-weight: 500;
        color: var(--text-dark);
        line-height: 1.7;
    }}

    .notes-box {{
        font-size: 1.05rem;
        color: var(--text-dark);
        background-color: var(--bg-slate);
        padding: 14px 16px;
        border-radius: 6px;
        border-left: 3px solid var(--text-light);
    }}

    .empty-evidence-message {{
        font-size: 0.85rem;
        font-style: italic;
        color: var(--text-light);
        text-align: center;
        padding: 32px 16px;
        background-color: var(--bg-slate);
        border-radius: 8px;
        border: 1px dashed var(--border-color);
    }}

    /* Gaps Cards */
    .gap-card {{
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 20px;
        box-shadow: var(--shadow-sm);
        border: 1px solid var(--border-color);
        margin-bottom: 16px;
        border-left: 5px solid var(--color-noncompliant);
    }}

    .gap-card:hover {{
        box-shadow: var(--shadow-md);
    }}

    .gap-header {{
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;
    }}

    .gap-id {{
        font-weight: 700;
        background-color: var(--bg-noncompliant);
        color: var(--color-noncompliant);
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
    }}

    .gap-link {{
        font-size: 0.75rem;
        color: var(--text-light);
        font-weight: 500;
        margin-left: auto;
    }}

    .sev-tag {{
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 2px 8px;
        border-radius: 4px;
    }}

    .tag-critical {{ background-color: var(--bg-noncompliant); color: var(--color-noncompliant); }}
    .tag-high {{ background-color: var(--bg-partial); color: var(--color-partial); }}
    .tag-medium {{ background-color: #EFF6FF; color: #1D4ED8; }}
    .tag-low {{ background-color: #F1F5F9; color: var(--text-light); }}

    .gap-body {{
        font-size: 0.9rem;
        color: var(--text-dark);
    }}

    .empty-state {{
        text-align: center;
        padding: 48px;
        color: var(--text-light);
        background-color: #FFFFFF;
        border-radius: 12px;
        border: 1px dashed var(--border-color);
        font-style: italic;
    }}

    /* Responsive adjustments */
    @media (max-width: 900px) {{
        .scorecard-grid {{ grid-template-columns: 1fr; }}
        .comparison-grid {{ grid-template-columns: 1fr; gap: 16px; }}
        .column-rfp {{ border-right: none; padding-right: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 20px; }}
    }}

    @media print {{
        body {{ background-color: #FFFFFF; padding: 0; }}
        .tabs-bar {{ display: none; }}
        .tab-pane {{ display: block !important; page-break-after: always; }}
        .comparison-card {{ page-break-inside: avoid; }}
        .gap-card {{ page-break-inside: avoid; }}
    }}
</style>
</head>
<body>

<div class="container">
    <!-- Header cover section -->
    <header class="report-header">
        <div class="header-accent"></div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 24px;">
            <div style="flex: 1;">
                <span class="project-tag">Compliance Report</span>
                <h1 class="report-title">{report.rfp_title}</h1>
                <p class="report-subtitle">Proposal Submission Compliance Assessment Report</p>
            </div>
            <!-- CheckMate Logo in Top Right -->
            <div style="display: flex; flex-direction: column; align-items: flex-end; text-align: right; flex-shrink: 0; margin-top: 10px;">
                <svg width="48" height="48" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 8px;">
                  <rect x="2" y="4" width="24" height="20" rx="4" stroke="#38BDF8" stroke-width="2.5" fill="none"/>
                  <path d="M8 14l4 4 8-9" stroke="#38BDF8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <div style="font-weight: 800; font-size: 1.2rem; color: #FFFFFF; letter-spacing: 0.05em; text-transform: uppercase; line-height: 1;">CheckMate</div>
                <div style="font-size: 0.65rem; color: #94A3B8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px;">Compliance Checker</div>
            </div>
        </div>
        
        <div class="header-meta-grid">
            <div class="meta-item">
                <span class="meta-label">Evaluation Date</span>
                <span class="meta-value">{report.date}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Requirements Checked</span>
                <span class="meta-value">{total_count} Clauses</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Compliant</span>
                <span class="meta-value" style="color: var(--color-compliant);">{compliant_count} Met</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Unresolved Gaps</span>
                <span class="meta-value" style="color: var(--color-noncompliant);">{non_compliant_count + partial_count} Items</span>
            </div>
        </div>
    </header>

    <!-- Tabs Navigation Bar -->
    <nav class="tabs-bar" style="display: flex; align-items: center;">
        <button class="tab-btn active" onclick="switchTab('scorecard')">Dashboard Scorecard</button>
        <button class="tab-btn" onclick="switchTab('criteria')">Compliance Registry ({total_count})</button>
        <button class="tab-btn" onclick="switchTab('gaps')">Gaps & Warnings ({len(report.gaps)})</button>
        
        <!-- Dark Mode Toggle Button -->
        <button class="theme-toggle-btn" onclick="toggleTheme()" style="margin-left: auto; background: none; border: 1px solid var(--border-color); border-radius: 8px; padding: 6px 12px; cursor: pointer; color: var(--text-light); font-weight: 600; display: flex; align-items: center; gap: 8px;">
            <svg class="sun-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: none;"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
            <svg class="moon-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
            <span class="theme-text">Dark Mode</span>
        </button>
    </nav>

    <!-- Tab Panels -->
    <!-- SCORECARD PANEL -->
    <div id="scorecard" class="tab-pane active">
        <div class="scorecard-grid">
            <div class="score-circle-card">
                <div class="score-badge {score_tier}">{score_label}</div>
                <div class="score-number" style="color: {score_color};">{report.overall_score:.0f}%</div>
                <p class="score-explain">Overall compliance status rating of the submitted bid proposals relative to the RFP specifications.</p>
            </div>
            
            <div class="metrics-card">
                <h3 style="margin-bottom: 20px; font-weight: 700;">Response Distribution Summary</h3>
                
                <div class="metric-bar-row">
                    <div class="metric-info">
                        <span>Compliant Requirements</span>
                        <span style="color: var(--color-compliant);">{compliant_count} / {total_count} ({compliant_pct:.1f}%)</span>
                    </div>
                    <div class="bar-outer"><div class="bar-inner bar-compliant" style="width: {compliant_pct:.1f}%;"></div></div>
                </div>

                <div class="metric-bar-row">
                    <div class="metric-info">
                        <span>Partially Compliant Gaps</span>
                        <span style="color: var(--color-partial);">{partial_count} / {total_count} ({partial_pct:.1f}%)</span>
                    </div>
                    <div class="bar-outer"><div class="bar-inner bar-partial" style="width: {partial_pct:.1f}%;"></div></div>
                </div>

                <div class="metric-bar-row">
                    <div class="metric-info">
                        <span>Non-Compliant Gaps</span>
                        <span style="color: var(--color-noncompliant);">{non_compliant_count} / {total_count} ({noncomp_pct:.1f}%)</span>
                    </div>
                    <div class="bar-outer"><div class="bar-inner bar-noncompliant" style="width: {noncomp_pct:.1f}%;"></div></div>
                </div>

                <div class="metric-bar-row" style="margin-bottom: 0;">
                    <div class="metric-info">
                        <span>Not Checked / OCR Issues</span>
                        <span style="color: var(--color-unchecked);">{not_checked_count} / {total_count} ({unchecked_pct:.1f}%)</span>
                    </div>
                    <div class="bar-outer"><div class="bar-inner bar-unchecked" style="width: {unchecked_pct:.1f}%;"></div></div>
                </div>
            </div>
        </div>
        
        <div class="metrics-card">
            <h3 style="margin-bottom: 12px; font-weight: 700; border-bottom: 1px solid var(--border-color); padding-bottom: 12px;">Submission Folder Summary</h3>
            <p style="font-size: 0.95rem; line-height: 1.6; white-space: pre-line; color: var(--text-muted);">{report.submission_summary}</p>
        </div>

        <div class="metrics-card" style="margin-top: 24px;">
            <h3 style="margin-bottom: 12px; font-weight: 700; border-bottom: 1px solid var(--border-color); padding-bottom: 12px;">Section-by-Section Compliance Commentary</h3>
            <div style="font-size: 0.95rem; line-height: 1.7; color: var(--text-muted);">{html_commentary}</div>
        </div>
    </div>

    <!-- CRITERIA REGISTRY PANEL -->
    <div id="criteria" class="tab-pane">
        {criteria_content}
    </div>

    <!-- GAPS REGISTER PANEL -->
    <div id="gaps" class="tab-pane">
        {gaps_content}
    </div>
    <!-- Footer Branding -->
    <footer style="margin-top: 48px; border-top: 1px solid var(--border-color); padding-top: 24px; padding-bottom: 24px; display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-light);">
        <div>
            <strong>CheckMate</strong> &middot; RFP Compliance Assessment Engine
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span>Powered by</span>
            <span style="font-weight: 700; color: #1E293B; letter-spacing: 0.05em; text-transform: uppercase;">JazzWorld AI Studio</span>
        </div>
    </footer>
</div>

<script>
    function switchTab(tabId) {{
        // Hide all panes
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        // Deactivate all buttons
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        
        // Show active pane
        document.getElementById(tabId).classList.add('active');
        // Find active button
        event.currentTarget.classList.add('active');
    }}

    function toggleTheme() {{
        const isDark = document.body.classList.toggle('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        updateThemeUI(isDark);
    }}

    function updateThemeUI(isDark) {{
        const sun = document.querySelector('.sun-icon');
        const moon = document.querySelector('.moon-icon');
        const text = document.querySelector('.theme-text');
        
        if (isDark) {{
            sun.style.display = 'block';
            moon.style.display = 'none';
            text.textContent = 'Light Mode';
        }} else {{
            sun.style.display = 'none';
            moon.style.display = 'block';
            text.textContent = 'Dark Mode';
        }}
    }}

    // Load initial theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {{
        document.body.classList.add('dark');
        updateThemeUI(true);
    }}
</script>
</body>
</html>"""
    return html


def generate_pdf(html_str: str, output_path: Union[str, Path]) -> bool:
    output_path = Path(output_path)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[ERROR] Playwright is not installed. Install it with:  pip install playwright  &&  playwright install chromium",
            file=sys.stderr,
        )
        return False

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
    tmp_path = Path(tmp.name)
    try:
        tmp.write(html_str)
        tmp.close()

        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True)
            except Exception as exc:
                print(
                    f"[ERROR] Could not launch Chromium for Playwright: {exc}",
                    file=sys.stderr,
                )
                print(
                    "Make sure Chromium is installed:  playwright install chromium",
                    file=sys.stderr,
                )
                return False

            page = browser.new_page(viewport={"width": 1200, "height": 1600})
            page.goto(f"file://{tmp_path.resolve()}", wait_until="networkidle")
            page.wait_for_timeout(2000)

            page.pdf(
                path=str(output_path),
                format="A4",
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
                print_background=True,
            )
            browser.close()

        print(f"[OK] PDF saved to {output_path}")
        return True

    except Exception as exc:
        print(f"[ERROR] PDF generation failed: {exc}", file=sys.stderr)
        return False

    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def save_reports(
    report: ComplianceReport,
    output_dir: Union[str, Path],
    rfp_filename: str = "report",
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / f"{rfp_filename}_compliance_report.html"
    pdf_path = output_dir / f"{rfp_filename}_compliance_report.pdf"

    html_str = generate_html(report)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    print(f"[OK] HTML saved to {html_path}")

    pdf_ok = generate_pdf(html_str, pdf_path)

    return {
        "html": str(html_path.resolve()),
        "pdf": str(pdf_path.resolve()) if pdf_ok else "",
    }
