import hashlib
import json

from django.utils import timezone

from orders.choices import TypZkouskyChoice
from orders.models import MereniBedny


def pozadavek_zkousky(predpis, typ_zkousky):
    fields = {
        TypZkouskyChoice.OHYB: ('ohyb', 'popis_ohyb', 'popis_ohyb_2'),
        TypZkouskyChoice.KRUT: ('krut', 'popis_krut', 'popis_krut_2'),
        TypZkouskyChoice.TVRDOST_POVRCHU: ('povrch', 'popis_povrch', 'popis_povrch_2'),
        TypZkouskyChoice.TVRDOST_JADRA: ('jadro', 'popis_jadro', 'popis_jadro_2'),
    }.get(typ_zkousky)
    if fields is None:
        return {'hodnota': '', 'popisy': []}
    return {
        'hodnota': getattr(predpis, fields[0]) or '',
        'popisy': [getattr(predpis, name) for name in fields[1:] if getattr(predpis, name)],
    }


def mereni_snapshot(measurements):
    """Detect edits made since the form was opened, including additions/deletions."""
    data = [
        [item.pk, str(item.hodnota), item.zmeril_id, item.zmereno_at.isoformat()]
        for item in measurements
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode('utf-8')).hexdigest()


def kontrola_snapshot(kontrola):
    data = None if kontrola is None else [
        kontrola.pk, kontrola.cistota, kontrola.ulozeni, kontrola.uvolneni,
        kontrola.poznamka, kontrola.uvolnil_id,
        kontrola.uvolneno_at.isoformat() if kontrola.uvolneno_at else None,
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode('utf-8')).hexdigest()


def ulozit_mereni_zkousky(kontrola, typ_zkousky, formset, user):
    """Caller holds the bedna lock and has validated the formset and snapshot."""
    existing = {item.pk: item for item in formset.measurements}
    next_order = max((item.poradi for item in existing.values()), default=0)
    measured_at = timezone.now()
    for form in formset.forms:
        data = form.cleaned_data
        item = existing.get(data.get('id'))
        if data.get('DELETE'):
            if item is not None:
                item._history_user = user
                item.delete()
            continue
        if not form.has_changed():
            continue
        if item is None:
            next_order += 1
            item = MereniBedny(
                kontrola=kontrola, typ_zkousky=typ_zkousky, poradi=next_order,
                zmeril=user, zmereno_at=measured_at,
            )
        item.hodnota = data['hodnota']
        item._history_user = user
        # Editing a value preserves the original measuring person/date.
        item.save()
