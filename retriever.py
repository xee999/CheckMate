"""retriever.py — BM25 evidence search for Bod compliance checker."""
from __future__ import annotations
import re
from pathlib import Path
from rank_bm25 import BM25Okapi
from pdf_extractor import ExtractedDoc

class EvidenceRetriever:
    def __init__(self, docs: list[ExtractedDoc], chunk_size: int = 1000):
        """Build a BM25 index over sentence-aligned chunks from submission docs."""
        self.chunks: list[str] = []
        self.chunk_sources: list[tuple[str, int]] = []  # (filename, page)
        self.bm25: BM25Okapi | None = None
        self._build_index(docs, chunk_size)

    def _build_index(self, docs: list[ExtractedDoc], chunk_size: int):
        """Split docs into page-aligned chunks, scanning for page markers."""
        for doc in docs:
            parts = re.split(r'(--- PAGE \d+ ---)', doc.text)
            current_page = 1
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                m = re.match(r'--- PAGE (\d+) ---', part)
                if m:
                    current_page = int(m.group(1))
                    continue

                # Split page text into sentences
                sentences = re.split(r'(?<=[.!?])\s+', part)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) > chunk_size:
                        if current:
                            self.chunks.append(current.strip())
                            self.chunk_sources.append((doc.filename, current_page))
                        current = sent
                    else:
                        current += " " + sent
                if current.strip():
                    self.chunks.append(current.strip())
                    self.chunk_sources.append((doc.filename, current_page))

        tokenized = [chunk.lower().split() for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: str, top_k: int = 10) -> list[tuple[str, str, int, float]]:
        """Return top-k (chunk_text, filename, page_number, score) matches."""
        if not self.bm25 or not self.chunks:
            return []
        tokens = query.lower().split()
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score > 0:
                chunk_text = self.chunks[idx]
                fname, page = self.chunk_sources[idx]
                results.append((chunk_text, fname, page, score))
        return results

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)
