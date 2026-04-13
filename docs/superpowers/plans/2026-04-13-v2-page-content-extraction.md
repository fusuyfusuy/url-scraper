# V2 Page Content Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract full visible page content from crawled internal HTML pages and save it to a separate JSON file alongside the existing CSV output.

**Architecture:** `fetch()` in `main.py` is extended to also return extracted page content (title, meta_description, h1, headings, body_text). The worker writes URL metadata to the CSV as before, and additionally accumulates page content into a dict that is serialized to `<domain>.json` at the end. A `--no-text` CLI flag disables JSON export.

**Tech Stack:** Python 3.11, BeautifulSoup4 (already a dependency), `json` stdlib

---

### Task 1: Extend `fetch()` to extract page content

**Files:**
- Modify: `main.py` — `fetch()` function

- [ ] **Step 1: Update the `fetch()` return to include page content**

Replace the current `fetch()` function body. The function now returns a 5-tuple: `(url, status_code, new_urls, external_urls, page_content)` where `page_content` is a dict or `None` if the page is not HTML.

```python
def fetch(current_url):
    time.sleep(delay)
    status_code = None
    new_urls = []
    external_urls = []
    page_content = None

    try:
        response = requests.get(current_url, timeout=timeout)
        status_code = response.status_code

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return current_url, status_code, new_urls, external_urls, page_content

        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("a", href=True):
            full_url = normalize_url(urljoin(current_url, link["href"]))
            if not full_url.startswith("http"):
                continue
            link_domain = urlparse(full_url).netloc
            if link_domain == target_domain:
                new_urls.append(full_url)
            else:
                external_urls.append(full_url)

        # Extract page content
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else ""
        h1_tag = soup.find("h1")
        h1 = h1_tag.get_text(strip=True) if h1_tag else ""
        headings = [tag.get_text(strip=True) for tag in soup.find_all(["h1", "h2", "h3"])]

        # Remove non-visible elements before extracting body text
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        body_text = " ".join(soup.get_text(separator=" ").split())

        page_content = {
            "title": title,
            "meta_description": meta_description,
            "h1": h1,
            "headings": headings,
            "body_text": body_text,
        }

    except requests.exceptions.Timeout:
        status_code = "TIMEOUT"
        print(f"  ✗ Timeout: {current_url}")
    except requests.exceptions.ConnectionError:
        status_code = "CONNECTION_ERROR"
        print(f"  ✗ Connection error: {current_url}")
    except Exception as e:
        status_code = f"ERROR: {e}"
        print(f"  ✗ Failed: {current_url} — {e}")

    return current_url, status_code, new_urls, external_urls, page_content
```

- [ ] **Step 2: Update the `worker()` call site to unpack the new 5-tuple**

Replace the existing unpack line in `worker()`:

```python
# Before:
url, status_code, new_urls, external_urls = fetch(current_url)

# After:
url, status_code, new_urls, external_urls, page_content = fetch(current_url)
```

- [ ] **Step 3: Verify the script still runs without errors**

```bash
uv run main.py --help
```

Expected: help text prints, no import or syntax errors.

---

### Task 2: Accumulate page content and write JSON output

**Files:**
- Modify: `main.py` — `crawl_website()` function signature, `worker()`, and post-crawl output section

- [ ] **Step 1: Add `save_text` parameter to `crawl_website()`**

Update the function signature:

```python
def crawl_website(
    start_url,
    output_file="results.csv",
    delay=0.3,
    workers=10,
    timeout=5.0,
    link_filter="all",
    errors_only=False,
    no_found_on=False,
    save_text=True,        # write <domain>.json with page content
):
```

- [ ] **Step 2: Add shared `page_data` dict and its lock inside `crawl_website()`**

Add after the existing `results_lock` / `results` declarations:

```python
page_data_lock = threading.Lock()
page_data = {}  # url -> page_content dict
```

- [ ] **Step 3: Accumulate page content in `worker()`**

Inside `worker()`, after unpacking `fetch()` results, add:

```python
if save_text and page_content is not None:
    with page_data_lock:
        page_data[url] = page_content
```

- [ ] **Step 4: Write JSON file after the CSV is written**

Add after the existing `with open(output_file, ...)` block:

```python
if save_text and page_data:
    json_file = output_file.replace(".csv", ".json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(page_data, f, ensure_ascii=False, indent=2)
    print(f"Page content  : {json_file}")
```

- [ ] **Step 5: Add `import json` at the top of the file**

```python
import json
```

- [ ] **Step 6: Verify output files are created**

```bash
uv run main.py https://example.com -w 2
```

Expected: `example.com.csv` and `example.com.json` both created. JSON keys are internal page URLs, each with `title`, `meta_description`, `h1`, `headings`, `body_text`.

---

### Task 3: Add `--no-text` CLI flag

**Files:**
- Modify: `main.py` — `main()` function

- [ ] **Step 1: Add `--no-text` flag to the output filters group**

```python
output_group.add_argument(
    "--no-text",
    action="store_true",
    help="Skip page content extraction and do not write the JSON file",
)
```

- [ ] **Step 2: Pass `save_text` to `crawl_website()`**

```python
crawl_website(
    args.url,
    output_file=args.output,
    delay=args.delay,
    workers=args.workers,
    timeout=args.timeout,
    link_filter=args.link_filter,
    errors_only=args.errors_only,
    no_found_on=args.no_found_on,
    save_text=not args.no_text,
)
```

- [ ] **Step 3: Verify flag works**

```bash
uv run main.py https://example.com --no-text -w 2
```

Expected: only `example.com.csv` created, no `.json` file.

---

### Task 4: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add JSON output to the Output section**

Add after the CSV table:

```markdown
### Page content (`<domain>.json`)

Saved alongside the CSV for all internal `text/html` pages. Keyed by URL:

\`\`\`json
{
  "https://example.com/about": {
    "title": "About Us",
    "meta_description": "Learn more about our team.",
    "h1": "Our Story",
    "headings": ["Our Story", "The Team", "Contact"],
    "body_text": "Full visible text content of the page..."
  }
}
\`\`\`
```

- [ ] **Step 2: Add `--no-text` to the output filters table**

```markdown
| `--no-text` | Skip page content extraction, do not write the JSON file |
```

- [ ] **Step 3: Add example to the Examples section**

```bash
# Crawl without saving page content
uv run main.py https://example.com --no-text
```

- [ ] **Step 4: Commit everything**

```bash
git add main.py README.md
git commit -m "feat: extract and save full page content to JSON (V2)"
```
