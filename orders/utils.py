from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML



def get_verbose_name_for_column(model, field_chain):
    """
    Vrátí verbose_name (popisek) i pro zanořené (řetězené) pole včetně FK (např. 'zakazka__celozavit').
    """
    fields = field_chain.split('__')
    current_model = model
    for i, field_name in enumerate(fields):
        field = current_model._meta.get_field(field_name)
        if i == len(fields) - 1:
            return field.verbose_name.capitalize()
        current_model = field.remote_field.model
    return field_chain  # fallback


def utilita_tisk_karet_beden(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden.
    """
    if queryset.count() > 0:
        from io import BytesIO
        pdf_buffer = BytesIO()
        all_html = ""
        for bedna in queryset:
            context = {"bedna": bedna}
            html = render_to_string("orders/karta_bedny_eur.html", context)
            all_html += html + '<p style="page-break-after: always"></p>'  # Oddělí stránky

        pdf_file = HTML(string=all_html).write_pdf()
        response = HttpResponse(pdf_file, content_type="application/pdf")
        response['Content-Disposition'] = f'inline; filename="karty_beden.pdf"'
        return response
    else:
        messages.error(request, "Není vybrána žádná bedna k tisku.")
        return None