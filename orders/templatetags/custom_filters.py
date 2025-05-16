from django import template

register = template.Library()

@register.filter(name='get_attribute')
def get_attribute(value, arg):
    """ Získá atribut podle jeho názvu z objektu a zobrazí 'ANO' nebo 'NE' pro boolean hodnoty. """
    result = getattr(value, arg, 'Atribut neexistuje')
    if isinstance(result, bool):
        return "ANO" if result else "NE"
    return result

@register.filter
def url_remove_param(querystring, params):
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
    """
    attrs = attr_chain.split('__')
    for attr in attrs:
        obj = getattr(obj, attr, None)
        if obj is None:
            return ''
    return obj