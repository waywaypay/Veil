"""Rebuild veil/data: the name lists and the everyday English words.

Needs wordfreq (pip install wordfreq) and three downloads, saved next to this script or passed as arguments:

- wd_given.csv, wd_surname.csv: the English labels of Wikidata's given names (Q12308941, Q11879590,
  Q3409032, Q202444) and family names (Q101352), one per line under a header, e.g. from
  https://qlever.dev/api/wikidata with  SELECT DISTINCT ?l WHERE { ?i wdt:P31 wd:Q101352 . ?i rdfs:label ?l .
  FILTER(LANG(?l)="en") }  and Accept: text/csv
- Names_2010Census.csv: https://www2.census.gov/topics/genealogy/2010surnames/names.zip
- enable1.txt: the ENABLE word list, which has no proper nouns, e.g.
  https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt

python scripts/build_name_lists.py wd_given.csv wd_surname.csv Names_2010Census.csv enable1.txt

A name is kept when it's no everyday English word: rare as a word (Zipf below 3.5), or common but in no dictionary
("Damien", "Thompson").  Each line says how common it is and whether it's a dictionary word too (1 for "Rose").
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


def main(given_csv, surname_csv, census_csv, enable_txt):
    dictionary = {w.strip() for w in open(enable_txt, encoding="utf-8")}
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
        write(name, f"word<TAB>Zipf frequency as an English word (wordfreq)<TAB>1 if a dictionary word; from {source}",
              (f"{w}\t{z:.1f}\t{int(w in dictionary)}" for w, z in sorted(best.items())
               if z < EVERYDAY or w not in dictionary))
    write("common_surnames", "Surnames of 500 or more people in the 2010 US Census that are everyday English words too",
          sorted(n.lower() for n, count in census if count >= 500 and zipf_frequency(n.lower(), "en") >= EVERYDAY))
    write("top_surnames", "The 1,000 commonest surnames in the 2010 US Census, everyday words or not",
          sorted(n.lower() for n, _ in sorted(census, key=lambda c: -c[1])[:1000]))
    write("common_words", "Dictionary words used at least about once in a million (Zipf 3 and up, wordfreq)",
          sorted({w for w in top_n_list("en", 100000) if w in dictionary and zipf_frequency(w, "en") >= 3}))


if __name__ == "__main__":
    main(*sys.argv[1:5])
