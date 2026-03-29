#!/usr/bin/env python3
"""Convert merged markdown with local images to a highly styled PDF."""

import markdown
import os
from weasyprint import HTML

INPUT_MD = "merged_handbook_local.cleaned.md"
OUTPUT_PDF = "African_Catfish_Farmers_Handbook.pdf"
BASE_DIR = os.path.abspath(".")

with open(INPUT_MD, "r") as f:
    md_content = f.read()

# Convert markdown to HTML
extensions = ["tables", "toc", "fenced_code", "sane_lists"]
html_body = markdown.markdown(md_content, extensions=extensions)

CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm 2.5cm 2cm;

    @top-center {
        content: "African Catfish Farmer's Handbook";
        font-family: 'Georgia', serif;
        font-size: 9pt;
        color: #5a7a5a;
        border-bottom: 0.5pt solid #5a7a5a;
        padding-bottom: 4pt;
    }

    @bottom-center {
        content: counter(page);
        font-family: 'Georgia', serif;
        font-size: 9pt;
        color: #5a7a5a;
    }
}

@page :first {
    @top-center { content: none; }
    @bottom-center { content: none; }
    margin: 0;
}

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #2c2c2c;
    text-align: justify;
    hyphens: auto;
}

h1 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 26pt;
    color: #1a472a;
    border-bottom: 3pt solid #2d7a4f;
    padding-bottom: 8pt;
    margin-top: 40pt;
    margin-bottom: 16pt;
    page-break-before: always;
    font-weight: 700;
    letter-spacing: -0.5pt;
}

h1:first-of-type {
    page-break-before: avoid;
}

h2 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 18pt;
    color: #2d7a4f;
    margin-top: 28pt;
    margin-bottom: 10pt;
    border-left: 4pt solid #2d7a4f;
    padding-left: 12pt;
    font-weight: 600;
}

h3 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 14pt;
    color: #3a8a5f;
    margin-top: 20pt;
    margin-bottom: 8pt;
    font-weight: 600;
}

h4, h5, h6 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    color: #4a9a6f;
    margin-top: 14pt;
    margin-bottom: 6pt;
}

p {
    margin-bottom: 8pt;
    orphans: 3;
    widows: 3;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 16pt auto;
    border: 1pt solid #ddd;
    border-radius: 4pt;
    box-shadow: 0 2pt 6pt rgba(0,0,0,0.1);
}

div[style*="text-align: center"] {
    text-align: center;
    margin: 16pt 0;
}

div[style*="text-align: center"] img {
    margin: 8pt auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 16pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

table, th, td {
    border: 1pt solid #b0c4b0;
}

th {
    background-color: #2d7a4f;
    color: white;
    padding: 8pt 6pt;
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-weight: 600;
    text-align: left;
}

td {
    padding: 6pt;
    vertical-align: top;
}

tr:nth-child(even) {
    background-color: #f0f7f0;
}

tr:hover {
    background-color: #e0efe0;
}

blockquote {
    border-left: 4pt solid #2d7a4f;
    background-color: #f5faf5;
    padding: 12pt 16pt;
    margin: 16pt 0;
    font-style: italic;
    color: #3a5a3a;
}

code {
    background-color: #f0f4f0;
    padding: 2pt 4pt;
    border-radius: 3pt;
    font-size: 9.5pt;
    font-family: 'Courier New', monospace;
}

pre {
    background-color: #f5f8f5;
    border: 1pt solid #d0ddd0;
    border-radius: 4pt;
    padding: 12pt;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
}

ul, ol {
    margin-bottom: 10pt;
    padding-left: 24pt;
}

li {
    margin-bottom: 4pt;
}

hr {
    border: none;
    border-top: 2pt solid #2d7a4f;
    margin: 24pt 0;
}

a {
    color: #2d7a4f;
    text-decoration: none;
}

/* Caption-like text after images */
em {
    display: block;
    text-align: center;
    font-size: 9.5pt;
    color: #666;
    margin-top: -8pt;
    margin-bottom: 12pt;
}
"""

full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>
"""

print("Converting to PDF... (this may take a minute)")
html = HTML(string=full_html, base_url=BASE_DIR)
html.write_pdf(OUTPUT_PDF)
print(f"PDF created: {OUTPUT_PDF}")
