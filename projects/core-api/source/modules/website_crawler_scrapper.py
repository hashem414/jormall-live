from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import requests

# ===================================================== #
#              SINGLE PAGE SCRAPER (FALLBACK)           #
# ===================================================== #
def fetch_website_text(url, max_length=1000):
    """
    Fetches and cleans text from a given website URL.
    Uses requests + BeautifulSoup for regular sites.
    Uses Playwright fallback for social platforms.
    """
    def fetch_general_text_social(url, max_length=1000):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_load_state("domcontentloaded")
                html = page.content()
                browser.close()

            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string if soup.title else ""
            meta_desc = ""
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and "content" in meta.attrs:
                meta_desc = meta["content"]

            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            return (title + " " + meta_desc + " " + text)[:max_length]
        except Exception as e:
            return f"[Error fetching social page: {e}]"

    try:
        if any(domain in url for domain in ["facebook.com", "instagram.com", "x.com", "twitter.com"]):
            return fetch_general_text_social(url, max_length=max_length)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'meta', 'footer', 'header', 'form']):
            tag.decompose()

        text = soup.get_text(separator=' ', strip=True)
        return text[:max_length]
    except Exception as e:
        return f"[Error fetching page: {e}]"


# ===================================================== #
#                   DOMAIN CRAWLER                      #
# ===================================================== #
def crawl_entire_domain_as_text(start_url, max_pages=50, max_text_length=3000):
    """
    Crawl all internal pages of a domain using Playwright.
    Falls back to fetch_website_text() if Playwright fails.
    Returns a single concatenated text with page headers.
    """
    visited = set()
    to_visit = [start_url]
    domain = urlparse(start_url).netloc
    all_text = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue

            print(f"[Crawler] Scraping: {url}")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle")
                html = page.content()

                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(['script', 'style', 'noscript', 'meta', 'footer', 'header', 'form']):
                    tag.decompose()

                text = soup.get_text(separator=" ", strip=True)
                all_text.append(f"CONTENT:\n{text[:max_text_length]}")

                for link in soup.find_all("a", href=True):
                    abs_url = urljoin(url, link["href"])
                    if urlparse(abs_url).netloc == domain:
                        if abs_url not in visited and abs_url not in to_visit:
                            to_visit.append(abs_url)

            except Exception as e:
                print(f"[Crawler] Failed on {url}: {e}")
                fallback_text = fetch_website_text(url)
                all_text.append(f"CONTENT:\nNo Data found")

            visited.add(url)

        browser.close()

    return "\n".join(all_text)


