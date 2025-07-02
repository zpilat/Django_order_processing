from django import template

register = template.Library()

@register.filter(name='url_remove_param')
def url_remove_param(querystring, params):
    """
    Odstraní parametry z query stringu.
    """
    params = params.split(',')
    new_querystring = '&'.join(
        f"{key}={value}"
        for part in querystring.split('&')
        if '=' in part and (key := part.split('=')[0]) not in params and (value := part.split('=')[1])
    )
    return new_querystring

@register.filter(name='attr_chain')
def attr_chain(obj, attr_chain):
    """
    Projde objekt podle řetězce atributů oddělených __ a vrátí hodnotu.
    Např. item|attr_chain:"zakazka_id__typ_hlavy"
    Pokud je objekt None nebo atribut neexistuje, vrátí prázdný řetězec.
    Pokud je atribut typu bool, vrátí ikonu ✔️ nebo ❌.
    """
    attrs = attr_chain.split('__')
    for attr in attrs:
        obj = getattr(obj, attr, None)
        if obj is None:
            return ''
        if isinstance(obj, bool):
            return "✔️" if obj else "❌"        
    return obj

@register.filter(name='get_bedna_by_stav')
def get_bedna_by_stav(bedny_stavy, stav_value):
    """
    Vrátí dict s daty pro daný stav bedny, pokud existuje; jinak None.
    """
    for row in bedny_stavy:
        if row['stav_bedny'] == stav_value:
            return row
    return None

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

@register.filter(name='nahrada_pomlcky_za_lomitko')
def nahrada_pomlcky_za_lomitko(cislo_dl):
    """
    Nahradí pomlčky v čísle dodacího listu lomítky.
    """
    return cislo_dl.replace('-', '/') if isinstance(cislo_dl, str) else cislo_dl