# CheckMate Project Documentation & Rules Log

This document serves as the master record of progress, architectural decisions, and design rules established for **CheckMate — Enterprise AI Tender & RFP Compliance Engine**.

## 1. Core Architecture & Philosophy
- **Privacy First (100% Local Execution):** CheckMate is designed to process highly confidential bid and tender documents without uploading raw files to external cloud servers. All initial OCR, table extraction, and heuristics are performed locally on the host machine.
- **Token Efficiency:** To minimize API costs (up to an 85% reduction), CheckMate uses local deterministic rules (TF-IDF vector pre-filtering, regex heuristics for "shall/must" clauses) and only forwards heavily semantic edge cases to the Gemini API.
- **Dynamic Model Routing:** Uses lightweight models (e.g., `gemini-3.5-flash-lite`) for rapid Boolean checks, and robust reasoning models (`gemini-3.1-pro`) for deep semantic evaluations.
- **Multi-File Indexing:** CheckMate recursively parses entire candidate submission directories (PDF, DOCX, XLSX) and cross-references them against either a single RFP document or a directory of multiple RFP section files.
- **Standalone Distribution:** The application is packaged into fully self-contained, offline-capable executables:
  - macOS: `installer/CheckMate-mac.dmg` (via `build/build_mac.py`)
  - Windows: `installer/CheckMate-windows.exe` (via `build/build_win.py`)

## 2. Design System & Theming ("Stratum AI")
All UI development must strictly adhere to the **Stratum AI** design guidelines. CheckMate uses `NiceGUI` (which relies on Quasar/Vue under the hood), requiring explicit overriding of default blue styles.

### Color Palette (Hex Codes Must Be Exact)
- **Primary Accent (Vibrant):** `#CCF458` (Neon Lime Green) — Active states, key metrics, primary buttons.
- **Secondary Accent (Deep):** `#34970D` (Forest Green) — Secondary data points, gradients, success states.
- **Primary Text & Dark Surfaces:** `#0B090A` (Deepest Charcoal) — Primary headings, dark panels, high-contrast text.
- **Light Surfaces:** Backgrounds use `#F1F4EE` or White `#FFFFFF`.

### UI Implementation Rules
- **No Quasar Default Colors:** Never use default `color="primary"` (Quasar Blue `#5898d4`).
- **Forcing Styles:** When styling `ui.button` or similar components, you **must** use the `unelevated` prop and include `!important` in inline CSS to prevent Quasar themes from overriding the Stratum AI palette.
  - *Example:* `ui.button('...').props('unelevated style="background-color: #CCF458 !important; color: #0B090A !important;"')`
- **Branding:** The footer must explicitly read **"Powered By Jazz Enterprise AI Studio"** (not Gemini), and include the copyright: **"MIT License © Zeeshan Mustafa"**.

## 3. Supported AI Models (Active Roster)
The Model Selection UI in `main.py` has been updated to reflect the most current API strings:
- **Gemini 3 Series:**
  - `gemini-3.6-flash` (Medium)
  - `gemini-3.5-flash` (Medium)
  - `gemini-3.5-flash-lite` (Fast/Checklists)
  - `gemini-3.1-pro` (High/Deep Reasoning)
  - `gemini-3.1-flash-lite` (Fast)
- **Gemini 2 Series:**
  - `gemini-2.5-pro`
  - `gemini-2.5-flash`
  - `gemini-2.5-flash-lite`
  - `gemini-2.0-flash`

## 4. Key Milestones Completed
1. **Engine Upgrades:**
   - Modified `_run_blocking` in `main.py` to support directory extraction for RFPs (previously only supported single PDF files).
   - Upgraded local OCR via `pypdfium2` and `pytesseract` to retain layout fidelity on scanned pages and complex tabular matrices.
2. **UI & Visual Overhaul:**
   - Redesigned the primary run button to correctly show disabled/enabled states with Stratum AI colors.
   - Audited and overrode all secondary export buttons ("Open HTML Report", "Open Output Folder", "Export Markdown", etc.) to strictly use the Stratum AI `!important` color scheme.
3. **Marketing & Pitch Assets:**
   - Built an interactive Executive Pitch single-page site (`checkmate_pitch.html`) featuring an interactive ROI calculator for tender generation, competitive matrix, and value pillars.
   - Generated a high-fidelity, print-ready PDF executive deck (`CheckMate_Executive_Pitch_Deck.pdf`).
4. **Cross-Platform Readiness:**
   - Populated the `WIN BOD` folder to prep for Windows compilation.
   - Authored the Windows-specific build prompt, ensuring instructions cover `bundled/tesseract/` inclusion for offline OCR and Playwright Chromium installations.

## 5. Ongoing Rules for Future Agents
- **Token Preservation:** Do not bypass the local TF-IDF pre-filtering logic in `compliance_engine.py` unless explicitly directed. LLM API calls must be reserved strictly for the heavily weighted semantic clauses, never raw document dumping.
- **Build Scripts:** Any new pip dependencies must be added to `requirements.txt` AND passed into the `hidden_imports` array within `build/build_mac.py` and `build/build_win.py`.
- **UI Modifications:** Always check the `_primary_btn` and `_small_btn` helper functions in `main.py` before creating raw `ui.button` instances. If creating a custom button, verify it respects the Stratum AI color palette and uses `unelevated` + `!important`.
