"""Bod — RFP Compliance Checker Desktop App.

NiceGUI-powered cross-platform app with two screens:
1. Configuration (API key, model, base URL)
2. Compliance check (upload RFP, select submission folder, run analysis)

The UI is built inside `build_ui()` and passed to `ui.run(root=...)` so that
NiceGUI does NOT enter "script mode" (which re-executes the file via runpy and
breaks under a PyInstaller bundle).
"""

from __future__ import annotations

import asyncio
import html
import os
import subprocess
import sys
import time
from pathlib import Path
from queue import Queue
from typing import Optional

from nicegui import app, ui

import config_manager
import pdf_extractor
from pdf_extractor import extract_file, SUPPORTED_EXTENSIONS
from compliance_engine import ComplianceEngine, BodError
from report_generator import save_reports
import auth
import admin_console

# ── Logging ────────────────────────────────────────────────────────

import logging

_log_dir = Path(__file__).parent / ".bod_data"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = str(_log_dir / "bod.log")
logging.basicConfig(

    filename=_log_file,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",

    force=True,
)
logger = logging.getLogger("bod")


# ── Constants ──────────────────────────────────────────────────────

APP_NAME = "CheckMate — RFP Compliance Checker"
LIME = "#CCF458"        # Primary Accent (Neon Lime Green)
FOREST = "#34970D"      # Secondary Accent (Deep Forest Green)
CHARCOAL = "#0B090A"    # Primary Text & Dark Surfaces
WHITE = "#FFFFFF"       # Pure White
BG = "#F1F4EE"          # Global Background (Soft desaturated sage/off-white)
BORDER = "#E0E5DC"      # Soft Gray/Sage Border
MUTED = "#52525B"       # Subtitle & Muted Text
CANCEL = "#E63946"      # Non-Compliant / Action Required Red

# Aliases for backwards compatibility & clean styling
EMERALD = FOREST
NAVY = CHARCOAL
INK = CHARCOAL

LOGO_SVG = """<svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="2" y="4" width="24" height="20" rx="8" fill="#0B090A"/>
  <path d="M8 14l4 4 8-9" stroke="#CCF458" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


# ── State ──────────────────────────────────────────────────────────

class State:
    show_config: bool = False
    show_admin: bool = False
    rfp_path: Optional[str] = None
    rfp_filename: Optional[str] = None
    running: bool = False
    cancel_requested: bool = False
    error: Optional[str] = None
    html_report: Optional[str] = None
    output_dir: Optional[str] = None
    q: Queue = Queue()
    activity_q: Queue = Queue()
    elapsed_seconds: int = 0
    last_log_time: float = 0.0
    summary: Optional[dict] = None
    log_entries: list[str] = list()
    manual_model_select: bool = False
    last_report: Optional[object] = None
    report_criteria: list[dict] = list()
    active_user_id: int = 1
    active_username: str = "admin"



state = State()
state.show_config = False



# ── Globals populated during UI build ──────────────────────────────

log_scroll: Optional[ui.scroll_area] = None
log_column: Optional[ui.column] = None
main_btn: Optional[ui.button] = None
sub_input: Optional[ui.input] = None
out_dir_input: Optional[ui.input] = None
rfp_input: Optional[ui.input] = None
rfp_label: Optional[ui.label] = None
result_container: Optional[ui.column] = None
html_link: Optional[ui.html] = None
open_btn: Optional[ui.button] = None
cfg_container: Optional[ui.column] = None
main_container: Optional[ui.column] = None
evals_container: Optional[ui.column] = None
eval_log: Optional[ui.log] = None
eval_matrix_container: Optional[ui.column] = None
eval_run_btn: Optional[ui.button] = None
eval_progress: Optional[ui.linear_progress] = None
eval_progress_label: Optional[ui.label] = None
eval_kpi_f1: Optional[ui.label] = None
eval_kpi_exact: Optional[ui.label] = None
eval_kpi_intel: Optional[ui.label] = None
eval_kpi_latency: Optional[ui.label] = None
eval_kpi_drift: Optional[ui.label] = None
test_log: Optional[ui.log] = None
test_btn: Optional[ui.button] = None
narrated_column: Optional[ui.column] = None
narrated_scroll: Optional[ui.scroll_area] = None
orb_element: Optional[ui.html] = None
status_pill: Optional[ui.label] = None
elapsed_label: Optional[ui.label] = None
model_dropdown: Optional[ui.select] = None
recommendation_label: Optional[ui.label] = None
_last_checked_rfp = None
_last_checked_sub = None


# ── Try to detect Tesseract on startup ─────────────────────────────

tesseract_path = pdf_extractor.find_tesseract()
if tesseract_path:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


# ── Helpers ────────────────────────────────────────────────────────

def _card():
    return ui.card().classes(
        "w-full bg-white dark:bg-gray-800/90 rounded-2xl p-6 shadow-sm hover:shadow-md transition-all duration-200 border border-gray-200/80 dark:border-gray-700/80 backdrop-blur-md"
    )


def _primary_btn(text: str, color: str, cb):
    return ui.button(text, on_click=cb).props(
        f'unelevated style="background: linear-gradient(135deg, {LIME} 0%, #10B981 100%) !important; color: #0F172A !important; font-size: 16px; '
        f'font-weight: 800; padding: 12px 28px; border-radius: 9999px; width: 100%; border: none; box-shadow: 0 8px 20px -4px rgba(16, 185, 129, 0.4); cursor: pointer;"'
    ).classes("hover:scale-[1.01] active:scale-[0.99] transition-transform")


def _small_btn(text: str, color: str, cb):
    bg_col = color if color not in (MUTED, NAVY, EMERALD) else CHARCOAL
    text_col = CHARCOAL if bg_col == LIME else WHITE
    return ui.button(text, on_click=cb).props(
        f'unelevated style="background-color: {bg_col} !important; color: {text_col} !important; '
        f'font-size: 13px; font-weight: 600; padding: 8px 20px; border-radius: 9999px; border: none;"'
    ).classes("hover:opacity-90 transition-opacity")



def _estimate_document_stats(path: str) -> tuple[int, int]:
    """Return (page_count, size_bytes) of the RFP file or folder."""
    p = Path(path)
    if not p.exists():
        return 0, 0
    if p.is_dir():
        return _estimate_submission_stats(path)
    size_bytes = p.stat().st_size
    ext = p.suffix.lower()
    if ext == ".pdf":
        try:
            import pypdfium2
            pdf = pypdfium2.PdfDocument(str(p))
            pages = len(pdf)
            pdf.close()
            return pages, size_bytes
        except Exception:
            try:
                import pdfplumber
                with pdfplumber.open(p) as pdf:
                    return len(pdf.pages), size_bytes
            except Exception:
                pass
    return 1, size_bytes


def _estimate_submission_stats(folder_path: str) -> tuple[int, int]:
    """Return (file_count, total_size_bytes) of supported files in the folder."""
    p = Path(folder_path)
    if not p.exists() or not p.is_dir():
        return 0, 0
    file_count = 0
    total_size = 0
    from pdf_extractor import SUPPORTED_EXTENSIONS
    for ext in SUPPORTED_EXTENSIONS:
        for f in p.rglob(f"*{ext}"):
            if f.is_file():
                file_count += 1
                total_size += f.stat().st_size
    return file_count, total_size


def _update_recommendation():
    global recommendation_label, _last_checked_rfp, _last_checked_sub
    if recommendation_label is None or model_dropdown is None:
        return
    rfp = rfp_input.value.strip() if rfp_input else ""
    sub = sub_input.value.strip() if sub_input else ""
    if rfp == _last_checked_rfp and sub == _last_checked_sub:
        return
    _last_checked_rfp = rfp
    _last_checked_sub = sub
    if not rfp or not sub:
        recommendation_label.set_text("Select files to see model recommendation.")
        return

    try:
        rfp_pages, rfp_size = _estimate_document_stats(rfp)
        sub_files, sub_size = _estimate_submission_stats(sub)
        total_mb = (rfp_size + sub_size) / (1024 * 1024)
        est_tokens = (rfp_pages * 800) + (sub_files * 3000)

        if est_tokens > 150000 or total_mb > 50:
            recommended_model = "gemini-2.5-pro"
            reason = f"Large dataset ({rfp_pages} RFP pages, {sub_files} sub files, ~{total_mb:.1f}MB). Using Gemini 2.5 Pro."
        else:
            recommended_model = "gemini-2.5-flash"
            reason = f"Standard dataset ({rfp_pages} RFP pages, {sub_files} sub files, ~{total_mb:.1f}MB). Using Gemini 2.5 Flash."

        recommendation_label.set_text(f"Auto-selected: {reason}")
        if not state.manual_model_select:
            if recommended_model in model_dropdown.options:
                model_dropdown.value = recommended_model
    except Exception as exc:
        logger.error("Error generating recommendation: %s", exc)


def _update_run_btn():
    if main_btn is None or state.running:
        return
    rfp_val = rfp_input.value.strip() if rfp_input is not None else ""
    sub_val = sub_input.value.strip() if sub_input is not None else ""
    ready = bool(state.rfp_path or rfp_val) and bool(sub_val)
    
    # Run recommendation scan dynamically when paths change
    _update_recommendation()
    
    if ready:
        main_btn.enable()
        main_btn.props(
            f'unelevated style="background-color: {LIME} !important; color: {CHARCOAL} !important; '
            f'font-size: 17px; font-weight: 800; padding: 14px 32px; border-radius: 9999px; '
            f'width: 100%; border: none; box-shadow: 0 6px 20px rgba(204, 244, 88, 0.6); opacity: 1 !important; cursor: pointer;"'
        )
    else:
        main_btn.disable()
        main_btn.props(
            f'unelevated style="background-color: #E2E8F0 !important; color: #64748B !important; '
            f'font-size: 17px; font-weight: 700; padding: 14px 32px; border-radius: 9999px; '
            f'width: 100%; border: none; opacity: 0.7 !important; cursor: not-allowed;"'
        )


def _log(msg: str):
    state.q.put(msg)
    state.log_entries.append(msg)
    logger.info("%s", msg)


def _eval_log(msg: str):
    state.eval_log_q.put(msg)
    logger.info("[EVAL] %s", msg)


def _poll():
    if log_column is not None:
        while not state.q.empty():
            msg = state.q.get_nowait()
            state.last_log_time = time.time()
            with log_column:
                is_error = msg.startswith("Error:")
                lbl = ui.label(msg)
                lbl.style(
                    "white-space: pre-wrap; word-break: break-all; "
                    "font-family: 'SF Mono', 'Cascadia Code', monospace; "
                    "font-size: 13px; line-height: 1.5; padding: 1px 0;"
                )
                if is_error:
                    lbl.style(
                        "background-color: #FEF2F2; color: #991B1B; "
                        "margin: 0 -12px; padding: 3px 12px;"
                    )
    if narrated_column is not None:
        while not state.activity_q.empty():
            msg, is_complete = state.activity_q.get_nowait()
            with narrated_column:
                lbl = ui.label(msg)
                lbl.style(
                    "font-size: 15px; line-height: 1.5; padding: 8px 0; "
                    "border-left: 3px solid #1A6B4F; padding-left: 12px; "
                    "margin: 2px 0;"
                )
                if is_complete:
                    lbl.style("font-weight: 600; color: #1A6B4F;")
    if narrated_scroll is not None:
        narrated_scroll.scroll_to(percent=100)
    if log_scroll is not None:
        log_scroll.scroll_to(percent=100)


def _heartbeat():
    if orb_element is not None:
        if state.running:
            orb_element.content = '<div class="orb-pulse"></div>'
        else:
            orb_element.content = '<div class="orb-idle"></div>'
    if not state.running:
        return

    state.elapsed_seconds += 1
    mins = state.elapsed_seconds // 60
    secs = state.elapsed_seconds % 60

    now = time.time()
    quiet = now - state.last_log_time
    if quiet > 20 and int(quiet) % 5 == 0:
        _log(f"   Still working\u2026 ({mins}m {secs:02d}s elapsed)")


def _load_rfp(path: str):
    global rfp_label
    p = Path(path)
    if not p.exists():
        ui.notification("File not found", type="negative")
        return False
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        ui.notification(f"Unsupported file type: {ext}", type="negative")
        return False
    temp_dir = Path.home() / ".bod" / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    dest = temp_dir / p.name
    import shutil
    shutil.copy2(str(p), str(dest))
    state.rfp_path = str(dest)
    state.rfp_filename = p.name
    if rfp_label:
        rfp_label.set_text(f"Loaded: {p.name}")
    ui.notification(f"RFP loaded: {p.name}", type="positive")
    return True


def _stat_badge(text: str, color: str, label: str):
    return ui.column().classes("items-center gap-0").add_slot("default",
        f'<div style="font-size: 20px; font-weight: 700; color: {color};">'
        f'{text}</div>'
        f'<div style="font-size: 11px; color: {MUTED};">{label}</div>'
    )


def _open_folder():
    if state.output_dir and Path(state.output_dir).exists():
        p = Path(state.output_dir).resolve()
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        elif sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])


def _copy_log():
    if not state.log_entries:
        ui.notification("No log entries to copy", type="info")
        return
    text = "\n".join(state.log_entries)
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        ui.notification("Log copied to clipboard", type="positive")
    except FileNotFoundError:
        if sys.platform == "win32":
            subprocess.run(["clip"], input=text, text=True, check=True)
            ui.notification("Log copied to clipboard", type="positive")
        elif sys.platform == "linux":
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text, text=True, check=True,
            )
            ui.notification("Log copied to clipboard", type="positive")
        else:
            ui.notification(
                "Clipboard not supported on this platform", type="negative"
            )


def _export_markdown_for_llm():
    lines = []
    if state.last_metrics is not None:
        m = state.last_metrics
        lines.append("# CheckMate Evaluation & Benchmark Export (For LLM Reviewer)\n")
        lines.append(f"- **Overall F1 Score:** `{m.f1_score:.1f}%`")
        lines.append(f"- **Exact Match:** `{m.exact_match_pct:.1f}%` ({m.exact_matches}/{m.total_evals})")
        lines.append(f"- **Intelligence Mapping Score:** `{m.intelligence_mapping_score:.1f}%`")
        lines.append(f"- **Intention Assessment Score:** `{m.intention_score:.1f}%`")
        lines.append(f"- **Total Latency:** `{m.total_latency_ms:.0f}ms`\n")
        lines.append("## Detailed Requirements Assessment Matrix\n")
        for r in m.rows:
            lines.append(f"### {r.req_id} \u2014 {r.clause_num}: {r.clause_name}")
            lines.append(f"- **RFP Clause Requirement:** {r.rfp_clause_text}")
            lines.append(f"- **Submission Excerpt / Evidence:** \"{r.bidder_quote}\"")
            lines.append(f"- **Model Verdict:** `{r.model_status.upper()}`")
            if r.expected_status and r.expected_status != "N/A":
                lines.append(f"- **Expected Ground Truth:** `{r.expected_status.upper()}`")
                match_str = "EXACT MATCH" if r.status_match else "MISMATCH"
                lines.append(f"- **Status Comparison:** `{match_str}`")
            lines.append(f"- **CheckMate Analysis Notes:** {r.notes}\n")
    elif state.last_report is not None:
        rep = state.last_report
        lines.append("# CheckMate RFP Compliance Assessment Export (For LLM Reviewer)\n")
        lines.append(f"- **RFP Title:** `{rep.rfp_title}`")
        lines.append(f"- **Assessment Date:** `{rep.date}`")
        lines.append(f"- **Overall Compliance Score:** `{rep.overall_score:.1f}%`\n")
        lines.append("## Executive Summary\n")
        lines.append(f"{rep.submission_summary}\n")
        lines.append("## Detailed Criteria Verification\n")
        for c in rep.criteria:
            lines.append(f"### {c.id} \u2014 Clause {c.rfp_clause_num}: {c.rfp_clause_name}")
            lines.append(f"- **RFP Section / Page:** {c.rfp_section} (Page {c.rfp_page})")
            lines.append(f"- **Requirement Text:** {c.rfp_clause_text}")
            lines.append(f"- **Bidder Reference:** {c.comp_section} (Page {c.comp_page})")
            lines.append(f"- **Status Verdict:** `{c.status.upper()}`")
            lines.append(f"- **Verbatim Evidence Quote:** \"{c.evidence}\"")
            lines.append(f"- **CheckMate Notes:** {c.notes}\n")
        if rep.gaps:
            lines.append("## Identified Compliance Gaps & Risks\n")
            for g in rep.gaps:
                lines.append(f"- **[{g.severity}]** (`{g.criterion_id}`): {g.description}")
    else:
        ui.notification("No assessment results available to export yet. Please run an assessment first.", type="warning")
        return

    text = "\n".join(lines)
    out_path = Path(state.output_dir if state.output_dir else Path.cwd()) / "checkmate_llm_export.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        _log(f"Failed to save markdown export file: {e}")

    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        ui.notification("Markdown exported & copied to clipboard! Ready to paste to LLM.", type="positive")
    except FileNotFoundError:
        if sys.platform == "win32":
            subprocess.run(["clip"], input=text, text=True, check=True)
            ui.notification("Markdown exported & copied to clipboard! Ready to paste to LLM.", type="positive")
        elif sys.platform == "linux":
            subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
            ui.notification("Markdown exported & copied to clipboard! Ready to paste to LLM.", type="positive")
        else:
            ui.notification(f"Saved to {out_path} (clipboard copy not supported on this platform)", type="positive")


def _icon(name: str, size: int = 16, color: str = MUTED) -> str:
    icons = {
        "check-circle": '<circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/>',
        "search": '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
        "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
        "alert-triangle": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        "x-circle": '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
        "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        "clipboard": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M9 14l2 2 4-4"/>',
        "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
        "external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    }
    svg = icons.get(name, "")
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{svg}</svg>'


def _make_progress_callback():
    def _on_progress(stage: int, message: str, current: int, total: int):
        _log(message)
        is_complete = stage == 4 and current == total
        state.activity_q.put((message, is_complete))
        if status_pill is not None:
            status_pill.set_text(message if message else "")
    return _on_progress


# ═══════════════════════════════════════════════════════════════════
# UI construction (runs per client connection)
# ═══════════════════════════════════════════════════════════════════

@ui.page('/')
def build_ui():

    global log_scroll, log_column, main_btn, sub_input, rfp_label, rfp_input
    global result_container, cfg_container, main_container, test_log, test_btn
    global narrated_column, narrated_scroll, orb_element, status_pill
    global evals_container, eval_log, eval_matrix_container, eval_run_btn
    global eval_progress, eval_progress_label, eval_kpi_f1, eval_kpi_exact
    global eval_kpi_intel, eval_kpi_latency, eval_kpi_drift

    # ── Styling ──────────────────────────────────────────────────
    ui.add_head_html(
        '<link href="https://fonts.googleapis.com/css2?'
        'family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
    )
    ui.add_head_html("""
<style>
@keyframes pulse {
  0% { opacity: 0.6; transform: scale(1); box-shadow: 0 0 4px #CCF458; }
  50% { opacity: 1; transform: scale(1.2); box-shadow: 0 0 12px #CCF458; }
  100% { opacity: 0.6; transform: scale(1); box-shadow: 0 0 4px #CCF458; }
}
.orb-pulse {
  width: 12px; height: 12px;
  border-radius: 50%;
  background-color: #CCF458;
  display: inline-block;
  animation: pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}
.orb-idle {
  width: 12px; height: 12px;
  border-radius: 50%;
  background-color: #E0E5DC;
  display: inline-block;
  flex-shrink: 0;
}
</style>""")
    ui.query("body").style(
        f"background-color: {BG}; font-family: 'Outfit', Inter, -apple-system, sans-serif;"
    )
    ui.query(".nicegui-content").classes("p-4 w-full max-w-none mx-auto")

    ui.timer(0.5, _poll)
    ui.timer(0.3, _update_run_btn)
    ui.timer(1.0, _heartbeat)

    # ── Session & Auth Check ────────────────────────────────────
    user_session = app.storage.user.get("user")
    if not user_session:
        with ui.column().classes("w-full max-w-md mx-auto mt-16 p-8 bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 gap-4 items-center"):
            ui.html(LOGO_SVG).classes("w-12 h-12 mb-2")
            ui.label("Sign in to CheckMate").classes("text-2xl font-bold text-gray-900 dark:text-white")
            ui.label("Enter your credentials to access the compliance workspace.").classes("text-xs text-gray-500 mb-2 text-center")
            
            uname_input = ui.input("Username or Email").classes("w-full")
            pwd_input = ui.input("Password", password=True, password_toggle_button=True).classes("w-full mb-2")
            
            def do_login():
                u = auth.authenticate_user(uname_input.value, pwd_input.value)
                if u:
                    app.storage.user["user"] = u
                    ui.navigate.reload()
                else:
                    ui.notify("Invalid username or password.", type="negative")

            ui.button("Sign In", icon="login", on_click=do_login).props("color=primary").classes("w-full py-3 text-base font-semibold")
            
            with ui.column().classes("w-full mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 border"):
                ui.label("Default Admin Login:").classes("font-bold")
                ui.label("Username: admin")
                ui.label("Password: AdminPassword123!")
        return

    is_admin = user_session.get("role") == "admin"
    state.active_user_id = user_session.get("id", 1)
    state.active_username = user_session.get("username", "admin")


    # ═══════════════════════════════════════════════════════════════
    # SCREEN 0 — Admin Management Console
    # ═══════════════════════════════════════════════════════════════
    admin_container = ui.column().classes("w-full max-w-7xl mx-auto p-4").bind_visibility_from(state, "show_admin")
    with admin_container:
        def _nav_workspace():
            state.show_admin = False
        admin_console.render_admin_console(user_session, _nav_workspace)

    # ═══════════════════════════════════════════════════════════════
    # SCREEN 1 — Configuration (Admin Only)
    # ═══════════════════════════════════════════════════════════════

    cfg_container = ui.column().classes("w-full max-w-7xl mx-auto p-4").bind_visibility_from(state, "show_config")
    with cfg_container:
        with ui.row().classes("w-full items-center"):
            def _back_to_main():
                state.show_config = False


            ui.button("← Back", on_click=_back_to_main).props(
                f'flat style="color: {MUTED}; font-size: 14px;"'
            )

        with ui.row().classes("w-full items-center justify-center gap-3"):
            ui.html(LOGO_SVG).classes("w-7 h-7")
            ui.label(APP_NAME).classes("text-3xl font-bold").style(
                f"color: {INK}"
            )
        ui.label(
            "Configure your API access before running compliance checks."
        ).classes("text-center text-lg").style(f"color: {MUTED}")

        with _card():
            saved_cfg = config_manager.load_config()

            ui.label("API Key").classes("text-sm font-semibold").style(
                f"color: {INK}"
            )
            api_key_input = ui.input(
                placeholder="Paste your API key here...",
                value=saved_cfg.get("api_key", ""),
            ).props("type=password").classes("w-full mb-4")

            ui.label("Model Name").classes("text-sm font-semibold").style(
                f"color: {INK}"
            )
            model_input = ui.input(
                value=saved_cfg.get("model", config_manager.DEFAULT_MODEL),
            ).classes("w-full mb-1")
            ui.label(
                "Defaults to deepseek/deepseek-r1-distill-llama-70b-free. You can use any "
                "supported model ID."
            ).classes("text-xs mb-4").style(f"color: {MUTED}")

            ui.label("Base URL").classes("text-sm font-semibold").style(
                f"color: {INK}"
            )
            url_input = ui.input(
                value=saved_cfg.get("base_url", config_manager.DEFAULT_BASE_URL),
            ).classes("w-full mb-6")

            def _save_clicked():
                key = api_key_input.value.strip()
                mod = model_input.value.strip()
                url = url_input.value.strip()
                if not key:
                    ui.notification("Please enter an API key", type="negative")
                    return
                if not mod:
                    mod = config_manager.DEFAULT_MODEL
                if not url:
                    url = config_manager.DEFAULT_BASE_URL
                config_manager.save_config(
                    {"api_key": key, "model": mod, "base_url": url}
                )
                ui.notification("Configuration saved!", type="positive")
                state.show_config = False

            _primary_btn("Save Configuration", EMERALD, _save_clicked)

            with ui.row().classes("w-full justify-between items-center mt-3"):
                ui.label()

                def _test_clicked():
                    ui.timer(0.01, _run_test_async, once=True)

                test_btn = _small_btn("Test Connection", NAVY, _test_clicked)

        test_log = ui.log(max_lines=50).classes("w-full mt-2").style(
            "height: 120px; font-family: monospace; font-size: 12px;"
        )

    # ═══════════════════════════════════════════════════════════════
    # SCREEN 2 — Main Compliance Check
    # ═══════════════════════════════════════════════════════════════

    main_container = ui.column().classes("w-full max-w-7xl mx-auto p-4").bind_visibility_from(
        state, "show_config", lambda v: not v and not state.show_admin
    )
    with main_container:
        # ── Header ────────────────────────────────────────────────
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-3"):
                ui.html(LOGO_SVG).classes("w-8 h-8")
                with ui.row().classes("items-center gap-2"):
                    ui.label("CheckMate").classes("text-2xl font-extrabold tracking-tight").style(f"color: {CHARCOAL}")
                    ui.label("RFP COMPLIANCE").classes("text-[11px] font-extrabold px-2.5 py-1 rounded-full").style(f"background-color: #E6FA95; color: {FOREST}; letter-spacing: 1px;")

            with ui.row().classes("items-center gap-3"):
                orb_element = ui.html('<div class="orb-idle"></div>')
                status_pill = ui.label("").classes("text-sm").style(
                    f"color: {MUTED}; min-width: 80px;"
                )

                role_lbl = "ADMIN" if is_admin else "USER"
                ui.label(f"{user_session.get('username')} ({role_lbl})").classes(
                    "text-xs font-bold px-3 py-1.5 rounded-full bg-gray-200 text-gray-800"
                )

                if is_admin:
                    def _toggle_admin():
                        state.show_admin = not state.show_admin
                        state.show_config = False

                    ui.button("Admin Console", icon="admin_panel_settings", on_click=_toggle_admin).props(
                        f'unelevated style="background-color: {CHARCOAL} !important; color: white !important; font-size: 13px; font-weight: 600; padding: 6px 18px; border-radius: 9999px;"'
                    )

                def do_logout():
                    app.storage.user.clear()
                    ui.navigate.reload()

                ui.button("Logout", icon="logout", on_click=do_logout).props("flat color=negative size=sm")


        # ── Config status ──────────────────────────────────────────
        ui.label("Powered By Jazz Enterprise AI Studio").classes(
            "text-xs font-bold tracking-wide"
        ).style(f"color: {FOREST}; letter-spacing: 0.5px;")

        # ── Two-column layout ─────────────────────────────────────
        with ui.row().classes("w-full gap-6 mt-4"):
            # ── Left column ───────────────────────────────────────
            with ui.column().classes("flex-1 gap-6 min-w-0"):
                # RFP document card
                with _card():
                    ui.label("RFP Document or Folder").classes("text-lg font-semibold")
                    ui.label("Select an RFP file or a folder containing multiple RFP documents (PDF, Word, Excel, text, image).").classes(
                        "text-sm"
                    ).style(f"color: {MUTED}")

                    with ui.row().classes("w-full items-center gap-2"):
                        rfp_input = ui.input(
                            placeholder="Path to RFP file or folder...",
                        ).props('style="font-size: 16px; flex: 1;"').classes("flex-1")

                        def _browse_rfp_file():
                            import subprocess as _sp
                            try:
                                res = _sp.run(
                                    ["osascript", "-e",
                                     'set p to POSIX path of '
                                     '(choose file with prompt "Select RFP Document File")'],
                                    capture_output=True, text=True, timeout=30,
                                )
                                path = res.stdout.strip()
                                if path:
                                    rfp_input.value = path
                                    _load_rfp(path)
                            except Exception:
                                ui.notification("Paste the file path manually.", type="info")

                        def _browse_rfp_folder():
                            import subprocess as _sp
                            try:
                                res = _sp.run(
                                    ["osascript", "-e",
                                     'POSIX path of '
                                     '(choose folder with prompt "Select RFP Documents Folder")'],
                                    capture_output=True, text=True, timeout=30,
                                )
                                path = res.stdout.strip()
                                if path:
                                    rfp_input.value = path
                                    _load_rfp(path)
                            except Exception:
                                ui.notification("Paste the folder path manually.", type="info")

                        _small_btn("Browse File", MUTED, _browse_rfp_file)
                        _small_btn("Browse Folder", MUTED, _browse_rfp_folder)

                    rfp_input.on("keydown.enter", lambda: _load_rfp(rfp_input.value))
                    rfp_label = ui.label("").classes("text-sm mt-2").style(
                        f"color: {MUTED}"
                    )

                # Submission folder card
                with _card():
                    ui.label("Submission Folder").classes("text-lg font-semibold")
                    ui.label(
                        "Full path to the folder containing submission PDFs."
                    ).classes("text-sm").style(f"color: {MUTED}")

                    with ui.row().classes("w-full items-center gap-2"):
                        sub_input = ui.input(
                            placeholder="Paste full path to submission folder...",
                        ).props('style="font-size: 16px; flex: 1;"').classes("flex-1")

                        def _browse_folder():
                            import subprocess as _sp
                            try:
                                res = _sp.run(
                                    ["osascript", "-e",
                                     'POSIX path of '
                                     '(choose folder with prompt "Select submission folder")'],
                                    capture_output=True, text=True, timeout=30,
                                )
                                path = res.stdout.strip()
                                if path:
                                    sub_input.value = path
                            except Exception:
                                ui.notification(
                                    "Paste the folder path manually.", type="info"
                                )

                        _small_btn("Browse", MUTED, _browse_folder)

                # Report Export Location card (Optional Override)
                with _card():
                    ui.label("Report Output Location (Optional)").classes("text-lg font-semibold")
                    ui.label(
                        "Choose where HTML & PDF reports are saved (defaults to submission folder)."
                    ).classes("text-sm").style(f"color: {MUTED}")

                    with ui.row().classes("w-full items-center gap-2"):
                        out_dir_input = ui.input(
                            placeholder="Defaults to submission folder...",
                        ).props('style="font-size: 16px; flex: 1;"').classes("flex-1")

                        def _browse_out_dir():
                            import subprocess as _sp
                            try:
                                res = _sp.run(
                                    ["osascript", "-e",
                                     'POSIX path of '
                                     '(choose folder with prompt "Select report output folder")'],
                                    capture_output=True, text=True, timeout=30,
                                )
                                path = res.stdout.strip()
                                if path:
                                    out_dir_input.value = path
                            except Exception:
                                ui.notification(
                                    "Paste the folder path manually.", type="info"
                                )

                        _small_btn("Browse", MUTED, _browse_out_dir)

            # ── Right column ──────────────────────────────────────
            with ui.column().classes("flex-1 gap-6 min-w-0"):
                # Saved Reports Vault Card (Visible to all users)
                with _card():
                    with ui.row().classes("w-full justify-between items-center mb-1"):
                        with ui.row().classes("items-center gap-2"):
                            ui.html('''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2">
                                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                                <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
                            </svg>''')
                            ui.label("Saved Reports & Output Vault").classes("text-lg font-bold text-gray-900 dark:text-white")
                        
                        def _trigger_refresh_vault():
                            _refresh_vault_list()

                        ui.button(icon="refresh", on_click=_trigger_refresh_vault).props("flat round size=sm color=primary").classes("hover:rotate-180 transition-transform")

                    ui.label("Access, preview, and download all your historical compliance evaluation reports.").classes("text-xs text-gray-500 mb-4")

                    vault_list_container = ui.column().classes("w-full gap-2 max-h-72 overflow-y-auto")

                    def _refresh_vault_list():
                        vault_list_container.clear()
                        runs = auth.list_audit_runs(user_id=state.active_user_id)
                        if not runs:
                            with vault_list_container:
                                ui.label("No saved reports yet. Run a compliance check to generate outputs.").classes("text-xs text-gray-400 italic p-4 text-center w-full")
                            return

                        with vault_list_container:
                            for r in runs:
                                with ui.row().classes("w-full items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-700/50 border border-gray-200/60 dark:border-gray-600/60 hover:border-emerald-500/50 transition-all"):
                                    with ui.column().classes("gap-0 flex-1 min-w-0 pr-2"):
                                        ui.label(r["rfp_filename"]).classes("font-semibold text-xs truncate text-gray-900 dark:text-gray-100")
                                        ui.label(r["created_at"][:19].replace("T", " ")).classes("text-[10px] text-gray-400")

                                    score_val = r.get("score", 0.0)
                                    score_bg = "bg-emerald-500" if score_val >= 80 else ("bg-amber-500" if score_val >= 50 else "bg-rose-500")
                                    ui.label(f"{score_val:.0f}%").classes(f"text-[10px] font-black px-2 py-0.5 rounded-full text-white {score_bg}")

                                    report_path = r.get("report_path", "")
                                    with ui.row().classes("items-center gap-1"):
                                        if report_path and Path(report_path).exists():
                                            def _view_report(p=report_path):
                                                with ui.dialog() as dlg, ui.card().classes("w-[95vw] max-w-6xl h-[90vh] p-4 bg-white dark:bg-gray-900"):
                                                    with ui.row().classes("w-full justify-between items-center pb-2 border-b"):
                                                        ui.label("Compliance Report Preview").classes("font-bold text-lg")
                                                        ui.button(icon="close", on_click=dlg.close).props("flat round")
                                                    try:
                                                        html_content = Path(p).read_text(encoding="utf-8")
                                                        ui.html(html_content).classes("w-full h-full overflow-auto")
                                                    except Exception as err:
                                                        ui.label(f"Could not load report content: {err}")
                                                dlg.open()

                                            ui.button(icon="visibility", on_click=_view_report).props("flat round color=primary size=sm")
                                            
                                            def _dl_report(p=report_path):
                                                ui.download(p)
                                            ui.button(icon="download", on_click=_dl_report).props("flat round color=positive size=sm")

                    _refresh_vault_list()

                # Model Selection card (Admin Only)
                if is_admin:
                    with _card():
                        ui.label("Model Selection (Admin Override)").classes("text-lg font-semibold")
                        ui.label("Configure active LLM model:").classes("text-sm").style(f"color: {MUTED}")
                        
                        cfg = config_manager.load_config()
                        configured_model = cfg.get("model", config_manager.DEFAULT_MODEL)
                        
                        options = PRESET_MODELS
                        if configured_model not in options:
                            options.append(configured_model)
                            
                        def _on_model_change(e):
                            if e.value:
                                state.manual_model_select = True

                        model_dropdown = ui.select(
                            options=options,
                            value=configured_model,
                            on_change=_on_model_change
                        ).props('style="width: 100%; font-size: 16px;"').classes("w-full")
                        
                        recommendation_label = ui.label("Default: gemini-3.6-flash").classes("text-xs mt-1").style(
                            f"color: {MUTED}; font-style: italic;"
                        )
                else:
                    model_dropdown = None
                    recommendation_label = None


                # Run + Cancel buttons
                with ui.row().classes("w-full gap-2"):
                    with ui.column().classes("flex-1"):
                        def _run_clicked():
                            ui.timer(0.01, _run_async, once=True)

                        main_btn = _primary_btn("Run Compliance Check", EMERALD, _run_clicked)

                    with ui.column():
                        def _cancel_clicked():
                            state.cancel_requested = True
                            ui.notification("Cancelling...", type="warning")

                        cancel_btn = _small_btn("Cancel", CANCEL, _cancel_clicked)
                        cancel_btn.bind_enabled_from(state, "running")

                # Activity panel
                with _card():
                    with ui.row().classes("w-full items-center justify-between mb-3"):
                        ui.label("Activity Log").classes("text-lg font-bold").style(f"color: {CHARCOAL}")
                        _small_btn("Copy Log", CHARCOAL, _copy_log)

                    # Prominent Segmented Pill Control for View Modes
                    with ui.row().classes("w-full items-center justify-start gap-2 mb-3 p-1.5 rounded-full").style("background-color: #EFEFEF;"):
                        view_state = {"mode": "narrated"}

                        def _set_view(mode: str):
                            view_state["mode"] = mode
                            if mode == "narrated":
                                narrated_btn.props(f'unelevated style="font-size: 13px; font-weight: 700; padding: 6px 22px; background-color: {LIME} !important; color: {CHARCOAL} !important; border-radius: 9999px; border: none; box-shadow: 0 2px 8px rgba(204, 244, 88, 0.4);"')
                                technical_btn.props(f'unelevated style="font-size: 13px; font-weight: 600; padding: 6px 22px; background-color: transparent !important; color: {MUTED} !important; border-radius: 9999px; border: none;"')
                            else:
                                narrated_btn.props(f'unelevated style="font-size: 13px; font-weight: 600; padding: 6px 22px; background-color: transparent !important; color: {MUTED} !important; border-radius: 9999px; border: none;"')
                                technical_btn.props(f'unelevated style="font-size: 13px; font-weight: 700; padding: 6px 22px; background-color: {LIME} !important; color: {CHARCOAL} !important; border-radius: 9999px; border: none; box-shadow: 0 2px 8px rgba(204, 244, 88, 0.4);"')

                            if narrated_column is not None:
                                narrated_column.style("display: " + ("flex" if mode == "narrated" else "none"))
                            if log_column is not None:
                                log_column.style("display: " + ("flex" if mode == "technical" else "none"))

                        narrated_btn = ui.button("Narrated", on_click=lambda: _set_view("narrated")).props(
                            f'unelevated style="font-size: 13px; font-weight: 700; padding: 6px 22px; '
                            f'background-color: {LIME} !important; color: {CHARCOAL} !important; border-radius: 9999px; border: none; box-shadow: 0 2px 8px rgba(204, 244, 88, 0.4);"'
                        )
                        technical_btn = ui.button("Technical", on_click=lambda: _set_view("technical")).props(
                            f'unelevated style="font-size: 13px; font-weight: 600; padding: 6px 22px; '
                            f'background-color: transparent !important; color: {MUTED} !important; border-radius: 9999px; border: none;"'
                        )

                    log_scroll = ui.scroll_area().props(
                        'style="min-height: 300px; max-height: 400px; '
                        'border: 1px solid #E3E1DA; '
                        'border-radius: 8px; padding: 8px 12px;"'
                    ).classes("w-full")
                    with log_scroll:
                        narrated_column = ui.column().classes("w-full gap-0")
                        ui.label(
                            "Activity will appear here once you run a compliance check."
                        ).style(f"color: {MUTED}; font-size: 14px; font-style: italic;")
                        log_column = ui.column().classes("w-full gap-0").style("display: none;")
                        ui.label(
                            "Logs will appear here once you run a compliance check."
                        ).style(f"color: {MUTED}; font-size: 13px; font-style: italic;")

                # Result links
                result_container = ui.column().classes("w-full gap-2")

        # ── Footer ─────────────────────────────────────────────────
        with ui.row().classes("w-full items-center justify-center mt-8 pt-4").style(
            f"border-top: 1px solid {BORDER};"
        ):
            ui.label("MIT License © Zeeshan Mustafa").classes(
                "text-xs font-semibold tracking-wider"
            ).style(f"color: {MUTED};")





# ═══════════════════════════════════════════════════════════════════
# Background analysis
# ═══════════════════════════════════════════════════════════════════

def _cancel_check():
    if state.cancel_requested:
        raise RuntimeError("Cancelled by user")


def _rfp_progress(filename: str, current: int, total: int):
    if current == 1:
        _log(f"   Processing {filename}: page {current}/{total}")
    elif current % 25 == 0:
        _log(f"   {filename}: page {current}/{total}")


def _sub_progress(filename: str, current: int, total: int):
    _log(f"   [{current}/{total}] {filename}")


def _run_blocking(
    rfp_path: str,
    sub_path: str,
    api_key: str,
    model: str,
    base_url: str,
    out_dir_override: str = "",
):
    """Heavy work — runs in a thread pool."""
    import datetime
    try:
        stem = Path(rfp_path).stem
        safe = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in stem
        )
        if out_dir_override and out_dir_override.strip():
            target_out_dir = Path(out_dir_override.strip()) / f"{safe}_compliance_report"
        else:
            target_out_dir = Path(sub_path) / f"{safe}_compliance_report"
        
        # Pre-flight check: verify write permission UPFRONT before spending time/tokens
        try:
            target_out_dir.mkdir(parents=True, exist_ok=True)
            test_file = target_out_dir / ".write_test"
            test_file.touch()
            test_file.unlink(missing_ok=True)
            out_dir = target_out_dir
        except (PermissionError, OSError):
            # Attempt to fix write permissions on the submission folder
            try:
                os.chmod(sub_path, 0o755)
                target_out_dir.mkdir(parents=True, exist_ok=True)
                test_file = target_out_dir / ".write_test"
                test_file.touch()
                test_file.unlink(missing_ok=True)
                out_dir = target_out_dir
                _log(f"   NOTICE: Granted write permission to target folder.")
            except (PermissionError, OSError):
                fallback_dir = Path.home() / ".bod" / "reports" / f"{safe}_compliance_report"
                fallback_dir.mkdir(parents=True, exist_ok=True)
                out_dir = fallback_dir
                _log(f"   WARN Target report folder is write-protected and permissions could not be updated.")
                _log(f"   Output reports (HTML & PDF) will be saved to: {fallback_dir}")

        _cancel_check()
        now = datetime.datetime.now().strftime("%H:%M:%S")
        _log(f"Compliance check started at {now}")
        _log(f"   RFP: {Path(rfp_path).name}")
        _log(f"   Folder: {Path(sub_path).name}")
        _log(f"   Target Output Dir: {out_dir}")
        _log("")
        _cancel_check()
        rfp_p = Path(rfp_path)
        if rfp_p.is_dir():
            _log(f"Extracting multiple RFP documents from folder: {rfp_p.name}...")
            rfp_docs = pdf_extractor.extract_directory(rfp_p, progress_callback=_rfp_progress)
            if not rfp_docs:
                raise ValueError(f"No supported RFP documents found in directory: {rfp_path}")
            _log(f"   OK {len(rfp_docs)} RFP file(s) found in folder")
            combined_text = []
            total_pages = 0
            all_failed = []
            for d in rfp_docs:
                tag = " (OCR)" if d.ocr_used else ""
                _log(f"     - {d.filename}: {d.total_pages}p{tag}")
                combined_text.append(f"=== RFP DOCUMENT: {d.filename} ===\n{d.text}")
                total_pages += d.total_pages
                all_failed.extend(d.failed_pages)
            rfp_doc = ExtractedDoc(
                filename=f"{rfp_p.name} (Folder: {len(rfp_docs)} docs)",
                text="\n\n".join(combined_text),
                total_pages=total_pages,
                ocr_used=any(d.ocr_used for d in rfp_docs),
                failed_pages=all_failed,
            )
        else:
            _log("Extracting RFP document...")
            rfp_doc = extract_file(rfp_path, progress_callback=_rfp_progress)
            _log(
                f"   OK {rfp_doc.filename} "
                f"({rfp_doc.total_pages} page{'s' if rfp_doc.total_pages != 1 else ''})"
            )
            if rfp_doc.failed_pages:
                _log(
                    f"   WARN {len(rfp_doc.failed_pages)} page(s) with low text"
                )

        _cancel_check()
        _log("Extracting submission documents...")
        docs = pdf_extractor.extract_directory(sub_path, progress_callback=_sub_progress)
        _log(f"   OK {len(docs)} file(s) found")
        for d in docs:
            tag = " (OCR)" if d.ocr_used else ""
            _log(f"     - {d.filename}: {d.total_pages}p{tag}")

        _cancel_check()
        _log("Initializing compliance engine...")
        engine = ComplianceEngine(
            base_url=base_url, api_key=api_key, model=model,
        )
        _log("   Engine ready")

        _cancel_check()
        progress_cb = _make_progress_callback()
        _log("Running compliance analysis...")
        report = engine.analyze(rfp_doc, docs, progress_callback=progress_cb)
        state.last_report = report
        state.report_criteria = [
            {
                "id": c.id,
                "rfp_page": c.rfp_page,
                "clause_num": c.rfp_clause_num,
                "clause_name": c.rfp_clause_name,
                "clause_text": c.rfp_clause_text,
                "comp_doc_name": c.comp_doc_name,
                "comp_page": c.comp_page,
                "status": c.status,
                "evidence": c.evidence,
                "notes": c.notes
            }
            for c in report.criteria
        ]

        c_count = sum(1 for c in report.criteria if c.status == "compliant")
        p_count = sum(1 for c in report.criteria if c.status == "partial")
        n_count = sum(1 for c in report.criteria if c.status == "non_compliant")
        u_count = sum(1 for c in report.criteria if c.status == "not_checked")

        _log(f"   OK {len(report.criteria)} criteria assessed")
        _log(f"     Compliant: {c_count}")
        _log(f"     Partial: {p_count}")
        _log(f"     Non-Compliant: {n_count}")
        _log(f"     Not Checked: {u_count}")
        _log(f"   Score: {report.overall_score:.0f}% ({len(report.gaps)} gap(s))")

        if progress_cb:
            total = len(report.criteria)
            progress_cb(4, f"Done — {c_count} of {total} requirements fully met, {p_count} partial, {n_count} gaps.", total, total)

        _log("Generating reports...")
        paths = save_reports(report, str(out_dir), rfp_filename=safe)
        _log(f"   OK HTML: {paths['html']}")
        if paths.get("pdf"):
            _log(f"   OK PDF:  {paths['pdf']}")
        else:
            _log("   WARN PDF skipped (Playwright not available)")

        state.html_report = paths["html"]
        state.output_dir = str(out_dir)
        state.summary = {
            "score": report.overall_score,
            "compliant": c_count,
            "partial": p_count,
            "non_compliant": n_count,
            "not_checked": u_count,
            "total": len(report.criteria),
            "gaps": len(report.gaps),
        }

        # Record in database for user history
        try:
            auth.record_audit_run(
                user_id=getattr(state, "active_user_id", 1),
                username=getattr(state, "active_username", "admin"),
                rfp_filename=Path(rfp_path).name,
                status="COMPLETED",
                score=report.overall_score,
                report_path=paths["html"],
            )
        except Exception as db_err:
            logger.error("Error recording audit run in DB: %s", db_err)

        _log("")
        _log("Compliance check complete")


    except Exception as exc:
        state.error = str(exc)
        error_code = getattr(exc, "error_code", "unknown")
        narrated_msg = {
            "no_criteria": "I couldn't find any requirements in this document \u2014 it may be scan-only, or my OCR pass came back empty.",
            "api_rejected": "The API rejected the request \u2014 check your API key and model name in Settings.",
            "ocr_failed": "I couldn't read some pages \u2014 the document may be encrypted or scanned with poor quality.",
            "timeout": "The request timed out \u2014 try a smaller document or check your network connection.",
            "cancelled": "Cancelled \u2014 I'll stop here.",
        }.get(error_code, f"Something went wrong \u2014 {exc}")

        progress_cb = _make_progress_callback()
        progress_cb(4, narrated_msg, 0, 0)
        _log(f"Error: {exc}")


async def _run_test_async():
    global test_btn, test_log
    cfg = config_manager.load_config()
    key = cfg.get("api_key", "")
    model = cfg.get("model", config_manager.DEFAULT_MODEL)
    base_url = cfg.get("base_url", config_manager.DEFAULT_BASE_URL)

    if not key:
        if test_log:
            test_log.push("No API key saved. Save configuration first.")
        return

    if test_btn:
        test_btn.disable()
        test_btn.props('style="opacity: 0.6;"')
    if test_log:
        test_log.clear()
        test_log.push(f"Testing: {base_url}")
        test_log.push(f"   Model: {model}")
        test_log.push("   Sending test message...")

    try:
        import httpx
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body: dict = {
            "model": model,
            "messages": [{"role": "user", "content": "Say hello in one word."}],
            "max_tokens": 50,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]["content"]
            if test_log:
                test_log.push(f"API responded: \"{reply.strip()}\"")
                test_log.push("Connection OK")
            ui.notification("Connection successful!", type="positive")
        else:
            err = resp.text[:200]
            if test_log:
                test_log.push(f"HTTP {resp.status_code}: {err}")
            ui.notification(f"API error: {resp.status_code}", type="negative")
    except Exception as exc:
        if test_log:
            test_log.push(f"{exc}")
        ui.notification(f"Connection failed: {exc}", type="negative")
    finally:
        if test_btn:
            test_btn.enable()
            test_btn.props(f'style="background-color: {NAVY}; color: white; '
                           'font-size: 14px; padding: 8px 16px; border-radius: 8px;"')


def _render_eval_matrix(metrics):
    if eval_kpi_f1 is not None:
        eval_kpi_f1.set_text(f"{metrics.f1_score:.1f}%")
    if eval_kpi_exact is not None:
        eval_kpi_exact.set_text(f"{metrics.exact_match_pct:.1f}% ({metrics.exact_matches}/{metrics.total_evals})")
    if eval_kpi_intel is not None:
        eval_kpi_intel.set_text(f"{metrics.intention_score:.1f}% / {metrics.intelligence_mapping_score:.1f}%")
    if eval_kpi_latency is not None:
        eval_kpi_latency.set_text(f"{metrics.total_latency_ms:.0f}ms (S1:{metrics.stage1_latency_ms:.0f}ms | S2:{metrics.stage2_latency_ms:.0f}ms)")
    if eval_kpi_drift is not None:
        sign = "+" if metrics.model_drift_delta >= 0 else ""
        eval_kpi_drift.set_text(f"{sign}{metrics.model_drift_delta:.1f}% vs {metrics.previous_model}")

    if eval_matrix_container is None:
        return
    eval_matrix_container.clear()
    with eval_matrix_container:
        with ui.card().props(f'style="background: white; border: 1px solid {BORDER}; border-radius: 16px; padding: 24px; width: 100%; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);"'):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("EVALUATION & BENCHMARK MATRIX").classes("text-xl font-bold").style(f"color: {INK}")
                ui.button(
                    "Export Markdown for LLM Evaluator",
                    on_click=_export_markdown_for_llm,
                ).props(
                    f'unelevated style="background-color: {CHARCOAL} !important; color: white !important; '
                    f'font-size: 13px; font-weight: 600; padding: 8px 18px; border-radius: 9999px; border: none;"'
                )
            with ui.column().classes("w-full gap-4"):
                for r in metrics.rows:
                    bg_card = "#F8FAF9" if r.status_match else "#FFF1F2"
                    border_card = "#6EE7B7" if r.status_match else "#FDA4AF"
                    with ui.card().props(f'style="background: {bg_card}; border: 1px solid {border_card}; border-radius: 12px; padding: 20px; width: 100%;"'):
                        # Header row
                        with ui.row().classes("w-full items-center justify-between pb-3 border-b mb-3").style(f"border-color: {border_card};"):
                            with ui.row().classes("items-center gap-3"):
                                ui.label(r.req_id).classes("font-extrabold text-lg px-3 py-1 rounded").style(f"background: #E2E8F0; color: {INK};")
                                ui.label(f"{r.clause_num} \u00b7 {r.clause_name}").classes("font-bold text-md").style(f"color: {INK};")
                            with ui.row().classes("items-center gap-2"):
                                match_text = "\u2714 EXACT MATCH" if r.status_match else "\u2718 MISMATCH"
                                match_color = EMERALD if r.status_match else CANCEL
                                ui.label(match_text).classes("font-extrabold text-md px-3 py-1 rounded-full text-white").style(f"background: {match_color};")
                                if r.intention_type != "verified_proof":
                                    ui.label(f"Flag: {r.intention_type}").classes("font-bold text-sm px-3 py-1 rounded-full").style("background: #FEF3C7; color: #B45309;")
                        # Two-column comparison grid inside card
                        with ui.row().classes("w-full gap-6"):
                            with ui.column().classes("flex-1 min-w-0"):
                                ui.label("RFP CLAUSE REQUIREMENT").classes("text-xs font-extrabold uppercase tracking-wider").style(f"color: {MUTED};")
                                ui.label(r.rfp_clause_text).classes("text-base leading-relaxed mt-1 font-medium").style(f"color: {INK};")
                            with ui.column().classes("flex-1 min-w-0 border-l pl-6").style(f"border-color: {BORDER};"):
                                ui.label("SUBMISSION EVIDENCE / BIDDER EXCERPT").classes("text-xs font-extrabold uppercase tracking-wider").style(f"color: {MUTED};")
                                ui.label(f'"{r.bidder_quote}"').classes("text-base leading-relaxed mt-1 italic").style(f"color: {INK};")
                                ui.label(f"Analysis Notes: {r.notes}").classes("text-sm mt-2 p-2 rounded bg-white font-normal").style(f"color: {MUTED}; border: 1px solid {BORDER};")
                        # Bottom row showing model vs ground truth verdicts
                        with ui.row().classes("w-full items-center justify-between mt-4 pt-3 border-t").style(f"border-color: {border_card};"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label("Model Verdict:").classes("font-bold text-sm").style(f"color: {MUTED};")
                                model_col = EMERALD if r.model_status == "compliant" else ("#D97706" if r.model_status == "partial" else CANCEL)
                                ui.label(r.model_status.upper()).classes("font-extrabold text-sm px-3 py-1 rounded text-white").style(f"background: {model_col};")
                            with ui.row().classes("items-center gap-2"):
                                ui.label("Ground Truth Expected:").classes("font-bold text-sm").style(f"color: {MUTED};")
                                gt_col = EMERALD if r.expected_status == "compliant" else ("#D97706" if r.expected_status == "partial" else CANCEL)
                                ui.label(r.expected_status.upper()).classes("font-extrabold text-sm px-3 py-1 rounded text-white").style(f"background: {gt_col};")


def _run_evals_blocking(api_key: str, model: str, base_url: str, target: str):
    from EVAL.eval_engine import EvalEngine
    engine = EvalEngine(base_url=base_url, api_key=api_key, model=model)
    def _cb(st, msg, cur, tot, metrics):
        _eval_log(msg)
        state.eval_progress_q.put((st, msg, cur, tot, metrics))
    report, metrics = engine.run_evals(target=target, progress_callback=_cb)
    return report, metrics


async def _run_evals_async():
    if state.evals_running:
        ui.notification("Evaluation check already running...", type="warning")
        return
    cfg = config_manager.load_config()
    key = cfg.get("api_key", "")
    model = cfg.get("model", config_manager.DEFAULT_MODEL)
    base_url = cfg.get("base_url", config_manager.DEFAULT_BASE_URL)
    if not key:
        ui.notification("No API key configured in Settings.", type="negative")
        return

    state.evals_running = True
    if eval_run_btn is not None:
        eval_run_btn.disable()
        eval_run_btn.props('style="opacity: 0.5;"')
    if eval_log is not None:
        eval_log.clear()
    if eval_matrix_container is not None:
        eval_matrix_container.clear()
        with eval_matrix_container:
            ui.label("Running benchmarks... Please wait for Stage 1 & 2 completion.").classes("text-lg italic py-8 text-center w-full").style(f"color: {MUTED}")

    _eval_log(f"Starting CheckMate Evaluation Suite ({state.selected_eval_target}) on {model}...")
    try:
        report, metrics = await asyncio.to_thread(_run_evals_blocking, key, model, base_url, state.selected_eval_target)
        ui.notification("Evaluation Suite completed successfully!", type="positive")
    except Exception as exc:
        _eval_log(f"Error running evaluation suite: {exc}")
        ui.notification(f"Eval error: {exc}", type="negative")
    finally:
        state.evals_running = False
        if eval_run_btn is not None:
            eval_run_btn.enable()
            suffix = "Synthetic Data" if state.selected_eval_target == "synthetic" else "Test 2"
            eval_run_btn.props(f'style="background-color: {EMERALD}; color: white; font-size: 18px; font-weight: bold; padding: 14px 28px; border-radius: 12px;"')
            eval_run_btn.set_text(f"▶ Run Evals on {suffix}")


async def _run_async():
    if state.running:
        ui.notification("Analysis already in progress", type="warning")
        return

    rfp = state.rfp_path
    if (not rfp or not Path(rfp).exists()) and rfp_input is not None:
        val = rfp_input.value.strip()
        if val and Path(val).exists() and Path(val).suffix.lower() in SUPPORTED_EXTENSIONS:
            _load_rfp(val)
            rfp = state.rfp_path

    sub = sub_input.value.strip() if sub_input is not None else ""

    if not rfp or not Path(rfp).exists():
        ui.notification("Select a valid RFP document first.", type="negative")
        return
    if not sub or not Path(sub).is_dir():
        ui.notification("Provide a valid submission folder path.", type="negative")
        return

    state.running = True
    state.error = None
    state.html_report = None
    state.output_dir = None
    state.summary = None
    state.report_criteria = []
    state.elapsed_seconds = 0
    state.last_log_time = time.time()
    state.log_entries = list()

    try:
        if narrated_column is not None:
            narrated_column.clear()
            with narrated_column:
                ui.label("Activity will appear here once you run a compliance check.").style(
                    f"color: {MUTED}; font-size: 14px; font-style: italic;"
                )
        if log_column is not None:
            log_column.clear()
        if log_scroll is not None:
            log_scroll.scroll_to(percent=100)

        if result_container is not None:
            result_container.clear()

        if main_btn is not None:
            main_btn.props("style=\"opacity: 0.6;\"")
            main_btn.disable()

        cfg = config_manager.load_config()
        api_key = cfg.get("api_key", "")
        model = model_dropdown.value if model_dropdown else cfg.get("model", config_manager.DEFAULT_MODEL)
        base_url = cfg.get("base_url", config_manager.DEFAULT_BASE_URL)

        out_dir_val = out_dir_input.value.strip() if out_dir_input is not None else ""

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _run_blocking, rfp, sub, api_key, model, base_url, out_dir_val,
        )
    except Exception as exc:
        state.error = str(exc)
        _log(f"Error: {exc}")
    finally:
        state.running = False
        state.cancel_requested = False

        if main_btn is not None:
            main_btn.props("style=\"opacity: 1;\"")
            main_btn.enable()

    if state.error:
        ui.notification(f"Analysis failed: {state.error}", type="negative")
        if result_container is not None:
            result_container.clear()
            with result_container:
                with _card():
                    ui.label("Analysis Failed").classes(
                        "text-lg font-semibold mb-2"
                    ).style(f"color: {CANCEL}")
                    ui.label(state.error).classes("text-sm").style(
                        f"color: {CANCEL}; white-space: pre-wrap; word-break: break-all;"
                    )
                    def _open_log_file():
                        import subprocess as _sp
                        _sp.Popen(["open", _log_file])
                    ui.button(
                        "View Log File", on_click=_open_log_file,
                    ).props(
                        f'unelevated style="background-color: {CHARCOAL} !important; color: white !important; '
                        f'font-size: 13px; font-weight: 600; padding: 8px 20px; border-radius: 9999px; border: none; margin-top: 8px;"'
                    )
    else:
        ui.notification("Compliance check complete!", type="positive")
        if result_container is not None:
            result_container.clear()
            with result_container:
                if state.summary:
                    s = state.summary
                    score = s["score"]
                    if score >= 70:
                        tier = "Strong Compliance"
                        tier_color = EMERALD
                    elif score >= 40:
                        tier = "Conditional \u2014 Gaps Remain"
                        tier_color = "#B8722A"
                    else:
                        tier = "At Risk \u2014 Action Required"
                        tier_color = CANCEL

                    with _card():
                        ui.label("Results Summary").classes(
                            "text-lg font-semibold mb-2"
                        )
                        with ui.row().classes("w-full items-center gap-4"):
                            ui.label(f"{score:.0f}%").style(
                                f"font-size: 48px; font-weight: 700; "
                                f"color: {tier_color}; font-variant-numeric: tabular-nums;"
                            )
                            with ui.column().classes("gap-0"):
                                ui.label(tier).style(
                                    f"color: {tier_color}; font-weight: 600; "
                                    f"font-size: 14px;"
                                )
                                ui.label(
                                    f"{s['total']} criteria, {s['gaps']} gap(s)"
                                ).style(
                                    f"color: {MUTED}; font-size: 12px;"
                                )

                        with ui.row().classes("w-full gap-4 mt-2"):
                            _stat_badge(f'{_icon("check-circle", 20, EMERALD)} {s["compliant"]}', EMERALD,
                                        "Compliant")
                            _stat_badge(f'{_icon("alert-triangle", 20, "#B8722A")} {s["partial"]}', "#B8722A",
                                        "Partial")
                            _stat_badge(f'{_icon("x-circle", 20, CANCEL)} {s["non_compliant"]}', CANCEL,
                                        "Non-Compliant")
                            _stat_badge(f'{_icon("search", 20, MUTED)} {s["not_checked"]}', MUTED,
                                        "Not Checked")

                def _export_reports_custom():
                    if not state.output_dir:
                        ui.notification("No report folder available.", type="warning")
                        return
                    import subprocess as _sp
                    import shutil
                    try:
                        res = _sp.run(
                            ["osascript", "-e",
                             'POSIX path of '
                             '(choose folder with prompt "Select folder to export compliance reports")'],
                            capture_output=True, text=True, timeout=60,
                        )
                        dest = res.stdout.strip()
                        if dest:
                            dest_path = Path(dest)
                            dest_path.mkdir(parents=True, exist_ok=True)
                            src_dir = Path(state.output_dir)
                            for file_path in src_dir.glob("*"):
                                if file_path.is_file():
                                    shutil.copy(file_path, dest_path)
                            ui.notification(f"Reports successfully exported to {dest}", type="positive")
                    except Exception as exc:
                        ui.notification(f"Export failed: {exc}", type="negative")

                with ui.row().classes("w-full gap-3 mt-4 items-center"):
                    if state.html_report:
                        def _open_html():
                            if state.html_report:
                                import webbrowser
                                webbrowser.open(f"file://{Path(state.html_report).resolve()}")
                        ui.button(
                            "Open HTML Report",
                            on_click=_open_html,
                        ).props(
                            f'unelevated style="background-color: {LIME} !important; color: {CHARCOAL} !important; '
                            f'font-size: 14px; font-weight: 700; padding: 10px 24px; border-radius: 9999px; border: none; box-shadow: 0 4px 12px rgba(204, 244, 88, 0.4);"'
                        )
                    if state.output_dir:
                        ui.button(
                            "Open Output Folder",
                            on_click=_open_folder,
                        ).props(
                            f'unelevated style="background-color: {CHARCOAL} !important; color: white !important; '
                            f'font-size: 14px; font-weight: 600; padding: 10px 24px; border-radius: 9999px; border: none;"'
                        )
                        ui.button(
                            "Export Reports to Folder...",
                            on_click=_export_reports_custom,
                        ).props(
                            f'unelevated style="background-color: {FOREST} !important; color: white !important; '
                            f'font-size: 14px; font-weight: 600; padding: 10px 24px; border-radius: 9999px; border: none;"'
                        )
                    ui.button(
                        "Export Markdown",
                        on_click=_export_markdown_for_llm,
                    ).props(
                        f'unelevated style="background-color: {CHARCOAL} !important; color: white !important; '
                        f'font-size: 14px; font-weight: 600; padding: 10px 24px; border-radius: 9999px; border: none;"'
                    )

                # Detailed Findings Direct UI Rendering
                if getattr(state, "report_criteria", []):
                    ui.label("Detailed Findings").classes("text-xl font-bold mt-6 mb-2").style(f"color: {CHARCOAL}")
                    for c in state.report_criteria:
                        status = c["status"]
                        if status == "compliant":
                            bg_color = "#F4FCE8"
                            border_color = LIME
                            text_color = FOREST
                            badge_bg = LIME
                            badge_fg = CHARCOAL
                            badge_text = "COMPLIANT"
                        elif status == "partial":
                            bg_color = "#FFFBEB"
                            border_color = "#FCD34D"
                            text_color = "#D97706"
                            badge_bg = "#FCD34D"
                            badge_fg = CHARCOAL
                            badge_text = "PARTIAL"
                        elif status == "non_compliant":
                            bg_color = "#FFF0F2"
                            border_color = "#FFB3BA"
                            text_color = CANCEL
                            badge_bg = CANCEL
                            badge_fg = WHITE
                            badge_text = "NON-COMPLIANT"
                        else:
                            bg_color = "#F8FAFC"
                            border_color = "#E2E8F0"
                            text_color = MUTED
                            badge_bg = MUTED
                            badge_fg = WHITE
                            badge_text = "NOT CHECKED"

                        with ui.card().props(f'style="background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 16px; padding: 20px; width: 100%; box-shadow: 0 4px 15px rgba(11, 9, 10, 0.03);"').classes("mb-4"):
                            with ui.row().classes("w-full justify-between items-center"):
                                ui.label(f"Clause {c['clause_num']}: {c['clause_name']}").classes("font-bold text-base").style(f"color: {CHARCOAL}")
                                ui.label(badge_text).classes("text-xs font-extrabold px-3 py-1 rounded-full").style(f"background-color: {badge_bg}; color: {badge_fg};")
                            
                            ui.separator().classes("my-2").style("opacity: 0.1;")
                            
                            with ui.column().classes("w-full gap-2 text-sm"):
                                with ui.row().classes("w-full items-start"):
                                    ui.label("RFP Requirement:").classes("font-semibold min-w-[130px]").style(f"color: {MUTED}")
                                    rfp_page_txt = f" [Page {c.get('rfp_page', 'N/A')}]" if c.get('rfp_page') else ""
                                    ui.label(f"{c['clause_text']}{rfp_page_txt}").classes("flex-1 font-medium").style(f"color: {INK}")
                                    
                                with ui.row().classes("w-full items-start"):
                                    ui.label("Submission Ref:").classes("font-semibold min-w-[130px]").style(f"color: {MUTED}")
                                    if status == "non_compliant":
                                        ui.label(f"Not Found in Submission (RFP Ref: Page {c.get('rfp_page', 'N/A')})").classes("flex-1 italic font-semibold").style(f"color: {CANCEL}")
                                    elif status == "not_checked":
                                        ui.label(f"Skipped / Unverified (RFP Ref: Page {c.get('rfp_page', 'N/A')})").classes("flex-1 italic").style(f"color: {MUTED}")
                                    else:
                                        doc_name = c.get("comp_doc_name", "N/A")
                                        comp_page_str = f"Page {c.get('comp_page')}" if c.get("comp_page") else "N/A"
                                        ui.label(f"{doc_name} — {comp_page_str}").classes("flex-1 font-semibold").style(f"color: {EMERALD}")

                                if c['evidence']:
                                    with ui.row().classes("w-full items-start"):
                                        ui.label("Extracted Evidence:").classes("font-semibold min-w-[130px]").style(f"color: {MUTED}")
                                        ui.label(f'"{c["evidence"]}"').classes("flex-1 italic").style(f"color: {INK}")
                                        
                                if c['notes']:
                                    with ui.row().classes("w-full items-start"):
                                        ui.label("Audit Review Notes:").classes("font-semibold min-w-[130px]").style(f"color: {MUTED}")
                                        ui.label(c['notes']).classes("flex-1").style(f"color: {text_color}")


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    ui.run(
        title="CheckMate — RFP Compliance Checker Web",
        favicon="✅",
        dark=False,
        reload=False,
        native=False,
        storage_secret="checkmate_super_secret_session_key_2026",
        host="0.0.0.0",
        port=8765,
    )




if __name__ == "__main__":
    main()

