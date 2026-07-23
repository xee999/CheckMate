# CheckMate — Project Roadmap

This document outlines the strategic progression, completed milestones, and future initiatives for the **CheckMate Compliance Checker** application.

---

## 1. Completed Milestones (v1.0.0 Release)

### Brand Renaming & UX Identity
* **CheckMate Identity**: Re-branded the entire app to CheckMate. Developed custom Apple-style squircle icons.
* **Presence Narration**: Integrated a live activity progress bar and animated status orb to communicate current processing pages.
* **HTML/PDF Compiler**: Built a beautiful, clean styled cover report with a custom toggle for Dark/Light themes, sans-serif font pairing, and Playwright Chromium printout engine.

### Parallel Processing & Ingestion
* **Concurrent Page Processing**: Rewrote the PDF extraction layer using `ThreadPoolExecutor` to extract and run Tesseract OCR on page chunks in parallel. Speeds up ingestion by **3x to 6x**.
* **Sequential Thread-Safe API Requests**: Implemented a thread-safe token-bucket `RateLimiter` class to throttle parallel LLM requests and ensure compliance under 15 RPM free limits.

### Multi-Agent Auditing Panel
* **Auditor Sub-Agent**: Extracts raw quotes, references, pages, and registries from the complete submission text.
* **Reviewer Sub-Agent**: Evaluates findings, checks dates/values, and filters out false-positives (boilerplate or empty templates).

---

## 2. Near-Term Roadmap (v1.1.0)

### Advanced Document Formats
* **Excel Checklist Ingestion**: Support reading compliance checklist forms directly from `.xlsx` tables.
* **Table Extraction Improvements**: Deep parsing of structured complex pricing tables from scanned bidder submissions.

### Multi-Model Auditing & Redundancy
* **Joint Panel Decision Making**: Allow users to run dual-model review processes (e.g. running Flash for fast extraction, and Pro for critiquing verdicts).
* **API Key Manager**: Secure storage keychain integration to store keys natively.

---

## 3. Long-Term Strategy (v2.0.0)
* **Tender Collaboration Space**: Collaborative multi-user web environments where analysts can override and comment on LLM verdicts in real-time.
* **Active Feedback Learning**: Slash-command `/learn` integration to persist specific domain constraints, helping CheckMate learn custom evaluation policies.
