# CheckMate — RFP Compliance Checker

## Overview
CheckMate is a desktop application (built with NiceGUI) designed to check RFP (Request for Proposal) submissions for compliance. It processes an uploaded RFP document and a folder containing bidder proposal files, runs a multi-agent validation pipeline, and compiles a responsive cover report with a dark theme toggle and PDF printout via Playwright.

---

## Tech Stack
| Layer | Choice | Status / Details |
|-------|--------|------------------|
| **UI Framework** | NiceGUI (Python, running in local browser window) | Premium, modern custom interface with activity console and status orb |
| **Text Ingestion** | pdfplumber (text PDFs) + PyPDFium2 with concurrent OCR (Tesseract) | Parallelized page-by-page OCR fallback via `ThreadPoolExecutor` |
| **Verification Engine** | Multi-Agent Audit and Review panel (Auditor sub-agent + Reviewer sub-agent) | Full-context verification comparing requirements against complete submission text |
| **Parallelization** | Concurrent PDF page extraction and thread-safe API rate throttling | Thread-safe `RateLimiter` ensures safe concurrency under API limits |
| **Report Compiler** | HTML5 Cover Template + Markdown2 Parser (Table extensions) + Playwright Chromium | Clean styled report with responsive layout, custom typography, and dark mode |
| **Installer Compiler** | PyInstaller + sips + iconutil + hdiutil | Compiles signed macOS app bundles and drag-and-drop DMG installers |

---

## Current Architecture & Pipeline Flow

### 1. Stage 1 — Concurrent Text Ingestion
* **Parallel Pages**: Inside `pdf_extractor.py`, `ThreadPoolExecutor` processes PDF page rendering, text extraction, and OCR fallback concurrently.
* **OCR Fallback**: If a page yields fewer than 50 characters, Tesseract OCR is triggered for that page.
* **Extraction Result**: Cache file is written (`stage1_*.json`) with text hashes to support instant recovery.

### 2. Stage 2 — Multi-Agent Audit & Critique
* **Full Proposal Ingestion**: Instead of keyword chunking (BM25), the entire text of the submission documents is concatenated and annotated with page markers.
* **Auditor Sub-Agent**: Extracts evidence, references, and parses for completeness.
* **Reviewer Sub-Agent**: Critique layer that verifies the findings, enforces rules on dates/values/registries, and flags false-positives (boilerplate or empty templates).
* **Concurrency**: Evaluates requirements in parallel using a `ThreadPoolExecutor` throttled by a thread-safe `RateLimiter` (maintaining 13 RPM limits on free endpoints).

### 3. Stage 3 — Report Assembly & Print
* **Markdown Parser**: Uses `markdown2` with `tables` extensions to render LLM tables and formatted lists.
* **Branding & Theme**: Integrates CheckMate squircle checkmark logos, dark-theme layout buttons, and custom brand footers.
* **Playwright Compiler**: Spawns a headless Chromium instance to print the final HTML report into a pixel-perfect A4 PDF document.

---

## Module Map

| File | Purpose |
|------|---------|
| [main.py](file:///Users/Zeeshan/VibeCode/Bod/main.py) | NiceGUI layout, background analysis orchestration, log panels, orb presence indicator |
| [compliance_engine.py](file:///Users/Zeeshan/VibeCode/Bod/compliance_engine.py) | Stage 2 Multi-Agent executor, Auditor + Reviewer prompts, thread-safe API `RateLimiter` |
| [pdf_extractor.py](file:///Users/Zeeshan/VibeCode/Bod/pdf_extractor.py) | Concurrent page extraction, dual-pass OCR (Tesseract) |
| [report_generator.py](file:///Users/Zeeshan/VibeCode/Bod/report_generator.py) | Markdown-to-HTML parser, cover templates, dark theme toggles, Playwright PDF renderer |
| [config_manager.py](file:///Users/Zeeshan/VibeCode/Bod/config_manager.py) | Config manager for active endpoints, API keys, and model parameters |
| [build_mac.py](file:///Users/Zeeshan/VibeCode/Bod/build/build_mac.py) | DMG builder script and macOS `.icns` compiler |
