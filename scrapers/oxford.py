import pandas as pd
import re
import os
import sys
import time
import random
from tqdm import tqdm
from function.config import oxford
from function.processing import postprocess
from function.browser import create_browser, human_delay, close_browser, wait_for_cloudflare
from function.record import save as record_save, _connect as record_connect


# Module-level browser state (initialized lazily)
pw = None
tmp_dir = None
context = None
page = None


def _browser_init():
    global pw, tmp_dir, context, page
    if page is not None:
        return
    print('Launching browser...')
    pw, tmp_dir, context, page = create_browser()


def _issues(j):
    """Get all issues for a journal by visiting each volume page.

    Phase 1: load the browse-by-volume page to get one entry per volume.
    Phase 2: visit each volume page to discover all issues within it.
    Returns a DataFrame with all individual issues.
    """
    url = f"https://academic.oup.com/{j}/issue/?browseBy=volume"
    print(f"  Loading {url} ...")
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    content = page.content()
    title = page.title()
    print(f"  Page title: {title}")

    # Handle bot detection / Cloudflare challenge
    if 'Validate User' in title or 'Just a moment' in content or 'Verifying you are human' in content:
        input("  ⏳ Bot detection — please solve it in the browser, then press Enter...")
        page.wait_for_timeout(5000)
        content = page.content()

    volumes = re.findall(r'value="(/\w+/issue/\d+/\d+)', content)
    volumes = list(dict.fromkeys(volumes))  # dedupe, preserve order

    # Check record.db: skip volumes already marked as 'scanned'
    min_vol = None
    try:
        conn = record_connect()
        row = conn.execute(
            'SELECT MIN(CAST(volume_num AS INTEGER)) FROM downloads WHERE journal = ? AND state IS NULL',
            (j,)
        ).fetchone()
        conn.close()
        if row and row[0] is not None:
            min_vol = row[0]
    except Exception:
        pass

    if min_vol is not None:
        # Only scan volumes >= the first unlabeled volume
        filtered = []
        for v in volumes:
            vol_num = int(re.search(r'/issue/(\d+)/', v).group(1))
            if vol_num >= min_vol:
                filtered.append(v)
        print(f"  Found {len(volumes)} volumes, scanning {len(filtered)} (vol >= {min_vol})...")
        volumes = filtered
    else:
        print(f"  Found {len(volumes)} volumes, discovering all issues...")

    # Visit each volume page to discover all issues
    all_issues = set()
    for vol_uri in tqdm(volumes, desc=f"  scanning", unit="vol"):
        vol_url = f"https://academic.oup.com{vol_uri}"
        try:
            page.goto(vol_url, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            page.wait_for_timeout(3000)
        page.wait_for_timeout(3000)
        vol_content = page.content()

        if 'Just a moment' in vol_content or 'Verifying you are human' in vol_content:
            input("  ⏳ Cloudflare — solve it in the browser, then press Enter...")
            page.wait_for_timeout(5000)
            vol_content = page.content()

        found = re.findall(r'issue-entry" value="(/\w+/issue/\d+/\d+)', vol_content)
        if found:
            all_issues.update(found)
        else:
            all_issues.add(vol_uri)
        human_delay(2, 5)

    df = pd.DataFrame(data={'uriLookup': list(all_issues)})
    if not df.empty:
        df['coverDateStart'] = df['uriLookup'].str.extract(r'(\d+/\d+)')
        df['coverDateStart'] = df['coverDateStart'].str.replace('/', '-')
    df.drop_duplicates(inplace=True)
    df.reset_index(drop=True, inplace=True)
    print(f"  Found {len(df)} total issues across all volumes")
    return df

def _dois(issue):
    """Get article DOIs from an issue page."""
    url = f"https://academic.oup.com{issue}"
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
    except Exception:
        tqdm.write(f"  [!] Timeout loading {issue}, retrying...")
        page.wait_for_timeout(3000)

    page.wait_for_timeout(5000)
    content = page.content()

    # If Cloudflare appeared, wait for manual solve
    if 'Just a moment' in content or 'Verifying you are human' in content:
        input("  ⏳ Cloudflare — solve it in the browser, then press Enter...")
        page.wait_for_timeout(5000)
        content = page.content()

    dois = re.findall(r'<a href="/\w+/article/\d+/\d+/\d+/(\d+)', content)
    dois = list(set(dois))
    return dois

def _ris(dois, file):
    """Download RIS for all article DOIs."""
    for attempt in range(5):
        try:
            ris_parts = []
            for doi in dois:
                url = f"https://academic.oup.com/Citation/Download?resourceId={doi}&resourceType=3&citationFormat=0"
                body = page.evaluate("""async (url) => {
                    const resp = await fetch(url);
                    return await resp.text();
                }""", url)

                if body and '<!DOCTYPE html>' not in body:
                    ris_parts.append(body)
                human_delay(1, 3)

            if ris_parts:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(ris_parts))
                tqdm.write(f"  Saved: {file} ({len(ris_parts)}/{len(dois)} articles)")
                return True
            else:
                tqdm.write(f"  [!] No valid RIS (attempt {attempt + 1}/5), cooling down...")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False

def download_journal(j):
    _browser_init()
    name = oxford[j]['name']
    print(f"\n=== Processing {name} ===")

    df = _issues(j)
    os.makedirs(f'./data/issues/oxford/{j}', exist_ok=True)

    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/oxford/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])

        dois = _dois(row['uriLookup'])
        if dois:
            success = _ris(dois, filepath)
            if success:
                record_save(j, row['coverDateStart'], filepath)
            else:
                failed.append(row['coverDateStart'])
        else:
            tqdm.write(f"  [!] No articles found for {row['coverDateStart']}")

        human_delay(5, 15)
    pbar.close()

    # Label all downloaded issues as 'scanned' except the latest volume
    try:
        conn = record_connect()
        max_vol = conn.execute(
            'SELECT MAX(CAST(volume_num AS INTEGER)) FROM downloads WHERE journal = ?',
            (j,)
        ).fetchone()[0]
        if max_vol is not None:
            conn.execute(
                'UPDATE downloads SET state = "scanned" WHERE journal = ? AND CAST(volume_num AS INTEGER) < ?',
                (j, max_vol)
            )
            conn.execute(
                'UPDATE downloads SET state = NULL WHERE journal = ? AND CAST(volume_num AS INTEGER) = ?',
                (j, max_vol)
            )
            conn.commit()
        conn.close()
    except Exception:
        pass

    if failed:
        print(f"\n[!] {name}: {len(failed)} issues failed:")
        for f in failed:
            print(f"    - {f}")
    return failed

def download_all():
    _browser_init()
    journals = [k for k in oxford.keys() if k != 'journals']
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='oxford')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='oxford')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
