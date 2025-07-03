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
from .models import Bedna, Zakazka, Kamion, Zakaznik, TypHlavy, Predpis, Odberatel, Cena
from .choices import  StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice

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
            'id', 'cislo_bedny', 'zakazka__priorita', 'zakazka__kamion_prijem__zakaznik__zkratka',
            'zakazka__kamion_prijem__datum', 'zakazka__kamion_prijem', 'zakazka__artikl', 'zakazka__prumer',
            'zakazka__delka', 'hmotnost', 'stav_bedny', 'zakazka__typ_hlavy', 'tryskat', 'rovnat',
            'poznamka',
        ]
        # Získání názvů sloupců pro zobrazení v tabulce - slovník {pole: názvy sloupců}
        columns = {field: get_verbose_name_for_column(Bedna, field) for field in columns_fields}
        columns['zakazka__kamion_prijem__zakaznik__zkratka'] = 'Zákazník'
        stav_choices = [("SKLAD", "SKLADEM"), ("", "VŠE")] + list(StavBednyChoice.choices)
        zakaznik_choices = [("", "VŠE")] + [(zakaznik.zkratka, zakaznik.zkratka) for zakaznik in Zakaznik.objects.all()]
        typ_hlavy_choices = [("", "VŠE")] + [(typ_hlavy.nazev, typ_hlavy.nazev) for typ_hlavy in TypHlavy.objects.all()]
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
                   'rovnat': self.request.GET.get('rovnat', '')}

        if stav_filter and stav_filter != 'VŠE':
            if stav_filter == 'SKLAD':
                queryset = queryset.exclude(stav_bedny='EX')
            else:
                queryset = queryset.filter(stav_bedny=stav_filter)

        if zakaznik_filter and zakaznik_filter != 'VŠE':
            queryset = queryset.filter(zakazka__kamion_prijem__zakaznik__zkratka=zakaznik_filter)

        if typ_hlavy_filter and typ_hlavy_filter != 'VŠE':
            queryset = queryset.filter(zakazka__typ_hlavy=typ_hlavy_filter)

        if priorita_filter and priorita_filter != 'VŠE':
            queryset = queryset.filter(zakazka__priorita=priorita_filter)

        for field, value in filters.items():
            if value == 'on':
                queryset = queryset.filter(**{field: True})

        if query:
            queryset = queryset.filter(
                Q(cislo_bedny__icontains=query) | Q(zakazka__kamion_prijem__datum__icontains=query)
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
def dashboard_bedny_view(request):
    """
    Přehled stavu beden dle zákazníků.
    """
    def get_stav_data(filter_kwargs):
        """
        Získává data o stavech beden pro dané filtry.
        """
        data = Bedna.objects.filter(**filter_kwargs).values(
            'zakazka__kamion_prijem__zakaznik__zkraceny_nazev'
        ).annotate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')
        )
        data_dict = {
            item['zakazka__kamion_prijem__zakaznik__zkraceny_nazev']: (item['pocet'], item['hmotnost']) for item in data
        }
        total = Bedna.objects.filter(**filter_kwargs).aggregate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')
        )
        data_dict['CELKEM'] = (total['pocet'], total['hmotnost'])
        return data_dict

    stavy = {
        'Zakalené': {'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO, StavBednyChoice.K_EXPEDICI]},
        'Ke kontrole': {'stav_bedny': StavBednyChoice.ZAKALENO},
        'Křivé': {'rovnat': RovnaniChoice.KRIVA},
        'Otryskané': {'tryskat': TryskaniChoice.OTRYSKANA},
        'K tryskání': {'tryskat': TryskaniChoice.SPINAVA, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},
        'K expedici': {'stav_bedny': StavBednyChoice.K_EXPEDICI},
        'Surové': {'stav_bedny__in': [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI]},
        'Navezené': {'stav_bedny': StavBednyChoice.NAVEZENO},
        'Přijaté': {'stav_bedny__in': [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]},
    }

    zakaznici = list(Zakaznik.objects.values_list('zkraceny_nazev', flat=True).order_by('zkraceny_nazev')) + ['CELKEM']
    prehled_beden_zakaznika = {zak: {stav: (0, 0) for stav in stavy} for zak in zakaznici}

    for stav, filter_kwargs in stavy.items():
        stav_data = get_stav_data(filter_kwargs)
        for zak in zakaznici:
            prehled_beden_zakaznika[zak][stav] = stav_data.get(zak, (0, 0))

    stavy_bedny_list = ['Zakalené', 'Ke kontrole', 'Křivé', 'Otryskané', 'K tryskání', 'K expedici', 'Surové', 'Navezené', 'Přijaté']

    context = {
        'prehled_beden_zakaznika': prehled_beden_zakaznika,
        'stavy_bedny_list': stavy_bedny_list,
        'db_table': 'dashboard_bedny',
        'current_time': timezone.now(),
    }

    if request.htmx:
        return render(request, "orders/partials/dashboard_bedny_content.html", context)
    return render(request, 'orders/dashboard_bedny.html', context)


@login_required
def dashboard_kamiony_view(request):
    """
    Zobrazení přehledu příjmů a výdejů kamionů za jednotlivé měsíce v roce.
    Umožňuje filtrovat podle roku a zobrazuje celkovou hmotnost beden pro jednotlivé zákazníky.
    V případě HTMX požadavku vrací pouze část obsahu pro aktualizaci.
    """
    zakaznici = Zakaznik.objects.all().order_by('zkratka')
    rok = request.GET.get('rok', timezone.now().year)
    kamiony_prijem_rok = Kamion.objects.filter(prijem_vydej='P', datum__year=rok)
    kamiony_vydej_rok = Kamion.objects.filter(prijem_vydej='V', datum__year=rok)

    kamiony_prijem = kamiony_prijem_rok.values(
        'datum__month', 'zakaznik__zkratka'
    ).annotate(
        celkova_hmotnost=Sum('zakazky_prijem__bedny__hmotnost')
    )

    kamiony_vydej = kamiony_vydej_rok.values(
        'datum__month', 'zakaznik__zkratka'
    ).annotate(
        celkova_hmotnost=Sum('zakazky_vydej__bedny__hmotnost')
    )

    # Inicializace slovníku pro měsíční pohyby
    mesicni_pohyby = {}
    # Přidání všech měsíců do slovníku, aby se zajistilo, že budou zobrazeny i prázdné měsíce
    mesice = ('leden / január', 'únor / február', 'březen / marec',
              'duben / apríl', 'květen / máj', 'červen / jún',
              'červenec / júl', 'srpen / august', 'září / september',
              'říjen / október', 'listopad / november', 'prosinec / december')
    for mesic in range(1, 13):
        # Inicializace prázdného slovníku pro každý měsíc
        mesicni_pohyby[mesic] = {}
        # Přidání všech zákazníků do každého měsíce, aby se zajistilo, že budou zobrazeny i zákazníci bez pohybu v daném měsíci
        for zakaznik in zakaznici:
            mesicni_pohyby[mesic][zakaznik.zkratka] = {'prijem': 0, 'vydej': 0}

    # Sčítání příjmů a výdejů pro jednotlivé měsíce a zákazníky
    for kamion_prijem in kamiony_prijem:
        mesic = kamion_prijem['datum__month']
        zakaznik = kamion_prijem['zakaznik__zkratka']
        mesicni_pohyby[mesic][zakaznik]['prijem'] += kamion_prijem['celkova_hmotnost'] or 0

    for kamion_vydej in kamiony_vydej:
        mesic = kamion_vydej['datum__month']
        zakaznik = kamion_vydej['zakaznik__zkratka']
        mesicni_pohyby[mesic][zakaznik]['vydej'] += kamion_vydej['celkova_hmotnost'] or 0

    # Přidání celkových součtů pro každý měsíc
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        celkovy_prijem = sum(pohyby['prijem'] for pohyby in zakaznici_pohyby.values())
        celkovy_vydej = sum(pohyby['vydej'] for pohyby in zakaznici_pohyby.values())
        mesicni_pohyby[mesic]['CELKEM'] = {
            'prijem': celkovy_prijem,
            'vydej': celkovy_vydej
        }

    # Přidání celkových součtů dle zákazníků za celý rok
    rocni_pohyby = {}
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        for zakaznik, pohyby in zakaznici_pohyby.items():
            if zakaznik not in rocni_pohyby:
                rocni_pohyby[zakaznik] = {'prijem': 0, 'vydej': 0}
            rocni_pohyby[zakaznik]['prijem'] += pohyby['prijem']
            rocni_pohyby[zakaznik]['vydej'] += pohyby['vydej']

    mesicni_pohyby['CELKEM'] = rocni_pohyby

    # Přidání rozdílu mezi příjmy a výdeji pro každý měsíc pro každého zákazníka
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        for zakaznik, pohyby in zakaznici_pohyby.items():
            mesicni_pohyby[mesic][zakaznik]['rozdil'] = pohyby['prijem'] - pohyby['vydej']

    context = {
        'mesicni_pohyby': mesicni_pohyby,
        'rok': rok,
        'db_table': 'dashboard_kamiony',
        'current_time': timezone.now(),
    }
    
    if request.htmx:
        return render(request, "orders/partials/dashboard_kamiony_content.html", context)
    return render(request, 'orders/dashboard_kamiony.html', context)
