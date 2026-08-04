# OTC Tax Deed Finder

Live inventory of US property you can buy **over the counter** — no auction, no bidding
war — scraped daily from state and county sources and rendered as a single browsable page.

**Live site:** https://suncal.github.io/tax-deeds/

## What it covers

| Source | Coverage | Publishes a market value? |
|---|---|---|
| Mississippi Secretary of State — tax-forfeited inventory | statewide, all counties | **Yes** — plus street address, acreage and a blighted flag |
| Texas struck-off / resale lists (Perdue Brandon) | ~20 counties & districts | **Yes** — court-appraised value beside the minimum bid |
| Alabama Dept. of Revenue transcripts | all 68 county transcripts | No — price only |
| Delaware County PA repository | 1 county, with addresses | No — flat $1,000 bid |

## Honesty rules baked into the build

- **Discount % is only shown where the government publishes a value.** It is never estimated.
- **ARV, rehab and profit are a model**, driven by assumptions the reader sets on the page.
  No tax list publishes an ARV.
- **Land vs. home and repair status are only claimed where the source states them.** Alabama
  legal descriptions like `LOT 11 BLK 4 HOMER HIGHLANDS` are platted city lots that often have a
  house on them, so those stay `unknown` rather than being guessed vacant.
- **A `floor price` badge** marks programs (Mississippi) where the published number is a
  statutory minimum, not a quote.
- A source that fails is shown in red on the page rather than silently vanishing from the counts.

## Running it locally

```bash
pip install -r scrapers/requirements.txt
python scrapers/build.py          # rebuilds data.json (~3 min)
python -m http.server 4488        # then open http://localhost:4488
```

`data.json` must be served over http — browsers block `fetch` on `file://`.

## Automation

`.github/workflows/update.yml` re-scrapes every day at 11:17 UTC, refuses to publish a run that
returns implausibly few rows, commits `data.json`, and redeploys Pages.

## Not investment advice

A screening tool built from public records. Verify every number against the county before
committing money.
