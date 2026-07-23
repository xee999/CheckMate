# CheckMate — Strict Evaluation Suite & Maximum-Space GUI Design

**Date**: 2026-07-15  
**Status**: Approved  
**Topic**: Strict Evals, Synthetic Edge-Case Dataset, and Live GUI Dashboard

---

## 1. Executive Summary
CheckMate requires a rigorous evaluation framework (`EVAL/` folder) to systematically verify stage-by-stage pipeline accuracy, detect model regression and drift, audit token count and latency, and stress-test known edge cases in extraction and multi-agent requirement auditing. Furthermore, the application requires an interactive, maximum-space live Evaluation Dashboard (Option A) inside `main.py` where users can execute synthetic benchmarks and inspect rich comparison matrices in real time, formatted with a clean, high-contrast, large-font light theme.

---

## 2. Synthetic Evaluation Suite (`EVAL/` Folder)

### 2.1 Directory Structure
```
EVAL/
├── __init__.py
├── eval_engine.py             # Core benchmark runner and metrics calculator
├── synthetic_generator.py     # Generates synthetic RFP & proposal documents
├── data/
│   ├── synthetic_rfp.py       # Raw text/data definitions for edge cases
│   ├── ground_truth.json      # Expected criteria IDs, statuses, quotes, and scores
│   ├── generated/             # Runtime destination for generated test PDFs/files
│   └── history.json           # Historical drift logs across runs and models
```

### 2.2 Synthetic Edge-Case Coverage
1. **Extraction Edge Cases (`Stage 1`)**:
   - **OCR/Scan Blocks**: Simulated low-text or noisy OCR pages (`--- PAGE X ---`).
   - **Missing Page Markers**: Chunks without explicit header markers.
   - **Complex Numbering & Clause Styles**: `Section III.A`, `Clause 3.1.2.4`, multiline headings, and embedded markdown tables.
2. **Matching & Auditing Edge Cases (`Stage 2`)**:
   - **Blank / Unfilled Templates**: Bidder submits empty form (`[Insert Tax ID here]`). Expected verdict: `non_compliant`.
   - **Vague Future Promises**: Bidder states *"We will provide FBR tax returns upon contract signing"*. Expected verdict: `partial` or `non_compliant`.
   - **Exact Verbatim Proof**: Bidder provides exact FBR NTN registration number and audited figures. Expected verdict: `compliant`.
   - **Subtle Mismatch**: Wrong years or expired certifications. Expected verdict: `non_compliant`.

---

## 3. Evaluation Metrics & Engine (`EVAL/eval_engine.py`)

### 3.1 Metrics Tracked
- **Accuracy & F1 Score**: Precision, recall, exact match percentage, and status confusion matrix (`compliant`, `partial`, `non_compliant`).
- **Intelligence Mapping & Intention**: Scores whether the Auditor and Reviewer sub-agents successfully mapped exact quotes (`evidence`) to the correct section headings (`rfp_section`, `comp_section`) and distinguished tangible proof from boilerplate promises.
- **Token Count & Latency**: Measures exact duration ($\text{ms}$) across Stage 1, Stage 2 (`Auditor` and `Reviewer` calls), and Stage 3. Estimates prompt/completion tokens per requirement.
- **Model Regression & Drift**: Compares current score against historical baseline stored in `history.json` (e.g. `gemini-2.5-pro` vs `deepseek-v4-flash-free`).

---

## 4. Maximum-Space Live Evaluation GUI (`main.py`)

### 4.1 Navigation & Screen Layout
- **Navbar Entry**: Adds an **`Evals`** tab button next to `Settings` in the top header bar (`state.show_evals = True`).
- **Full Viewport Utilization**: Uses `w-full max-w-none px-8 py-6` to ensure the live evaluation dashboard spans the maximum screen width and height.

### 4.2 Dashboard Components
1. **Summary Stat Strip**: Cards displaying `Overall F1 Score`, `Avg Latency / Req`, `Estimated Tokens`, `Exact Match %`, and `Model Drift Delta`.
2. **Action Bar**: Prominent primary button **"Run Evals on Synthetic Data"** (`_primary_btn`) with model selector dropdown and cancel control.
3. **Split Live Execution Window**:
   - **Left Panel (40% width)**: Real-time multi-stage progress indicator and streaming log console (`ui.log()` with `min-height: 550px`, custom styling for readability).
   - **Right Panel (60% width)**: Real-time **Evaluation Comparison Matrix** table showing side-by-side results as each synthetic requirement is assessed.

---

## 5. Report & Matrix Optimization (Large Fonts & Aesthetic Light Theme)

### 5.1 Aesthetic Light Theme Design System
- **Canvas & Cards**: Off-white background (`#FAFAF7`) with pure white (`#FFFFFF`) cards, soft borders (`#E3E1DA`), and subtle drop-shadows.
- **Typography & Font Scaling**:
  - `Inter` / `Outfit` modern sans-serif typography.
  - **Body text**: Increased to `18px` (`line-height: 1.6`) for maximum readability.
  - **Table headers**: `20px` bold uppercase headers.
  - **Section headers**: `28px` to `36px` clear titles.
- **Status Pills & Color Contrast**:
  - **Compliant**: Emerald `#10B981` pill with white bold text (`font-size: 16px`).
  - **Partial**: Amber `#F59E0B` pill with dark ink bold text (`font-size: 16px`).
  - **Non-Compliant / Gaps**: Rose `#F43F5E` pill with white bold text (`font-size: 16px`).

### 5.2 Criteria & Evaluation Matrix Layout
- Structured HTML/CSS table layout with generous cell padding (`16px 20px`), alternating row backgrounds, and distinct borders.
- Columns: `Req ID & Section` | `RFP Clause Text` | `Bidder Quote / Evidence` | `Model Verdict` | `Ground Truth` | `Accuracy Status`.
