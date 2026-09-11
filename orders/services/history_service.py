from django.db.models import OuterRef, Q, Subquery


def history_transitions_to_qs(*, model, field_name, target_value):
    """Vrátí historické záznamy skutečných přechodů pole na cílovou hodnotu."""
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
        .filter(history_type='~', **{field_name: target_value})
        .annotate(
            previous_history_id=Subquery(previous.values('history_id')[:1]),
            previous_field_value=Subquery(previous.values(field_name)[:1]),
        )
        .filter(previous_history_id__isnull=False)
        .exclude(previous_field_value=target_value)
    )
