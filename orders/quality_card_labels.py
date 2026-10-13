"""Pomocné štítky pro vyplněné karty kvality; české štítky zůstávají v šabloně."""

from orders.choices import UvolneniKontrolyChoice

HELPER_LANGUAGE_BY_COUNTRY = {
    'D': 'de',
    'A': 'de',
    'CZ': None,
    'I': 'it',
}

HELPER_LABELS = {
    'de': {
        'title': 'Qualitätskontrollkarte',
        'customer': 'Kunde',
        'container': 'Gebinde',
        'article_batch': 'Art. Nr.',
        'dimension': 'Abmessung',
        'net_weight': 'Netto',
        'collection_date': 'Abholdatum',
        'measurement_period': 'Prüfzeitraum',
        'cleanliness': 'Reinheit',
        'arrangement': 'Einlagerung',
        'blasted': 'Sandgestrahlt?',
        'release': 'Freigabe',
        'release_status': {
            UvolneniKontrolyChoice.UVOLNENO: 'Freigegeben',
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU: 'Freigegeben mit Abweichung',
            UvolneniKontrolyChoice.NESHODA: 'Nichtkonformität',
        },
        'layer': 'Schicht',
        'requirement': 'Anforderung',
        'measured': 'Gemessen',
        'inspector': 'Kontrolliert',
        'sample': 'Probe',
        'mechanical_tests': 'Mechanische Prüfungen',
        'bending_check': 'Abweichung Geradheit',
        'hardness_test': 'Härteprüfung',
        'bend': 'Biegewinkel',
        'torsion': 'Drehmoment',
        'after_heat_treatment': 'Nach der Wärmebehandlung',
        'after_sorting': 'Nach dem Sortieren',
        'after_straightening': 'Nach dem Richten',
        'surface': 'Oberfläche',
        'core': 'Kern',
        'minimum_samples': 'Mind. {count} Prüfmuster',
    },
    # Based on the blank ROT card, with additional labels for the filled card.
    'it': {
        'title': 'Scheda di controllo della qualità',
        'customer': 'Cliente',
        'container': 'Cassa',
        'article_batch': 'Articolo',
        'dimension': 'Dimensione',
        'net_weight': 'Netto',
        'collection_date': 'Data di ritiro',
        'measurement_period': 'Periodo di misurazione',
        'cleanliness': 'Pulizia',
        'arrangement': 'Disposizione',
        'blasted': 'Sabbiata?',
        'release': 'Rilascio',
        'release_status': {
            UvolneniKontrolyChoice.UVOLNENO: 'Rilasciato',
            UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU: 'Rilasciato con deroga',
            UvolneniKontrolyChoice.NESHODA: 'Non conformità',
        },
        'layer': 'Strato',
        'requirement': 'Requisito',
        'measured': 'Valore misurato',
        'inspector': 'Ha controllato',
        'sample': 'Campione',
        'mechanical_tests': 'Prove meccaniche',
        'bending_check': 'Controllo della deflessione',
        'hardness_test': 'Prova di durezza',
        'bend': 'Prova di flessione',
        'torsion': 'Prova di torsione',
        'after_heat_treatment': 'Dopo il trattamento termico',
        'after_sorting': 'Dopo lo smistamento',
        'after_straightening': 'Dopo il livellamento',
        'surface': 'Superficie',
        'core': 'Nucleo',
        'minimum_samples': 'Minimo {count} campion{suffix} di prova',
    },
}


def get_helper_labels(country_code):
    country = (country_code or '').strip().upper()
    language = HELPER_LANGUAGE_BY_COUNTRY.get(country)
    return HELPER_LABELS.get(language, {})


def minimum_samples_labels(count, helper_labels):
    if count is None:
        return {}
    noun = 'vzorek' if count == 1 else 'vzorky' if 2 <= count <= 4 else 'vzorků'
    secondary = helper_labels.get('minimum_samples', '')
    return {
        'main': f'Min. {count} {noun}',
        'secondary': secondary.format(count=count, suffix='e' if count == 1 else 'i'),
    }
