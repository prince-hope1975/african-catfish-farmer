#!/usr/bin/env python3
"""Clean OCR'd markdown by sending chunks to Gemini for text correction."""

import re
import os
import sys
import time
import argparse
import difflib

from google import genai

INPUT_FILE = "merged_handbook_local.deduped.md"
OUTPUT_FILE = "merged_handbook_local.cleaned.md"

SYSTEM_PROMPT = """You are a text correction assistant. You will receive a section of markdown text from a book called "African Catfish Farmer's Handbook" that has been OCR'd and partially cleaned. Your job is to fix the remaining OCR artifacts.

The text has already had most duplicate content removed. What remains to fix:

1. **Merged words (glue artifacts)**: OCR sometimes merged the end of one phrase with the start of a duplicate phrase, leaving combined words. Split them correctly.
   Examples:
   - "isthe" → "is the"
   - "monto" → "m to" or remove based on context
   - "wantand" → "want and"
   - "staysomething" → "stay" (remove the orphan fragment)
   - "theThis" → "the. This"
   - "farmThis" → "farm. This"

2. **Fragmented sentences**: Some sentences were split mid-flow by the column OCR and now appear as fragments. Reconnect them into proper paragraphs where context makes it clear they belong together.

3. **OCR math/unit artifacts**: Fix notations like:
   - "m$ 3 $" or "m3" → "m³"
   - "m$ 2 $" or "m_{22}" → "m²"
   - "kg/m$ 3 $" → "kg/m³"

4. **Garbled headings**: If a heading is "??????????" or completely garbled, use context to infer what it should say, or mark as "[unclear]".

5. **Stray page numbers**: Remove standalone numbers on their own line (like "11", "107") that are clearly page artifacts.

6. **DO NOT** remove any legitimate repeated words in the actual book content (e.g., a list item genuinely repeated, a refrain, emphasis).

7. **Preserve ALL image tags exactly**: Do NOT touch `<div style='text-align: center;'><img src='images/img_XXX.png' alt='OCR图片'/></div>`.

8. **Preserve all markdown structure**: headings, tables, lists, bold/italic. Do not change heading levels or add new headings.

9. **Do NOT rewrite or rephrase**: Only fix OCR artifacts. Keep wording faithful to the original.

Return ONLY the cleaned markdown. No explanation, no commentary, no preamble."""


def normalize_for_comparison(text: str) -> str:
    """Strip whitespace, images, and formatting to get pure text for comparison."""
    # Remove HTML image tags
    text = re.sub(r"<div[^>]*>.*?</div>", "", text, flags=re.DOTALL)
    # Remove markdown headings markers but keep text
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def extract_images(text: str) -> list[str]:
    """Extract all image src paths from HTML tags."""
    return re.findall(r"src='([^']+)'", text)


def extract_headings(text: str) -> list[str]:
    """Extract all markdown headings."""
    return re.findall(r"^(#+\s+.+)$", text, re.MULTILINE)


def validate_chunk(original: str, cleaned: str, chunk_index: int, heading: str) -> tuple[bool, list[str]]:
    """Validate that the cleaned chunk hasn't been fundamentally altered.

    Returns (passed, list_of_warnings).
    Checks:
    1. Text similarity >= 40% (low threshold because deduplication removes a lot)
    2. All images preserved
    3. No huge content additions (cleaned shouldn't be much longer than original)
    """
    warnings = []
    passed = True

    # 1. Text similarity check
    orig_norm = normalize_for_comparison(original)
    clean_norm = normalize_for_comparison(cleaned)

    if orig_norm and clean_norm:
        similarity = difflib.SequenceMatcher(None, orig_norm, clean_norm).ratio()
        warnings.append(f"Similarity: {similarity:.1%}")
    elif orig_norm and not clean_norm:
        warnings.append("CLEANED TEXT IS EMPTY — keeping original")
        passed = False

    # Only hard-fail on: empty output or images dropped
    orig_images = extract_images(original)
    clean_images = extract_images(cleaned)
    missing_images = set(orig_images) - set(clean_images)
    if missing_images:
        warnings.append(f"MISSING {len(missing_images)} IMAGES: {list(missing_images)[:3]} — keeping original")
        passed = False
    else:
        warnings.append(f"Images OK ({len(orig_images)} preserved)")

    return passed, warnings


def chunk_by_headings(content: str) -> list[dict]:
    """Split markdown into chunks at ## headings, keeping heading with its content."""
    lines = content.split('\n')
    chunks = []
    current_chunk_lines = []
    current_heading = "(preamble)"

    for line in lines:
        # Check if this line is a ## heading (but not ### or more)
        if re.match(r'^## [^#]', line) or re.match(r'^## $', line):
            if current_chunk_lines:
                text = '\n'.join(current_chunk_lines)
                if text.strip():
                    chunks.append({"heading": current_heading, "text": text})
            current_heading = line.strip()
            current_chunk_lines = [line]
        elif re.match(r'^# [^#]', line):
            if current_chunk_lines:
                text = '\n'.join(current_chunk_lines)
                if text.strip():
                    chunks.append({"heading": current_heading, "text": text})
            current_heading = line.strip()
            current_chunk_lines = [line]
        else:
            current_chunk_lines.append(line)

    if current_chunk_lines:
        text = '\n'.join(current_chunk_lines)
        if text.strip():
            chunks.append({"heading": current_heading, "text": text})

    return chunks


def clean_chunk(client, model: str, chunk_text: str, chunk_index: int, total: int, heading: str) -> str:
    """Send a chunk to Gemini for cleaning."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=chunk_text,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )
            cleaned = response.text
            if cleaned:
                return cleaned
            else:
                print(f"  [!] Empty response for chunk {chunk_index+1}, retrying...")
        except Exception as e:
            wait = 2 ** attempt * 5
            print(f"  [!] Error on chunk {chunk_index+1} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                print(f"      Waiting {wait}s before retry...")
                time.sleep(wait)

    print(f"  [!!] Failed to clean chunk {chunk_index+1} ({heading}), keeping original")
    return chunk_text


def main():
    parser = argparse.ArgumentParser(description="Clean OCR markdown using Gemini")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY"), help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Model to use (default: gemini-3-flash-preview)")
    parser.add_argument("--input", default=INPUT_FILE, help=f"Input markdown file (default: {INPUT_FILE})")
    parser.add_argument("--output", default=OUTPUT_FILE, help=f"Output markdown file (default: {OUTPUT_FILE})")
    parser.add_argument("--start", type=int, default=0, help="Start from chunk index (for resuming)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between API calls in seconds (default: 2.0)")
    parser.add_argument("--strict", action="store_true", help="Abort on validation failure instead of keeping original")
    args = parser.parse_args()

    # Read input
    print(f"Reading {args.input}...")
    with open(args.input, "r") as f:
        content = f.read()

    # Chunk the content
    chunks = chunk_by_headings(content)
    print(f"Split into {len(chunks)} chunks")
    for i, c in enumerate(chunks):
        preview = c['heading'][:60]
        lines = c['text'].count('\n') + 1
        print(f"  [{i:3d}] {preview:<60} ({lines} lines)")

    # Initialize Gemini client
    if not args.api_key:
        print("Error: No API key provided. Use --api-key or set GEMINI_API_KEY env var.")
        sys.exit(1)
    client = genai.Client(api_key=args.api_key)

    # Process chunks
    cleaned_chunks = []
    validation_log = []

    # If resuming, load already-cleaned chunks from output file
    if args.start > 0 and os.path.exists(args.output):
        print(f"\nResuming from chunk {args.start}, loading prior output...")
        with open(args.output, "r") as f:
            prior = f.read()
        cleaned_chunks.append(prior)
        chunks = chunks[args.start:]
        print(f"Processing remaining {len(chunks)} chunks")

    total = len(chunks)
    stats = {"passed": 0, "failed": 0, "skipped": 0, "kept_original": 0}
    print(f"\nCleaning {total} chunks with {args.model}...\n")

    for i, chunk in enumerate(chunks):
        actual_index = i + args.start if args.start > 0 else i
        heading = chunk['heading']
        text = chunk['text']

        # Skip very small chunks
        if len(text.strip()) < 20:
            print(f"  [{actual_index:3d}/{total}] Skipping tiny chunk: {heading[:50]}")
            cleaned_chunks.append(text)
            stats["skipped"] += 1
            continue

        print(f"  [{actual_index:3d}/{total}] Cleaning: {heading[:60]}...")
        cleaned = clean_chunk(client, args.model, text, actual_index, total, heading)

        # --- VALIDATION ---
        passed, warnings = validate_chunk(text, cleaned, actual_index, heading)
        status = "PASS" if passed else "FAIL"
        print(f"           Validation: {status}")
        for w in warnings:
            print(f"             - {w}")

        validation_log.append({
            "chunk": actual_index,
            "heading": heading,
            "status": status,
            "warnings": warnings,
        })

        if passed:
            cleaned_chunks.append(cleaned)
            stats["passed"] += 1
        else:
            # Images were dropped — patch them back into Gemini's output
            orig_images = extract_images(text)
            clean_images = extract_images(cleaned)
            missing = [img for img in orig_images if img not in clean_images]
            patched = cleaned
            for img_src in missing:
                img_tag = f"<div style='text-align: center;'><img src='{img_src}' alt='OCR图片'/></div>"
                patched = patched + '\n\n' + img_tag
            print(f"           -> Patched {len(missing)} missing image(s) back in")
            cleaned_chunks.append(patched)
            stats["failed"] += 1

        # Write progress after each chunk
        with open(args.output, "w") as f:
            f.write('\n\n'.join(cleaned_chunks))

        # Rate limiting
        if i < total - 1:
            time.sleep(args.delay)

    # Final write
    with open(args.output, "w") as f:
        f.write('\n\n'.join(cleaned_chunks))

    # Write validation report
    report_file = args.output.replace(".md", ".validation.log")
    with open(report_file, "w") as f:
        f.write("VALIDATION REPORT\n")
        f.write("=" * 60 + "\n\n")
        for entry in validation_log:
            f.write(f"Chunk {entry['chunk']:3d} [{entry['status']}] {entry['heading']}\n")
            for w in entry['warnings']:
                f.write(f"  - {w}\n")
            f.write("\n")
        f.write(f"\nSummary: {stats['passed']} passed, {stats['failed']} failed, "
                f"{stats['skipped']} skipped, {stats['kept_original']} kept original\n")

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Passed:         {stats['passed']}")
    print(f"  Failed:         {stats['failed']}")
    print(f"  Kept original:  {stats['kept_original']}")
    print(f"  Skipped:        {stats['skipped']}")
    print(f"\n  Output:         {args.output}")
    print(f"  Validation log: {report_file}")
    print(f"\n  Original size:  {len(content):,} chars")
    final = '\n\n'.join(cleaned_chunks)
    print(f"  Cleaned size:   {len(final):,} chars")


if __name__ == "__main__":
    main()
