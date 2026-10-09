def build_bedny_visual_summary(stavy):
    """Build disjoint warehouse stages from the existing, overlapping totals."""
    raw_count, raw_weight = stavy['Surové'][:2]
    processed_count, processed_weight = stavy['Zpracované'][:2]
    ready_count, ready_weight = stavy['K expedici'][:2]
    total_count = raw_count + processed_count
    stages = [
        {'key': 'raw', 'label': 'Surové', 'count': raw_count, 'weight': raw_weight},
        {
            'key': 'finishing', 'label': 'Dokončování',
            'count': processed_count - ready_count,
            'weight': processed_weight - ready_weight,
        },
        {'key': 'ready', 'label': 'K expedici', 'count': ready_count, 'weight': ready_weight},
    ]
    for stage in stages:
        # CSS needs a decimal point regardless of Django's active locale.
        stage['width'] = format(stage['count'] * 100 / total_count, '.3f') if total_count else '0'

    return {
        'count': total_count,
        'weight': raw_weight + processed_weight,
        'stages': stages,
        'unreceived_count': stavy['Nepřijaté'][0],
        'expired_count': stavy['Po exspiraci'][0],
        'expired_weight': stavy['Po exspiraci'][1],
        'operations': [
            {'key': key, 'label': label, 'count': stavy[label][0]}
            for key, label in [
                ('inspection', 'Zakalené ke kontrole'),
                ('blasting', 'K tryskání'),
                ('straightening', 'K rovnání'),
                ('zincing', 'K zinkování'),
            ]
            if stavy[label][0]
        ],
    }
