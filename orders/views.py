from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.urls import reverse_lazy
from django.db.models import Q, Sum, Count
from django.utils.translation import gettext_lazy as _
import django.utils.timezone as timezone

from .utils import get_verbose_name_for_column
from .models import Bedna, Zakazka, Kamion, Zakaznik
from .choices import (
    TypHlavyChoice, StavBednyChoice, RovnaniChoice, TryskaniChoice,
    PrioritaChoice, ZinkovnaChoice, KamionChoice
)

import logging
logger = logging.getLogger('orders')

# Create your views here.

def home_view(request):
    """
    Zobrazuje úvodní stránku aplikace.
    
    Parameters:
    - request: HTTP request objekt.

    Vrací:
    - render: HTML stránku `home.html` s aktuálním přihlášeným uživatelem v kontextu.
    """
    context = {'db_table': 'home'}
    logger.debug(f'Zahájena view home_view s uživatelem: {request.user}')
    return render(request, "orders/home.html", context)


class BednyListView(LoginRequiredMixin, ListView):
    """
    Zobrazuje seznam beden.

    Template:
    - `bedny_list.html`

    Kontext:
    - Seznam beden a možnosti filtrování.
    """
    model = Bedna
    template_name = 'orders/bedny_list.html'
    ordering = ['id']

    def get_context_data(self, **kwargs):
        """
        Přidává další data do kontextu pro zobrazení v šabloně.

        Vrací:
        - Kontext obsahující filtry a řazení.
        """
        context = super().get_context_data(**kwargs)

        columns_fields = [
            'id', 'cislo_bedny', 'zakazka_id__priorita', 'zakazka_id__kamion_prijem_id__zakaznik_id__zkratka',
            'zakazka_id__kamion_prijem_id__datum', 'zakazka_id__kamion_prijem_id', 'zakazka_id__artikl', 'zakazka_id__prumer',
            'zakazka_id__delka', 'hmotnost', 'stav_bedny', 'zakazka_id__typ_hlavy', 'tryskat', 'rovnat',
            'zakazka_id__komplet', 'poznamka',
        ]
        # Získání názvů sloupců pro zobrazení v tabulce - slovník {pole: názvy sloupců}
        columns = {field: get_verbose_name_for_column(Bedna, field) for field in columns_fields}
        columns['zakazka_id__kamion_prijem_id__zakaznik_id__zkratka'] = 'Zákazník'
        stav_choices = [("SKLAD", "SKLADEM"), ("", "VŠE")] + list(StavBednyChoice.choices)
        zakaznik_choices = [("", "VŠE")] + [(zakaznik.zkratka, zakaznik.zkratka) for zakaznik in Zakaznik.objects.all()]
        typ_hlavy_choices = [("", "VŠE")] + list(TypHlavyChoice.choices)
        priorita_choices = [("", "VŠE")] + list(PrioritaChoice.choices)

        context.update({
            'db_table': 'bedny',
            'sort': self.request.GET.get('sort', 'id'),
            'order': self.request.GET.get('order', 'up'),
            'query': self.request.GET.get('query', ''),
            'stav_filter': self.request.GET.get('stav_filter', 'VŠE'),
            'stav_choices': stav_choices,
            'priorita_filter': self.request.GET.get('priorita_filter', 'VŠE'),
            'priorita_choices': priorita_choices,
            'zakaznik_filter': self.request.GET.get('zakaznik_filter', 'VŠE'),
            'zakaznik_choices': zakaznik_choices,
            'typ_hlavy_filter': self.request.GET.get('typ_hlavy_filter', 'VŠE'),
            'typ_hlavy_choices': typ_hlavy_choices,
            'zakazka_komplet': self.request.GET.get('zakazka_komplet', ''),
            'tryskat': self.request.GET.get('tryskat', ''),
            'rovnat': self.request.GET.get('rovnat', ''),
            'columns': columns,
        })
        return context

    
    def get_queryset(self):
        """
        Získává seznam beden na základě vyhledávání a filtrování.

        Vrací:
        - queryset: Filtrovaný a seřazený seznam beden.
        """
        queryset = Bedna.objects.all()

        query = self.request.GET.get('query', '')
        sort = self.request.GET.get('sort', 'id')
        order = self.request.GET.get('order', 'up')
        stav_filter = self.request.GET.get('stav_filter','SKLAD')      
        zakaznik_filter = self.request.GET.get('zakaznik_filter', 'VŠE')
        typ_hlavy_filter = self.request.GET.get('typ_hlavy_filter', 'VŠE')  
        priorita_filter = self.request.GET.get('priorita_filter', 'VŠE')
        # Filtrování podle checkboxů
        filters = {'tryskat': self.request.GET.get('tryskat', ''),
                   'rovnat': self.request.GET.get('rovnat', ''),
                   'zakazka_id__komplet': self.request.GET.get('zakazka_komplet', '')}

        if stav_filter and stav_filter != 'VŠE':
            if stav_filter == 'SKLAD':
                queryset = queryset.exclude(stav_bedny='EX')
            else:
                queryset = queryset.filter(stav_bedny=stav_filter)

        if zakaznik_filter and zakaznik_filter != 'VŠE':
            queryset = queryset.filter(zakazka_id__kamion_prijem_id__zakaznik_id__zkratka=zakaznik_filter)

        if typ_hlavy_filter and typ_hlavy_filter != 'VŠE':
            queryset = queryset.filter(zakazka_id__typ_hlavy=typ_hlavy_filter)

        if priorita_filter and priorita_filter != 'VŠE':
            queryset = queryset.filter(zakazka_id__priorita=priorita_filter)

        for field, value in filters.items():
            if value == 'on':
                queryset = queryset.filter(**{field: True})

        if query:
            queryset = queryset.filter(
                Q(cislo_bedny__icontains=query) | Q(zakazka_id__kamion_prijem_id__datum__icontains=query)
            )

        if order == 'down':
            sort = f"-{sort}"
         
        queryset = queryset.order_by(sort)

        return queryset
    
    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('Hx-Request') == 'true':
            return render(self.request, "orders/partials/listview_table.html", context)
        else:
            return super().render_to_response(context, **response_kwargs)


class ZakazkyListView(LoginRequiredMixin, ListView):
    """
    Zobrazuje seznam zakázek.

    Template:
    - `zakazky_list.html`

    Kontext:
    - Seznam zakázek a možnosti filtrování.
    """
    model = Zakazka
    template_name = 'orders/zakazky_list.html'
    ordering = ['id']


@login_required
def dashboard_view(request):
    '''
    Zobrazení přehledu stavu beden jednotlivých zákazníků,
    pro každého zákazníka a pro všechny dohromady zobrazí pro jednotlivé stavy celkovou hmotnost.
    '''
    prehled_beden_zakaznika = {}
    
    # Získání přehledu beden pro každého zákazníka
    for zakaznik in Zakaznik.objects.all():
        bedny_zakaznika = Bedna.objects.filter(zakazka_id__kamion_prijem_id__zakaznik_id=zakaznik)
        prehled_beden_zakaznika[zakaznik.nazev] = bedny_zakaznika.values('stav_bedny').annotate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')
        )
    
    # Přidání celkového přehledu pro všechny zákazníky
    prehled_beden_zakaznika['CELKEM'] = Bedna.objects.values('stav_bedny').annotate(
        pocet=Count('id'),
        hmotnost=Sum('hmotnost')
    )

    context = {
        'prehled_beden_zakaznika': prehled_beden_zakaznika,
        'stav_bedny_choices': StavBednyChoice.choices,
        'db_table': 'dashboard',
        'current_time': timezone.now(),
        }
    
    if request.htmx:
        return render(request, "orders/partials/dashboard_content.html", context)
    return render(request, 'orders/dashboard.html', context)