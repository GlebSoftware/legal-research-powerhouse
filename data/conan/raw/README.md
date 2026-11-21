# Constitution Annotated tables

Download each table's CSV export from your browser (the site blocks automated clients):

- https://constitution.congress.gov/resources/decisions-overruled/ as `decisions-overruled.csv`
- https://constitution.congress.gov/resources/unconstitutional-laws/ as `unconstitutional-laws.csv`

Then run `uv run python scripts/conan_tables.py`. A page saved as HTML (`<name>.html`) also works; the CSV wins when both exist. Refresh monthly.
