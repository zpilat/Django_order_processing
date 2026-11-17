from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from simple_history.utils import bulk_update_with_history


def update_queryset_with_history(queryset, *, user, change_reason, **changes):
    """Hromadně uloží konkrétní hodnoty polí i historii s autorem a popisem akce.

    Čerstvé řádky se zamknou před sestavením celých historických záznamů, aby
    historie zachovala i aktuální hodnoty neměněných polí. Zápis dat a historie
    tvoří jednu transakci. Stejně jako QuerySet.update() nevolá save() ani
    validaci modelu; volající zajišťuje pravidla příslušné operace.
    """
    model = queryset.model
    fields = [model._meta.get_field(name).name for name in changes]
    if not fields:
        raise ValueError('Musí být zadáno alespoň jedno pole ke změně.')

    with transaction.atomic():
        objects = list(queryset.select_for_update().order_by('pk'))
        for obj in objects:
            for name, value in changes.items():
                setattr(obj, name, value)
        return bulk_update_with_history(
            objects, model, fields,
            default_user=user,
            default_change_reason=change_reason,
        )


def history_transitions_to_qs(*, model, field_name, target_value):
    """Vrátí skutečné přechody pole do jedné cílové hodnoty nebo množiny hodnot."""
    history = getattr(model, 'history', None)
    if history is None:
        raise ValueError(f"Model {model.__name__} nemá nakonfigurovanou historii.")

    history_model = getattr(history, 'model', None)
    if history_model is None or not hasattr(history_model, 'tracked_fields'):
        raise ValueError(
            f'Atribut history modelu {model.__name__} není manager django-simple-history.'
        )

    tracked_field_names = {field.name for field in history_model.tracked_fields}
    if field_name not in tracked_field_names:
        raise ValueError(
            f"Pole '{field_name}' není sledováno v historii modelu {model.__name__}."
        )

    if isinstance(target_value, (list, tuple, set, frozenset)):
        target_values = tuple(target_value)
    else:
        target_values = (target_value,)
    if not target_values:
        raise ValueError('Musí být zadána alespoň jedna cílová hodnota.')

    original_pk_field = model._meta.pk.attname
    previous = (
        history
        .filter(**{original_pk_field: OuterRef(original_pk_field)})
        .filter(
            Q(history_date__lt=OuterRef('history_date'))
            | Q(
                history_date=OuterRef('history_date'),
                history_id__lt=OuterRef('history_id'),
            )
        )
        .order_by('-history_date', '-history_id')
    )

    return (
        history
        .filter(history_type='~', **{f'{field_name}__in': target_values})
        .annotate(
            previous_history_id=Subquery(previous.values('history_id')[:1]),
            previous_field_value=Subquery(previous.values(field_name)[:1]),
        )
        .filter(previous_history_id__isnull=False)
        .exclude(previous_field_value__in=target_values)
    )
