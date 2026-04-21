# Country packs

A country pack is a directory under `countries/<code>/` with four JSON files:

- `country.json` - metadata (name, default language, currency)
- `staffing_patterns.json` - company-name fragments that flag a staffing agency
- `geo_allowlist.json` - location substrings that count as on-country
- `language_hints.json` - per-language stopword lists for likely-language heuristics

## Adding a new country

1. Copy an existing pack: `cp -r countries/de countries/fr`
2. Edit each JSON file for the target country. For France you would swap `germany` / `deutschland` / etc. for `france` / `paris` / `lyon` in `geo_allowlist.json`, and replace the German staffing agencies in `staffing_patterns.json` with French ones (e.g., `adecco`, `manpower`, `randstad`, `crit`).
3. Add a French-language entry to `language_hints.json` under `languages.fr` (stopwords like `le`, `la`, `et`, `nous`, `vous`, `pour`, etc.).
4. Edit the `code` field in `country.json` to match the directory name (`"code": "fr"`). The loader validates this.
5. Select the new pack in your profile: `profiles/<yours>/search.json` -> `"country": "fr"`.
6. If the new country needs a local crawler, author one under `scripts/n8n/` and add an entry to `scripts/n8n/crawlers.json` with `"countries": ["fr"]`.
7. Run `python scripts/build_workflow.py` to regenerate `workflow.json`.

## Shipped packs

- `de` - Germany (DACH staffing agencies, EU/DACH geo allowlist, EN + DE language hints)
- `global` - stub for remote-only profiles (empty allowlists, EN-only)

## Notes

- The English stopword list is duplicated across `de` and `global` packs. If you add a third pack, consider whether to extract it to a shared default; for now the duplication is small enough to tolerate.
- The `code` field in `country.json` must match the directory name. The Python loader raises `ValueError` if they drift.
