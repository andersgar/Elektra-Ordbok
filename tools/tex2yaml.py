#!/usr/bin/env python3
"""One-off migration: the old Overleaf dictionary.tex -> ordbok.yaml.

    python tools/tex2yaml.py path/to/dictionary.tex > ordbok.yaml
"""
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build  # noqa: E402

HEADER = """\
# Ordbok for Linjeforeningen Elektra
#
# Hver oppføring ser slik ut:
#
# - ord: Arrkom                 (påkrevd)
#   nynorsk: Arrkjem            (valgfri)
#   stikkord: Komité            (valgfri)
#   id: arrkom                  (valgfri – lages automatisk fra ordet)
#   definisjon: >-
#     Komiteen som arrangerer fester. Ansvarlig for [[Åre]]-turen og
#     *veldig* mye "moro".
#
# - [[Ord]] eller [[vist tekst|ord eller id]] lager en lenke til et annet ord.
# - *tekst* blir kursiv, "tekst" blir sitat.
# - Tom definisjon (definisjon: '') = ordet skjules i PDF-en til den fylles ut.
# - Rekkefølgen her spiller ingen rolle; PDF-en sorteres alfabetisk automatisk.
# - Linjer kan brytes fritt under "definisjon: >-" så lenge de er rykket inn.

"""

BS = "\\"
ENTRY = re.compile(re.escape(BS) + r"entryref\{(.*?)\}\{(.*?)\}\{(.*?)\}\{(.*)\}\{(.*?)\}\s*$", re.M)
HYPERLINK = re.compile(re.escape(BS) + r"hyperlink\{([^{}]*)\}\{([^{}]*)\}")
TEXTIT = re.compile(re.escape(BS) + r"textit\{([^{}]*)\}")


def convert(definition, resolve):
    def link(m):
        target_id, text = m.group(1), m.group(2).strip()
        hit = resolve(text)
        return f"[[{text}]]" if hit and hit["id"] == target_id else f"[[{text}|{target_id}]]"

    s = HYPERLINK.sub(link, definition)
    s = TEXTIT.sub(r"*\1*", s)
    s = re.sub(r"``(.*?)''", r'"\1"', s)
    s = s.replace(BS + "%", "%").replace(BS + "&", "&")
    if BS in s:
        print(f"WARNING: leftover LaTeX in: {s[:80]}", file=sys.stderr)
    return s


def main():
    tex = Path(sys.argv[1]).read_text(encoding="utf-8")
    raw = [dict(zip(("ord", "nynorsk", "stikkord", "definisjon", "id"), m.groups()))
           for m in ENTRY.finditer(tex)]
    entries = [build.normalize(r, r["ord"]) for r in raw]
    resolve = build.resolver(entries)
    for e in entries:
        e["definisjon"] = convert(e["definisjon"], resolve)
    entries.sort(key=lambda e: build.sort_key(e["ord"]))
    out = HEADER + "\n".join(build.format_entry(e) for e in entries)
    # Round-trip check: what we wrote must load back identically.
    back = [build.normalize(r, "check") for r in yaml.safe_load(out)]
    assert back == entries, "YAML round-trip mismatch"
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    print(f"{len(entries)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
