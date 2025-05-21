from django import template

register = template.Library()

@register.filter
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

@register.filter
def attr_chain(obj, attr_chain):
    """
    Projde objekt podle řetězce atributů oddělených __ a vrátí hodnotu.
    Např. item|attr_chain:"zakazka_id__typ_hlavy"
    Pokud je objekt None nebo atribut neexistuje, vrátí prázdný řetězec.
    Pokud je atribut typu bool, vrátí "ANO" nebo "NE".
    """
    attrs = attr_chain.split('__')
    for attr in attrs:
        obj = getattr(obj, attr, None)
        if obj is None:
            return ''
        if isinstance(obj, bool):
            return "ANO" if obj else "NE"        
    return obj