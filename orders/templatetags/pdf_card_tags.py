from functools import lru_cache
from math import floor

from django import template
from django.utils.html import format_html
from weasyprint import HTML


register = template.Library()


@lru_cache(maxsize=1024)
def _eur_artikl_sarze_font_size(text):
    """Measure with the PDF renderer and shrink only overflowing EUR labels."""
    # The cell spans 8 of 18 columns on A4 landscape with 10 mm margins.
    # Allow 450 px for text after cell padding, borders and a small reserve.
    available_width = 450
    base_size = 40  # fs-25 = 2.5rem
    html = format_html(
        '<span id="label" style="display: inline-block; white-space: nowrap; '
        'font-family: Liberation Sans, Arial; font-weight: bold; '
        'font-size: 40px;">{}</span>',
        text,
    )
    document = HTML(string=str(html)).render()
    left, _, right, _ = document.pages[0].anchors['label']
    width = right - left
    size = min(base_size, base_size * available_width / width) if width else base_size
    # Round down, keeping a CSS decimal point regardless of Django's locale.
    return f'{floor(size * 100) / 100:.2f}'


@register.simple_tag
def eur_artikl_sarze_font_size(artikl, sarze):
    return _eur_artikl_sarze_font_size(f'{artikl} - {sarze}')
