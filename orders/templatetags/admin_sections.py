from django import template

register = template.Library()

ORDERS_ADMIN_SECTIONS = (
    {
        'key': 'logistika',
        'title': 'Logistika',
        'models': ('zakazka', 'bedna', 'kamion'),
    },
    {
        'key': 'vyroba',
        'title': 'Výroba',
        'models': ('sarze', 'zarizeni', 'sarzebedna'),
    },
    {
        'key': 'ciselniky',
        'title': 'Číselníky',
        'models': ('zakaznik', 'odberatel', 'cena', 'typhlavy', 'predpis', 'pletivo', 'pozice'),
    },
    {
        'key': 'system',
        'title': 'Systém',
        'models': ('notification', 'prioritynotificationrecipient', 'pozicezakazkaorder', 'rozpracovanost'),
    },
)


def _is_model_accessible(model):
    if not model:
        return False
    if isinstance(model, dict):
        return bool(model.get('admin_url') or model.get('add_url'))
    return bool(getattr(model, 'admin_url', None) or getattr(model, 'add_url', None))


def _get_object_name(model):
    if isinstance(model, dict):
        return (model.get('object_name') or '').lower()
    return (getattr(model, 'object_name', None) or '').lower()


@register.simple_tag
def orders_admin_sections(models):
    model_map = {
        _get_object_name(model): model
        for model in (models or [])
        if _get_object_name(model)
    }

    sections = []
    for section in ORDERS_ADMIN_SECTIONS:
        section_models = [
            model_map[name]
            for name in section['models']
            if name in model_map and _is_model_accessible(model_map[name])
        ]
        if section_models:
            sections.append(
                {
                    'key': section['key'],
                    'title': section['title'],
                    'models': section_models,
                }
            )
    return sections
