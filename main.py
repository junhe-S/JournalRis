#!/usr/bin/env python3
"""Zotero Journal Scraper — Main Entry Point

Usage:
    python main.py                     # Download all journals from all publishers
    python main.py sciencedirect       # Download all journals from one publisher
    python main.py jfe rfs jf          # Download specific journals
    python main.py --list              # List all available journals
    python main.py --publisher oxford  # Download all journals from Oxford
"""

import sys
import os
import time
import random

# Suppress multiprocessing resource_tracker warnings (leaked semaphores from Playwright)
os.environ['PYTHONWARNINGS'] = 'ignore'

# Ensure we're in the right working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from function.config import PUBLISHERS, JOURNAL_PUBLISHER
from function.browser import close_browser


LEGACY_PUBLISHERS = {'sage', 'jstor'}


def list_journals():
    """Print all available journals grouped by publisher."""
    print("\nAvailable journals:\n")
    for publisher, journals in PUBLISHERS.items():
        label = f"  {publisher} (legacy):" if publisher in LEGACY_PUBLISHERS else f"  {publisher}:"
        print(label)
        for j in journals:
            print(f"    - {j}")
    print()


def get_scraper(publisher):
    """Import and return the scraper module for a publisher."""
    mod = __import__(f'scrapers.{publisher}', fromlist=[publisher])
    return mod


def download_publisher(publisher):
    """Download all journals for a publisher."""
    print(f"\n{'='*60}")
    print(f"  Publisher: {publisher}")
    print(f"{'='*60}")

    scraper = get_scraper(publisher)
    if hasattr(scraper, 'download_all'):
        scraper.download_all()
    else:
        journals = PUBLISHERS.get(publisher, [])
        for j in journals:
            scraper.download_journal(j)

    # Cleanup browser if the scraper initialized one
    if hasattr(scraper, 'pw') and scraper.pw is not None:
        close_browser(scraper.pw, scraper.tmp_dir, scraper.context)


def download_journal(journal):
    """Download a single journal."""
    publisher = JOURNAL_PUBLISHER.get(journal)
    if not publisher:
        print(f"Unknown journal: {journal}")
        print(f"Use --list to see available journals.")
        return False

    print(f"\n--- {journal} (via {publisher}) ---")
    scraper = get_scraper(publisher)
    scraper.download_journal(journal)
    return True


def download_all():
    """Download all journals from all publishers."""
    for publisher in PUBLISHERS:
        download_publisher(publisher)
        wait = random.uniform(20, 40)
        print(f"\nWaiting {wait:.0f}s before next publisher...")
        time.sleep(wait)


def main():
    args = sys.argv[1:]

    if not args:
        print("Downloading ALL journals from ALL publishers...")
        download_all()
        return

    if '--list' in args:
        list_journals()
        return

    if '--publisher' in args:
        idx = args.index('--publisher')
        if idx + 1 < len(args):
            publisher = args[idx + 1]
            if publisher in PUBLISHERS:
                download_publisher(publisher)
            else:
                print(f"Unknown publisher: {publisher}")
                print(f"Available: {', '.join(PUBLISHERS.keys())}")
        else:
            print("Missing publisher name after --publisher")
        return

    # Check if args are publisher names or journal names
    for arg in args:
        if arg in PUBLISHERS:
            download_publisher(arg)
        elif arg in JOURNAL_PUBLISHER:
            download_journal(arg)
        else:
            print(f"Unknown journal or publisher: {arg}")
            print(f"Use --list to see available options.")


if __name__ == '__main__':
    try:
        main()
        print("\nSuccessfully downloaded.")
    finally:
        # Ensure all scraper browsers are closed before exiting
        for pub in list(PUBLISHERS.keys()):
            try:
                mod = sys.modules.get(f'scrapers.{pub}')
                if mod and getattr(mod, 'pw', None) is not None:
                    close_browser(mod.pw, mod.tmp_dir, mod.context)
            except Exception:
                pass
        os._exit(0)
