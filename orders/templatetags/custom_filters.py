from django import template
from decimal import Decimal, ROUND_HALF_UP

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

@register.filter(name='dict_get')
def dict_get(d, key):
    """
    Vrátí hodnotu z dict podle klíče, pokud existuje; jinak None.
    """
    return d.get(key)

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class})

@register.filter(name='nahrada_pomlcky_za_lomitko')
def nahrada_pomlcky_za_lomitko(cislo_dl):
    """
    Nahradí pomlčky v čísle dodacího listu lomítky.
    """
    return cislo_dl.replace('-', '/') if isinstance(cislo_dl, str) else cislo_dl

@register.filter
def multiply(value, arg):
    """
    Vynásobí value * arg a vrátí Decimal zaokrouhlený na 2 desetinná místa.
    Funguje i když value je Decimal a arg je float/int.
    """
    try:
        result = Decimal(str(value)) * Decimal(str(arg))
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (ValueError, TypeError, AttributeError):
        return Decimal('0.00')

@register.simple_tag
def flatten_bedny(zakazky):
    """
    Sloučí všechny bedny ze všech zakázek do jednoho seznamu s čísly pozic.
    Vrací list tuplů: (pozice, bedna, zakazka)
    """
    result = []
    pos = 1
    for zakazka in zakazky:
        for bedna in zakazka.bedny.all():
            result.append((pos, bedna, zakazka))
            pos += 1
    return result

@register.filter(name='splitlines')
def splitlines(value):
    """Rozdělí text na řádky, vhodné pro iteraci v šabloně."""
    if value is None:
        return []
    return str(value).splitlines()