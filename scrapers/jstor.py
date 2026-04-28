import pandas as pd
import re
import os
import sys
import time
import random
from tqdm import tqdm
from function.config import jstor
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

def _volumes(journal):
    """Step 1: Get decade filters from journal page."""
    url = jstor[journal]['url']
    print(f"  Loading {url} ...")
    # Navigate first to establish session/cookies
    _goto(url)
    # Fetch raw HTML like the notebook does with requests.get
    text = page.evaluate("""async (url) => {
        const resp = await fetch(url, { credentials: 'include' });
        return await resp.text();
    }""", url)
    text = text.replace('\\"', '"')
    volumes = re.findall(r'filter\="(.*)"', text)
    volumes = list(dict.fromkeys(volumes))
    print(f"  Found {len(volumes)} decade filters")
    return volumes

def _issues(journal, volume):
    """Step 2: Get issues for a given decade."""
    url = f"{jstor[journal]['url']}/decade/{volume}"
    text = page.evaluate("""async (url) => {
        const resp = await fetch(url, { credentials: 'include' });
        return await resp.text();
    }""", url)
    text = text.replace('\\"', '"')
    issues = re.findall(r'/stable/\d+\.\d+/\w+', text)
    names = re.findall(r"(\w+)'", str(issues))
    df = pd.DataFrame(data={
        'coverDateStart': names,
        'uriLookup': issues
    })
    df.drop_duplicates(inplace=True)
    return df

def _dois(issue):
    """Step 3: Get article DOIs from an issue page."""
    url = f'https://www.jstor.org{issue}'
    text = page.evaluate("""async (url) => {
        const resp = await fetch(url, { credentials: 'include' });
        return await resp.text();
    }""", url)
    text = text.replace('\\"', '"')
    dois = re.findall(r'\d+\.\d+/\d+', text)
    dois = list(set(dois))
    return dois

def _ris(doi, file):
    """Step 4: Download RIS for a single DOI. POST with form data, append to file."""
    for attempt in range(3):
        try:
            body = page.evaluate("""async ([url, doi]) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'citations=' + encodeURIComponent(doi),
                    credentials: 'include'
                });
                return await resp.text();
            }""", ['https://www.jstor.org/citation/bulk/ris', doi])

            if body and len(body.strip()) > 10:
                with open(file, 'a', encoding='utf-8') as f:
                    f.write(body)
                return True
        except Exception as e:
            if attempt == 2:
                tqdm.write(f"  [!] RIS error for {doi}: {e}")
        human_delay(2, 5)
    return False

def download_journal(j):
    _browser_init()
    name = jstor[j]['name']
    print(f"\n=== Processing {name} ===")

    volumes = _volumes(j)
    os.makedirs(f'./data/issues/jstor/{j}', exist_ok=True)

    # Resume from last failed decade if available
    resume_file = f'./data/issues/jstor/{j}/.resume'
    reversed_volumes = list(reversed(volumes))
    if os.path.exists(resume_file):
        with open(resume_file) as rf:
            resume_vol = rf.read().strip()
        if resume_vol in reversed_volumes:
            idx = reversed_volumes.index(resume_vol)
            reversed_volumes = reversed_volumes[idx:]
            print(f"  Resuming from decade {resume_vol}")

    failed = []
    last_failed_vol = None
    for vol in reversed_volumes:
        df = _issues(j, vol)
        if df.empty:
            continue

        attempted = 0
        pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
        for index, row in pbar:
            filepath = f'./data/issues/jstor/{j}/{row["coverDateStart"]}.ris'
            if os.path.exists(filepath):
                pbar.set_postfix_str("skipped")
                continue
            attempted += 1
            pbar.set_postfix_str(row['coverDateStart'])

            dois = _dois(row['uriLookup'])
            if not dois:
                tqdm.write(f"  [!] No DOIs for {row['coverDateStart']}")
                failed.append(row['coverDateStart'])
                last_failed_vol = vol
                continue

            success_count = 0
            for doi in dois:
                if _ris(doi, filepath):
                    success_count += 1
                human_delay(1, 3)

            if success_count > 0:
                tqdm.write(f"  Saved: {filepath} ({success_count}/{len(dois)} articles)")
                record_save(j, row['coverDateStart'], filepath)
            else:
                tqdm.write(f"  [!] No RIS for {row['coverDateStart']}")
                failed.append(row['coverDateStart'])
                last_failed_vol = vol

            human_delay(5, 15)
        pbar.close()

        if attempted == 0:
            print(f"  Decade {vol}: all issues already downloaded, stopping.")
            break

    if failed and last_failed_vol:
        with open(resume_file, 'w') as rf:
            rf.write(last_failed_vol)
        print(f"\n[!] {name}: {len(failed)} issues failed (will resume from decade {last_failed_vol}):")
        for f in failed:
            print(f"    - {f}")
    elif os.path.exists(resume_file):
        os.remove(resume_file)
        print(f"  All done, resume file cleared.")
    return failed

def download_all():
    _browser_init()
    journals = [k for k in jstor.keys() if k != 'journals']
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='jstor')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='jstor')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
