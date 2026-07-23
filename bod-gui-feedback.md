# Bod — GUI / UX / Feature Feedback

Reviewed: Main Screen and Settings screen (NiceGUI, macOS build) against `scope.md`.

---

## 1. Critical / Fix First

**1.1 — "Upload" metaphor is misleading**
The RFP panel uses a cloud-upload icon and shows "4.9MB / 0.00%" like a network transfer. This is a **local file picker**, not an upload — nothing leaves the machine at this stage. Users will assume it's hung when the % stays at 0.00. Relabel to "Select RFP PDF" and drop the progress-bar/percentage UI entirely for local file selection; only show progress once the file is actually being parsed (extraction phase).

**1.2 — Settings has no way back**
There's no back/cancel/close affordance on the Settings screen — no header nav, no "Back to Main," no X. If a user opens Settings from the main screen just to check something, they're stuck until they hit Save. Add a top-left back arrow or make Settings a modal/dialog over the main screen instead of a full page replacement.

**1.3 — Model field is free text**
`Model` is a plain text input pre-filled with `deepseek-v4-flash-free`. A typo here fails silently or produces a confusing API error deep in `compliance_engine.py`. Replace with a dropdown populated by hitting OpenCode Zen's `/models` endpoint (if it exists) or a curated list, with free text as an "advanced/custom" fallback only.

**1.4 — No "Test Connection" button**
Users won't know their API key/model/base URL are valid until they run a full compliance check (which may take minutes and burn tokens on a large RFP). Add a "Test Connection" button next to Save Configuration that does a cheap 1-token ping and shows ✅/❌ inline.

**1.5 — API key storage**
`config.json` stores the key in plain JSON in `~/.bod/`. Even for a local desktop tool, prefer the OS keychain (macOS Keychain via `keyring` package, Windows Credential Manager) over a plaintext file. At minimum, warn the user in the UI that the key is stored locally in plaintext.

---

## 2. Layout & Visual Design

- **Massive dead space.** On both screens, content is packed into the left ~40% of the window with a large empty void on the right. Either cap the window's max-width (center the content, ~900–1000px) or use the freed space productively (e.g., a live preview pane, recent-runs list, or criteria checklist).
- **No branding/icon.** Just text titles. A small logo/mark in the top-left next to "Bod" would help, especially since this will be a standalone .exe/.dmg with its own icon anyway — reuse it in-app.
- **Progress Log is a big empty gray box at rest.** Add placeholder text like "Logs will appear here once you run a compliance check" so it doesn't look broken/unfinished before first run.
- **Truncated folder path.** `/Users/Zeeshan/Desktop/B...` cuts off with no way to see the full path (no tooltip, no wrap). Add a hover tooltip showing the full path, and/or truncate from the middle (`...Desktop/BOI Compliance`) rather than the end, since the end is usually the more identifying part.
- **Settings fields lack helper text.** "Base URL" and "Model" assume the user already knows OpenCode Zen's conventions. Add small gray helper text under each field (e.g., "Format: provider/model-name" and a link to OpenCode Zen's docs for valid model IDs).
- **No visual state for "ready to run."** The Run Compliance Check button appears identically active whether or not an RFP + folder are actually selected. Disable it (grayed out) until both required inputs are present, and/or show inline validation ("Please select a submission folder").

---

## 3. Missing Functionality (relative to scope.md's own pipeline)

- **No stop/cancel button** once a run starts — for a multi-file OCR + multi-stage LLM pipeline, runs could take minutes; users need a way to abort.
- **No run history.** Given the app produces a report per run, keep a lightweight list of past runs (RFP name, date, score, link to report) so users don't have to dig through the filesystem. This also gives a natural use for that empty right-hand space.
- **No output location control.** Scope says reports are generated and the output folder is opened automatically, but there's no setting for *where* — default should be configurable (e.g., alongside the submission folder vs. a dedicated `~/Bod Reports/` folder).
- **No pre-run review of extracted criteria.** The pipeline extracts criteria from the RFP before checking compliance — surfacing that list to the user *before* the expensive evidence-search stage runs would let them catch extraction errors early (e.g., OCR garbling a clause) instead of finding out only in the final report.
- **No indication of scan quality / OCR fallback in the UI.** The extractor silently falls back from pdfplumber to OCR — the Progress Log should say when OCR kicked in per-page, since that correlates directly with the "🔍 Not Checked" status and users will want to know why.
- **No drag-and-drop for the submission folder** (only Browse), inconsistent with the RFP panel which does support drag-and-drop for a file. Folder drag-and-drop is supported in most desktop-shell-backed pickers; worth adding for consistency.
- **No dark mode.** Minor, but common expectation in 2026 desktop tooling, and NiceGUI supports it with little effort.
- **No "last used" memory.** Reopening the app should probably remember the last submission folder / RFP directory location as a starting point for Browse dialogs.

---

## 4. Error Handling & Edge Cases to Verify

- What happens if the submission folder contains non-PDF files, or PDFs that are corrupted/password-protected?
- What happens if the OpenCode Zen API returns a rate-limit or auth error mid-run — does the Progress Log surface a clear, actionable message, or does it just stop?
- What happens on a fully scanned (image-only) RFP with poor scan quality — does the UI communicate confidence, or does it silently produce a low-quality report?
- Playwright/Chromium PDF export failing (e.g., missing bundled binary on a stripped-down Windows install) — needs a clear fallback message, not a silent crash, given this is a bundled dependency that's a common source of PyInstaller packaging failures.

---

## 5. Prioritized Action List

1. Fix upload/local-file terminology and remove misleading progress % (1.1)
2. Add Settings back-navigation (1.2)
3. Add Test Connection button + model dropdown (1.3, 1.4)
4. Move API key to OS keychain, or disclose plaintext storage (1.5)
5. Disable Run button until required inputs are valid; add inline validation
6. Add cancel/stop for in-progress runs
7. Add run history panel (fills dead space, high user value)
8. Surface extracted criteria for review before the evidence-search stage
9. Center/cap layout width, add placeholder text to empty states
10. Dark mode + tooltip/truncation fixes (lower priority polish)

---

*Prepared for handoff to development. Each numbered item above can be turned into a standalone ticket against `main.py` (UI), `config_manager.py` (settings/storage), and `compliance_engine.py` (pipeline visibility hooks).*
