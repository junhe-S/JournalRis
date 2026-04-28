# JournalRis

A tool for batch downloading RIS citation files from academic journal websites, designed for use with Zotero.

> **Note:** The original code that did not rely on Chrome has been invalidated since Cloudflare strengthened its bot protection. The entire codebase has been rewritten to use Chrome (via Playwright) to scrape data, leveraging your local Chrome profile to bypass anti-bot measures.

## Supported Publishers & Journals

| Publisher | Journals |
|-----------|----------|
| ScienceDirect | JCF, JME, JE, JBF, RED, JDE, JIE, JFE, JFI, JFM, JBV, RP |
| Oxford | QJE, RESTUD, RFS, ROF, RCFS |
| Wiley | JF, Econometrica, IER, JMCB |
| UChicago | JPE, JOLE |
| Cambridge | JFQA |
| INFORMS | MNSC, ORSC |
| Springer | JIBS |
| Sage | ASQ |
| AOM | AMJ, AMR |
| JSTOR (legacy) | AER, Econometrica (old) |

## Requirements

- Python 3
- Google Chrome (uses your local Chrome profile for authentication/cookies)
- macOS (Chrome profile path is hardcoded for macOS)

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Download all journals from all publishers
python main.py

# Download all journals from a specific publisher
python main.py sciencedirect

# Download specific journals
python main.py jfe rfs jf

# Download all journals from a publisher by name
python main.py --publisher oxford

# List all available journals
python main.py --list
```

## How It Works

1. Launches Chrome via Playwright using a copy of your local Chrome profile (cookies/auth).
2. Navigates to journal issue pages and downloads RIS citation files.
3. Post-processes the downloaded files: merges, deduplicates, filters junk entries (editorials, etc.), fixes capitalization, and standardizes journal names.
4. Tracks downloads in a local SQLite database (`data/record.db`) to avoid re-downloading.

## Project Structure

```
main.py              # Entry point
function/
  config.py          # Journal/publisher configurations
  browser.py         # Playwright browser setup with stealth settings
  processing.py      # RIS post-processing pipeline
  record.py          # SQLite download tracking
scrapers/            # Per-publisher scraper modules
data/
  issues/            # Downloaded RIS files per journal
  record.db          # Download tracking database
```

## Roadmap

- **Google Chrome Extension** — Under construction. Once available, this will provide a browser-native alternative that eliminates the need for Playwright and `playwright install chromium`.

## Notes

- Some publishers use Cloudflare protection. When detected, the tool pauses and waits for you to solve the challenge in the browser window.
- A random delay is added between publishers to avoid rate limiting.
