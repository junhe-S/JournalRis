"""Post-processing pipeline for downloaded RIS citation files.

Pipeline: merge → dedup → filter junk → fix case → fix journal names
"""

import os
import re
from datetime import datetime


# ─── Junk title filter ─────────────────────────────────────────
JUNK_TITLES = {
    'editorial board', 'news items', 'news item', 'index', 'joint editorial',
    'editorial data', 'front matter', 'back matter', 'announcements',
    'discussion', 'miscellanea', 'reply', 'book reviews', 'association meetings',
    'american finance association', 'style instructions', 'editorial',
    'issue information fm', 'issue information bm', 'introduction',
    'about our authors', 'rumors', 'author index of the abstracts',
    "author's correction", "author\u2019s correction",
}

# ─── Canonical journal names ───────────────────────────────────
JOURNAL_NAMES = {
    'jcf': 'Journal of Corporate Finance',
    'jme': 'Journal of Monetary Economics',
    'je': 'Journal of Econometrics',
    'jbf': 'Journal of Banking and Finance',
    'red': 'Review of Economic Dynamics',
    'jde': 'Journal of Development Economics',
    'jie': 'Journal of International Economics',
    'jfe': 'Journal of Financial Economics',
    'jfi': 'Journal of Financial Intermediation',
    'jfm': 'Journal of Financial Markets',
    'jbv': 'Journal of Business Venturing',
    'rp': 'Research Policy',
    'jpe': 'Journal of Political Economy',
    'jole': 'Journal of Labor Economics',
    'aer': 'American Economic Review',
    'jfqa': 'Journal of Financial and Quantitative Analysis',
    'econometrica': 'Econometrica',
    'econometrica-old': 'Econometrica',
    'qje': 'Quarterly Journal of Economics',
    'restud': 'Review of Economic Studies',
    'rfs': 'Review of Financial Studies',
    'rof': 'Review of Finance',
    'rcfs': 'Review of Corporate Finance Studies',
    'jf': 'The Journal of Finance',
    'ier': 'International Economic Review',
    'jmcb': 'Journal of Money, Credit and Banking',
    'mnsc': 'Management Science',
    'orsc': 'Organization Science',
    'amj': 'Academy of Management Journal',
    'amr': 'Academy of Management Review',
    'asq': 'Administrative Science Quarterly',
    'jibs': 'Journal of International Business Studies',
}


def _ris_path(journal, update=True):
    """Get the RIS file path for a journal."""
    today = datetime.now().date()
    return f'./data/output/{today}/{journal}.ris' if update else f'./data/output/{journal}.ris'


def merge(journal, publisher=None, update=True):
    """Concatenate individual RIS files into one consolidated file."""
    base = f'./data/issues/{publisher}/{journal}' if publisher else f'./data/issues/{journal}'
    dir_list = os.listdir(base)
    today = datetime.now().date()
    os.makedirs(f'./data/output/{today}', exist_ok=True)

    if update:
        for i in dir_list:
            if i == ".DS_Store":
                continue
            file_ris = f'{base}/{i}'
            creation_time = os.path.getctime(file_ris)
            creation_date = datetime.fromtimestamp(creation_time).date()
            if creation_date == today:
                with open(file_ris) as fin:
                    content = fin.read()
                with open(f'./data/output/{today}/{journal}.ris', 'a') as fout:
                    fout.write(content)
    else:
        for i in dir_list:
            if i == ".DS_Store":
                continue
            with open(f'{base}/{i}') as fin:
                content = fin.read()
            with open(f'./data/output/{journal}.ris', 'a') as fout:
                fout.write(content)


def dedup(journal, update=True):
    """Remove duplicate RIS entries."""
    path = _ris_path(journal, update)
    if not os.path.exists(path):
        return

    with open(path) as f:
        content = f.read()
    entries = re.findall(r'(TY  - JOUR\n.*?\nER  - )', content, flags=re.DOTALL)
    deduplicated = '\n\n'.join(list(set(entries)))
    with open(path, 'w') as f:
        f.write(deduplicated)


def filter_junk(journal, update=True):
    """Remove entries with junk titles (editorials, indexes, etc.)."""
    path = _ris_path(journal, update)
    if not os.path.exists(path):
        return

    with open(path) as f:
        content = f.read()

    entries = re.findall(r'(TY  - JOUR\n.*?\nER  - )', content, flags=re.DOTALL)
    kept = []
    removed = 0
    for entry in entries:
        title_match = re.search(r'^T1  - (.+)$', entry, re.MULTILINE)
        if title_match and title_match.group(1).strip().lower() in JUNK_TITLES:
            removed += 1
            continue
        kept.append(entry)

    if removed:
        with open(path, 'w') as f:
            f.write('\n\n'.join(kept))
        print(f"  Filtered {removed} junk entries from {journal}")


def fix_case(journal, update=True):
    """Fix ALL-CAPS author names and titles."""
    path = _ris_path(journal, update)
    if not os.path.exists(path):
        return

    with open(path) as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.rstrip('\n')
        if stripped.startswith('AU  - '):
            name = stripped[6:]
            parts = name.split()
            result = []
            for part in parts:
                subparts = part.split('-')
                subparts = [s.capitalize() if s.isupper() and len(s) > 1 else s for s in subparts]
                result.append('-'.join(subparts))
            new_lines.append('AU  - ' + ' '.join(result) + '\n')
        elif stripped.startswith('T1  - '):
            title = stripped[6:]
            words = re.findall(r'[A-Za-z]{2,}', title)
            if words and sum(1 for w in words if w.isupper()) / len(words) >= 0.6:
                new_lines.append('T1  - ' + title.title() + '\n')
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(path, 'w') as f:
        f.writelines(new_lines)


def fix_journal(journal, update=True):
    """Standardize journal name tags in RIS."""
    path = _ris_path(journal, update)
    if not os.path.exists(path):
        return

    name = JOURNAL_NAMES.get(journal)
    if not name:
        return

    with open(path) as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.rstrip('\n')
        if stripped.startswith(('T2  - ', 'JF  - ', 'JO  - ', 'JA  - ')):
            tag = stripped[:6]
            new_lines.append(f'{tag}{name}\n')
        else:
            new_lines.append(line)

    with open(path, 'w') as f:
        f.writelines(new_lines)


def postprocess(journal, publisher=None, update=True):
    """Run the full post-processing pipeline for a journal."""
    merge(journal, publisher=publisher, update=update)
    dedup(journal, update=update)
    filter_junk(journal, update=update)
    fix_case(journal, update=update)
    fix_journal(journal, update=update)
