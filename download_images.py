#!/usr/bin/env python3
"""Download all images from the merged markdown and update references to local paths."""

import re
import os
import hashlib
import urllib.request
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

MERGED_FILE = "merged_handbook.md"
OUTPUT_FILE = "merged_handbook_local.md"
IMAGES_DIR = "images"

os.makedirs(IMAGES_DIR, exist_ok=True)

# Read the markdown
with open(MERGED_FILE, "r") as f:
    content = f.read()

# Extract all image URLs
urls = re.findall(r"src='([^']+)'", content)
unique_urls = list(dict.fromkeys(urls))  # preserve order, deduplicate

print(f"Found {len(unique_urls)} unique image URLs to download")

# Create SSL context that doesn't verify (these are temporary OCR URLs)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url_to_local = {}
failed = []

def download_image(idx_url):
    idx, url = idx_url
    ext = ".png"
    filename = f"img_{idx:03d}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return url, filepath, True

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
        return url, filepath, True
    except Exception as e:
        return url, filepath, False

# Download with thread pool
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(download_image, (i, url)): url
               for i, url in enumerate(unique_urls)}

    done = 0
    for future in as_completed(futures):
        url, filepath, success = future.result()
        done += 1
        if success:
            url_to_local[url] = filepath
            sys.stdout.write(f"\r  Downloaded {done}/{len(unique_urls)}")
        else:
            failed.append(url)
            sys.stdout.write(f"\r  Downloaded {done}/{len(unique_urls)} (failed: {len(failed)})")
        sys.stdout.flush()

print()
print(f"Successfully downloaded: {len(url_to_local)}")
print(f"Failed: {len(failed)}")

# Replace URLs with local paths in the markdown
new_content = content
for url, local_path in url_to_local.items():
    new_content = new_content.replace(url, local_path)

with open(OUTPUT_FILE, "w") as f:
    f.write(new_content)

print(f"Written {OUTPUT_FILE} with local image references")

if failed:
    print("\nFailed URLs:")
    for u in failed:
        print(f"  {u}")
