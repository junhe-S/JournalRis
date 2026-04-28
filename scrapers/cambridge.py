import pandas as pd
import re
import os
import sys
import time
import random
from tqdm import tqdm
from function.config import cambridge
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


def _issues(journal):
    url = f"{cambridge[journal]['url']}/all-issues"
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

    issues = re.findall(r'/issue/(.*?)[\"\']', content)
    names = re.findall(r'<span class="date[^"]*">\s*(\w+)\s+(\d{4})', content)
    names = [f"{i[1]}-{i[0]}" for i in names]
    # issues may have duplicates, pair with names by taking every unique issue in order
    seen = set()
    unique_issues = []
    for iss in issues:
        if iss not in seen:
            seen.add(iss)
            unique_issues.append(iss)
    # Trim to same length (names only has month-year entries, issues may have extras)
    min_len = min(len(names), len(unique_issues))
    df = pd.DataFrame(data={
        'coverDateStart': names[:min_len],
        'uriLookup': unique_issues[:min_len]
    })
    print(f"  Found {len(df)} issues")
    return df

def _dois(journal, issue):
    url = f"{cambridge[journal]['url']}/issue/{issue}"
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

    dois = re.findall(r'data-prod-id="(.*?)"', content)
    return dois

def _ris(dois, file):
    params = '&'.join([f'productIds={d}' for d in dois])
    url = f'https://www.cambridge.org/core/services/aop-citation-tool/download?downloadType=ris&{params}&citationStyle=american-medical-association'

    for attempt in range(5):
        try:
            body = page.evaluate("""async (url) => {
                const resp = await fetch(url);
                return await resp.text();
            }""", url)

            if body and 'TY  -' in body:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(body)
                tqdm.write(f"  Saved: {file}")
                return True
            else:
                tqdm.write(f"  [!] RIS not valid (attempt {attempt + 1}/5), cooling down...")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False

def download_journal(j):
    _browser_init()
    journal_url = cambridge[j]['url']
    name = cambridge[j]['name']
    print(f"\n=== Processing {name} ===")

    df = _issues(j)
    os.makedirs(f'./data/issues/cambridge/{j}', exist_ok=True)

    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/cambridge/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])
        dois = _dois(j, row['uriLookup'])
        if not dois:
            tqdm.write(f"  [!] No DOIs found for {row['coverDateStart']}")
            failed.append(row['coverDateStart'])
            continue
        success = _ris(dois, filepath)
        if success:
            record_save(j, row['coverDateStart'], filepath)
        else:
            failed.append(row['coverDateStart'])
        human_delay(5, 15)
    pbar.close()

    if failed:
        print(f"\n[!] {name}: {len(failed)} issues failed:")
        for f in failed:
            print(f"    - {f}")
    return failed

def download_all():
    _browser_init()
    journals = [k for k in cambridge.keys() if k != 'journals']
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='cambridge')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='cambridge')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
