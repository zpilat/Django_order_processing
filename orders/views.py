from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.urls import reverse_lazy
from django.db.models import Q

from .models import Bedna, Zakazka, Kamion, Zakaznik, StavBednyChoice, TypHlavyChoice

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

        columns = [
            # (atribut v querysetu, popisek v tabulce)
            ('id', 'ID'),
            ('zakazka_id__kamion_id__zakaznik_id__zkratka', 'Dodavatel'),
            ('zakazka_id', 'Zakázka'),
            ('cislo_bedny', 'Č. bedny'),
            ('zakazka_id__prumer', 'Průměr'),
            ('zakazka_id__delka', 'Délka'),
            ('stav_bedny', 'Stav bedny'),
            ('zakazka_id__typ_hlavy', 'Typ hlavy'),
            ('tryskat', 'K tryskání'),
            ('rovnat', 'K rovnání'),
            ('zakazka_id__komplet', 'Kompletní?'),
            ('poznamka', 'Poznámka'),
        ]

        stav_choices = [("", "VŠE")] + StavBednyChoice.choices

        context.update({
            'db_table': 'bedny',
            'sort': self.request.GET.get('sort', 'id'),
            'order': self.request.GET.get('order', 'up'),
            'query': self.request.GET.get('query', ''),
            'stav_filter': self.request.GET.get('stav_filter', 'VŠE'),     
            'stav_choices': stav_choices,       
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

        queryset = queryset.exclude(stav_bedny='EX')  

        if stav_filter and stav_filter != 'VŠE':
            queryset = queryset.filter(stav_bedny=stav_filter)

        if query:
            queryset = queryset.filter(
                Q(cislo_bedny__icontains=query) | Q(zakazka_id__kamion_id__datum__icontains=query)
            )

        if order == 'down':
            sort = f"-{sort}"
         
        queryset = queryset.order_by(sort)

        return queryset
   