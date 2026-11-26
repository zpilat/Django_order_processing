from django.db.models import Prefetch

from orders.choices import KamionChoice, TypZkouskyChoice, UvolneniKontrolyChoice
from orders.models import Bedna, MereniBedny

from .exceptions import ServiceValidationError


MEASUREMENT_TYPES = (
    TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA,
    TypZkouskyChoice.PROHYB_PO_ROVNANI, TypZkouskyChoice.PROHYB_PO_TZ,
)
MECHANICAL_REASONS = (
    'neshoda_ohyb_nizky', 'neshoda_krut_nizky', 'neshoda_krut_vysoky',
)


def build_spx_certificate_rows(kamion):
    """Sestaví certifikát z aktuálních kontrol pouze výdejových částí zakázek."""
    if kamion.prijem_vydej != KamionChoice.VYDEJ or kamion.zakaznik.zkratka != 'SPX':
        raise ServiceValidationError('Certifikát 3.1 lze tisknout pouze pro kamiony výdej zákazníka SPX.')

    measurements = MereniBedny.objects.filter(typ_zkousky__in=MEASUREMENT_TYPES).order_by('poradi', 'pk')
    crates = Bedna.objects.select_related('kontrola').order_by('cislo_bedny', 'pk').prefetch_related(
        Prefetch('kontrola__mereni', queryset=measurements, to_attr='certificate_measurements'),
    )
    orders = kamion.zakazky_vydej.order_by('pk').prefetch_related(
        Prefetch('bedny', queryset=crates, to_attr='certificate_crates'),
    )
    rows = []
    errors = []
    for order in orders:
        row = {
            'zakazka': order, 'bedny': order.certificate_crates,
            'tvrdost_povrchu': [], 'tvrdost_jadra': [], 'hazeni': [],
            'ohyb': 'OK', 'krut': 'OK',
        }
        if not row['bedny']:
            errors.append(f'Zakázka {order.artikl} (ID {order.pk}) nemá žádné bedny.')
        for index, crate in enumerate(row['bedny']):
            control = getattr(crate, 'kontrola', None)
            label = f'Zakázka {order.artikl} (ID {order.pk}), bedna {crate.cislo_bedny}'
            if control and control.uvolneni == UvolneniKontrolyChoice.NESHODA:
                reasons = [
                    str(control._meta.get_field(field).verbose_name)
                    for field in MECHANICAL_REASONS if getattr(control, field)
                ]
                if reasons:
                    errors.append(f'{label}: Neshoda – {", ".join(reasons)}.')
            if index >= 3:
                continue

            first_values = {}
            for measurement in (control.certificate_measurements if control else ()):
                first_values.setdefault(measurement.typ_zkousky, measurement.hodnota)
            for kind in (TypZkouskyChoice.TVRDOST_POVRCHU, TypZkouskyChoice.TVRDOST_JADRA):
                value = first_values.get(kind)
                if value is None:
                    errors.append(f'{label}: chybí měření {kind.label}.')
                else:
                    row[kind].append(value)
            deflection = first_values.get(TypZkouskyChoice.PROHYB_PO_ROVNANI)
            if deflection is None:
                deflection = first_values.get(TypZkouskyChoice.PROHYB_PO_TZ)
            if deflection is None:
                errors.append(f'{label}: chybí Prohyb po rovnání i Prohyb po TZ.')
            else:
                row['hazeni'].append(deflection)
        rows.append(row)

    if not rows:
        errors.append('Kamion nemá žádné výdejové zakázky.')
    if errors:
        raise ServiceValidationError('Certifikát 3.1 nelze vytvořit:\n' + '\n'.join(errors))
    return rows
