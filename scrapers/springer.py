import pandas as pd
import re
import os
import sys
import time
import random
from datetime import datetime
from tqdm import tqdm
from function.processing import postprocess
from function.browser import create_browser, human_delay, close_browser, wait_for_cloudflare
from function.record import save as record_save


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


springer = {
    'jibs': {
        'id': '41267',
        'name': 'journal-of-international-business-studies',
    },
}

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

def _issues(j):
    """Get all issues from the volumes-and-issues page."""
    journal_id = springer[j]['id']
    url = f'https://link.springer.com/journal/{journal_id}/volumes-and-issues'
    content = _goto(url)

    issues = re.findall(
        rf'href="(/journal/{journal_id}/volumes-and-issues/(\d+-\d+))"', content
    )
    df = pd.DataFrame(data={
        'uriLookup': [i[0] for i in issues],
        'coverDateStart': [i[1] for i in issues],
    })
    df.drop_duplicates(inplace=True)
    print(f"  Found {len(df)} issues")
    return df

def _dois(issue):
    """Get article DOIs from an issue page."""
    url = f'https://link.springer.com{issue}'
    content = _goto(url)
    articles = re.findall(r'href="/article/(10\.\d+/[^"]+)"', content)
    dois = list(set(articles))
    return dois

def _ris(dois, file):
    """Download RIS for all DOIs in an issue via Springer citation API."""
    ris_parts = []
    for doi in dois:
        url = f'https://citation-needed.springer.com/v2/references/{doi}?format=refman&flavour=citation'
        try:
            resp = context.request.get(url)
            if resp.status == 200:
                body = resp.text()
                if body and 'TY  -' in body:
                    ris_parts.append(body)
            human_delay(1, 3)
        except Exception as e:
            tqdm.write(f"  [!] RIS error for {doi}: {e}")

    if ris_parts:
        with open(file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ris_parts))
        tqdm.write(f"  Saved: {file} ({len(ris_parts)}/{len(dois)} articles)")
        return True

    tqdm.write(f"  [!] No RIS downloaded for {file}")
    return False

def download_journal(j):
    _browser_init()
    end_year = datetime.now().year
    name = springer[j]['name']
    print(f"\n=== Processing {name} ===")

    df = _issues(j)
    os.makedirs(f'./data/issues/springer/{j}', exist_ok=True)

    failed = []
    downloaded = 0
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/springer/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])

        dois = _dois(row['uriLookup'])
        if not dois:
            tqdm.write(f"  [!] No DOIs for {row['coverDateStart']}")
            failed.append(row['coverDateStart'])
            continue

        if _ris(dois, filepath):
            record_save(j, row['coverDateStart'], filepath)
            downloaded += 1
        else:
            failed.append(row['coverDateStart'])
        human_delay(5, 15)

        # Stop if we've gone through issues and nothing new was downloaded
        # Check every 10 issues
        if (index + 1) % 10 == 0 and downloaded == 0:
            print(f"\n  No new downloads in first {index + 1} issues, stopping.")
            break

    pbar.close()

    if failed:
        print(f"\n[!] {name}: {len(failed)} issues failed:")
        for f in failed:
            print(f"    - {f}")
    return failed

def download_all():
    _browser_init()
    for idx, j in enumerate(springer.keys()):
        download_journal(j)
        postprocess(j, publisher='springer')
        if idx < len(springer) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='springer')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
