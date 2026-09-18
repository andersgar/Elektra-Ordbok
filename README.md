# Ordbok for Linjeforeningen Elektra

Den ferdige ordboka ligger alltid oppdatert på **https://ordbok.garberg.wtf/ordbok.pdf**.

## Legge til et ord

**Alle medlemmer:** bruk skjemaet [Nytt ord](../../issues/new?template=nytt-ord.yml). Det lages
automatisk et forslag (pull request) som ordbokansvarlig godkjenner. Når det er godkjent, er
PDF-en oppdatert etter et par minutter. Finnes ordet fra før, for eksempel uten definisjon,
fylles det ut i stedet.

**Ordbokansvarlig:** rediger [`ordbok.yaml`](ordbok.yaml) direkte på GitHub (blyant-ikonet) og
commit til `main`. Formatet står øverst i fila:

```yaml
- ord: Arrkom
  nynorsk: Arrkjem
  stikkord: Komité
  definisjon: >-
    Komiteen som arrangerer fester. Ansvarlig for [[Åre]]-turen og
    *veldig* mye "moro".
```

- Rekkefølgen i fila spiller ingen rolle. PDF-en sorteres alfabetisk (tall/tegn, A–Z, Æ, Ø, Å) med
  bokstavoverskrifter automatisk.
- `[[Ord]]` eller `[[vist tekst|ord eller id]]` lenker til et annet ord. En lenke til et ord som
  ikke finnes, stopper byggingen med en tydelig feilmelding.
- `definisjon: ''` gjør at ordet blir liggende i fila, men skjules i PDF-en til det fylles ut.
- Tegn som `&`, `%` og `$` kan skrives rett inn. Du trenger ikke LaTeX.

Forordet og oppsettet ligger i [`template/`](template), og bildene i [`assets/`](assets).

## Hvordan det funker

`build.py` leser `ordbok.yaml`, sjekker den, sorterer og skriver LaTeX til `build/`, som kompileres
med `latexmk`. GitHub Actions ([`.github/workflows/ordbok.yml`](.github/workflows/ordbok.yml))
bygger ved hver endring. Pull requests får PDF-en som nedlastbar artifact, og `main` publiseres
som statisk side på Cloudflare Workers (`elektra-ordbok`, se [`wrangler.jsonc`](wrangler.jsonc)).

Bygge lokalt (krever Python med `pyyaml` og en TeX-installasjon med `latexmk`):

```sh
pip install pyyaml
python build.py          # -> build/ordbok.pdf
python build.py --check  # bare sjekk ordbok.yaml
```
