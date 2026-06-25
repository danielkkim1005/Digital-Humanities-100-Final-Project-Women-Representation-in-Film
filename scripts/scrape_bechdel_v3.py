"""
Bechdel Test scraper v3
- Fixes: double-bracket alt [[N]], relative /view/ URLs, <div class="movie"> structure
- Fetches year-specific pages to recover the full database, not just recent years
"""

import re
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://bechdeltest.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.encoding = "ISO-8859-1"
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  Retry {attempt+1}/{retries} for {url}: {e}")
            time.sleep(3)
    return None


def parse_movies(html, year_hint=None):
    """Parse movie entries from an HTML page. Returns list of dicts."""
    movies = []
    soup = BeautifulSoup(html, "html.parser")

    current_year = year_hint

    # Year headings (<h3>) set the context when not passed in
    elements = soup.find_all(["h2", "h3", "div"])

    for el in elements:
        if el.name in ("h2", "h3"):
            m = re.search(r'(\d{4})', el.get_text())
            if m:
                current_year = int(m.group(1))
            continue

        if el.name == "div" and el.get("class") == ["movie"]:
            if current_year is None:
                continue

            # IMDb ID — absolute URL
            imdb_a = el.find("a", href=re.compile(r'imdb\.com/title/tt\d+'))
            if not imdb_a:
                continue
            imdb_m = re.search(r'/title/tt(\d+)', imdb_a["href"])
            if not imdb_m:
                continue
            imdbid = imdb_m.group(1)

            # Rating from alt="[[N]]"
            img = el.find("img", alt=re.compile(r'\[\[\d\]\]'))
            if not img:
                continue
            rating_m = re.search(r'\[{1,2}(\d)\]{1,2}', img.get("alt", ""))
            if not rating_m:
                continue
            rating = int(rating_m.group(1))

            # Dubious from title attribute on the img
            img_title = img.get("title", "")
            dubious = 1 if "dubious" in img_title.lower() else 0

            # Bechdel ID + title from relative /view/ID/ link
            view_a = el.find("a", href=re.compile(r'^/view/\d+/'))
            if not view_a:
                continue
            view_m = re.search(r'/view/(\d+)/', view_a["href"])
            if not view_m:
                continue
            bechdel_id = int(view_m.group(1))
            title = view_a.get_text(strip=True)

            movies.append({
                "id":      bechdel_id,
                "imdbid":  imdbid,
                "title":   title,
                "year":    current_year,
                "rating":  rating,
                "dubious": dubious,
            })

    return movies


def discover_years(html):
    """Find all year links on the page (e.g. /?year=2020 or /year/2020)."""
    years = set()
    # Year headings on-page
    for m in re.finditer(r'(\d{4})\s*\(\d+ movies\)', html):
        years.add(int(m.group(1)))
    # Linked year pages
    for m in re.finditer(r'[?/]year[=/](\d{4})', html):
        years.add(int(m.group(1)))
    return sorted(years)


def find_year_url_pattern(html):
    """Detect what URL pattern the site uses for year-specific pages."""
    patterns = [
        r'href="(/\?year=\d{4})"',
        r'href="(/year/\d{4})"',
        r'href="(/movies/\d{4})"',
        r'href="(/\d{4})"',
    ]
    for pat in patterns:
        if re.search(pat, html):
            return pat
    return None


def main():
    print("Fetching main page...")
    main_html = fetch(BASE_URL)
    if not main_html:
        print("Failed to fetch main page.")
        return

    print(f"  {len(main_html):,} bytes")

    # Parse movies from main page
    all_movies = parse_movies(main_html)
    print(f"  Main page: {len(all_movies)} movies")

    if not all_movies:
        print("  No movies found on main page — check HTML structure.")
        # Print a sample div.movie snippet for debugging
        m = re.search(r'<div class="movie">(.{0,400})', main_html, re.DOTALL)
        if m:
            print("  Sample movie HTML:", repr(m.group()))
        return

    # Check for year-specific pages to get older data
    on_page_years = set(mv["year"] for mv in all_movies)
    print(f"  Years on main page: {sorted(on_page_years)}")

    # Try to find older year URLs
    year_pattern = find_year_url_pattern(main_html)
    print(f"  Year URL pattern: {year_pattern or 'not found on page'}")

    # Try common patterns to find older data
    # Check a few candidate year URL formats
    sample_year = min(on_page_years) - 1
    year_url_candidates = [
        f"{BASE_URL}/?year={sample_year}",
        f"{BASE_URL}/year/{sample_year}",
        f"{BASE_URL}/movies/{sample_year}",
        f"{BASE_URL}/{sample_year}/",
    ]

    working_year_url = None
    for candidate in year_url_candidates:
        print(f"  Testing year URL: {candidate}")
        html = fetch(candidate)
        if html:
            test_movies = parse_movies(html, year_hint=sample_year)
            if test_movies:
                working_year_url = candidate
                print(f"    -> Works! Found {len(test_movies)} movies")
                break
            else:
                print(f"    -> No movies found")
        else:
            print(f"    -> Fetch failed")
        time.sleep(1)

    if working_year_url:
        # Determine the oldest year we need (e.g., 1888)
        oldest_year = 1888
        newest_missing = min(on_page_years) - 1

        print(f"\nFetching year pages {oldest_year}–{newest_missing}...")
        url_template = re.sub(str(sample_year), "{year}", working_year_url)

        years_to_fetch = range(newest_missing, oldest_year - 1, -1)
        for year in years_to_fetch:
            url = url_template.format(year=year)
            html = fetch(url)
            if html:
                yr_movies = parse_movies(html, year_hint=year)
                if yr_movies:
                    all_movies.extend(yr_movies)
                    print(f"  {year}: {len(yr_movies)} movies")
            time.sleep(1.5)   # be polite to their shared hosting
    else:
        print("\nCould not find year-specific URL pattern.")
        print("The main page data only covers recent years.")
        print("You may need to inspect the site manually for pagination.")

    # Build final dataframe
    df = (pd.DataFrame(all_movies)
            .drop_duplicates(subset=["id"])
            .sort_values(["year", "id"])
            .reset_index(drop=True))

    print(f"\n--- Summary ---")
    print(f"Total movies:  {len(df):,}")
    print(f"Year range:    {df['year'].min()}–{df['year'].max()}")
    print(f"Passed (3):    {(df['rating'] == 3).sum():,}")
    print(f"Dubious:       {df['dubious'].sum():,}")
    print(f"\nRating breakdown:\n{df['rating'].value_counts().sort_index().to_string()}")

    out = "bechdel_all_movies.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
