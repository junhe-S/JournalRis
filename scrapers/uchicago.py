import pandas as pd
import re
import os
import sys
import time
import random
from datetime import datetime
from tqdm import tqdm
from function.config import uchicago
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


def _issues(j, year):
    """Get all issues for a journal in a given year."""
    url = uchicago[j]['url']
    params = uchicago['data'].copy()
    params['id'] = f'y{year}'
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    full_url = f'{url}?{query}'

    page.goto(full_url, wait_until='networkidle')
    content = page.content()

    if 'Just a moment' in content or 'Verifying you are human' in content:
        tqdm.write("  ⏳ Cloudflare challenge — please solve it in the browser.")
        try:
            page.wait_for_function(
                """() => !document.title.includes('Just a moment')
                      && !document.body.innerText.includes('Verifying you are human')""",
                timeout=120000
            )
            page.wait_for_load_state('networkidle')
        except Exception:
            tqdm.write("  [!] Timed out waiting for Cloudflare")
        content = page.content()

    issues = re.findall(f'href="(/toc/{j}/\\d+/\\d+/\\d+)"', content)

    df = pd.DataFrame(data={'uriLookup': issues})
    if not df.empty:
        df['coverDateStart'] = df['uriLookup'].apply(
            lambda x: re.sub(r'/(?=\d)', '-', x.split(f"/toc/{j}/")[1])
        )
    human_delay(1, 3)
    return df


def _scan_all_issues(j, start_year, end_year):
    """Phase 1: Scan years to build a complete issue list, skipping scanned volumes."""
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
            # No issues found for this year, stop
            break

        if min_vol is not None:
            # coverDateStart is like "year-vol-issue", vol_num is second part
            df['_vol'] = df['coverDateStart'].str.split('-').str[1].astype(int)
            filtered = df[df['_vol'] >= min_vol].drop(columns=['_vol'])
            if filtered.empty:
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


def _ris(j, file, issue_url):
    """Download RIS for all articles in an issue."""
    url = uchicago['journals']['url'] + issue_url

    for attempt in range(5):
        try:
            page.goto(url, wait_until='networkidle')
            content = page.content()

            if 'Just a moment' in content or 'Verifying you are human' in content:
                tqdm.write("  ⏳ Cloudflare challenge — please solve it in the browser.")
                try:
                    page.wait_for_function(
                        """() => !document.title.includes('Just a moment')
                              && !document.body.innerText.includes('Verifying you are human')""",
                        timeout=120000
                    )
                    page.wait_for_load_state('networkidle')
                except Exception:
                    tqdm.write("  [!] Timed out waiting for Cloudflare")
                content = page.content()

            dois = re.findall(r'href="/doi/(\d+\.\d+/[^"]+)"', content)
            dois = list(set(dois))

            if not dois:
                tqdm.write(f"  [!] No DOIs found (attempt {attempt + 1}/5)")
                human_delay(15 + attempt * 15, 30 + attempt * 20)
                continue

            link = uchicago['ris']['url']
            for doi in dois:
                link += f"doi={doi}&"
            link += f"downloadFileName=uchicago_{uchicago[j]['download']}&include=abs&format=ris&submit=Download+article+citation+data"

            body = page.evaluate("""async (url) => {
                const resp = await fetch(url, { method: 'POST' });
                return await resp.text();
            }""", link)

            if body and '<!DOCTYPE html>' not in body and body.strip():
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(body)
                tqdm.write(f"  Saved: {file} ({len(dois)} articles)")
                return True
            else:
                tqdm.write(f"  [!] RIS not valid (attempt {attempt + 1}/5), cooling down...")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False


def _get_volume_num(cover_date):
    """Extract volume number from coverDateStart (e.g. '2026-134-4' -> '134')."""
    parts = cover_date.split('-')
    return parts[1] if len(parts) >= 3 else parts[0]


def download_journal(j, start_year=1900):
    _browser_init()
    end_year = datetime.now().year

    name = uchicago[j]['name']
    print(f"\n=== Processing {name} ===")

    os.makedirs(f'./data/issues/uchicago/{j}', exist_ok=True)

    # Phase 1: scan all issues
    df = _scan_all_issues(j, start_year, end_year)
    if df.empty:
        print(f"  No issues found.")
        return []

    # Phase 2: download missing issues
    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/uchicago/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])
        success = _ris(j, filepath, row['uriLookup'])
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
    journals = [k for k in uchicago.keys() if k not in ('journals', 'data', 'ris')]
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='uchicago')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='uchicago')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
