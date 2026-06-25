"""
Bechdel + IMDb Update Pipeline
================================
Takes the existing Kaggle dataset (Bechdel_IMDB_Merge0524.csv) as a base,
scrapes bechdeltest.com for all movies from 2024 onward, enriches them with
IMDb metadata, and merges everything into a single updated CSV.

Output columns (matching the Kaggle dataset exactly):
  title, year, imdbid, id, bechdelRating,
  imdbAverageRating, numVotes, runtimeMinutes, genre1, genre2, genre3

Sources:
  - Existing dataset:         Bechdel_IMDB_Merge0524.csv  (your Kaggle file)
  - New Bechdel ratings:      bechdeltest.com (scraped)
  - New IMDb metadata:        datasets.imdbws.com (free TSV downloads)

Run:
  pip install requests beautifulsoup4 pandas
  python bechdel_update_pipeline.py
"""

import re
import time
import gzip
import shutil
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from io import BytesIO

# ── Config ────────────────────────────────────────────────────────────────────

EXISTING_CSV    = "Bechdel_IMDB_Merge0524.csv"   # your downloaded Kaggle file
OUTPUT_CSV      = "bechdel_imdb_updated.csv"
SCRAPE_FROM     = 2024                            # scrape this year and later
BASE_URL        = "https://bechdeltest.com"
IMDB_BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
IMDB_RATINGS_URL= "https://datasets.imdbws.com/title.ratings.tsv.gz"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── Scraper ───────────────────────────────────────────────────────────────────

def fetch_html(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.encoding = "ISO-8859-1"
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  Retry {attempt+1}/{retries} for {url}: {e}")
            time.sleep(3)
    return None


def parse_movies_from_html(html, year_hint=None):
    """Extract movie rows from a bechdeltest.com HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    movies = []
    current_year = year_hint

    for el in soup.find_all(["h2", "h3", "div"]):
        # Year headings
        if el.name in ("h2", "h3"):
            m = re.search(r"(\d{4})", el.get_text())
            if m:
                current_year = int(m.group(1))
            continue

        # Movie entries
        if el.name != "div" or el.get("class") != ["movie"]:
            continue
        if current_year is None or current_year < SCRAPE_FROM:
            continue

        # IMDb ID (absolute URL)
        imdb_a = el.find("a", href=re.compile(r"imdb\.com/title/tt\d+"))
        if not imdb_a:
            continue
        imdb_m = re.search(r"/title/tt(\d+)", imdb_a["href"])
        if not imdb_m:
            continue
        imdbid_int = int(imdb_m.group(1))

        # Rating from alt="[[N]]"
        img = el.find("img", alt=re.compile(r"\[\[\d\]\]"))
        if not img:
            continue
        rating_m = re.search(r"\[{1,2}(\d)\]{1,2}", img.get("alt", ""))
        if not rating_m:
            continue
        rating = int(rating_m.group(1))

        # Dubious flag (not in Kaggle schema but useful for filtering)
        dubious = 1 if "dubious" in img.get("title", "").lower() else 0

        # Bechdeltest ID + title (relative URL /view/ID/)
        view_a = el.find("a", href=re.compile(r"^/view/\d+/"))
        if not view_a:
            continue
        view_m = re.search(r"/view/(\d+)/", view_a["href"])
        if not view_m:
            continue
        bechdel_id = int(view_m.group(1))
        title = view_a.get_text(strip=True)

        movies.append({
            "title":         title,
            "year":          current_year,
            "imdbid":        float(imdbid_int),   # match Kaggle dtype (float)
            "id":            bechdel_id,
            "bechdelRating": rating,
        })

    return movies


def scrape_new_movies():
    """Scrape bechdeltest.com for all movies from SCRAPE_FROM onward."""
    print(f"\n── SCRAPING bechdeltest.com (year >= {SCRAPE_FROM}) ──")
    main_html = fetch_html(BASE_URL)
    if not main_html:
        raise RuntimeError("Failed to fetch main page")

    all_movies = parse_movies_from_html(main_html)
    on_page_years = sorted(set(m["year"] for m in all_movies))
    print(f"  Main page years found: {on_page_years}")
    print(f"  Main page movies:      {len(all_movies)}")

    # Probe year-specific URL patterns for years missing from main page
    # (site only shows ~6 most recent years on homepage)
    needed_years = [y for y in range(SCRAPE_FROM, max(on_page_years, default=SCRAPE_FROM))
                    if y not in on_page_years]

    if needed_years:
        # Detect which URL pattern the site uses
        probe_year = needed_years[0] if needed_years else SCRAPE_FROM
        candidates = [
            f"{BASE_URL}/?year={probe_year}",
            f"{BASE_URL}/year/{probe_year}",
            f"{BASE_URL}/{probe_year}/",
        ]
        working_template = None
        for candidate in candidates:
            html = fetch_html(candidate)
            if html:
                test = parse_movies_from_html(html, year_hint=probe_year)
                if test:
                    working_template = candidate.replace(str(probe_year), "{year}")
                    print(f"  Year URL template: {working_template}")
                    all_movies.extend(test)
                    break
            time.sleep(1)

        if working_template:
            for year in needed_years[1:]:
                url = working_template.format(year=year)
                html = fetch_html(url)
                if html:
                    yr_movies = parse_movies_from_html(html, year_hint=year)
                    all_movies.extend(yr_movies)
                    print(f"  {year}: {len(yr_movies)} movies")
                time.sleep(1.5)
        else:
            print("  Could not find year-specific URL pattern; only main page data available.")

    df = (pd.DataFrame(all_movies)
            .drop_duplicates(subset=["id"])
            .reset_index(drop=True))
    print(f"  Total new movies scraped: {len(df)}")
    return df


# ── IMDb data ─────────────────────────────────────────────────────────────────

def download_imdb_tsv(url, local_path):
    """Download a gzipped IMDb TSV and decompress it."""
    tsv_path = local_path.with_suffix("")   # strip .gz
    if tsv_path.exists():
        print(f"  Using cached {tsv_path.name}")
        return tsv_path
    print(f"  Downloading {url} ...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(local_path, "wb") as f:
        shutil.copyfileobj(r.raw, f)
    with gzip.open(local_path, "rb") as gz, open(tsv_path, "wb") as out:
        shutil.copyfileobj(gz, out)
    local_path.unlink()   # remove the .gz
    print(f"  Saved → {tsv_path.name}")
    return tsv_path


def load_imdb_metadata(imdbid_set):
    """
    Download title.basics and title.ratings, filter to the imdbids we need,
    and return a DataFrame with the columns the Kaggle schema expects.
    """
    print("\n── DOWNLOADING IMDb METADATA ──")
    basics_path  = download_imdb_tsv(IMDB_BASICS_URL,  Path("title.basics.tsv.gz"))
    ratings_path = download_imdb_tsv(IMDB_RATINGS_URL, Path("title.ratings.tsv.gz"))

    # tconst like "tt0000009" → numeric 9 for matching
    def tconst_to_float(s):
        try:
            return float(int(s.lstrip("t")))
        except Exception:
            return None

    print("  Loading title.basics ...")
    basics = pd.read_csv(
        basics_path, sep="\t", dtype=str, na_values=["\\N"],
        usecols=["tconst", "runtimeMinutes", "genres"]
    )
    basics["imdbid"] = basics["tconst"].map(tconst_to_float)
    basics = basics[basics["imdbid"].isin(imdbid_set)].copy()

    # Split genres into genre1/genre2/genre3
    genre_split = basics["genres"].str.split(",", expand=True).reindex(columns=[0,1,2])
    genre_split.columns = ["genre1", "genre2", "genre3"]
    basics = pd.concat([basics[["imdbid", "runtimeMinutes"]], genre_split], axis=1)
    basics["runtimeMinutes"] = pd.to_numeric(basics["runtimeMinutes"], errors="coerce")

    print("  Loading title.ratings ...")
    ratings = pd.read_csv(
        ratings_path, sep="\t", dtype=str, na_values=["\\N"],
        usecols=["tconst", "averageRating", "numVotes"]
    )
    ratings["imdbid"] = ratings["tconst"].map(tconst_to_float)
    ratings = ratings[ratings["imdbid"].isin(imdbid_set)].copy()
    ratings = ratings.rename(columns={"averageRating": "imdbAverageRating"})
    ratings[["imdbAverageRating", "numVotes"]] = ratings[["imdbAverageRating", "numVotes"]].apply(
        pd.to_numeric, errors="coerce"
    )
    ratings = ratings[["imdbid", "imdbAverageRating", "numVotes"]]

    imdb = basics.merge(ratings, on="imdbid", how="inner")
    print(f"  IMDb records matched: {len(imdb)}")
    return imdb


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    # 1. Load existing dataset
    print("\n── LOADING EXISTING DATASET ──")
    existing = pd.read_csv(EXISTING_CSV)
    print(f"  Rows: {len(existing):,}  |  Years: {existing['year'].min()}–{existing['year'].max()}")

    # 2. Scrape new movies
    new_bechdel = scrape_new_movies()
    if new_bechdel.empty:
        print("No new movies scraped — check the scraper output above.")
        return

    # 3. Get IMDb metadata for new movies only
    new_imdbids = set(new_bechdel["imdbid"].dropna())
    imdb_meta   = load_imdb_metadata(new_imdbids)

    # 4. Build new rows (inner join: only movies that have both bechdel + IMDb data)
    new_rows = new_bechdel.merge(imdb_meta, on="imdbid", how="inner")
    # Reorder to match Kaggle schema exactly
    col_order = ["title", "year", "imdbid", "id", "bechdelRating",
                 "imdbAverageRating", "numVotes", "runtimeMinutes",
                 "genre1", "genre2", "genre3"]
    new_rows = new_rows[col_order]
    print(f"\n  New rows after inner join: {len(new_rows)}")

    # 5. Remove from existing any rows whose imdbid appears in new scrape
    #    (the 15 existing 2024 entries may overlap; prefer fresher scraped data)
    existing_trimmed = existing[~existing["imdbid"].isin(new_imdbids)].copy()
    print(f"  Existing rows kept (no overlap): {len(existing_trimmed):,}")

    # 6. Combine and sort
    combined = pd.concat([existing_trimmed, new_rows], ignore_index=True)
    combined = (combined
                .drop_duplicates(subset=["imdbid"])
                .sort_values(["year", "id"])
                .reset_index(drop=True))

    print(f"\n── FINAL DATASET ──")
    print(f"  Total rows:   {len(combined):,}")
    print(f"  Year range:   {combined['year'].min()}–{combined['year'].max()}")
    print(f"  Columns:      {combined.columns.tolist()}")
    print(f"\n  Bechdel rating distribution (all years):")
    print(combined["bechdelRating"].value_counts().sort_index().to_string())
    print(f"\n  New movies (year >= {SCRAPE_FROM}):")
    print(combined[combined["year"] >= SCRAPE_FROM].to_string(index=False))

    combined.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
