#!/usr/bin/env python3
"""
Algorithmic deduplication of OCR'd markdown.

The OCR produced a two-column merge where each visual line of the original PDF
was read twice and interleaved. The result looks like:

  [phrase_col1] [phrase_col1_again] [next_phrase_col1] [next_phrase_col1_again] ...

Algorithm: for each non-structural line, tokenize into words, then greedily
skip any word sequence that has already appeared in the recent context.

Also handles:
- Stray page numbers ("11", "4.0" etc.) on their own line
- Glued word merges ("theMany" → "the Many", "there.Some" → "there. Some")
- Consecutive duplicate paragraphs
"""

import re
import sys


def fix_glued_words(text: str) -> str:
    """Add spaces where OCR merged end-of-column words with start-of-next-column words."""
    # "there.Some" → "there. Some"
    text = re.sub(r'([.!?,;])([A-Z])', r'\1 \2', text)
    # "theMany" → "the Many" (lowercase word immediately followed by capital)
    text = re.sub(r'([a-z]{2,})([A-Z][a-z])', r'\1 \2', text)
    # "production.production" → "production. production"
    text = re.sub(r'(\w)\.(\w)', r'\1. \2', text)
    return text


def remove_repeated_ngrams(text: str, min_n: int = 5, lookback: int = 150) -> str:
    """
    Tokenize `text` into words and skip any run of words that has already
    appeared in the most recent `lookback` words of the output.

    min_n: minimum n-gram length to match (shorter = more aggressive dedup,
           but risks removing legitimate repeated phrases)
    """
    words = text.split()
    result: list[str] = []

    i = 0
    while i < len(words):
        # Build the context window from recent result
        context = result[-lookback:]
        context_len = len(context)

        # Try to find the longest match starting at words[i] within context
        matched_len = 0
        max_try = min(30, len(words) - i)  # cap to avoid huge scans

        for n in range(max_try, min_n - 1, -1):
            candidate = words[i: i + n]
            # Slide the context window to find this candidate
            for j in range(context_len - n + 1):
                if context[j: j + n] == candidate:
                    matched_len = n
                    break
            if matched_len:
                break

        if matched_len:
            i += matched_len  # skip duplicate
        else:
            result.append(words[i])
            i += 1

    return ' '.join(result)


def is_structural(line: str) -> bool:
    s = line.strip()
    return (not s or
            s.startswith('#') or
            s.startswith('<') or
            s.startswith('|'))


def is_stray_page_number(line: str) -> bool:
    return bool(re.match(r'^\s*\d{1,3}(\.\d{1,2})?\s*$', line))


def process(content: str) -> str:
    lines = content.split('\n')
    out: list[str] = []
    i = 0

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Structural lines pass through unchanged
        if is_structural(raw):
            out.append(raw)
            i += 1
            continue

        # Drop stray page numbers
        if is_stray_page_number(stripped):
            i += 1
            continue

        # For non-structural content, collect the whole paragraph
        para_lines: list[str] = []
        while i < len(lines):
            l = lines[i]
            if not l.strip():
                break
            if is_structural(l) and para_lines:
                break
            para_lines.append(l.strip())
            i += 1

        if not para_lines:
            i += 1
            continue

        # If paragraph contains structural lines, pass through as-is
        if any(is_structural(l) for l in para_lines):
            out.extend(para_lines)
            continue

        # Join paragraph, fix glued words, then dedup
        joined = ' '.join(para_lines)
        joined = fix_glued_words(joined)
        deduped = remove_repeated_ngrams(joined)

        # Skip paragraphs that are exact/near duplicates of the immediately preceding paragraph
        last_para = next((l for l in reversed(out) if l.strip() and not is_structural(l)), '')
        if last_para:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, deduped.lower(), last_para.lower()).ratio()
            if ratio > 0.85:
                continue

        out.append(deduped)

    return '\n'.join(out)


if __name__ == '__main__':
    input_file  = sys.argv[1] if len(sys.argv) > 1 else 'merged_handbook_local.md'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'merged_handbook_local.deduped.md'

    with open(input_file) as f:
        content = f.read()

    print(f'Input:  {content.count(chr(10))+1:,} lines  {len(content):,} chars')

    result = process(content)

    with open(output_file, 'w') as f:
        f.write(result)

    saved = len(content) - len(result)
    print(f'Output: {result.count(chr(10))+1:,} lines  {len(result):,} chars')
    print(f'Saved:  {saved:,} chars  ({saved/len(content)*100:.1f}% reduction)')
    print(f'→ {output_file}')
