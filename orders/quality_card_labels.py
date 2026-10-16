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
        'straightened': 'Gerichtet?',
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
        'minimum_values': 'Mind. {count} Messwerte',
        'minimum_value': 'Mind. {count} Messwert',
        'from_samples': ' aus {sample_count} Prüfmustern',
        'from_sample': ' aus {sample_count} Prüfmuster',
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
        'straightened': 'Raddrizzata?',
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
        'minimum_samples': 'Minimo {count} campioni di prova',
        'minimum_sample': 'Minimo {count} campione di prova',
        'minimum_values': 'Minimo {count} valori',
        'minimum_value': 'Minimo {count} valore',
        'from_samples': ' da {sample_count} campioni',
        'from_sample': ' da {sample_count} campione',
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
    secondary = helper_labels.get('minimum_sample' if count == 1 else 'minimum_samples')
    if secondary is None:
        secondary = helper_labels.get('minimum_samples', '')
    return {'main': f'Min. {count} {noun}', 'secondary': secondary.format(count=count)}


def minimum_values_labels(count, helper_labels, *, sample_count=None):
    if count is None:
        return {}
    noun = 'hodnota' if count == 1 else 'hodnoty' if 2 <= count <= 4 else 'hodnot'
    main = f'Min. {count} {noun}'
    secondary = helper_labels.get('minimum_value' if count == 1 else 'minimum_values', '')
    secondary = secondary.format(count=count)
    if sample_count is not None:
        sample_noun = 'vzorku' if sample_count == 1 else 'vzorků'
        main += f' z {sample_count} {sample_noun}'
        if secondary:
            secondary += helper_labels.get('from_sample' if sample_count == 1 else 'from_samples', '').format(sample_count=sample_count)
    return {'main': main, 'secondary': secondary}
