# ComIreland PDF Invoice Processing

A focused web app that converts Robbez PDF invoices into individually downloadable CSV and PDF invoices. Each output contains exactly one Order Ref. The results screen supports downloading one file at a time or downloading all CSVs or PDFs together as individual files.

## Pricing rules

- Standard products: supplier unit price plus the chosen markup (35% by default).
- Gold markup is adjustable and defaults to 27%.
- 9CT/9K gold in Mode `t`: `Gold Fix × Metal ÷ Qty + supplier unit price × 1.27`.
- 18CT/18K gold in Mode `t`: `Gold Fix × Metal × 2 ÷ Qty + supplier unit price × 1.27`.
- Gold items in another Mode: supplier unit price plus the chosen gold markup, with no metal component.
- Unit and line totals are rounded to euro cents.

The invoice date is the date on which the file is processed. The input PDF is handled in memory and is not retained.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8000>.

## Docker

```powershell
docker compose up --build
```

## Tests

```powershell
pytest -q
```

The included tests validate parsing against the provided invoice 4690899, Order Ref splitting, gold calculations, and ZIP/CSV generation.
