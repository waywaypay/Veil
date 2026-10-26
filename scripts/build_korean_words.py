"""Rebuild veil/data/korean_words.txt.gz: the Korean words veil.hangul counts as everyday, with how common each is.

Needs wordfreq (pip install wordfreq), only here: veil reads the packaged list and needs no wordfreq itself.

python scripts/build_korean_words.py

Kept are the words of Zipf 3.5 and up (hangul.ZIPF), each with its frequency cut, not rounded, to two places, so
no word crosses one of hangul's thresholds on the way.
"""
import gzip
import math
from pathlib import Path

from wordfreq import get_frequency_dict

DATA = Path(__file__).resolve().parents[1] / "veil" / "data"
EVERYDAY = 3.5


def main():
    rows = []
    for word, f in get_frequency_dict("ko").items():
        z = math.log10(f) + 9
        if z >= EVERYDAY:
            rows.append(f"{word}\t{math.floor(z * 100) / 100:.2f}")
    with gzip.open(DATA / "korean_words.txt.gz", "wt", encoding="utf-8", compresslevel=9) as out:
        out.write("# word<TAB>Zipf frequency as a Korean word (wordfreq), Zipf 3.5 and up\n")
        out.writelines(f"{row}\n" for row in sorted(rows))


if __name__ == "__main__":
    main()
