"""Extract data/raw/*.pdf -> data/pages.jsonl + data/manifest.json.

Needs poppler's `pdftotext`/`pdfinfo`. Run: python3 scripts/build_corpus.py
"""
import hashlib, json, re, subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, MIN_CHARS = ROOT / "data/raw", 500  # page counts only if >= MIN_CHARS normalized chars

LICENSE = ("US federal government work (NIST), not subject to copyright in the US (17 U.S.C. 105); "
           "free redistribution. See https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications. "
           "Third-party figures/quotes keep their own rights; none are redistributed separately.")

# content_range: first/last physical page of body (cover, notices, TOC before; refs/colophon after).
# offset: physical - printed page number. sections: (first_physical_page, name).
DOCS = [
    dict(id="nist-ai-100-1", file="nist-ai-100-1.pdf", title="Artificial Intelligence Risk Management Framework (AI RMF 1.0)",
         url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf", doi="10.6028/NIST.AI.100-1",
         version="AI RMF 1.0, January 2023", year=2023, content_range=(6, 47), offset=5,
         sections=[(6, "executive_summary"), (9, "framing_risk"), (14, "audience"), (17, "ai_risks_trustworthiness"),
                   (24, "effectiveness"), (25, "core"), (39, "profiles"), (40, "appendix_a"), (43, "appendix_b"),
                   (45, "appendix_c"), (47, "appendix_d")]),
    dict(id="nist-ai-600-1", file="nist-ai-600-1.pdf", title="AI RMF: Generative Artificial Intelligence Profile",
         url="https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf", doi="10.6028/NIST.AI.600-1",
         version="NIST AI 600-1, approved 2024-07-25 (July 2024)", year=2024, content_range=(5, 57), offset=4,
         sections=[(5, "introduction"), (6, "risks_overview"), (17, "suggested_actions"), (51, "appendix_a")]),
]
OUT_OF_RANGE = {"before": "front matter (cover/notices/TOC/lists)", "after": "back matter (colophon/references)"}
HDR = re.compile(r"^(NIST AI 100-1|AI RMF 1\.0|NIST Trustworthy and Responsible AI|NIST AI 600-1|\d{1,2}|[ivx]+|"
                 r"This publication is available free of charge.*)$")
ACTION_PREFIX = {"GV": "GOVERN", "MP": "MAP", "MS": "MEASURE", "MG": "MANAGE"}
LIG = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})


def page_text(pdf, p):
    raw = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    raw = raw.translate(LIG).replace("\x0c", "")
    lines = [l.strip() for l in raw.splitlines() if l.strip() and not HDR.match(l.strip())]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def section_of(page, sections):
    return [n for s, n in sections if s <= page][-1]


def main():
    pages, docs = [], []
    accessed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in DOCS:
        pdf = RAW / d["file"]
        total = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
        lo, hi = d["content_range"]
        counted, excluded, func = [], [], None
        for p in range(1, total + 1):
            t = page_text(pdf, p)
            if p < lo or p > hi:
                excluded.append(dict(page=p, chars=len(t), reason=OUT_OF_RANGE["before" if p < lo else "after"])); continue
            if len(t) < MIN_CHARS:
                excluded.append(dict(page=p, chars=len(t), reason=f"<{MIN_CHARS} normalized chars (figure/divider page)")); continue
            # AI 600-1 action tables: function = dominant action-ID prefix on page, inherited if none
            sec = section_of(p, d["sections"])
            if d["id"] == "nist-ai-600-1" and sec == "suggested_actions":
                c = Counter(ACTION_PREFIX[m] for m in re.findall(r"\b(GV|MP|MS|MG)-\d\.\d-\d{3}", t))
                func = c.most_common(1)[0][0] if c else (func or "GOVERN")
            elif d["id"] == "nist-ai-100-1" and sec == "core":
                func = next((f for f in ("GOVERN", "MAP", "MEASURE", "MANAGE") if re.search(rf"\b{f}\b", t[:400])), func)
            else:
                func = None
            pid = f"{d['id']}#p{p:03d}"
            pages.append(dict(page_id=pid, document_id=d["id"], source=d["file"], page=p, printed_page=p - d["offset"],
                              section=sec, function=func, year=d["year"], chars=len(t), text=t))
            counted.append(dict(page_id=pid, page=p, printed_page=p - d["offset"], chars=len(t)))
        docs.append(dict(source_id=d["id"], title=d["title"], source_path_or_url=f"data/raw/{d['file']}", original_url=d["url"],
                         doi=d["doi"], license_or_permission=LICENSE, accessed_at=accessed, snapshot_version=d["version"],
                         sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), physical_pages=total,
                         counted_pages=len(counted), counted_chars=sum(c["chars"] for c in counted),
                         page_counting_rule=f"physical pages {lo}-{hi}, 1-based; drop pages <{MIN_CHARS} chars after stripping running headers/footers and whitespace. printed_page = physical - {d['offset']}.",
                         pages=counted, excluded_pages=excluded))
    man = dict(corpus="NIST AI risk management (AI RMF 1.0 + Generative AI Profile)", total_counted_pages=len(pages),
               total_chars=sum(p["chars"] for p in pages), ocr_needed=False,
               extraction="pdftotext (poppler), born-digital PDFs, no OCR; ligatures normalized; running headers removed. "
                          "Known loss: figures/diagrams are images (Fig.1-3 of AI RMF) and not extracted; multi-column tables (action tables in 600-1) flatten to reading order.",
               documents=docs)
    (ROOT / "data/manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "data/pages.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pages))
    for d in docs:
        print(d["source_id"], d["counted_pages"], "pages", d["counted_chars"], "chars; excluded", [e["page"] for e in d["excluded_pages"] if e["reason"][0] == "<"])
    print("total", len(pages))


if __name__ == "__main__":
    main()
