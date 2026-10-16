"""Rebuild veil/data: the name lists and the everyday English words.

Needs wordfreq (pip install wordfreq) and three downloads, saved next to this script or passed as arguments:

- wd_given.csv, wd_surname.csv: the English labels of Wikidata's given names (Q12308941, Q11879590,
  Q3409032, Q202444) and family names (Q101352), one per line under a header, e.g. from
  https://qlever.dev/api/wikidata with  SELECT DISTINCT ?l WHERE { ?i wdt:P31 wd:Q101352 . ?i rdfs:label ?l .
  FILTER(LANG(?l)="en") }  and Accept: text/csv
- Names_2010Census.csv: https://www2.census.gov/topics/genealogy/2010surnames/names.zip

python scripts/build_name_lists.py wd_given.csv wd_surname.csv Names_2010Census.csv
"""
import csv
import gzip
import re
import sys
from pathlib import Path

from wordfreq import top_n_list, zipf_frequency

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from veil.redactor import _ascii  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "veil" / "data"
EVERYDAY = 3.5   # Zipf frequency from which a word counts as everyday English


def labels(path):
    out = set()
    with open(path, encoding="utf-8") as f:
        for i, row in enumerate(csv.reader(f)):
            w = row[0].strip() if row else ""
            if i and re.fullmatch(r"[^\W\d_]+(?:['-][^\W\d_]+)*", w) and len(w) >= 2 and w[0].isupper():
                out.add(w)
    return out


def write(name, header, rows):
    with gzip.open(DATA / f"{name}.txt.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        f.write(f"# {header}\n")
        f.writelines(f"{row}\n" for row in rows)


def main(given_csv, surname_csv, census_csv):
    census = [(row["name"].strip(), int(row["count"])) for row in csv.DictReader(open(census_csv))
              if row["name"].strip().isalpha() and row["name"] != "ALL OTHER NAMES"]
    lists = {"given_names": labels(given_csv), "surnames": labels(surname_csv) | {n.title() for n, _ in census}}
    for name, words in lists.items():
        best = {}
        for w in words:
            folded = _ascii(w).casefold()
            if re.fullmatch(r"[a-z]+(?:['-][a-z]+)*", folded):
                z = max(zipf_frequency(w.lower(), "en"), zipf_frequency(folded, "en"))
                best[folded] = max(best.get(folded, 0), z)
        source = "Wikidata" + (" and the 2010 US Census" if name == "surnames" else "")
        write(name, f"word<TAB>Zipf frequency as an English word (wordfreq); from {source}",
              (f"{w}\t{z:.1f}" for w, z in sorted(best.items()) if z < EVERYDAY))
    write("common_surnames", "Surnames of 500 or more people in the 2010 US Census that are everyday English words too",
          sorted(n.lower() for n, count in census if count >= 500 and zipf_frequency(n.lower(), "en") >= EVERYDAY))
    write("common_words", "English words used at least about 3 times in a million (Zipf 3.5 and up, wordfreq)",
          sorted({w for w in top_n_list("en", 60000)
                  if re.fullmatch(r"[a-z]+(?:['-][a-z]+)*", w) and zipf_frequency(w, "en") >= EVERYDAY}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
