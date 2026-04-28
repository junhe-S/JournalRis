import pandas as pd
import re
import os
import sys
from function.config import sciencedirect
from function.processing import postprocess
from function.browser import create_browser, human_delay, close_browser, wait_for_cloudflare
from function.record import save as record_save
import time
import random
from tqdm import tqdm


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


def _journal(url, pg, issue):
    params = f"?page={pg}"
    full_url = url + params

    try:
        response = page.goto(full_url, wait_until='networkidle')
    except Exception as e:
        print(f"  [!] Error loading page {pg}: {type(e).__name__}")
        return None, issue

    content = page.content()

    # Check for Cloudflare challenge
    if 'Just a moment' in content or 'Checking your browser' in content or 'Verifying you are human' in content:
        print(f"  ⏳ Cloudflare challenge on page {pg} — please solve it in the browser.")
        try:
            page.wait_for_function(
                """() => !document.title.includes('Just a moment')
                      && !document.body.innerText.includes('Verifying you are human')""",
                timeout=120000
            )
            page.wait_for_load_state('networkidle')
        except Exception:
            print(f"  [!] Timed out waiting for Cloudflare on page {pg}")
        content = page.content()

    # Try to extract JSON from the page
    # The /years endpoint returns JSON directly
    try:
        text = page.inner_text('body')
        import json
        req = json.loads(text)
    except Exception:
        if pg > 1:
            return None, issue
        print(f"  [!] Non-JSON response on page {pg}")
        return None, issue

    if 'status' not in req:
        for i in req['data']['results']:
            issue += i['issues']
        return pg, issue
    else:
        return None, issue

def _issues(url):
    issue = []
    for i in range(1, 10):
        page_num, issue = _journal(url, pg=i, issue=issue)
        if page_num is None:
            break
        human_delay(4, 10)
    df = pd.json_normalize(issue)
    return df

def _ris(file, name, url):
    issue_url = f"https://www.sciencedirect.com/journal/{name}" + url

    piis = []
    for attempt in range(3):
        try:
            page.goto(issue_url, wait_until='networkidle')
        except Exception as e:
            tqdm.write(f"  [!] Error loading issue (attempt {attempt + 1}/3): {type(e).__name__}")
            time.sleep(5)
            continue

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

        text = content.replace('\\"', '"')
        piis = re.findall(r'\"/science/article/pii/(\w+)', text)
        if not piis:
            piis = re.findall(r'"pii"\s*:\s*"(S\w+)"', text)
        piis = list(set(piis))
        if piis:
            break
        tqdm.write(f"  [!] No articles found (attempt {attempt + 1}/3), retrying...")
        human_delay(5, 12)

    if not piis:
        tqdm.write(f"  [!] Skipped: {url}")
        return False

    link = sciencedirect['ris']['url']
    for pii in piis:
        link += f"pii={pii}&"
    link += "citationType=risabs"

    human_delay(3, 8)

    for attempt in range(5):
        try:
            body = page.evaluate("""async (url) => {
                const resp = await fetch(url);
                return await resp.text();
            }""", link)

            if body and 'TY  -' in body:
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(body)
                tqdm.write(f"  Saved: {file}")
                return True
            else:
                tqdm.write(f"  [!] RIS not valid (attempt {attempt + 1}/5), cooling down...")
        except Exception as e:
            tqdm.write(f"  [!] RIS error (attempt {attempt + 1}/5): {e}")
        # Increasing backoff: 15-30s, 30-50s, 45-70s, ...
        human_delay(15 + attempt * 15, 30 + attempt * 20)

    tqdm.write(f"  [!] Failed after 5 retries: {file}")
    return False

def download_journal(j):
    _browser_init()
    journal_url = sciencedirect[j]['url']
    name = sciencedirect[j]['name']
    print(f"\n=== Processing {name} ===")

    df = _issues(journal_url)[['coverDateStart', 'uriLookup']]
    os.makedirs(f'./data/issues/sciencedirect/{j}', exist_ok=True)

    failed = []
    pbar = tqdm(df.iterrows(), total=len(df), desc=f"  {j}", unit="issue")
    for index, row in pbar:
        filepath = f'./data/issues/sciencedirect/{j}/{row["coverDateStart"]}.ris'
        if os.path.exists(filepath):
            pbar.set_postfix_str("skipped")
            continue
        pbar.set_postfix_str(row['coverDateStart'])
        success = _ris(filepath, name, row['uriLookup'])
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
    journals = list(sciencedirect.keys())[:-2]
    for idx, j in enumerate(journals):
        download_journal(j)
        postprocess(j, publisher='sciencedirect')
        if idx < len(journals) - 1:
            wait = random.uniform(20, 40)
            print(f"\nWaiting {wait:.0f}s before next journal...")
            time.sleep(wait)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            for j in sys.argv[1:]:
                download_journal(j)
                postprocess(j, publisher='sciencedirect')
        else:
            download_all()
    finally:
        close_browser(pw, tmp_dir, context)
