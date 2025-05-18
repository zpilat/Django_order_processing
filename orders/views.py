from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.urls import reverse_lazy
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .utils import get_verbose_name_for_column
from .models import Bedna, Zakazka, Kamion, Zakaznik, StavBednyChoice, TypHlavyChoice

import logging
logger = logging.getLogger('orders')

# Create your views here.

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
    ordering = ['-zakazka_id__id']

    def get_context_data(self, **kwargs):
        """
        Přidává další data do kontextu pro zobrazení v šabloně.

        Vrací:
        - Kontext obsahující filtry a řazení.
        """
        context = super().get_context_data(**kwargs)

        columns_fields = [
            'cislo_bedny', 'zakazka_id__kamion_id__zakaznik_id__zkratka', 'zakazka_id__kamion_id__datum',
            'zakazka_id__kamion_id', 'zakazka_id__artikl', 'zakazka_id__prumer', 'zakazka_id__delka', 'hmotnost',
            'stav_bedny', 'zakazka_id__typ_hlavy', 'tryskat', 'rovnat', 'zakazka_id__komplet', 'poznamka',
        ]
        # Získání názvů sloupců pro zobrazení v tabulce - slovník {pole: názvy sloupců}
        columns = {field: get_verbose_name_for_column(Bedna, field) for field in columns_fields}
        columns['zakazka_id__kamion_id__zakaznik_id__zkratka'] = 'Zákazník'
        stav_choices = [("", "VŠE")] + list(StavBednyChoice.choices)
        zakaznik_choices = [("", "VŠE")] + [(zakaznik.zkratka, zakaznik.zkratka) for zakaznik in Zakaznik.objects.all()]
        typ_hlavy_choices = [("", "VŠE")] + list(TypHlavyChoice.choices)

        context.update({
            'db_table': 'bedny',
            'sort': self.request.GET.get('sort', 'id'),
            'order': self.request.GET.get('order', 'up'),
            'query': self.request.GET.get('query', ''),
            'stav_filter': self.request.GET.get('stav_filter', 'VŠE'),
            'stav_choices': stav_choices,
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
        stav_filter = self.request.GET.get('stav_filter','VŠE')      
        zakaznik_filter = self.request.GET.get('zakaznik_filter', 'VŠE')
        typ_hlavy_filter = self.request.GET.get('typ_hlavy_filter', 'VŠE')  
        filters = {'tryskat': self.request.GET.get('tryskat', ''),
                   'rovnat': self.request.GET.get('rovnat', ''),
                   'zakazka_id__komplet': self.request.GET.get('zakazka_komplet', '')}


        queryset = queryset.exclude(stav_bedny='EX')  

        if stav_filter and stav_filter != 'VŠE':
            queryset = queryset.filter(stav_bedny=stav_filter)

        if zakaznik_filter and zakaznik_filter != 'VŠE':
            queryset = queryset.filter(zakazka_id__kamion_id__zakaznik_id__zkratka=zakaznik_filter)

        if typ_hlavy_filter and typ_hlavy_filter != 'VŠE':
            queryset = queryset.filter(zakazka_id__typ_hlavy=typ_hlavy_filter)

        for field, value in filters.items():
            if value == 'on':
                queryset = queryset.filter(**{field: True})

        if query:
            queryset = queryset.filter(
                Q(cislo_bedny__icontains=query) | Q(zakazka_id__kamion_id__datum__icontains=query)
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

   