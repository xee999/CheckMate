"""compliance_engine.py — RFP compliance analysis engine for Bod."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import random
import time
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Literal, Optional

import httpx

from pdf_extractor import ExtractedDoc
from retriever import EvidenceRetriever

CACHE_DIR = Path.home() / ".bod" / "cache"

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[int, str, int, int], None]]


class BodError(Exception):
    def __init__(self, message: str, error_code: str = "unknown"):
        self.error_code = error_code
        super().__init__(message)


@dataclass
class Criterion:
    id: str
    
    # RFP Citing
    rfp_doc_name: str
    rfp_page: int
    rfp_section: str
    rfp_clause_num: str
    rfp_clause_name: str
    rfp_clause_text: str
    
    # Cross-referenced Submission Citing
    comp_doc_name: str
    comp_page: int
    comp_section: str
    comp_clause_num: str
    comp_clause_name: str
    
    # Compliance results
    status: Literal["compliant", "partial", "non_compliant", "not_checked"]
    evidence: str
    notes: str


@dataclass
class Gap:
    id: str
    severity: Literal["Critical", "High", "Medium", "Low"]
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
    commentary: str


_STAGE1_EXAMPLE = """{"criteria": [{"page": 4, "section_name": "Technical Proposal", "clause_number": "3.1.2", "clause_name": "Technical Approach", "clause_text": "Provide a detailed technical approach..."}]}"""

STAGE1_PROMPT = f"""Extract EVERY compliance criterion and requirement from the RFP text.

Look for page markers like "--- PAGE X ---" in the text to identify the page number for each requirement.
For each requirement, find the section heading it resides in, the clause number (e.g. 3.1.2 or Section III.A), the clause name/heading (e.g. Technical Approach), and the exact requirement text itself.

Return ONLY a JSON object with key "criteria" — an array of:
{{"page": page_number, "section_name": "section name", "clause_number": "clause number or N/A", "clause_name": "clause name or N/A", "clause_text": "extracted requirement text"}}

No markdown, no backticks, no explanation. Just raw JSON.

Example: {_STAGE1_EXAMPLE}"""

_STAGE2_EXAMPLE = """{"results": [{"clause_number": "Section 3.1.2", "status": "compliant", "evidence": "verbatim quote...", "doc_name": "Proposal.pdf", "page": 12, "section_name": "Technical Section", "clause_name": "Approach Details", "notes": "..."}]}"""

AUDITOR_PROMPT = """You are a senior compliance auditor sub-agent. Your task is to scan the provided proposal documents and extract any direct evidence or citations related to the given RFP requirement.

Identify:
1. The exact section, page, or table where this requirement is addressed.
2. The exact verbatim quote of the bidder's response or proof.
3. Check for tangible completion proof: Does the text contain actual dates, monetary values, registration IDs/NTN, completed tables, or specific listings of completed projects/deployments (with client names, project scopes, and completion years)? Or is it an unfilled blank template, an expired certificate, or a vague future promise?

Return ONLY a JSON object:
{
  "doc_name": "name of document or N/A",
  "page": 1,
  "section_name": "section name or N/A",
  "evidence": "exact verbatim quote from document or N/A",
  "has_tangible_proof": true or false,
  "findings": "summary of the findings regarding NTN/GST/dates/monetary values/certificates/project experience lists"
}

No markdown, no explanation. Just raw JSON."""

REVIEWER_PROMPT = """You are the Lead Proposal Reviewer sub-agent. Your task is to review the Auditor sub-agent's findings against the original RFP requirement and make the final compliance decision.

CRITICAL THREE-WAY STATUS DECISION — READ CAREFULLY:

**STATUS: "compliant"**
The bidder fully addressed the clause with verifiable, tangible proof:
- Specific numbers, percentages, dates, registration IDs, or certificate references
- Cited SLA documents, named projects with client names and completion years
- Architecture details that demonstrably satisfy the requirement

**STATUS: "partial"**
The bidder directly addressed the clause topic but provided no measurable proof, SLA, or metric:
- They mentioned the right subject areas (e.g. support, response time, security) but only in generic terms
- Vague language like "we are committed to...", "we aim to...", "we will provide outstanding..." without any numbers or binding commitments
- Restated the RFP's own language back without adding verifiable substance
- Missing ONE specific element but otherwise substantive (e.g. mentions redundancy but no SLA credits)
→ USE "partial" when the bidder ENGAGED with the requirement topic but did NOT provide sufficient verifiable evidence.

**STATUS: "non_compliant"**
The bidder failed to substantively engage with the requirement:
- Unfilled placeholder / blank template text (e.g. "[Insert ISO 27001 certificate number here]")
- "TBD", "To be confirmed", "Upon contract signing" for a mandatory requirement
- Submitted section is absent, off-topic, or directly contradicts the requirement
- Expired certificate without valid extension
→ USE "non_compliant" when the bidder FAILED TO ENGAGE at all — missing, blank, placeholder, or contradictory.

DOMAIN-SPECIFIC RULES:
1. Vague Promises: A response that echoes the RFP language ("outstanding support", "fast response") but adds NO specific SLA, tier, or metric = "partial", NOT "non_compliant".
2. Blank/Template responses: "[Insert...]" or "TBD" for a mandatory document = "non_compliant".
3. Expired Certificates: Past expiration without formal extension = "non_compliant".
4. Past Experience (Clause 6.1): Enumerated projects with client names, years, and scopes = "compliant". Do NOT penalize for repository-stored certificates if project details are listed.
5. Tax/Legal Registration: Valid registration numbers and active taxpayer status = "compliant".

Determine:
1. "status": "compliant", "partial", or "non_compliant"
2. "notes": "brief final justification explaining the assessment"

Return ONLY a JSON object:
{
  "status": "compliant/partial/non_compliant",
  "notes": "auditor notes"
}

No markdown, no explanation. Just raw JSON."""


import threading

class RateLimiter:
    def __init__(self, requests_per_minute: float):
        self.delay = 60.0 / requests_per_minute
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.delay:
                sleep_time = self.delay - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()


class ComplianceEngine:

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "opencode/deepseek-v4-flash-free",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        
        # Check if rate limiting is needed (for free tier or rate-limited endpoints)
        is_free_tier = (
            "free" in model.lower()
            or "flash" in model.lower()
            or "opencode" in self.base_url.lower()
            or "googleapis" in self.base_url.lower()
        )
        if is_free_tier:
            self.rate_limiter = RateLimiter(requests_per_minute=13.0)  # Safe buffer below 15 RPM
        else:
            self.rate_limiter = None

    # ── Public API ──────────────────────────────────────────────

    def analyze(
        self,
        rfp_doc: ExtractedDoc,
        submission_docs: list[ExtractedDoc],
        progress_callback: ProgressCallback = None,
    ) -> ComplianceReport:
        self.progress_callback = progress_callback
        rfp_title = rfp_doc.filename

        try:
            raw_criteria = self._extract_criteria(rfp_doc.text, rfp_doc.filename, progress_callback)
            if not raw_criteria:
                raise BodError(
                    "Failed to extract any criteria from the RFP document",
                    error_code="no_criteria",
                )

            criteria = self._check_criteria(raw_criteria, submission_docs, progress_callback)

            compliant_count = sum(
                1 for c in criteria if c.status == "compliant"
            )
            partial_count = sum(
                1 for c in criteria if c.status == "partial"
            )
            non_compliant_count = sum(
                1 for c in criteria if c.status == "non_compliant"
            )
            total = len(criteria)
            overall_score = round(
                (compliant_count / total) * 100.0 if total else 0.0, 1
            )

            gaps = self._identify_gaps(criteria)

            submission_summary = self._build_summary(submission_docs)

            # Generate the section commentary using LLM
            if progress_callback:
                progress_callback(4, "Generating section-by-section compliance commentary...", total, total)
            commentary = self._generate_commentary(criteria)

            if progress_callback:
                progress_callback(
                    4,
                    f"Done — {compliant_count} of {total} requirements fully met, "
                    f"{partial_count} partial, {non_compliant_count} gaps.",
                    total,
                    total,
                )

            return ComplianceReport(
                rfp_title=rfp_title,
                date=date.today().isoformat(),
                overall_score=overall_score,
                criteria=criteria,
                gaps=gaps,
                submission_summary=submission_summary,
                commentary=commentary,
            )

        except BodError:
            raise
        except Exception as exc:
            error_code, message = self._classify_error(exc)
            raise BodError(message, error_code=error_code) from exc

    # ── Cache helpers ───────────────────────────────────────────

    @staticmethod
    def _ensure_cache_dir():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _save_cache(cache_key: str, data: object):
        ComplianceEngine._ensure_cache_dir()
        path = CACHE_DIR / cache_key
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def _load_cache(cache_key: str) -> object | None:
        path = CACHE_DIR / cache_key
        if not path.exists():
            return None
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def _save_text(text: str, filename: str):
        ComplianceEngine._ensure_cache_dir()
        path = CACHE_DIR / filename
        with open(path, "w") as f:
            f.write(text)

    # ── Stage 1 — Extract criteria (chunked) ────────────────────

    def _extract_criteria(
        self,
        rfp_text: str,
        rfp_filename: str,
        progress_callback: ProgressCallback = None,
    ) -> list[dict]:
        text_hash = self._content_hash(rfp_text)

        cached = self._load_cache(f"stage1_{text_hash}.json")
        if cached is not None and isinstance(cached, list) and len(cached) > 0:
            logger.info("Stage 1 cache hit (%d criteria)", len(cached))
            for item in cached:
                item["doc_name"] = rfp_filename
            if progress_callback:
                progress_callback(
                    2, f"Loaded {len(cached)} requirements from cache.",
                    len(cached), 0,
                )
            return cached

        self._save_text(rfp_text, f"rfp_text_{text_hash}.txt")

        if progress_callback:
            progress_callback(2, "Reading the RFP to find requirements...", 0, 0)

        # Check if we should use single-call criteria extraction (Gemini/Google models or small RFPs)
        is_large_context = "gemini" in self.model.lower() or self._is_google_endpoint(f"{self.base_url}/chat/completions")
        
        # 1.5M characters (~375k tokens) fits easily in Gemini's 1M/2M token context window
        if (is_large_context and len(rfp_text) < 1500000) or len(rfp_text) < 100000:
            logger.info("Attempting single-call criteria extraction (length: %d chars)", len(rfp_text))
            messages = [
                {"role": "system", "content": STAGE1_PROMPT},
                {"role": "user", "content": f"RFP DOCUMENT:\n\n{rfp_text}"},
            ]
            resp = self._call_zen_api(messages)
            if "error" not in resp:
                content = self._get_content(resp)
                data = self._extract_json(content)
                single_criteria = []
                if isinstance(data, list):
                    single_criteria = data
                elif isinstance(data, dict):
                    for key in ("criteria", "requirements", "results"):
                        if key in data:
                            single_criteria = data[key]
                            break
                if single_criteria:
                    logger.info("Single-call criteria extraction succeeded with %d requirements", len(single_criteria))
                    for item in single_criteria:
                        item["doc_name"] = rfp_filename
                    self._save_cache(f"stage1_{text_hash}.json", single_criteria)
                    if progress_callback:
                        progress_callback(
                            2,
                            f"Found {len(single_criteria)} requirements in a single pass.",
                            len(single_criteria),
                            0,
                        )
                    return single_criteria
            logger.warning("Single-call extraction failed or returned no criteria; falling back to chunked extraction.")

        chunk_size = 25000
        overlap = 2000
        chunks = self._chunk_text(rfp_text, chunk_size, overlap)

        all_raw: list[list[dict]] = []
        for ci, chunk in enumerate(chunks):
            if ci > 0:
                time.sleep(8.0)
            messages = [
                {"role": "system", "content": STAGE1_PROMPT},
                {"role": "user", "content": f"RFP DOCUMENT (section):\n\n{chunk}"},
            ]

            resp = self._call_zen_api(messages)
            if "error" in resp:
                logger.warning("Stage 1 chunk %d failed: %s", ci, resp["error"])
                continue

            content = self._get_content(resp)
            if not content:
                logger.warning("Stage 1 chunk %d returned empty — retrying in halves", ci)
                sub_chunks = self._chunk_text(chunk, len(chunk) // 2, 1000)
                for sub in sub_chunks:
                    sub_resp = self._call_zen_api([
                        {"role": "system", "content": STAGE1_PROMPT},
                        {"role": "user", "content": f"RFP DOCUMENT (section):\n\n{sub}"},
                    ])
                    if "error" in sub_resp:
                        continue
                    sub_content = self._get_content(sub_resp)
                    data = self._extract_json(sub_content)
                    sub_criteria = []
                    if isinstance(data, list):
                        sub_criteria = data
                    elif isinstance(data, dict):
                        for key in ("criteria", "requirements", "results"):
                            if key in data:
                                sub_criteria = data[key]
                                break
                    if sub_criteria:
                        all_raw.append(sub_criteria)
                continue

            data = self._extract_json(content)

            chunk_criteria = []
            if isinstance(data, list):
                chunk_criteria = data
            elif isinstance(data, dict):
                for key in ("criteria", "requirements", "results"):
                    if key in data:
                        chunk_criteria = data[key]
                        break
            if chunk_criteria:
                all_raw.append(chunk_criteria)

        merged = self._merge_criteria(all_raw)
        for item in merged:
            item["doc_name"] = rfp_filename

        self._save_cache(f"stage1_{text_hash}.json", merged)

        if progress_callback:
            progress_callback(
                2,
                f"Found {len(merged)} requirements across {len(chunks)} sections.",
                len(merged),
                0,
            )

        return merged

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) > chunk_size:
                if current:
                    chunks.append(current.strip())
                    overlap_text = current[-overlap:] if len(current) > overlap else current
                    current = overlap_text + " " + sent
                else:
                    chunks.append(sent.strip())
                    current = ""
            else:
                current += " " + sent
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _merge_criteria(raw_groups: list[list[dict]]) -> list[dict]:
        """Deduplicate criteria across chunks by clause + description similarity."""
        seen: list[dict] = []
        for group in raw_groups:
            for item in group:
                clause_num = str(item.get("clause_number") or item.get("clause") or "").strip()
                clause_name = str(item.get("clause_name") or "").strip()
                desc = str(item.get("clause_text") or item.get("description") or "").strip()
                
                if not clause_num and not clause_name and not desc:
                    continue
                
                duplicate = False
                for existing in seen:
                    e_clause_num = str(existing.get("clause_number") or existing.get("clause") or "").strip()
                    e_clause_name = str(existing.get("clause_name") or "").strip()
                    e_desc = str(existing.get("clause_text") or existing.get("description") or "").strip()
                    
                    if clause_num and e_clause_num and clause_num == e_clause_num:
                        duplicate = True
                        break
                    if desc and e_desc:
                        ratio = SequenceMatcher(None, desc, e_desc).ratio()
                        if ratio > 0.8:
                            duplicate = True
                            break
                if not duplicate:
                    seen.append(item)
        return seen

    # ── Stage 2 — Check criteria (BM25-retrieved context) ───────

    def _check_criteria(
        self,
        raw_criteria: list[dict],
        submission_docs: list[ExtractedDoc],
        progress_callback: ProgressCallback = None,
    ) -> list[Criterion]:
        # Build the full submission context containing all proposal pages
        context_parts = []
        for doc in submission_docs:
            context_parts.append(f"=== START OF DOCUMENT: {doc.filename} ===")
            context_parts.append(doc.text)
            context_parts.append(f"=== END OF DOCUMENT: {doc.filename} ===")
        submission_context = "\n\n".join(context_parts)
        
        # Limit text length to prevent overloading context window (1.2M chars ~ 300k tokens)
        if len(submission_context) > 1200000:
            submission_context = submission_context[:1200000] + "\n\n[TRUNCATED DUE TO EXTREME LENGTH]"

        stage2_key = f"stage2_v6_{self._content_hash(json.dumps(raw_criteria, sort_keys=True))}_{self._content_hash(submission_context)}.json"

        cached = self._load_cache(stage2_key)
        if cached is not None and isinstance(cached, list) and len(cached) > 0:
            logger.info("Stage 2 cache hit (%d criteria)", len(cached))
            criteria_out = []
            for i, item in enumerate(cached):
                criteria_out.append(Criterion(
                    id=f"C{i + 1}",
                    rfp_doc_name=item.get("rfp_doc_name", "N/A"),
                    rfp_page=item.get("rfp_page", 1),
                    rfp_section=item.get("rfp_section", "N/A"),
                    rfp_clause_num=item.get("rfp_clause_num", item.get("rfp_clause", "N/A")),
                    rfp_clause_name=item.get("rfp_clause_name", "N/A"),
                    rfp_clause_text=item.get("rfp_clause_text", item.get("description", "")),
                    comp_doc_name=item.get("comp_doc_name", "N/A"),
                    comp_page=item.get("comp_page", 1),
                    comp_section=item.get("comp_section", "N/A"),
                    comp_clause_num=item.get("comp_clause_num", "N/A"),
                    comp_clause_name=item.get("comp_clause_name", "N/A"),
                    status=self._normalize_status(item.get("status", "not_checked")),
                    evidence=item.get("evidence", ""),
                    notes=item.get("notes", ""),
                ))
            if progress_callback:
                progress_callback(3, f"Loaded {len(criteria_out)} results from cache.", len(criteria_out), len(criteria_out))
            return criteria_out

        total = len(raw_criteria)
        results_list: list[Optional[Criterion]] = [None] * total
        completed_count = 0
        progress_lock = threading.Lock()

        from concurrent.futures import ThreadPoolExecutor

        def process_criterion(idx: int, rc: dict):
            nonlocal completed_count
            
            # Step 1: Auditor Sub-Agent (Scan and extract)
            audit_messages = [
                {"role": "system", "content": AUDITOR_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"SUBMISSION DOCUMENTS:\n\n{submission_context}\n\n"
                        f"RFP REQUIREMENT TO SCAN:\n\n{json.dumps(rc, indent=2)}"
                    ),
                },
            ]
            
            audit_resp = self._call_zen_api(audit_messages, require_json=True)
            audit_result = {}
            if "error" not in audit_resp:
                content = self._get_content(audit_resp)
                if content:
                    audit_result = self._extract_json(content) or {}
            
            # Step 2: Reviewer Sub-Agent (Evaluate findings & check tangible proof)
            reviewer_messages = [
                {"role": "system", "content": REVIEWER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"RFP REQUIREMENT:\n{json.dumps(rc, indent=2)}\n\n"
                        f"AUDITOR FINDINGS:\n{json.dumps(audit_result, indent=2)}"
                    ),
                },
            ]
            
            review_resp = self._call_zen_api(reviewer_messages, require_json=True)
            review_result = {}
            if "error" not in review_resp:
                content = self._get_content(review_resp)
                if content:
                    review_result = self._extract_json(content) or {}

            # Construct Criterion object
            status = self._normalize_status(review_result.get("status", "non_compliant"))
            notes = review_result.get("notes", "No notes provided by reviewer sub-agent.")
            
            criterion = Criterion(
                id=f"C{idx + 1}",
                rfp_doc_name=rc.get("doc_name", "N/A"),
                rfp_page=rc.get("page", 1),
                rfp_section=rc.get("section_name", "N/A"),
                rfp_clause_num=rc.get("clause_number", rc.get("clause", "N/A")),
                rfp_clause_name=rc.get("clause_name", "N/A"),
                rfp_clause_text=rc.get("clause_text", rc.get("description", "")),
                comp_doc_name=audit_result.get("doc_name", "N/A"),
                comp_page=audit_result.get("page", 1),
                comp_section=audit_result.get("section_name", "N/A"),
                comp_clause_num="N/A",
                comp_clause_name="N/A",
                status=status,
                evidence=audit_result.get("evidence", ""),
                notes=notes,
            )
            
            results_list[idx] = criterion
            
            with progress_lock:
                completed_count += 1
                if progress_callback:
                    progress_callback(3, f"Assessed {completed_count} of {total} requirements...", completed_count, total)

        max_threads = 1 if self.rate_limiter else 10
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = [executor.submit(process_criterion, idx, rc) for idx, rc in enumerate(raw_criteria)]
            for fut in futures:
                try:
                    fut.result()
                except Exception as e:
                    logger.error("Error processing criterion in thread pool: %s", e)

        # Gather results and fill in any failed indices
        criteria_out: list[Criterion] = []
        for idx, rc in enumerate(raw_criteria):
            item = results_list[idx]
            if item is None:
                item = Criterion(
                    id=f"C{idx + 1}",
                    rfp_doc_name=rc.get("doc_name", "N/A"),
                    rfp_page=rc.get("page", 1),
                    rfp_section=rc.get("section_name", "N/A"),
                    rfp_clause_num=rc.get("clause_number", rc.get("clause", "N/A")),
                    rfp_clause_name=rc.get("clause_name", "N/A"),
                    rfp_clause_text=rc.get("clause_text", rc.get("description", "")),
                    comp_doc_name="N/A",
                    comp_page=1,
                    comp_section="N/A",
                    comp_clause_num="N/A",
                    comp_clause_name="N/A",
                    status="not_checked",
                    evidence="",
                    notes="Failed to perform multi-agent verification.",
                )
            criteria_out.append(item)

        # Cache the complete list of criteria results
        cache_data = [c.__dict__ for c in criteria_out]
        self._save_cache(stage2_key, cache_data)
        return criteria_out

    # ── Stage 3 helpers ─────────────────────────────────────────

    def _identify_gaps(self, criteria: list[Criterion]) -> list[Gap]:
        severity_map = {
            "non_compliant": "Critical",
            "partial": "High",
        }
        gaps: list[Gap] = []
        for i, c in enumerate(criteria):
            severity = severity_map.get(c.status)
            if severity is None:
                continue
            gaps.append(
                Gap(
                    id=f"G{len(gaps) + 1}",
                    severity=severity,
                    description=(
                        f"{c.rfp_clause_num} {c.rfp_clause_name}: {c.rfp_clause_text[:200]}"
                    ),
                    criterion_id=c.id,
                )
            )
        return gaps

    def _build_summary(
        self, submission_docs: list[ExtractedDoc]
    ) -> str:
        parts: list[str] = []
        for doc in submission_docs:
            pages = doc.total_pages
            ocr = " (OCR applied)" if doc.ocr_used else ""
            parts.append(
                f"- {doc.filename}: {pages} page{'s' if pages != 1 else ''}{ocr}"
            )
        if not parts:
            return "No submission documents provided."
        return "Submitted documents:\n" + "\n".join(parts)

    def _generate_commentary(self, criteria: list[Criterion]) -> str:
        # Check cache first
        criteria_str = json.dumps([c.__dict__ for c in criteria], sort_keys=True)
        cache_key = f"commentary_{self._content_hash(criteria_str)}.json"
        cached = self._load_cache(cache_key)
        if cached and isinstance(cached, str):
            return cached

        summary_lines = []
        for c in criteria:
            summary_lines.append(
                f"- Section: {c.rfp_section} | Clause: {c.rfp_clause_num} ({c.rfp_clause_name}) | Status: {c.status} | Notes: {c.notes}"
            )
        
        input_data = "\n".join(summary_lines)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Senior Proposal Compliance Manager. Review the list of check results below. "
                    "Write a professional, detailed section-by-section compliance commentary and executive summary. "
                    "Group your commentary by RFP sections (e.g. Technical, Financial, Management) and explain what was "
                    "found, key compliance strengths, specific missing requirements (gaps), and recommendations. "
                    "Make it structured and highly readable. Return ONLY plain text or markdown."
                )
            },
            {
                "role": "user",
                "content": f"COMPLIANCE CHECK RESULTS:\n\n{input_data[:20000]}"
            }
        ]
        
        resp = self._call_zen_api(messages, require_json=False)
        commentary = ""
        if "error" not in resp:
            commentary = self._get_content(resp)
        if not commentary:
            commentary = "Detailed section-by-section analysis could not be generated."
        
        self._save_cache(cache_key, commentary)
        return commentary

    # ── Error classification ────────────────────────────────────

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[str, str]:
        err_str = str(exc).lower()
        if "cancelled" in err_str:
            return ("cancelled", "Cancelled — I'll stop here.")
        if any(w in err_str for w in ("401", "403", "unauthorized", "forbidden")):
            return ("api_rejected", "The API rejected the request — check your API key in Settings.")
        if any(w in err_str for w in ("extract", "pdf", "tesseract", "ocr")):
            return ("ocr_failed", "I couldn't read some of the document pages — it may be encrypted or scanned with poor quality.")
        if any(w in err_str for w in ("timeout", "timed out")):
            return ("timeout", "The request timed out — try a smaller document or check your network connection.")
        if any(w in err_str for w in ("model", "404", "not found")):
            return ("api_rejected", "The model name wasn't recognised — check your Settings.")
        if "no criteria" in err_str or "no requirements" in err_str:
            return ("no_criteria", "I couldn't find any requirements in this document — it may be scan-only, or my OCR pass came back empty.")
        if "empty content" in err_str or "empty_response" in err_str:
            return ("api_empty", "The API returned empty responses — the model may have been overloaded. Try with smaller documents, or check your connection.")
        return ("unknown", f"Something unexpected happened — {exc}")

    # ── API helpers ─────────────────────────────────────────────

    @staticmethod
    def _is_google_endpoint(url: str) -> bool:
        return "googleapis.com" in url

    def _call_zen_api(
        self,
        messages: list,
        temperature: float = 0.1,
        require_json: bool = True,
    ) -> dict:
        if self.rate_limiter:
            self.rate_limiter.wait()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self._is_google_endpoint(url):
            payload["max_tokens"] = 8192
            if require_json:
                payload["response_format"] = {"type": "json_object"}
        else:
            payload["max_tokens"] = 2048

        max_retries = 15
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text
                if status == 429 and attempt < max_retries - 1:
                    retry_delay = 5.0
                    m = re.search(r'retry in (\d+(?:\.\d+)?)s', body)
                    if m:
                        retry_delay = float(m.group(1)) + random.uniform(2.0, 7.0)
                    msg_err = f"Rate limited by Gemini API (HTTP 429). Retrying in {retry_delay:.0f}s..."
                    logger.info(
                        "HTTP 429, retry %d/%d in %.0fs...",
                        attempt + 1, max_retries, retry_delay,
                    )
                    if getattr(self, "progress_callback", None):
                        try:
                            self.progress_callback(3, msg_err, 0, 0)
                        except Exception:
                            pass
                    time.sleep(min(retry_delay, 75.0))
                    continue
                if status in (502, 503, 504) and attempt < max_retries - 1:
                    sleep_time = min(2 ** attempt, 30)
                    msg_err = f"API Server unavailable (HTTP {status}). Retrying in {sleep_time}s..."
                    logger.info(
                        "HTTP %d, retry %d/%d in %ds...",
                        status, attempt + 1, max_retries, sleep_time,
                    )
                    if getattr(self, "progress_callback", None):
                        try:
                            self.progress_callback(3, msg_err, 0, 0)
                        except Exception:
                            pass
                    time.sleep(sleep_time)
                    continue
                return {"error": f"HTTP {status} from {url}: {body[:500]}"}
            except httpx.RequestError as exc:
                if attempt < max_retries - 1:
                    sleep_time = min(2 ** attempt, 30)
                    msg_err = f"Connection failed. Retrying in {sleep_time}s..."
                    logger.info(
                        "Request failed (%s), retry %d/%d in %ds...",
                        exc, attempt + 1, max_retries, sleep_time,
                    )
                    if getattr(self, "progress_callback", None):
                        try:
                            self.progress_callback(3, msg_err, 0, 0)
                        except Exception:
                            pass
                    time.sleep(sleep_time)
                    continue
                return {"error": f"Request failed for {url}: {exc}"}
            except Exception as exc:
                return {"error": f"Unexpected error calling {url}: {exc}"}
        return {"error": f"Failed after {max_retries} retries"}

    def _get_content(self, resp: dict) -> str:
        try:
            choice = resp["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError):
            logger.warning("Unexpected API response shape: %s", resp)
            return ""
        content = msg.get("content", "")
        if content:
            return content
        finish_reason = choice.get("finish_reason", "unknown")
        safety_ratings = resp.get("safety_ratings", [])
        if finish_reason in ("safety", "blocked", "recitation"):
            reasons = [f"{r.get('category','?')}={r.get('probability','?')}" for r in safety_ratings]
            logger.warning("Content blocked (finish_reason=%s) safety=%s", finish_reason, reasons)
        else:
            logger.warning("Empty content (finish_reason=%s) — empty_response", finish_reason)
        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            try:
                json.loads(reasoning)
                return reasoning
            except json.JSONDecodeError:
                pass
        return ""

    @staticmethod
    def _extract_json(text: str) -> dict | list:
        if not text:
            return {}

        stripped = text.strip()

        # Try markdown code fences
        for marker in ("```json", "```"):
            start = stripped.find(marker)
            if start == -1:
                continue
            after = stripped[start + len(marker):]
            end = after.find("```")
            candidate = after[:end].strip() if end != -1 else after.strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    for key in ("criteria", "requirements", "results"):
                        if key in parsed:
                            return parsed[key]
                return parsed
            except json.JSONDecodeError:
                continue

        # Try raw parse
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                for key in ("criteria", "requirements", "results"):
                    if key in parsed:
                        return parsed[key]
            return parsed
        except json.JSONDecodeError:
            pass

        # Try to find JSON object (starting with {) or array (starting with [)
        for start_char, end_char in (("{", "}"), ("[", "]")):
            brace_start = stripped.find(start_char)
            if brace_start == -1:
                continue
            depth = 0
            end_pos = -1
            for pos in range(brace_start, len(stripped)):
                if stripped[pos] == start_char:
                    depth += 1
                elif stripped[pos] == end_char:
                    depth -= 1
                    if depth == 0:
                        end_pos = pos + 1
                        break
            if end_pos == -1:
                continue
            candidate = stripped[brace_start:end_pos]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    for key in ("criteria", "requirements", "results"):
                        if key in parsed:
                            return parsed[key]
                return parsed
            except json.JSONDecodeError:
                continue

        logger.warning(
            "Could not parse JSON from LLM response. "
            "First 1000 chars: %s", stripped[:1000]
        )
        return {}

    @staticmethod
    def _normalize_status(
        raw: str,
    ) -> Literal["compliant", "partial", "non_compliant", "not_checked"]:
        val = raw.strip().lower().replace(" ", "_").replace("-", "_")
        valid = {"compliant", "partial", "non_compliant", "not_checked"}
        return val if val in valid else "not_checked"

    @staticmethod
    def _build_submission_text(
        submission_docs: list[ExtractedDoc],
    ) -> str:
        parts: list[str] = []
        total = 0
        limit = 100_000
        for doc in submission_docs:
            header = f"=== FILE: {doc.filename} ===\n"
            remaining = limit - total - len(header)
            if remaining <= 0:
                break
            text = doc.text[:remaining]
            parts.append(f"{header}{text}")
            total += len(header) + len(text)
        if total >= limit:
            parts.append(
                "\n\n[NOTE: Submission text truncated to "
                f"{limit} characters]"
            )
        return "\n\n".join(parts)
