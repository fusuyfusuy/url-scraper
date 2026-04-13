import csv
import time
import threading
import queue
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed


def normalize_url(url):
    parsed = urlparse(url)
    return parsed._replace(fragment="", query="").geturl()


def crawl_website(
    start_url,
    output_file="results.csv",
    delay=0.3,
    workers=10,
    timeout=5.0,
    link_filter="all",       # "all" | "internal" | "external"
    errors_only=False,       # only rows with non-2xx / error status
    no_found_on=False,       # omit Found_On column
):
    target_domain = urlparse(start_url).netloc

    url_queue = queue.Queue()
    url_queue.put((normalize_url(start_url), ""))  # (url, found_on)

    visited_lock = threading.Lock()
    visited_urls = set()

    results_lock = threading.Lock()
    results = []

    # Track in-flight URLs so we don't double-queue them
    queued_lock = threading.Lock()
    queued_urls = {normalize_url(start_url)}

    active_count = threading.Semaphore(0)
    in_flight = threading.Lock()
    pending = [0]  # mutable counter: URLs submitted but not yet finished
    pending_lock = threading.Lock()

    print(f"Starting crawl on: {start_url} (workers={workers})\n" + "-" * 40)

    def fetch(current_url):
        time.sleep(delay)
        status_code = None
        new_urls = []
        external_urls = []

        try:
            response = requests.get(current_url, timeout=timeout)
            status_code = response.status_code

            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return current_url, status_code, new_urls, external_urls

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

        except requests.exceptions.Timeout:
            status_code = "TIMEOUT"
            print(f"  ✗ Timeout: {current_url}")
        except requests.exceptions.ConnectionError:
            status_code = "CONNECTION_ERROR"
            print(f"  ✗ Connection error: {current_url}")
        except Exception as e:
            status_code = f"ERROR: {e}"
            print(f"  ✗ Failed: {current_url} — {e}")

        return current_url, status_code, new_urls, external_urls

    def worker():
        while True:
            try:
                current_url, found_on = url_queue.get(timeout=2)
            except queue.Empty:
                break

            with visited_lock:
                if current_url in visited_urls:
                    url_queue.task_done()
                    continue
                visited_urls.add(current_url)

            print(f"Crawling: {current_url}")
            url, status_code, new_urls, external_urls = fetch(current_url)

            with results_lock:
                results.append({
                    "Original_URL": url,
                    "HTTP_Status_Code": status_code,
                    "Link_Type": "Internal",
                    "Found_On": found_on,
                })
                for ext_url in external_urls:
                    results.append({
                        "Original_URL": ext_url,
                        "HTTP_Status_Code": None,
                        "Link_Type": "External",
                        "Found_On": current_url,
                    })

            with queued_lock:
                for new_url in new_urls:
                    if new_url not in queued_urls:
                        queued_urls.add(new_url)
                        url_queue.put((new_url, current_url))

            url_queue.task_done()

    threads = []
    for _ in range(workers):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)

    url_queue.join()

    for t in threads:
        t.join(timeout=0)

    # Deduplicate
    seen = set()
    unique_results = []
    for row in results:
        key = (row["Original_URL"], row["Link_Type"])
        if key not in seen:
            seen.add(key)
            unique_results.append(row)

    # Apply output filters
    filtered = unique_results
    if link_filter == "internal":
        filtered = [r for r in filtered if r["Link_Type"] == "Internal"]
    elif link_filter == "external":
        filtered = [r for r in filtered if r["Link_Type"] == "External"]

    def _is_error(r):
        code = r["HTTP_Status_Code"]
        if code is None:
            return False
        if isinstance(code, int):
            return code >= 400
        return True  # TIMEOUT / CONNECTION_ERROR / ERROR strings

    if errors_only:
        filtered = [r for r in filtered if _is_error(r)]

    fieldnames = ["Original_URL", "HTTP_Status_Code", "Link_Type"]
    if not no_found_on:
        fieldnames.append("Found_On")
    else:
        for row in filtered:
            row.pop("Found_On", None)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filtered)

    internal = [r for r in unique_results if r["Link_Type"] == "Internal"]
    external = [r for r in unique_results if r["Link_Type"] == "External"]
    errors = [r for r in unique_results if _is_error(r)]

    print("\n" + "=" * 40)
    print("CRAWL COMPLETE")
    print("=" * 40)
    print(f"Internal URLs : {len(internal)}")
    print(f"External URLs : {len(external)}")
    print(f"Errors        : {len(errors)}")
    print(f"Rows exported : {len(filtered)}")
    print(f"Output saved  : {output_file}")

    return unique_results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="url-scraper",
        description="Recursively crawl a static website and export all URLs to CSV.",
    )
    parser.add_argument(
        "url",
        help="Root URL to start crawling from (e.g. https://example.com)",
    )
    parser.add_argument(
        "-o", "--output",
        default="results.csv",
        metavar="FILE",
        help="Output CSV file path (default: results.csv)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=10,
        metavar="N",
        help="Number of parallel worker threads (default: 10)",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=0.3,
        metavar="SECONDS",
        help="Delay between requests per worker in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="HTTP request timeout in seconds (default: 5)",
    )

    output_group = parser.add_argument_group("output filters")
    output_group.add_argument(
        "--filter",
        dest="link_filter",
        choices=["all", "internal", "external"],
        default="all",
        help="Which link types to include in the CSV (default: all)",
    )
    output_group.add_argument(
        "--errors-only",
        action="store_true",
        help="Only export URLs with error status codes (4xx, 5xx, timeouts)",
    )
    output_group.add_argument(
        "--no-found-on",
        action="store_true",
        help="Omit the Found_On column from the CSV",
    )

    args = parser.parse_args()
    if args.output == "results.csv":
        domain = urlparse(args.url).netloc.replace(":", "_")
        args.output = f"{domain}.csv"
    crawl_website(
        args.url,
        output_file=args.output,
        delay=args.delay,
        workers=args.workers,
        timeout=args.timeout,
        link_filter=args.link_filter,
        errors_only=args.errors_only,
        no_found_on=args.no_found_on,
    )


if __name__ == "__main__":
    main()
