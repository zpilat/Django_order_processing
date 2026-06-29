from functools import lru_cache
from io import BytesIO
from urllib.parse import urljoin

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def _empty_svg():
    return ""


def _inline_svg(svg):
    start = svg.find("<svg")
    if start == -1:
        return ""
    return svg[start:]


@lru_cache(maxsize=4096)
def _qr_svg(value):
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return _empty_svg()

    image_factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(
        image_factory=image_factory,
        attrib={"class": "bedna-qr-svg"},
    )

    output = BytesIO()
    image.save(output)
    return _inline_svg(output.getvalue().decode("utf-8"))


@lru_cache(maxsize=4096)
def _code128_svg(value):
    try:
        import barcode
        from barcode.writer import SVGWriter
    except ImportError:
        return _empty_svg()

    writer = SVGWriter()
    code128 = barcode.get_barcode_class("code128")
    image = code128(
        value,
        writer=writer,
    )
    svg_bytes = image.render(
        writer_options={
            "module_width": 0.7,
            "module_height": 12.0,
            "quiet_zone": 2.5,
            "font_size": 0,
            "text_distance": 0,
            "write_text": False,
        }
    )
    return _inline_svg(svg_bytes.decode("utf-8"))


@register.simple_tag(takes_context=True)
def bedna_qr_svg(context, bedna):
    if not bedna or not getattr(bedna, "cislo_bedny", None):
        return ""

    scan_path = reverse("bedna_scan", args=[bedna.cislo_bedny])
    base_url = context.get("barcode_base_url") or "/"
    value = urljoin(base_url, scan_path.lstrip("/"))
    return mark_safe(_qr_svg(value))


@register.simple_tag
def bedna_code128_svg(bedna):
    if not bedna or not getattr(bedna, "cislo_bedny", None):
        return ""

    return mark_safe(_code128_svg(str(bedna.cislo_bedny)))


@register.simple_tag
def sarze_code128_svg(sarze):
    if not sarze or not getattr(sarze, "cislo_sarze", None):
        return ""

    return mark_safe(_code128_svg(str(sarze)))


@register.simple_tag(takes_context=True)
def bedna_scan_url(context, bedna):
    if not bedna or not getattr(bedna, "cislo_bedny", None):
        return ""

    scan_path = reverse("bedna_scan", args=[bedna.cislo_bedny])
    base_url = context.get("barcode_base_url") or "/"
    return format_html("{}", urljoin(base_url, scan_path.lstrip("/")))
