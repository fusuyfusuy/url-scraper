# url-scraper

A lightweight, recursive web crawler that maps a static website, extracts all unique hyperlinks, categorizes them as internal or external, and outputs a redirect-ready CSV dataset.

## Features

- Recursive crawl starting from a root URL
- Normalizes URLs: strips query parameters and fragments (treats `example.com/page?a=1` and `example.com/page?a=2` as the same page)
- Categorizes links as **Internal** or **External**
- Records HTTP status codes for every internal URL
- MIME-type filtering: only parses `text/html` pages, skips PDFs, images, etc.
- Graceful error handling: logs timeouts, connection errors, and HTTP errors without crashing
- Rate limiting with configurable delay between requests
- Parallel crawling with configurable worker threads

## Output

Exports a `results.csv` file with columns:

| Column | Description |
|---|---|
| `Original_URL` | The full normalized URL |
| `HTTP_Status_Code` | HTTP response code, or `TIMEOUT` / `CONNECTION_ERROR` on failure |
| `Link_Type` | `Internal` or `External` |
| `Found_On` | The page where this URL was discovered (empty for the start URL) |

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Usage

```bash
uv run main.py <url> [options]
```

### Arguments

**Crawl settings**

| Flag | Default | Description |
|---|---|---|
| `url` | *(required)* | Root URL to start crawling from |
| `-o`, `--output` | `<domain>.csv` | Output CSV file path |
| `-w`, `--workers` | `10` | Number of parallel worker threads |
| `-d`, `--delay` | `0.3` | Delay between requests per worker (seconds) |
| `--timeout` | `5.0` | HTTP request timeout (seconds) |

**Output filters**

| Flag | Description |
|---|---|
| `--filter [all\|internal\|external]` | Only include the specified link type in the CSV (default: `all`) |
| `--errors-only` | Only export URLs with error status codes (4xx, 5xx, timeouts) |
| `--no-found-on` | Omit the `Found_On` column from the CSV |

### Examples

```bash
# Basic crawl
uv run main.py https://example.com

# Save only internal URLs
uv run main.py https://example.com --filter internal

# Find all broken links
uv run main.py https://example.com --errors-only

# Export external links without the Found_On column
uv run main.py https://example.com --filter external --no-found-on -o external.csv

# Gentler crawl (fewer workers, longer delay)
uv run main.py https://example.com -w 5 -d 1.0

# Faster crawl with longer timeout for slow servers
uv run main.py https://example.com -w 20 --timeout 10
```
