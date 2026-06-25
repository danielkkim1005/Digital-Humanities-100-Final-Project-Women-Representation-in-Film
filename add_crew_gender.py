"""
add_crew_gender.py
==================
Takes bechdel_imdb_updated.csv and adds four crew-gender columns by joining
against two freely available IMDb datasets (title.crew and name.basics) and
inferring gender from first names via gender-guesser.

New columns added:
  hasFemaleDirector    - 1 if any director on the film is inferred female, else 0
  hasFemaleWriter      - 1 if any writer on the film is inferred female, else 0
  primaryDirGender     - 'F', 'M', or 'unknown' for the first-listed director
  primaryWriterGender  - 'F', 'M', or 'unknown' for the first-listed writer

Gender inference notes:
  - Uses first name only via the gender-guesser dictionary (no API, works offline)
  - 'female' and 'mostly_female'  -> 'F'
  - 'male'  and 'mostly_male'     -> 'M'
  - 'andy' (androgynous), 'unknown', or no name -> 'unknown'
  - Non-Western names skew toward 'unknown'; flag this as a dataset limitation

Run:
  pip install pandas requests gender-guesser
  python add_crew_gender.py
"""

import gzip
import shutil
import requests
import pandas as pd
import gender_guesser.detector as gender_lib
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_CSV   = "bechdel_imdb_updated.csv"
OUTPUT_CSV  = "bechdel_imdb_with_gender.csv"

IMDB_CREW_URL  = "https://datasets.imdbws.com/title.crew.tsv.gz"
IMDB_NAMES_URL = "https://datasets.imdbws.com/name.basics.tsv.gz"

CHUNK_SIZE = 100_000   # rows per chunk when reading large IMDb TSVs

# ── Helpers ───────────────────────────────────────────────────────────────────

def imdbid_to_tconst(imdbid_float):
    """9.0 -> 'tt0000009',  6146586.0 -> 'tt6146586'"""
    return f"tt{int(imdbid_float):07d}"


def download_and_unpack(url: str, gz_path: Path) -> Path:
    """Download a .tsv.gz, decompress it, return the .tsv path. Caches locally."""
    tsv_path = gz_path.with_suffix("")          # strip .gz
    if tsv_path.exists():
        print(f"  Using cached {tsv_path.name}")
        return tsv_path
    print(f"  Downloading {url} ...")
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(gz_path, "wb") as f:
            shutil.copyfileobj(r.raw, f)
    print(f"  Decompressing ...")
    with gzip.open(gz_path, "rb") as gz, open(tsv_path, "wb") as out:
        shutil.copyfileobj(gz, out)
    gz_path.unlink()
    print(f"  Ready: {tsv_path.name}")
    return tsv_path


def classify_gender(raw: str) -> str:
    """Map gender-guesser output to 'F', 'M', or 'unknown'."""
    if raw in ("female", "mostly_female"):
        return "F"
    if raw in ("male", "mostly_male"):
        return "M"
    return "unknown"


# ── Step 1: load existing dataset ─────────────────────────────────────────────

print("\n── LOADING DATASET ──")
df = pd.read_csv(INPUT_CSV)
print(f"  {len(df):,} rows  |  columns: {df.columns.tolist()}")

df["tconst"] = df["imdbid"].apply(imdbid_to_tconst)
tconst_set = set(df["tconst"])
print(f"  Unique tconsts: {len(tconst_set):,}")


# ── Step 2: download crew file, filter to our movies ─────────────────────────

print("\n── CREW DATA ──")
crew_tsv = download_and_unpack(IMDB_CREW_URL, Path("title.crew.tsv.gz"))

print("  Filtering crew rows ...")
crew_chunks = []
for chunk in pd.read_csv(
    crew_tsv, sep="\t", na_values=["\\N"], dtype=str,
    usecols=["tconst", "directors", "writers"],
    chunksize=CHUNK_SIZE
):
    match = chunk[chunk["tconst"].isin(tconst_set)]
    if not match.empty:
        crew_chunks.append(match)

crew = pd.concat(crew_chunks, ignore_index=True) if crew_chunks else pd.DataFrame(
    columns=["tconst", "directors", "writers"]
)
print(f"  Matched crew rows: {len(crew):,}")

# Collect every nconst we need for name lookup
def split_nconsts(series):
    result = set()
    for val in series.dropna():
        result.update(val.split(","))
    return result

director_nconsts = split_nconsts(crew["directors"])
writer_nconsts   = split_nconsts(crew["writers"])
all_nconsts      = director_nconsts | writer_nconsts
print(f"  Unique nconsts to look up: {len(all_nconsts):,}")


# ── Step 3: download name.basics, get first names ────────────────────────────

print("\n── NAME DATA ──")
names_tsv = download_and_unpack(IMDB_NAMES_URL, Path("name.basics.tsv.gz"))

print("  Filtering name rows ...")
name_chunks = []
for chunk in pd.read_csv(
    names_tsv, sep="\t", na_values=["\\N"], dtype=str,
    usecols=["nconst", "primaryName"],
    chunksize=CHUNK_SIZE
):
    match = chunk[chunk["nconst"].isin(all_nconsts)]
    if not match.empty:
        name_chunks.append(match)

names = pd.concat(name_chunks, ignore_index=True) if name_chunks else pd.DataFrame(
    columns=["nconst", "primaryName"]
)
print(f"  Matched name rows: {len(names):,}")


# ── Step 4: infer gender from first name ─────────────────────────────────────

print("\n── GENDER INFERENCE ──")
detector = gender_lib.Detector()

def first_name(full_name):
    if pd.isna(full_name) or not str(full_name).strip():
        return ""
    return str(full_name).strip().split()[0]

names["firstName"]      = names["primaryName"].apply(first_name)
names["inferredGender"] = names["firstName"].apply(
    lambda n: classify_gender(detector.get_gender(n)) if n else "unknown"
)
nconst_to_gender = dict(zip(names["nconst"], names["inferredGender"]))

# Distribution
dist = names["inferredGender"].value_counts()
total = len(names)
print(f"  F:       {dist.get('F', 0):,}  ({dist.get('F', 0)/total*100:.1f}%)")
print(f"  M:       {dist.get('M', 0):,}  ({dist.get('M', 0)/total*100:.1f}%)")
print(f"  unknown: {dist.get('unknown', 0):,}  ({dist.get('unknown', 0)/total*100:.1f}%)")
print("  (Note: non-Western first names disproportionately land in 'unknown')")


# ── Step 5: compute per-movie gender flags ────────────────────────────────────

print("\n── BUILDING PER-MOVIE FLAGS ──")

def genders_for_nconst_list(nconst_str):
    """Given a comma-separated nconst string, return list of inferred genders."""
    if pd.isna(nconst_str):
        return []
    return [nconst_to_gender.get(n, "unknown") for n in nconst_str.split(",")]

def has_female(genders):
    return 1 if "F" in genders else 0

def primary_gender(genders):
    return genders[0] if genders else "unknown"

crew["dirGenders"]    = crew["directors"].apply(genders_for_nconst_list)
crew["writerGenders"] = crew["writers"].apply(genders_for_nconst_list)

crew["hasFemaleDirector"]   = crew["dirGenders"].apply(has_female)
crew["hasFemaleWriter"]     = crew["writerGenders"].apply(has_female)
crew["primaryDirGender"]    = crew["dirGenders"].apply(primary_gender)
crew["primaryWriterGender"] = crew["writerGenders"].apply(primary_gender)

crew_flags = crew[["tconst", "hasFemaleDirector", "hasFemaleWriter",
                    "primaryDirGender", "primaryWriterGender"]]


# ── Step 6: merge back into main dataset ─────────────────────────────────────

print("\n── MERGING ──")
merged = df.merge(crew_flags, on="tconst", how="left")
merged = merged.drop(columns=["tconst"])

# Movies with no crew entry get NaN → fill with 0 / 'unknown'
merged["hasFemaleDirector"]   = merged["hasFemaleDirector"].fillna(0).astype(int)
merged["hasFemaleWriter"]     = merged["hasFemaleWriter"].fillna(0).astype(int)
merged["primaryDirGender"]    = merged["primaryDirGender"].fillna("unknown")
merged["primaryWriterGender"] = merged["primaryWriterGender"].fillna("unknown")

print(f"  Final rows: {len(merged):,}")
print(f"  Final columns: {merged.columns.tolist()}")

print(f"\n  hasFemaleDirector = 1: {merged['hasFemaleDirector'].sum():,}  "
      f"({merged['hasFemaleDirector'].mean()*100:.1f}%)")
print(f"  hasFemaleWriter   = 1: {merged['hasFemaleWriter'].sum():,}  "
      f"({merged['hasFemaleWriter'].mean()*100:.1f}%)")

print(f"\n  primaryDirGender distribution:")
print(merged["primaryDirGender"].value_counts().to_string())

print(f"\n  Bechdel pass rate by director gender:")
for g in ["F", "M", "unknown"]:
    sub = merged[merged["primaryDirGender"] == g]
    if len(sub) > 0:
        pass_rate = (sub["bechdelRating"] == 3).mean() * 100
        print(f"    {g}: {pass_rate:.1f}%  (n={len(sub):,})")


# ── Step 7: save ──────────────────────────────────────────────────────────────

merged.to_csv(OUTPUT_CSV, index=False)
print(f"\nSaved -> {OUTPUT_CSV}")
