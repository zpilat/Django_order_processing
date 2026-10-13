"""Dočasné nastavení minimálních počtů vzorků a názvů protokolů vyplněných KKK.

Výchozí počty vzorků jsou převzaté z původních nevyplněných zákaznických karet.
None znamená, že minimum není stanovené a na kartě se nezobrazí.
Název protokolu může obsahovat více řádků oddělených znakem nového řádku.
Později lze tyto čtyři položky přesunout do modelu Zakaznik.
"""

QUALITY_CARD_CONFIG_BY_CUSTOMER = {
    'EUR': {
        'mechanicka_zkouska': 5,
        'prohyb': 5,
        'tvrdost': 2,
        'nazev_protokolu': 'HPM - F 73c\nEurotec - F.3',
    },
    'ROT': {
        'mechanicka_zkouska': 10,
        'prohyb': None,
        'tvrdost': 3,
        'nazev_protokolu': 'HPM - F XXX',
    },
    'SPX': {
        'mechanicka_zkouska': 5,
        'prohyb': 3,
        'tvrdost': 1,
        'nazev_protokolu': 'HPM - F XXX',
    },
    'SSH': {
        'mechanicka_zkouska': None,
        'prohyb': None,
        'tvrdost': None,
        'nazev_protokolu': 'HPM - F 11b',
    },
    'HPM': {
        'mechanicka_zkouska': 5,
        'prohyb': 25,
        'tvrdost': 3,
        'nazev_protokolu': 'HPM - F 86a',
    },
    'SWG': {
        'mechanicka_zkouska': 5,
        'prohyb': None,
        'tvrdost': 5,
        'nazev_protokolu': 'HPM - F XXX',
    },
    'FIS': {
        'mechanicka_zkouska': 5,
        'prohyb': 25,
        'tvrdost': 2,
        'nazev_protokolu': 'HPM - F XXX',
    },
}
