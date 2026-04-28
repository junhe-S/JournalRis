import pandas as pd
import re
import os
import sys
import time
import random
from tqdm import tqdm
from function.config import wiley
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

def _issues_Y(journal):
    """Step 1: Get year links from main LOI page."""
    url = wiley[journal]['url']
    print(f"  Loading {url} ...")
    content = _goto(url)
    issues_Y = re.findall(r'href="(/loi/\d+/year/\d+)', content)
    issues_Y = list(dict.fromkeys(issues_Y))
    print(f"  Found {len(issues_Y)} year pages")
    return issues_Y

def _issues(issue_Y):
    """Step 2: Get issue TOC links for a given year."""
    url = 'https://onlinelibrary.wiley.com' + issue_Y
    content = _goto(url)
    issues = re.findall(r'href="(/toc/\d+/\d+/\d+/\d+)', content)
    df = pd.DataFrame(data={'uriLookup': issues})
    if not df.empty:
        df['coverDateStart'] = df['uriLookup'].str.extract(r'/(\d+/\d+/\d+)$')
        df['coverDateStart'] = df['coverDateStart'].str.replace('/', '-')
        df.drop_duplicates(inplace=True)
    return df

def _scan_all_issues(j):
    """Phase 1: Scan year pages to build complete issue list, skipping scanned volumes."""
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

    issues_Y = _issues_Y(j)

    all_dfs = []
    for issue_Y in tqdm(issues_Y, desc=f"  scanning years", unit="yr"):
        df = _issues(issue_Y)
        if df.empty:
            continue

        if min_vol is not None:
            # coverDateStart is year-vol-issue, vol is second part
            df['_vol'] = df['coverDateStart'].str.split('-').str[1].astype(int)
            filtered = df[df['_vol'] >= min_vol].drop(columns=['_vol'])
            if filtered.empty:
                break
            all_dfs.append(filtered)
        else:
            all_dfs.append(df)
        human_delay(2, 5)

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
    """Step 3: Get article DOIs from an issue page. URL-encode with %2F."""
    url = 'https://onlinelibrary.wiley.com' + issue
    content = _goto(url)
    dois = re.findall(r'href="/doi/([\d.]*/[\w.-]*)', content)
    dois = [i.replace('/', '%2F') for i in dois]
    dois = list(set(dois))
    return dois

def _ris(dois, file):
    """Step 4: Bulk download RIS for all DOIs in one request."""
    doi_params = '&'.join([f'doi={d}' for d in dois])
    url = (f'https://onlinelibrary.wiley.com/action/downloadCitation'
           f'?{doi_params}'
           f'&downloadFileName=pericles_exported_citations'
           f'&include=abs'
           f'&format=RIS'
           f'&direct=direct')

    for attempt in range(5):
        try:
            body = page.evaluate("""async (url) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    credentials: 'include'
                });
                return await resp.text();
            }""", url)

            if body and 'TY  -' in body:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(body)
                tqdm.write(f"  Saved: {file}")
                return True
            else:
                tqdm.write(f"  [!] RIS not valid (attempt {attempt + 1}/5)")
                if attempt == 0:
                    tqdm.write(f"  [debug] Response ({len(body)} chars): {body[:200]}")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False

def _get_volume_num(cover_date):
    """Extract volume number from coverDateStart (e.g. '2026-81-2' -> '81')."""
    parts = cover_date.split('-')
    return parts[1] if len(parts) >= 3 else parts[0]

def download_journal(j):
    _browser_init()
    name = wiley[j]['name']
    print(f"\n=== Processing {name} ===")

    os.makedirs(f'./data/issues/wiley/{j}', exist_ok=True)

    # Phase 1: scan all issues
    df = _scan_all_issues(j)
    if df.empty:
        print(f"  No issues found.")
        return []

    # Phase 2: download missing issues
    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/wiley/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])

        dois = _dois(row['uriLookup'])
        if not dois:
            tqdm.write(f"  [!] No DOIs for {row['coverDateStart']}")
            failed.append(row['coverDateStart'])
            continue

        success = _ris(dois, filepath)
        if success:
            record_save(j, row['coverDateStart'], filepath,
                        volume_num=_get_volume_num(row['coverDateStart']))
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
    journals = [k for k in wiley.keys() if k != 'journals']
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='wiley')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='wiley')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
