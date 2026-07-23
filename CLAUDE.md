# CheckMate — Project Anchor

## What It Is
CheckMate is a desktop application (built with NiceGUI) designed to check RFP submission compliance. It processes an uploaded RFP PDF and a folder containing bidder proposal documents, running a multi-agent validation pipeline before compiling a structured, dark-mode-toggleable HTML/PDF report.

## Current State — 2026-07-15

### Pipeline (3 stages)
| Stage | What | Implementation / Tech |
|---|---|---|
| **Stage 1** | Text Extraction | Extract text from PDF/docx/xlsx using PyPDFium2 and `pdfplumber` with concurrent page-by-page OCR fallback via Tesseract (`ThreadPoolExecutor`). |
| **Stage 2** | Multi-Agent Audit | Multi-agent auditing panel (Auditor sub-agent scans context, Reviewer sub-agent performs a verification critique against strict standards, e.g. dates, registry IDs, certificates, and overrides blank templates) running concurrently via thread-safe `RateLimiter` throttling. |
| **Stage 3** | Report Generation | Assemble a responsive cover report with section commentary, compliance score matrix, dark-mode toggle, custom styling, and Playwright Chromium PDF compilation. |

### Architecture & Parallelization
1. **Parallel Extraction**: PDF pages are parsed and OCRed concurrently in `pdf_extractor.py`, speeding up text extraction by **3x to 6x**.
2. **Parallel Auditing**: Criteria checks run concurrently in a `ThreadPoolExecutor`. A thread-safe token-bucket `RateLimiter` throttles API requests to `13 RPM` on free endpoints to respect Gemini limits, while allowing instant concurrent execution on custom/paid endpoints.
3. **Multi-Agent Decoupling**: In Stage 2, evaluation is separated into two sub-agent prompts:
   * **Auditor Sub-Agent**: Extracts evidence, references, and parses for completeness.
   * **Reviewer Sub-Agent**: Critique layer that verifies the findings, enforces rules on dates/values/registries, and flags false-positives (boilerplate or empty templates).

### Key Files
| File | Purpose |
|------|---------|
| [main.py](file:///Users/Zeeshan/VibeCode/Bod/main.py) | App entry: UI layout, file managers, log panels, background orchestration |
| [compliance_engine.py](file:///Users/Zeeshan/VibeCode/Bod/compliance_engine.py) | Analysis pipeline, Auditor + Reviewer Multi-Agent panel, RateLimiter |
| [pdf_extractor.py](file:///Users/Zeeshan/VibeCode/Bod/pdf_extractor.py) | Concurrent page extraction, dual-pass OCR (Tesseract) |
| [report_generator.py](file:///Users/Zeeshan/VibeCode/Bod/report_generator.py) | Markdown-to-HTML parser, cover templates, dark theme toggles, Playwright PDF renderer |
| [config_manager.py](file:///Users/Zeeshan/VibeCode/Bod/config_manager.py) | Stores active endpoints, model definitions, and API keys |
| [build_mac.py](file:///Users/Zeeshan/VibeCode/Bod/build/build_mac.py) | Compiles DMG bundle and squircle Dock icons |

## Commands

### Setup & Run
* Run locally: `python3 main.py` (ensure virtual env at `temp/venv` is active)
* Compile macOS installer: `python3 build/build_mac.py`

### Testing
* Run syntax verification: `python3 -m py_compile compliance_engine.py pdf_extractor.py main.py`
