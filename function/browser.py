"""Shared browser setup for all publisher scrapers.

Launches Chrome with a copy of the user's profile (cookies, auth)
and stealth settings to bypass Cloudflare / bot detection.
"""

import os
import shutil
import tempfile
import time
import random
from playwright.sync_api import sync_playwright


def create_browser(timeout=60000):
    """Launch Chrome with profile copy and stealth settings.

    Returns (pw, tmp_dir, context, page).
    Caller is responsible for cleanup via close_browser().
    """
    pw = sync_playwright().start()
    chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    src = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default')
    tmp_dir = tempfile.mkdtemp(prefix='chrome_profile_')
    dst = os.path.join(tmp_dir, 'Default')

    print("Copying Chrome profile (cookies only)...")
    os.makedirs(dst, exist_ok=True)
    for f in ['Cookies', 'Cookies-journal', 'Preferences', 'Secure Preferences',
              'Local State', 'Login Data', 'Web Data']:
        src_file = os.path.join(src, f)
        if os.path.exists(src_file):
            shutil.copy2(src_file, dst)
    local_state = os.path.join(src, '..', 'Local State')
    if os.path.exists(local_state):
        shutil.copy2(local_state, tmp_dir)

    context = pw.chromium.launch_persistent_context(
        user_data_dir=tmp_dir,
        executable_path=chrome_path,
        channel='chrome',
        headless=False,
        no_viewport=True,
        args=[
            '--profile-directory=Default',
            '--disable-blink-features=AutomationControlled',
        ],
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)
    context.set_default_timeout(timeout)
    page = context.pages[0] if context.pages else context.new_page()
    return pw, tmp_dir, context, page


def close_browser(pw, tmp_dir, context):
    """Clean up browser resources."""
    import threading

    def _shutdown():
        try:
            context.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    t = threading.Thread(target=_shutdown)
    t.start()
    t.join(timeout=10)  # Wait up to 10s for graceful shutdown

    if tmp_dir and os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if t.is_alive():
        pass  # Will be force-killed by os._exit() in main


def human_delay(low=3, high=8):
    """Random delay to mimic human browsing."""
    time.sleep(random.uniform(low, high))


def wait_for_cloudflare(page, timeout=120000):
    """Wait for Cloudflare challenge to resolve. Returns page content."""
    content = page.content()
    if 'Just a moment' in content or 'Checking your browser' in content or 'Verifying you are human' in content:
        print("  ⏳ Cloudflare challenge — please solve it in the browser.")
        try:
            page.wait_for_function(
                """() => !document.title.includes('Just a moment')
                      && !document.body.innerText.includes('Verifying you are human')""",
                timeout=timeout
            )
            page.wait_for_load_state('networkidle')
        except Exception:
            print("  [!] Timed out waiting for Cloudflare")
        content = page.content()
    return content
