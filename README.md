# Gender Representation in Film
### Bechdel Test Outcomes and the Gender Composition of Above-the-Line Creative Roles

A data pipeline and analysis project examining whether the gender of a film's creative workforce — its directors and writers — correlates with on-screen gender representation as measured by the Bechdel Test, across Hollywood's production history from 1894 to 2026.

Developed as a group project for Digital Humanities (DIGHUM), UC Berkeley, Spring 2025.

---

## Research Question

> Does the gender composition of a film's creative workforce correlate with on-screen gender representation as measured by Bechdel Test outcomes?

Prior work suggests the answer is yes. Lauzen (2026) found that films with at least one woman director employ substantially more women in other behind-the-scenes roles than films with exclusively male directors. Friedman et al. (2017) found that the presence of even one woman writer measurably improved a film's odds of passing the Bechdel Test. This project uses computational methods to test whether that correlation holds at scale across the broader production history captured in the data.

---

## Dataset

The final dataset contains **9,904 films** spanning **1894–2026**, combining crowdsourced Bechdel Test ratings with IMDb metadata and gender-inferred crew information.

### Sources

| Source | What it provides | Access |
|---|---|---|
| [Bechdel Test Movie List](https://bechdeltest.com) | Bechdel ratings (0–3), bechdeltest.com IDs | Scraped (API deprecated 2024) |
| [Nelia Bouzid / Kaggle](https://www.kaggle.com/datasets/nliabzd/movies-imdb-and-bechdel-information/versions/3) | Base merged dataset through early 2024 | Manual download |
| [IMDb Datasets](https://datasets.imdbws.com) | Runtime, genres, ratings, votes, crew | Free TSV downloads |
| [gender-guesser](https://pypi.org/project/gender-guesser/) | First-name gender inference | Python library |

### Column Schema

| Column | Type | Description |
|---|---|---|
| `title` | string | Film title |
| `year` | int | Release year |
| `imdbid` | float | IMDb numeric ID (strip `tt` prefix; e.g. `tt0000574` → `574.0`) |
| `id` | int | bechdeltest.com internal ID |
| `bechdelRating` | int | 0–3 (see scale below) |
| `imdbAverageRating` | float | IMDb weighted average rating |
| `numVotes` | float | Number of IMDb user votes |
| `runtimeMinutes` | int | Film runtime in minutes |
| `genre1` | string | Primary IMDb genre |
| `genre2` | string | Secondary IMDb genre (nullable) |
| `genre3` | string | Tertiary IMDb genre (nullable) |
| `hasFemaleDirector` | int | 1 if any director is inferred female, else 0 |
| `hasFemaleWriter` | int | 1 if any writer is inferred female, else 0 |
| `primaryDirGender` | string | `F`, `M`, or `unknown` — first-listed director |
| `primaryWriterGender` | string | `F`, `M`, or `unknown` — first-listed writer |

### Bechdel Rating Scale

| Score | Criterion |
|---|---|
| 0 | Fewer than two named women |
| 1 | Two named women, but they do not speak to each other |
| 2 | They speak to each other, but only about a man |
| 3 | They speak to each other about something other than a man ✓ |

**57.7% of films in the dataset receive a score of 3** (pass). Score distribution: 0 → 929, 1 → 2,204, 2 → 1,058, 3 → 5,713.

---

## Repository Structure

```
.
├── README.md
├── requirements.txt
├── data/
│   ├── Bechdel_IMDB_Merge0524.csv         # base Kaggle dataset (download separately)
│   ├── bechdel_imdb_updated.csv           # updated through 2026, 9,904 rows
│   └── bechdel_imdb_with_gender.csv       # final dataset with crew gender columns
├── scripts/
│   ├── bechdel_update_pipeline.py         # step 1: scrape bechdeltest.com and merge with IMDb metadata
│   └── add_crew_gender.py                 # step 2: add crew gender columns
└── analysis/
    └── (R scripts for visualization — in progress)
```

---

## Reproducing the Pipeline

### Prerequisites

```bash
pip install -r requirements.txt
```

```
# requirements.txt
requests
beautifulsoup4
pandas
gender-guesser
```

### Step 1 — Update Bechdel ratings through 2026

The [bechdeltest.com](https://bechdeltest.com) API was permanently shut down in 2024 (all endpoints return HTTP 410). This script scrapes the live HTML directly.

```bash
python scripts/scrape_bechdel_v3.py
# Output: bechdel_all_movies.csv
```

### Step 2 — Merge with IMDb metadata

Downloads the base Kaggle dataset (manual, see link above), scrapes bechdeltest.com for all films from 2024 onward, fetches IMDb `title.basics` and `title.ratings`, and produces a single merged CSV.

```bash
# Place Bechdel_IMDB_Merge0524.csv in the same directory first
python scripts/bechdel_update_pipeline.py
# Output: bechdel_imdb_updated.csv
```

### Step 3 — Add crew gender columns

Downloads IMDb `title.crew` and `name.basics`, infers gender from first names via `gender-guesser`, and appends the four crew gender columns to the dataset.

```bash
python scripts/add_crew_gender.py
# Output: bechdel_imdb_with_gender.csv
```

> **Note on runtime:** Steps 2 and 3 each download ~400–600 MB of IMDb data on first run. Both scripts cache the decompressed TSV files locally so subsequent runs are fast.

---

## Methodology Notes

### On gender inference

Gender is inferred from first names using the `gender-guesser` library, which uses a dictionary weighted toward Western European naming conventions. Names common in South Asian, East Asian, and African contexts return `unknown` at a higher rate, introducing a systematic blind spot in the data. This is a documented limitation of the source, not a cleaned-away artifact — consistent with the data feminism principle of showing rather than hiding uncertainty (Rezai 2022).

The category `unknown` is retained as a distinct value in analysis rather than being collapsed into either binary.

### On the Bechdel Test as a measure

The Bechdel Test is a minimum threshold, not a comprehensive measure of gender representation. A film can score 3 while still centering male characters; a film can score 0 while being genuinely substantive. It is treated here as a structural proxy — useful at scale, limited at the level of any individual film — consistent with its use in prior computational work (Friedman et al. 2017).

### On the dataset's scope

The data does not disaggregate women along race, sexuality, disability, or other identity categories. Following Day (2024), this limitation is named openly rather than normalized, and the analysis does not make claims that require that disaggregation.

### On the bechdeltest.com scraper

The site's API (`/api/v1/getAllMovies` and related endpoints) returned HTTP 410 Gone as of mid-2024. The scraper targets the site's HTML directly. Key structural details that differ from the former API:

- Movies are in `<div class="movie">` elements, not `<p>` tags
- Image alt text uses double brackets: `alt="[[2]]"`
- View links use relative paths: `/view/ID/slug/`
- The main page displays approximately 6 recent years; the scraper probes year-specific URL patterns to recover older data

---

## Theoretical Framework

This project sits at the intersection of data feminism and digital humanities practice. Two principles from Rezai (2022) guide the analytical choices: *examine power* — asking who produced the data and under what conditions — and *challenge power* — using the data to surface structural inequalities rather than reproduce them.

The Bechdel Test dataset and IMDb metadata were not designed with feminist data practice in mind. They carry the assumptions of the industries and communities that sourced them. Following Prescott (2023), they are treated as objects to be interrogated rather than neutral inputs, and following Hepworth and Church (2019), each visualization decision is documented to make the embedded arguments explicit.

---

## Limitations

- Gender inference via first name is imprecise, particularly for non-Western names
- The Bechdel Test measures a minimum structural threshold, not representational quality
- Race, sexuality, and other identity categories are not captured in any data source used
- bechdeltest.com ratings are crowdsourced and may reflect individual interpretation
- IMDb crew data reflects credited roles only; uncredited contributions are invisible

---

## Attribution

Dataset concept, research framing, and project direction by **Daniel Kim** and group (DIGHUM, UC Berkeley).

Scraping logic, pipeline architecture, and debugging assisted by **Claude (Anthropic)** via [claude.ai](https://claude.ai). Specifically: the HTML scraper for bechdeltest.com (replacing the defunct API), the IMDb metadata join pipeline, and the crew gender enrichment script.

---

## References

Day, Faithe J. "Debates in #BlackDH: Key Moments and Queer Directions in Black Studies Scholarship." *Digital Humanities Quarterly*, vol. 18, no. 4, 2024.

Friedman, Lyle, et al. "The Writers, Directors, and Producers Who Make Films That Fail the Bechdel Test." *The Pudding*, Mar. 2017, pudding.cool/2017/03/bechdel/.

Hepworth, Katherine, and Christopher Church. "Racism in the Machine: Visualization Ethics in Digital Humanities Projects." *Digital Humanities Quarterly*, vol. 12, no. 4, 2019.

Lauzen, Martha. "The Celluloid Ceiling: Employment of Behind-the-Scenes Women on Top Grossing U.S. Films in 2025." Center for the Study of Women in Television & Film, 14 Jan. 2026.

Prescott, Andrew. "Bias in Big Data, Machine Learning and AI: What Lessons for the Digital Humanities?" *Digital Humanities Quarterly*, vol. 17, no. 2, 2023.

Rezai, Yasamin. "Data Stories for/from All: Why Data Feminism Is for Everyone." *Digital Humanities Quarterly*, vol. 16, no. 2, 2022.
