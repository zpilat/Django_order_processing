import gc
import logging

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from .exceptions import ServiceValidationError

logger = logging.getLogger("orders")


def validate_cards_input(*, bedny_qs, template_paths, require_single_customer=True):
    errors = []
    if not template_paths:
        errors.append("Není k dispozici žádná šablona pro tisk dokumentace.")
    if not bedny_qs.exists():
        errors.append("Není vybrána žádná bedna k tisku.")
    if require_single_customer and bedny_qs.exists():
        if bedny_qs.values("zakazka__kamion_prijem__zakaznik").distinct().count() != 1:
            errors.append("Pro tisk karet musí být vybrány bedny od jednoho zákazníka.")
    return errors


def resolve_customer_templates(*, zakaznik_zkratka, mode):
    zkratka = (zakaznik_zkratka or "").lower()
    if not zkratka:
        raise ServiceValidationError("Chybí zkratka zákazníka pro výběr šablon.")

    if mode == "bedna":
        return [f"orders/karta_bedny_{zkratka}.html"], f"karty_beden_{zkratka}.pdf"
    if mode == "kkk":
        return [f"orders/karta_kontroly_kvality_{zkratka}.html"], f"karty_kontroly_kvality_{zkratka}.pdf"
    if mode == "kombi":
        return [
            f"orders/karta_bedny_{zkratka}.html",
            f"orders/karta_kontroly_kvality_{zkratka}.html",
        ], f"karty_bedny_a_kontroly_{zkratka}.pdf"

    raise ServiceValidationError(f"Neznámý mód tisku: {mode}")


def build_context_for_bedna(bedna, generated_at, user_display_name):
    return {
        "bedna": bedna,
        "generated_at": generated_at,
        "user_last_name": user_display_name,
    }


def render_pages(*, bedny_qs, template_paths, context_builder):
    html_parts = []
    for bedna in bedny_qs:
        context = context_builder(bedna)
        for template_path in template_paths:
            html_parts.append(render_to_string(template_path, context))
            html_parts.append('<p style="page-break-after: always"></p>')
    return "".join(html_parts)


def build_cards_pdf(*, bedny_qs, template_paths, filename, request=None, generated_at=None, user_display_name=""):
    errors = validate_cards_input(
        bedny_qs=bedny_qs,
        template_paths=template_paths,
        require_single_customer=False,
    )
    if errors:
        raise ServiceValidationError("; ".join(errors))

    gc.collect()
    generated_at = generated_at or timezone.now()

    if not user_display_name and request and hasattr(request, "user") and request.user.is_authenticated:
        user_display_name = (
            request.user.last_name
            or request.user.get_full_name()
            or request.user.get_username()
        )

    html_string = render_pages(
        bedny_qs=bedny_qs,
        template_paths=template_paths,
        context_builder=lambda bedna: build_context_for_bedna(bedna, generated_at, user_display_name),
    )

    base_url = request.build_absolute_uri("/") if request else None
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf()
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f"inline; filename={filename}"

    logger.info(
        f"Vygenerována PDF dokumentace pro {bedny_qs.count()} beden ({len(template_paths)} šablon na bednu)."
    )
    return response
