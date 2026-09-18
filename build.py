#!/usr/bin/env python3
"""Build the Elektra dictionary PDF from ordbok.yaml.

    python build.py              validate + build build/ordbok.pdf
    python build.py --check      validate only (no LaTeX needed)
    python build.py --tex-only   write build/*.tex without running LaTeX (CI compiles it)
    python build.py --site DIR   put build/ordbok.pdf + index.html into DIR for hosting

Entries are sorted Norwegian-style (0-9/symbols, A-Z, Æ, Ø, Å) and grouped under
letter headings automatically. Entries with an empty definition stay in the YAML
but are left out of the PDF; links pointing to them render as plain text.
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import textwrap
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "ordbok.yaml"
TEMPLATE = ROOT / "template"
ASSETS = ROOT / "assets"
SITE = ROOT / "site"

FIELDS = ("ord", "nynorsk", "stikkord", "id", "definisjon")
NO_LETTER = "Ikke bokstav"
MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
          "august", "september", "oktober", "november", "desember"]

# [[text]] / [[text|target]], *italic*, "quote"
TOKEN = re.compile(r'\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]|\*([^*\n]+?)\*|"([^"\n]+?)"')
ID_OK = re.compile(r"^[\w-]+$")


class OrdbokError(Exception):
    pass


# ---------------------------------------------------------------- sorting

_NORDIC = {"æ": "{", "ä": "{", "ø": "|", "ö": "|", "å": "}"}  # sort after z


def _fold(ch):
    ch = ch.lower()
    if ch in _NORDIC:
        return _NORDIC[ch]
    return unicodedata.normalize("NFD", ch)[0]


def sort_key(word):
    folded = "".join(_fold(c) for c in word.strip())
    return (0 if section_of(word) == NO_LETTER else 1, folded, word)


def section_of(word):
    first = _fold(word.strip()[:1] or "#")
    if first in "{|}":
        return {"{": "Æ", "|": "Ø", "}": "Å"}[first]
    if "a" <= first <= "z":
        return first.upper()
    return NO_LETTER


def slug(word):
    s = word.lower().replace("æ", "ae").replace("ø", "o").replace("å", "a")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s) or "ord"


# ---------------------------------------------------------------- loading

def _clean(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize(raw, where):
    if not isinstance(raw, dict):
        raise OrdbokError(f"{where}: forventet en oppføring med 'ord:', fikk {raw!r}")
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise OrdbokError(f"{where}: ukjente felt {sorted(unknown)} (lovlige: {', '.join(FIELDS)})")
    e = {k: _clean(raw.get(k)) for k in FIELDS}
    if not e["ord"]:
        raise OrdbokError(f"{where}: mangler 'ord'")
    e["id"] = e["id"] or slug(e["ord"])
    if not ID_OK.match(e["id"]):
        raise OrdbokError(f"{where} ({e['ord']}): ugyldig id {e['id']!r} – bruk bare bokstaver, tall og -")
    return e


def load(path=DATA):
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or []
    except yaml.YAMLError as exc:
        raise OrdbokError(f"{Path(path).name} er ikke gyldig YAML:\n{exc}")
    if not isinstance(data, list):
        raise OrdbokError(f"{Path(path).name} må være en liste med oppføringer (- ord: ...)")
    entries, errors = [], []
    for i, raw in enumerate(data, 1):
        try:
            entries.append(normalize(raw, f"oppføring {i}"))
        except OrdbokError as exc:
            errors.append(str(exc))
    seen = {}
    for e in entries:
        if e["id"] in seen:
            errors.append(f"id {e['id']!r} brukes av både {seen[e['id']]!r} og {e['ord']!r} – sett en unik 'id:'")
        seen.setdefault(e["id"], e["ord"])
    # Render every definition once so broken links are caught here, not by LaTeX.
    if not errors:
        resolve = resolver(entries)
        for e in entries:
            render_text(e["definisjon"], resolve, e["ord"], errors)
    if errors:
        raise OrdbokError("\n".join(errors))
    return entries


def resolver(entries):
    by_id = {e["id"]: e for e in entries}
    by_word = {e["ord"].lower(): e for e in entries}
    return lambda target: by_id.get(target.strip()) or by_word.get(target.strip().lower())


# ---------------------------------------------------------------- LaTeX

_ESC = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "&": r"\&", "%": r"\%",
        "$": r"\$", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def esc(s):
    return "".join(_ESC.get(c, c) for c in s)


def render_text(text, resolve, where, errors):
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        out.append(esc(text[pos:m.start()]))
        pos = m.end()
        link_text, link_target, italic, quote = m.groups()
        if link_text is not None:
            shown = link_text.strip()
            target = resolve(link_target or link_text)
            if target is None:
                errors.append(f"{where}: lenken [[{m.group(0)[2:-2]}]] peker ikke på noe ord eller id")
                out.append(esc(shown))
            elif not target["definisjon"]:
                out.append(esc(shown))  # target is hidden in the PDF
            else:
                out.append(rf"\hyperlink{{{target['id']}}}{{{esc(shown)}}}")
        elif italic is not None:
            out.append(r"\textit{" + render_text(italic, resolve, where, errors) + "}")
        else:
            out.append("``" + render_text(quote, resolve, where, errors) + "''")
    out.append(esc(text[pos:]))
    return "".join(out)


def render_entries(entries):
    resolve = resolver(entries)
    errors = []
    lines, current = [], None
    for e in sorted((e for e in entries if e["definisjon"]), key=lambda e: sort_key(e["ord"])):
        section = section_of(e["ord"])
        if section != current:
            current = section
            lines += [f"\\section*{{{section}}}", r"\hspace*{1em}", ""]
        head = []
        if e["nynorsk"]:
            head.append(f"({esc(e['nynorsk'])})")
        if e["stikkord"]:
            head.append(rf"\textit{{{esc(e['stikkord'])}}}")
        head.append(r"$\bullet$ " + render_text(e["definisjon"], resolve, e["ord"], errors))
        lines += [rf"\ordbokentry{{{e['id']}}}{{{esc(e['ord'])}}}{{{' '.join(head)}}}", ""]
    if errors:
        raise OrdbokError("\n".join(errors))
    return "\n".join(lines) + "\n"


def last_updated():
    """Date of the last commit touching ordbok.yaml (so rebuilds don't move it)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", DATA.name], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        day = datetime.date.fromisoformat(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        day = datetime.date.today()
    return day


def norsk_dato(day):
    return f"{day.day}. {MONTHS[day.month - 1]} {day.year}"


def build(outdir, pdf=True):
    entries = load()
    outdir = Path(outdir)
    if outdir.exists():
        shutil.rmtree(outdir)
    shutil.copytree(TEMPLATE, outdir)
    shutil.copytree(ASSETS, outdir / "assets")
    (outdir / "entries.tex").write_text(render_entries(entries), encoding="utf-8")
    (outdir / "meta.tex").write_text(
        f"\\newcommand{{\\sistoppdatert}}{{{norsk_dato(last_updated())}}}\n", encoding="utf-8")
    if pdf:
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "ordbok.tex"],
                       cwd=outdir, check=True)
    return entries


def build_site(sitedir, pdf, entries):
    sitedir = Path(sitedir)
    if sitedir.exists():
        shutil.rmtree(sitedir)
    shutil.copytree(SITE, sitedir)
    shutil.copy(pdf, sitedir / "ordbok.pdf")
    shutil.copy(ASSETS / "Elektra-Full-Horisontal-Gra.png", sitedir / "logo.png")
    shown = sum(1 for e in entries if e["definisjon"])
    index = sitedir / "index.html"
    index.write_text(index.read_text(encoding="utf-8")
                     .replace("{{ANTALL}}", str(shown))
                     .replace("{{DATO}}", norsk_dato(last_updated())), encoding="utf-8")


# ---------------------------------------------------------------- YAML writing

def _scalar(s):
    if not s:
        return "''"
    out = yaml.safe_dump(s, allow_unicode=True, width=float("inf")).rstrip("\n")
    return out[:-4].rstrip("\n") if out.endswith("\n...") else out


def format_entry(e):
    """One entry as YAML text, definition folded to ~80 columns."""
    lines = [f"- ord: {_scalar(e['ord'])}"]
    for key in ("nynorsk", "stikkord"):
        lines.append(f"  {key}: {_scalar(e.get(key, ''))}")
    if e.get("id") and e["id"] != slug(e["ord"]):
        lines.append(f"  id: {_scalar(e['id'])}")
    definition = _clean(e.get("definisjon"))
    if definition:
        lines.append("  definisjon: >-")
        lines += ["    " + ln for ln in textwrap.wrap(definition, 76, break_long_words=False,
                                                       break_on_hyphens=False)]
    else:
        lines.append("  definisjon: ''")
    return "\n".join(lines) + "\n"


def upsert_entry(entry, path=DATA):
    """Add entry to ordbok.yaml at its alphabetical spot, or fill in the existing entry
    with the same word (empty fields in `entry` keep the old value). Everything else in
    the file is left untouched. Returns "oppdatert" or "lagt til"."""
    text = Path(path).read_text(encoding="utf-8")
    existing = yaml.safe_load(text) or []
    chunks = re.split(r"(?m)^(?=- )", text)
    header, blocks = chunks[0], chunks[1:]
    aligned = len(blocks) == len(existing)
    words = [_clean(raw.get("ord")) if isinstance(raw, dict) else "" for raw in existing]

    match = next((i for i, w in enumerate(words) if w.lower() == entry["ord"].lower()), None)
    if match is not None:
        if not aligned:
            raise OrdbokError(f"fant {entry['ord']!r}, men klarte ikke å lese strukturen i {Path(path).name}")
        old = normalize(existing[match], entry["ord"])
        merged = {k: entry.get(k) or old[k] for k in FIELDS}
        merged["ord"], merged["id"] = old["ord"], old["id"]  # keep existing links working
        blocks[match] = format_entry(merged) + ("\n" if match < len(blocks) - 1 else "")
        result = "oppdatert"
    else:
        block = format_entry(entry)
        if aligned:
            key = sort_key(entry["ord"])
            i = next((i for i, w in enumerate(words) if sort_key(w) > key), len(blocks))
        else:  # unusual formatting: just append
            i = len(blocks)
        if i == len(blocks):
            if blocks:
                blocks[-1] = blocks[-1].rstrip("\n") + "\n\n"
            else:
                header = header.rstrip("\n") + "\n\n" if header.strip() else ""
        else:
            block += "\n"
        blocks.insert(i, block)
        result = "lagt til"
    Path(path).write_text(header + "".join(blocks), encoding="utf-8", newline="\n")
    return result


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate ordbok.yaml only")
    ap.add_argument("--tex-only", action="store_true", help="write the LaTeX sources but don't run latexmk")
    ap.add_argument("--out", default=str(ROOT / "build"), help="build directory")
    ap.add_argument("--site", help="assemble the website in this directory from the built PDF "
                                   "(builds it first if it doesn't exist)")
    args = ap.parse_args()
    pdf = Path(args.out) / "ordbok.pdf"
    try:
        if args.check:
            entries = load()
            render_entries(entries)
        elif args.site and pdf.exists():
            entries = load()
        else:
            entries = build(args.out, pdf=not args.tex_only)
        if args.site:
            build_site(args.site, pdf, entries)
    except OrdbokError as exc:
        for line in str(exc).splitlines():
            print(f"::error file=ordbok.yaml::{line}" if os.environ.get("GITHUB_ACTIONS") else f"FEIL: {line}",
                  file=sys.stderr)
        sys.exit(1)
    hidden = [e["ord"] for e in entries if not e["definisjon"]]
    print(f"OK: {len(entries) - len(hidden)} ord i PDF-en, {len(hidden)} skjult (mangler definisjon)")
    if hidden:
        print("  skjult: " + ", ".join(sorted(hidden, key=sort_key)))


if __name__ == "__main__":
    main()
