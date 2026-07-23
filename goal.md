# CheckMate — RFP Compliance Checker

## Goal
Build a cross-platform desktop application that takes an RFP PDF + submission folder → extracts all text (including parallel OCR) → analyzes compliance via a Multi-Agent Audit and Review panel using the OpenCode Zen API (or Google Gemini API) → outputs a beautiful, responsive HTML compliance report with a dark theme toggle and PDF printout via Playwright.

---

## Architecture
```
config_manager.py  ↔  compliance_engine.py  ↔  report_generator.py
      ↓                      ↓                        ↓
  config.json       Zen / Gemini API           HTML + Playwright PDF
      
pdf_extractor.py ← feeds → compliance_engine.py ← feeds → main.py (NiceGUI UI)
```

---

## Module Assignments & Status

| Module | Purpose | Status | File Path |
|--------|---------|--------|-----------|
| `config_manager.py` | Configuration storage and active profile loader | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/config_manager.py](file:///Users/Zeeshan/VibeCode/Bod/config_manager.py) |
| `pdf_extractor.py` | Concurrent page extraction, dual-pass OCR (Tesseract) | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/pdf_extractor.py](file:///Users/Zeeshan/VibeCode/Bod/pdf_extractor.py) |
| `compliance_engine.py` | Analysis pipeline, Auditor + Reviewer Multi-Agent panel, RateLimiter | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/compliance_engine.py](file:///Users/Zeeshan/VibeCode/Bod/compliance_engine.py) |
| `report_generator.py` | Markdown-to-HTML parser, cover templates, dark theme toggles, Playwright PDF renderer | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/report_generator.py](file:///Users/Zeeshan/VibeCode/Bod/report_generator.py) |
| `main.py` | NiceGUI desktop app UI, background execution progress monitoring | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/main.py](file:///Users/Zeeshan/VibeCode/Bod/main.py) |
| `requirements.txt` | Package dependencies | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/requirements.txt](file:///Users/Zeeshan/VibeCode/Bod/requirements.txt) |
| `build/build_mac.py` | Packages CheckMate as a macOS DMG and custom squircle icons | ✅ Completed | [/Users/Zeeshan/VibeCode/Bod/build/build_mac.py](file:///Users/Zeeshan/VibeCode/Bod/build/build_mac.py) |

---

## Data Contracts

### Config (~/.bod/config.json)
```json
{
  "api_key": "sk-...",
  "model": "model-name",
  "base_url": "https://opencode.ai/zen/v1"
}
```

### ExtractionResult
```python
@dataclass
class ExtractedDoc:
    filename: str
    text: str
    total_pages: int
    ocr_used: bool
    failed_pages: list[int]
```

### ComplianceReport
```python
@dataclass
class Criterion:
    id: str
    rfp_doc_name: str
    rfp_page: int
    rfp_section: str
    rfp_clause_num: str
    rfp_clause_name: str
    rfp_clause_text: str
    comp_doc_name: str
    comp_page: int
    comp_section: str
    comp_clause_num: str
    comp_clause_name: str
    status: str  # "compliant" | "partial" | "non_compliant" | "not_checked"
    evidence: str
    notes: str

@dataclass
class Gap:
    id: str
    severity: str  # "Critical" | "High" | "Medium" | "Low"
    description: str
    criterion_id: str

@dataclass
class ComplianceReport:
    rfp_title: str
    date: str
    overall_score: float
    criteria: list[Criterion]
    gaps: list[Gap]
    submission_summary: str
    section_commentaries: dict[str, str]
```

---

## UI/UX Styling Guidelines
- Clean, premium, state-of-the-art NiceGUI web interface.
- Vibrant color coding (Compliant = green, Partial = yellow, Non-Compliant = red).
- Modern dark mode toggle in report body.
- Real-time logging console panel with custom scrolling.

---

## Build Targets
- macOS: PyInstaller → app bundle + DMG installer (bundled Tesseract OCR + Playwright Chromium dependencies).
