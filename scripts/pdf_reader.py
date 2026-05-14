"""PDF reader for annual / quarterly reports.

Design:
- Download PDFs from URLs (cninfo.com.cn for A-shares, hkex for HK, SEC for US).
- Extract text page-by-page using pypdf.
- Section-level extraction using regex patterns tuned for CN reports:
    * 主要会计数据和财务指标
    * 资产负债表项目变动（含"变动原因"）
    * 利润表项目变动（含"变动原因"——关键！）
    * 现金流量表项目变动
    * 管理层讨论与分析 / 经营情况讨论
    * 主要控股参股公司
    * 风险因素
    * 前十大股东
    * 非经常性损益项目

Usage:
    from scripts.pdf_reader import PDFReader
    r = PDFReader()
    p = r.download("http://cninfo.com.cn/.../xxx.PDF", "output/.../raw_data/pdfs/q3_2025.pdf")
    sections = r.extract_sections(p)
    print(sections["income_change_reasons"])  # 原文
    hits = r.search(p, r"超隆光电")           # 关键词定位

CLI:
    python3 -m scripts.pdf_reader path/to/report.pdf [--section income]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import pypdf
import requests

# ---- A-share report section heading patterns ----
# 每个 section 对应 (regex 开始标识, 候选结束标识列表, 含义描述)
SECTION_PATTERNS: dict[str, dict] = {
    "main_financial_data": {
        "start": r"一、?\s*主要财务数据|一、?\s*主要会计数据和财务指标|主要会计数据及财务指标",
        "end": [
            r"二、?\s*股东信息", r"非经常性损益项目和金额",
            r"二、?\s*股东人数", r"资产负债表项目变动",
        ],
        "desc": "核心财务数据表",
    },
    "non_recurring_items": {
        "start": r"非经常性损益项目和金额|非经常性损益",
        "end": [
            r"主要会计数据和财务指标发生变动", r"变动的情况及原因",
            r"资产负债表项目变动",
        ],
        "desc": "非经常性损益明细",
    },
    "balance_sheet_changes": {
        "start": r"(?:1\s*、|1\s*\.)\s*资产负债表项目变动|资产负债表项目变动的原因",
        "end": [
            r"(?:2\s*、|2\s*\.)\s*利润表项目变动",
            r"利润表项目变动的原因",
        ],
        "desc": "资产负债表项目变动（含变动原因）",
    },
    "income_statement_changes": {
        "start": r"(?:2\s*、|2\s*\.)\s*利润表项目变动|利润表项目变动的原因",
        "end": [
            r"(?:3\s*、|3\s*\.)\s*现金流量表项目变动",
            r"现金流量表项目变动的原因",
            r"二、?\s*股东信息",
        ],
        "desc": "★ 利润表项目变动（含关键'变动原因'说明 — Q3 亏损归因在此）",
    },
    "cashflow_changes": {
        "start": r"(?:3\s*、|3\s*\.)\s*现金流量表项目变动|现金流量表项目变动的原因",
        "end": [
            r"二、?\s*股东信息",
            r"二、?\s*股东人数",
            r"三、?\s*其他重要事项",
        ],
        "desc": "现金流量表项目变动",
    },
    "mda": {
        "start": r"管理层讨论与分析|经营情况讨论与分析|报告期内公司所处行业情况",
        "end": [
            r"公司治理", r"重要事项", r"股份变动及股东情况",
        ],
        "desc": "管理层讨论与分析（MD&A）",
    },
    "subsidiaries": {
        "start": r"主要控股参股公司|主要子公司及对公司净利润影响达|主要境外资产情况",
        "end": [
            r"报告期内取得和处置子公司",
            r"公司控制的结构化主体情况",
            r"公司面临的风险",
            r"十、?\s*公司面临",
        ],
        "desc": "主要子公司 / 参股公司业绩表",
    },
    "risks": {
        "start": r"公司面临的风险和应对措施|公司面临的风险|风险因素",
        "end": [
            r"市值管理制度", r"质量回报双提升",
            r"第四节", r"公司治理",
        ],
        "desc": "风险因素披露",
    },
    "top10_holders": {
        "start": r"前\s*10?\s*名股东持股情况|前十名股东持股情况",
        "end": [
            r"前\s*10?\s*名无限售条件股东",
            r"优先股股东",
            r"三、?\s*其他重要事项",
        ],
        "desc": "前十大股东（季报/年报披露）",
    },
}


class PDFReader:
    """Read A-share / HK / US report PDFs with section-level extraction."""

    def __init__(self, timeout: int = 60):
        self._timeout = timeout

    # ---- download ----

    def download(self, url: str, out_path: str | Path) -> Path:
        """Download a PDF from a URL to local path. Returns the Path."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and out_path.stat().st_size > 1024:
            return out_path  # assume cached
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0 Safari/537.36",
            "Accept": "application/pdf,*/*",
        }
        resp = requests.get(url, headers=headers, timeout=self._timeout, stream=True)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return out_path

    # ---- extraction ----

    def extract_text(self, pdf_path: str | Path, pages: Iterable[int] | None = None) -> list[str]:
        """Return list[str] where element i = page i+1 text. If pages given, only extract those."""
        pdf_path = Path(pdf_path)
        reader = pypdf.PdfReader(str(pdf_path))
        n = len(reader.pages)
        idxs = list(pages) if pages is not None else list(range(n))
        texts: list[str] = []
        for i in idxs:
            if i >= n:
                texts.append("")
                continue
            try:
                texts.append(reader.pages[i].extract_text() or "")
            except Exception:  # noqa: BLE001
                texts.append("")
        return texts

    def full_text(self, pdf_path: str | Path) -> str:
        """Return concatenated text with page markers."""
        pages = self.extract_text(pdf_path)
        return "\n".join(f"\n===== PAGE {i + 1} =====\n{t}" for i, t in enumerate(pages))

    def extract_sections(self, pdf_path: str | Path) -> dict[str, dict]:
        """Extract known sections from the PDF. Returns dict keyed by section id.

        Each value:
            {
              "desc": str,
              "found": bool,
              "start_page": int | None,
              "end_page": int | None,
              "text": str,   # extracted text (empty if not found)
            }
        """
        pages = self.extract_text(pdf_path)
        full = "\n".join(f"__PAGE_{i + 1}__\n{t}" for i, t in enumerate(pages))
        out: dict[str, dict] = {}

        for sec_id, conf in SECTION_PATTERNS.items():
            start_re = re.compile(conf["start"])
            m_start = start_re.search(full)
            if not m_start:
                out[sec_id] = {"desc": conf["desc"], "found": False, "start_page": None, "end_page": None, "text": ""}
                continue

            start_pos = m_start.start()
            # find end (first of candidates after start)
            end_positions = []
            for end_pat in conf["end"]:
                m_end = re.compile(end_pat).search(full, pos=m_start.end())
                if m_end:
                    end_positions.append(m_end.start())
            end_pos = min(end_positions) if end_positions else min(start_pos + 8000, len(full))

            snippet = full[start_pos:end_pos]

            # figure out start/end page from __PAGE_N__ markers
            start_page = self._find_page(full, start_pos)
            end_page = self._find_page(full, max(end_pos - 1, start_pos))

            # strip __PAGE_N__ markers from snippet but keep annotations
            snippet_clean = re.sub(r"__PAGE_(\d+)__", lambda m: f"\n[P.{m.group(1)}] ", snippet).strip()

            out[sec_id] = {
                "desc": conf["desc"],
                "found": True,
                "start_page": start_page,
                "end_page": end_page,
                "text": snippet_clean,
            }

        return out

    @staticmethod
    def _find_page(full: str, pos: int) -> int:
        """Given position in the full-text with __PAGE_N__ markers, return page number (1-indexed)."""
        sub = full[:pos]
        pages = re.findall(r"__PAGE_(\d+)__", sub)
        if not pages:
            return 1
        return int(pages[-1])

    def dump_text(self, pdf_path: str | Path, out_path: str | Path) -> dict:
        """Export full PDF text as markdown with page headings. Returns stats dict."""
        pages = self.extract_text(pdf_path)
        total_chars = sum(len(t) for t in pages)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        filename = Path(pdf_path).name
        lines = [f"# {filename} Full Text ({len(pages)} pages, {total_chars} chars)\n"]
        for i, text in enumerate(pages):
            lines.append(f"\n## Page {i + 1}\n")
            lines.append(text)
        out_path.write_text("\n".join(lines), encoding="utf-8")

        stats = {"pages": len(pages), "total_chars": total_chars,
                 "per_page": [len(t) for t in pages]}
        return stats

    @staticmethod
    def merge_sections(regex_path: str | Path, llm_path: str | Path, out_path: str | Path) -> dict:
        """Merge regex-extracted and LLM-extracted sections. Regex wins when found=True."""
        regex_path, llm_path, out_path = Path(regex_path), Path(llm_path), Path(out_path)
        regex_data = json.loads(regex_path.read_text()) if regex_path.exists() else {}
        llm_data = json.loads(llm_path.read_text()) if llm_path.exists() else {}

        merged = {}
        all_keys = set(list(regex_data.keys()) + list(llm_data.keys()))
        regex_count = llm_count = missing_count = 0
        for key in all_keys:
            r = regex_data.get(key, {})
            l = llm_data.get(key, {})
            if r.get("found"):
                merged[key] = {**r, "method": "regex"}
                regex_count += 1
            elif l.get("found"):
                merged[key] = {**l, "method": "llm"}
                llm_count += 1
            else:
                merged[key] = r if r else l if l else {"found": False, "text": ""}
                merged[key]["method"] = "none"
                missing_count += 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
        total = len(all_keys)
        print(f"命中率: {regex_count + llm_count}/{total} (regex: {regex_count}, llm: {llm_count}, missing: {missing_count})")
        return {"total": total, "regex": regex_count, "llm": llm_count, "missing": missing_count}

    def search(self, pdf_path: str | Path, pattern: str, flags: int = re.IGNORECASE) -> list[dict]:
        """Full-text regex search. Returns list of {page, line, snippet}."""
        pages = self.extract_text(pdf_path)
        hits: list[dict] = []
        rx = re.compile(pattern, flags)
        for i, text in enumerate(pages):
            for line_no, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append({
                        "page": i + 1,
                        "line": line_no,
                        "snippet": line.strip()[:300],
                    })
        return hits


# ---- CLI ----

def main():
    ap = argparse.ArgumentParser(description="Read a financial report PDF.")
    ap.add_argument("pdf_path", help="Path or URL to PDF")
    ap.add_argument("--section", default=None,
                    help=f"Extract a single section. Choices: {','.join(SECTION_PATTERNS)}")
    ap.add_argument("--search", default=None, help="Regex to search in full text")
    ap.add_argument("--all-sections", "--regex-sections", action="store_true",
                    dest="all_sections", help="Extract all known sections via regex")
    ap.add_argument("--out", default=None, help="If given, dump extracted sections to this JSON path")
    ap.add_argument("--dump-text", default=None, dest="dump_text",
                    help="Export full PDF text as markdown to this path (for LLM processing)")
    ap.add_argument("--stats", action="store_true",
                    help="Print page count, total chars, and per-page char summary")
    ap.add_argument("--merge", nargs=2, metavar=("REGEX_JSON", "LLM_JSON"),
                    help="Merge regex and LLM section JSONs. Use with --out for output path")
    args = ap.parse_args()

    r = PDFReader()

    # -- merge mode (no PDF needed) --
    if args.merge:
        if not args.out:
            print("--merge requires --out <path>", file=sys.stderr)
            sys.exit(2)
        r.merge_sections(args.merge[0], args.merge[1], args.out)
        return

    # download if URL
    p = args.pdf_path
    if p.startswith("http://") or p.startswith("https://"):
        tmp = Path("/tmp") / Path(p).name
        p = r.download(p, tmp)
        print(f"Downloaded to {p}", file=sys.stderr)

    # -- dump-text mode --
    if args.dump_text:
        stats = r.dump_text(p, args.dump_text)
        print(f"Exported {stats['pages']} pages, {stats['total_chars']} chars → {args.dump_text}")
        return

    # -- stats mode --
    if args.stats:
        pages = r.extract_text(p)
        total = sum(len(t) for t in pages)
        print(f"{len(pages)} pages, {total} chars total")
        for i, t in enumerate(pages):
            print(f"  Page {i+1:3d}: {len(t):6d} chars")
        return

    if args.search:
        hits = r.search(p, args.search)
        for h in hits[:50]:
            print(f"[P.{h['page']}:L{h['line']}] {h['snippet']}")
        if len(hits) > 50:
            print(f"... ({len(hits) - 50} more)", file=sys.stderr)
        return

    if args.section:
        if args.section not in SECTION_PATTERNS:
            print(f"Unknown section. Choices: {list(SECTION_PATTERNS)}", file=sys.stderr)
            sys.exit(2)
        sections = r.extract_sections(p)
        s = sections[args.section]
        print(f"# {s['desc']}")
        print(f"found: {s['found']}  pages: {s['start_page']}-{s['end_page']}\n")
        print(s["text"])
        return

    if args.all_sections or args.out:
        sections = r.extract_sections(p)
        if args.out:
            Path(args.out).write_text(json.dumps(sections, ensure_ascii=False, indent=2))
            print(f"Saved sections to {args.out}")
        found = sum(1 for s in sections.values() if s["found"])
        total = len(sections)
        for sec_id, info in sections.items():
            marker = "✅" if info["found"] else "❌"
            pg = f"P.{info['start_page']}-{info['end_page']}" if info["found"] else "(not found)"
            print(f"{marker} {sec_id:28s} {pg}  — {info['desc']}")
        print(f"\nRegex 命中率: {found}/{total}")
        return

    # default: page count + length summary
    pages = r.extract_text(p)
    total_chars = sum(len(t) for t in pages)
    print(f"{len(pages)} pages, {total_chars} chars total")
    for i, t in enumerate(pages[:3]):
        print(f"\n--- Page {i + 1} preview ---")
        print(t[:500])


if __name__ == "__main__":
    main()
