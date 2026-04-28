import pandas as pd
import re
import os
import sys
import time
import random
from tqdm import tqdm
from function.config import informs
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


def _goto(url):
    """Navigate and handle Cloudflare if needed."""
    try:
        page.goto(url, wait_until='commit', timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(8000)
    content = page.content()
    if 'Just a moment' in content or 'Verifying you are human' in content:
        input("  ⏳ Cloudflare — solve it in the browser, then press Enter...")
        page.wait_for_timeout(5000)
        content = page.content()
    return content

def _issues(j, year):
    """Get issues for a given year via widget API."""
    url = informs[j]['url']
    url += f'd{year - (year % 10)}.y{year}'

    body = page.evaluate("""async (url) => {
        const resp = await fetch(url, { credentials: 'include' });
        return await resp.text();
    }""", url)

    text = body.replace('\\"', '"')
    issues = re.findall(f'href="(/toc/{j}/\\d+/\\d+)"', text)

    df = pd.DataFrame(data={'uriLookup': issues})
    if not df.empty:
        df['coverDateStart'] = df['uriLookup'].apply(
            lambda x: re.sub(r'/(?=\d)', '-', x.split(f"/toc/{j}/")[1])
        )
        df.drop_duplicates(inplace=True)
    time.sleep(1)
    return df

def _scan_all_issues(j, start_year, end_year):
    """Phase 1: Scan all years to build a complete issue list."""
    # Check record.db for the first unlabeled volume to limit scanning
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

    all_dfs = []
    for year in tqdm(range(end_year, start_year - 1, -1), desc=f"  scanning years", unit="yr"):
        df = _issues(j, year)
        if df.empty:
            continue

        if min_vol is not None:
            # Only keep issues from volumes >= min_vol
            df['_vol'] = df['coverDateStart'].str.split('-').str[0].astype(int)
            filtered = df[df['_vol'] >= min_vol].drop(columns=['_vol'])
            if filtered.empty:
                # All issues in this year are from scanned volumes, stop going further back
                break
            all_dfs.append(filtered)
        else:
            all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame(columns=['uriLookup', 'coverDateStart'])

    result = pd.concat(all_dfs, ignore_index=True)
    result.drop_duplicates(subset='coverDateStart', inplace=True)
    result.reset_index(drop=True, inplace=True)

    if min_vol is not None:
        print(f"  Found {len(result)} issues (vol >= {min_vol})")
    else:
        print(f"  Found {len(result)} total issues")
    return result

def _dois(issue):
    """Get article DOIs from an issue page."""
    url = informs['journals']['url'] + issue
    content = _goto(url)
    text = content.replace('\\"', '"')
    dois = re.findall(r'href="https://doi.org/([\d\.]+/[\w+\.]+)"', text)
    return dois

def _ris(j, dois, file):
    """Bulk download RIS for all DOIs. POST with query params, write binary."""
    link = informs['ris']['url']
    for doi in dois:
        doi = doi.replace('/', '%2F')
        link += f"doi={doi}&"
    link += f"downloadFileName=informs_{informs[j]['download']}&include=abs&format=ris&submit=Download+article+citation+data"

    for attempt in range(5):
        try:
            body = page.evaluate("""async (url) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'include'
                });
                return await resp.text();
            }""", link)

            if body and '<!DOCTYPE html>' not in body and len(body.strip()) > 10:
                with open(file, 'wb') as f:
                    f.write(body.encode('utf-8'))
                tqdm.write(f"  Saved: {file}")
                return True
            else:
                tqdm.write(f"  [!] RIS not valid (attempt {attempt + 1}/5)")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False

def download_journal(j, start_year=1950, end_year=2026):
    _browser_init()
    name = informs[j]['name']
    print(f"\n=== Processing {name} ===")

    # Navigate to informs site to establish cookies/session
    print(f"  Loading informs site...")
    _goto(f"https://pubsonline.informs.org/loi/{j}")

    os.makedirs(f'./data/issues/informs/{j}', exist_ok=True)

    # Phase 1: scan all issues
    df = _scan_all_issues(j, start_year, end_year)
    if df.empty:
        print(f"  No issues found.")
        return []

    # Phase 2: download missing issues
    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/informs/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])

        dois = _dois(row['uriLookup'])
        if not dois:
            tqdm.write(f"  [!] No DOIs for {row['coverDateStart']}")
            failed.append(row['coverDateStart'])
            continue

        success = _ris(j, dois, filepath)
        if success:
            record_save(j, row['coverDateStart'], filepath)
        else:
            failed.append(row['coverDateStart'])
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
    journals = [k for k in informs.keys() if k not in ('journals', 'ris')]
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='informs')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='informs')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
