"""Journal configurations and HTTP headers for all publishers."""

# ─── Publisher journal configs ─────────────────────────────────

sciencedirect = {
    'jcf':  {'url': 'https://www.sciencedirect.com/journal/09291199/years', 'name': 'journal-of-corporate-finance'},
    'jme':  {'url': 'https://www.sciencedirect.com/journal/03043932/years', 'name': 'journal-of-monetary-economics'},
    'je':   {'url': 'https://www.sciencedirect.com/journal/03044076/years', 'name': 'journal-of-econometrics'},
    'jbf':  {'url': 'https://www.sciencedirect.com/journal/03784266/years', 'name': 'journal-of-banking-and-finance'},
    'red':  {'url': 'https://www.sciencedirect.com/journal/10942025/years', 'name': 'review-of-economic-dynamics'},
    'jde':  {'url': 'https://www.sciencedirect.com/journal/03043878/years', 'name': 'journal-of-development-economics'},
    'jie':  {'url': 'https://www.sciencedirect.com/journal/00221996/years', 'name': 'journal-of-international-economics'},
    'jfe':  {'url': 'https://www.sciencedirect.com/journal/0304405X/years', 'name': 'journal-of-financial-economics'},
    'jfi':  {'url': 'https://www.sciencedirect.com/journal/10429573/years', 'name': 'journal-of-financial-intermediation'},
    'jfm':  {'url': 'https://www.sciencedirect.com/journal/13864181/years', 'name': 'journal-of-financial-markets'},
    'jbv':  {'url': 'https://www.sciencedirect.com/journal/08839026/years', 'name': 'journal-of-business-venturing'},
    'rp':   {'url': 'https://www.sciencedirect.com/journal/00487333/years', 'name': 'research-policy'},
    'data': {'page': '1'},
    'ris':  {'url': 'https://www.sciencedirect.com/journal/issue/export-citations?'},
}

uchicago = {
    'journals': {'url': 'https://www.journals.uchicago.edu'},
    'jpe':  {'url': 'https://www.journals.uchicago.edu/pb/widgets/loi/content', 'name': 'journal-of-political-economy', 'download': 'jpe132'},
    'jole': {'url': 'https://www.journals.uchicago.edu/pb/widgets/loi/content', 'name': 'journal-of-labor-economics', 'download': 'jole42'},
    'data': {
        'widgetId': 'd5f8ed75-af9d-496c-ad6e-4da5285b1b4d',
        'pbContext': ';page:string:List of Issues;requestedJournal:journal:jpe;ctype:string:Journal Content;wgroup:string:Publication Websites;journal:journal:jpe;pageGroup:string:Publication Pages;website:website:uchicago',
        'id': 'y2017',
    },
    'ris': {'url': 'https://www.journals.uchicago.edu/action/downloadCitation?'},
}

jstor = {
    'journals': {'url': 'https://www.jstor.org/journal'},
    'aer':            {'url': 'https://www.jstor.org/journal/amereconrevi', 'movingwall': '2', 'name': 'american-economic-review'},
    'jfqa':           {'url': 'https://www.jstor.org/journal/jfinaquananal', 'movingwall': '4', 'name': 'journal-of-financial-and-quantitative-analysis'},
    'econometrica-old': {'url': 'https://www.jstor.org/journal/econometrica', 'movingwall': '4', 'name': 'econometrica-old'},
}

cambridge = {
    'journals': {'url': 'https://www.cambridge.org/core/journals'},
    'jfqa': {'url': 'https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis', 'name': 'journal-of-financial-and-quantitative-analysis'},
}

oxford = {
    'journals': {'url': 'https://academic.oup.com'},
    'qje':    {'url': '', 'name': 'quarterly-journal-of-economics'},
    'restud': {'url': '', 'name': 'review-of-economic-studies'},
    'rfs':    {'url': '', 'name': 'review-of-financial-studies'},
    'rof':    {'url': '', 'name': 'review-of-finance'},
    'rcfs':   {'url': '', 'name': 'review-of-corporate-finance-studies'},
}

wiley = {
    'journals': {'url': 'https://onlinelibrary.wiley.com'},
    'jf':          {'url': 'https://onlinelibrary.wiley.com/loi/15406261', 'name': 'journal-of-finance'},
    'econometrica': {'url': 'https://onlinelibrary.wiley.com/loi/14680262', 'name': 'econometrica'},
    'ier':          {'url': 'https://onlinelibrary.wiley.com/loi/14682354', 'name': 'international-economic-review'},
    'jmcb':         {'url': 'https://onlinelibrary.wiley.com/loi/15384616', 'name': 'journal-of-money-credit-and-banks'},
}

informs = {
    'journals': {'url': 'https://pubsonline.informs.org'},
    'mnsc': {
        'url': 'https://pubsonline.informs.org/pb/widgets/loi/content?widgetId=50c2fbc0-2f69-41a1-8f28-ed6a67b2e323&pbContext=;page:string:List%20of%20Issues;ctype:string:Journal%20Content;requestedJournal:journal:mnsc;wgroup:string:Publication%20Websites;pageGroup:string:Publication%20Pages;website:website:informs-site;journal:journal:mnsc&id=',
        'name': 'management-science',
        'download': 'mnsc66_5485',
        'data': {
            'widgetId': '50c2fbc0-2f69-41a1-8f28-ed6a67b2e323',
            'pbContext': ';page:string:List%20of%20Issues;ctype:string:Journal%20Content;requestedJournal:journal:mnsc;wgroup:string:Publication%20Websites;pageGroup:string:Publication%20Pages;website:website:informs-site;journal:journal:mnsc',
            'id': 'y2017',
        },
    },
    'orsc': {
        'url': 'https://pubsonline.informs.org/pb/widgets/loi/content?widgetId=6b3f7d35-3d08-482b-8ee4-df8f7c33c14a&pbContext=;page:string:List%20of%20Issues;ctype:string:Journal%20Content;requestedJournal:journal:orsc;wgroup:string:Publication%20Websites;pageGroup:string:Publication%20Pages;website:website:informs-site;journal:journal:orsc&id=',
        'name': 'management-science',
        'download': 'orsc31_821',
        'data': {
            'widgetId': '6b3f7d35-3d08-482b-8ee4-df8f7c33c14a',
            'pbContext': ';page:string:Journal%20Home;ctype:string:Journal%20Content;requestedJournal:journal:orsc;wgroup:string:Publication%20Websites;pageGroup:string:Publication%20Pages;website:website:informs-site;journal:journal:orsc',
            'id': 'd2020.y2017',
        },
    },
    'ris': {'url': 'https://pubsonline.informs.org/action/downloadCitation?'},
}

# ─── Journal → publisher mapping ──────────────────────────────
# Maps each journal abbreviation to its publisher and scraper module name
JOURNAL_PUBLISHER = {
    # ScienceDirect
    'jcf': 'sciencedirect', 'jme': 'sciencedirect', 'je': 'sciencedirect',
    'jbf': 'sciencedirect', 'red': 'sciencedirect', 'jde': 'sciencedirect',
    'jie': 'sciencedirect', 'jfe': 'sciencedirect', 'jfi': 'sciencedirect',
    'jfm': 'sciencedirect', 'jbv': 'sciencedirect', 'rp': 'sciencedirect',
    # Oxford
    'qje': 'oxford', 'restud': 'oxford', 'rfs': 'oxford', 'rof': 'oxford', 'rcfs': 'oxford',
    # Wiley
    'jf': 'wiley', 'econometrica': 'wiley', 'ier': 'wiley', 'jmcb': 'wiley',
    # UChicago
    'jpe': 'uchicago', 'jole': 'uchicago',
    # JSTOR
    'aer': 'jstor', 'jfqa-jstor': 'jstor', 'econometrica-old': 'jstor',
    # Cambridge
    'jfqa': 'cambridge',
    # INFORMS
    'mnsc': 'informs', 'orsc': 'informs',
    # Springer
    'jibs': 'springer',
    # Sage
    'asq': 'sage',
    # AOM
    'amj': 'aom', 'amr': 'aom',
}

# All available journals grouped by publisher
PUBLISHERS = {
    'sciencedirect': ['jcf', 'jme', 'je', 'jbf', 'red', 'jde', 'jie', 'jfe', 'jfi', 'jfm', 'jbv', 'rp'],
    'oxford':        ['qje', 'restud', 'rfs', 'rof', 'rcfs'],
    'wiley':         ['jf', 'econometrica', 'ier', 'jmcb'],
    'uchicago':      ['jpe', 'jole'],
    'jstor':         ['aer', 'econometrica-old'],
    'cambridge':     ['jfqa'],
    'informs':       ['mnsc', 'orsc'],
    'springer':      ['jibs'],
    'sage':          ['asq'],
    'aom':           ['amj', 'amr'],
}
