#!/usr/bin/env python3
"""Turn a "Nytt ord" issue (GitHub issue form) into an edit of ordbok.yaml.

Reads the issue body from $ISSUE_BODY, adds the word at its alphabetical spot (or
fills in the existing entry with the same word), then validates the whole file.
Writes `ord` and `handling` to $GITHUB_OUTPUT. On failure, writes the reason
to $GITHUB_OUTPUT as `feil` and exits 1.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build  # noqa: E402

LABELS = {"ord": "ord", "nynorsk": "nynorsk", "stikkord": "stikkord", "definisjon": "definisjon"}


def parse(body):
    fields = {}
    for m in re.finditer(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", body, re.M | re.S):
        key = LABELS.get(m.group(1).strip().lower())
        value = m.group(2).strip()
        if key and value != "_No response_":
            fields[key] = value
    return fields


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = []
    for k, v in kv.items():
        lines.append(f"{k}<<__EOF__\n{v}\n__EOF__")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def main():
    fields = parse(os.environ.get("ISSUE_BODY", ""))
    original = build.DATA.read_bytes()
    try:
        if not fields.get("ord"):
            raise build.OrdbokError("fant ikke feltet «Ord» – bruk skjemaet «Nytt ord» når du lager saken")
        if not fields.get("definisjon"):
            raise build.OrdbokError("definisjonen er tom")
        entry = build.normalize(fields, "skjemaet")
        entry["id"] = ""  # let upsert keep an existing id / format_entry derive one
        handling = build.upsert_entry(entry)
        build.render_entries(build.load())
    except build.OrdbokError as exc:
        build.DATA.write_bytes(original)
        output(feil=str(exc))
        print(f"FEIL: {exc}", file=sys.stderr)
        sys.exit(1)
    output(ord=entry["ord"], handling=handling)
    print(f"{entry['ord']}: {handling}")


if __name__ == "__main__":
    main()
