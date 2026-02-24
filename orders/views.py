from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.urls import reverse_lazy
from django.db.models import Q, Sum, Count, F, Exists, OuterRef
from django.utils.translation import gettext_lazy as _
import django.utils.timezone as timezone
from datetime import timedelta, time, date
from django.db import transaction
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.http import HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.utils.text import slugify
from django.shortcuts import get_object_or_404

from .utils import get_verbose_name_for_column, utilita_tisk_dl_a_proforma_faktury
from .models import Bedna, Zakazka, Kamion, Zakaznik, TypHlavy, Predpis, Odberatel, Cena, Pozice, PoziceZakazkaOrder, Sarze, SarzeBedna
from .choices import  StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice, ZinkovaniChoice, STAV_BEDNY_ROZPRACOVANOST, STAV_BEDNY_SKLADEM
from weasyprint import HTML, CSS

import logging
logger = logging.getLogger('orders')

 
def _format_hours(hours_value):
    return f"{hours_value:.1f}".replace('.', ',')


def _format_tuny(value):
    if value is None:
        return '0'
    return f"{value / 1000:.1f}".replace('.', ',')


def _calc_prostoj_minutes(sarze_list):
    total_minutes = 0
    for sarze in sarze_list:
        prodleva = sarze.prodleva
        if isinstance(prodleva, int):
            total_minutes += max(prodleva - 10, 0)
    return total_minutes


def _build_vyroba_dashboard_context(date_value=None):
    date_value = date_value or (timezone.localdate() - timedelta(days=1))
    today = date_value + timedelta(days=1)
    device_codes = ["TQF_XL1", "TQF_XL2"]

    base_qs = Sarze.objects.filter(
        datum=date_value,
        zarizeni__kod_zarizeni__in=device_codes,
    ).select_related('zarizeni')

    bedna_exists = SarzeBedna.objects.filter(
        sarze=OuterRef('pk'),
        bedna__isnull=False,
    )
    manual_exists = SarzeBedna.objects.filter(
        sarze=OuterRef('pk'),
        bedna__isnull=True,
    ).filter(
        popis__isnull=False,
    )

    qs = base_qs.annotate(
        has_vruty=Exists(bedna_exists),
        has_zelezo=Exists(manual_exists),
    )

    def _calc_vykon_vruty_kg(code: list[str]):
        sarze_bedny = (
            SarzeBedna.objects
            .filter(
                sarze__datum=date_value,
                sarze__zarizeni__kod_zarizeni__in=code,
                bedna__isnull=False,
                bedna__hmotnost__isnull=False,
                bedna__hmotnost__gt=0,
            )
            .select_related('sarze', 'bedna')
        )

        prior_exists = SarzeBedna.objects.filter(
            bedna_id=OuterRef('bedna_id'),
            sarze__zarizeni_id=OuterRef('sarze__zarizeni_id'),
        ).exclude(pk=OuterRef('pk')).filter(
            Q(sarze__datum__lt=OuterRef('sarze__datum'))
            | Q(sarze__datum=OuterRef('sarze__datum'), sarze__zacatek__lt=OuterRef('sarze__zacatek'))
        )

        first_use_qs = sarze_bedny.annotate(
            has_prior=Exists(prior_exists),
        ).filter(has_prior=False)

        return first_use_qs.aggregate(total=Sum('bedna__hmotnost')).get('total') or 0

    def _device_stats(code: list[str]):
        dqs = qs.filter(zarizeni__kod_zarizeni__in=code)
        total = dqs.count()
        vruty = dqs.filter(has_vruty=True).count()
        zelezo = dqs.filter(has_zelezo=True).count()
        prostoj_minutes = _calc_prostoj_minutes(list(dqs))
        prostoj_hours = _format_hours(prostoj_minutes / 60) if prostoj_minutes else '0,0'
        vykon_vruty_tuny = _format_tuny(_calc_vykon_vruty_kg(code))
        return {
            'total': total,
            'vruty': vruty,
            'zelezo': zelezo,
            'prostoj_hours': prostoj_hours,
            'vykon_vruty_tuny': vykon_vruty_tuny,
        }

    xl1 = _device_stats([device_codes[0]])
    xl2 = _device_stats([device_codes[1]])
    summary = _device_stats(device_codes)

    def _shift_stats(shift_qs):
        xl1_qs = shift_qs.filter(zarizeni__kod_zarizeni=device_codes[0])
        xl2_qs = shift_qs.filter(zarizeni__kod_zarizeni=device_codes[1])

        xl1_count = xl1_qs.count()
        xl2_count = xl2_qs.count()
        total_count = xl1_count + xl2_count

        xl1_minutes = _calc_prostoj_minutes(list(xl1_qs))
        xl2_minutes = _calc_prostoj_minutes(list(xl2_qs))
        total_minutes = xl1_minutes + xl2_minutes

        return {
            'counts': {
                'xl1': xl1_count,
                'xl2': xl2_count,
                'total': total_count,
            },
            'prostoje': {
                'xl1': _format_hours(xl1_minutes / 60) if xl1_minutes else '0,0',
                'xl2': _format_hours(xl2_minutes / 60) if xl2_minutes else '0,0',
                'total': _format_hours(total_minutes / 60) if total_minutes else '0,0',
            },
        }

    day_qs = base_qs.filter(zacatek__gte=time(7, 0), zacatek__lt=time(19, 0))
    night_qs = Sarze.objects.filter(
        zarizeni__kod_zarizeni__in=device_codes,
    ).filter(
        Q(datum=date_value, zacatek__gte=time(19, 0))
        | Q(datum=today, zacatek__lt=time(7, 0))
    ).select_related('zarizeni')

    dashboard = {
        'date_label': date_value.strftime('%d.%m.%Y'),
        'devices': {
            'xl1': xl1,
            'xl2': xl2,
            'celkem': summary,
        },
        'shifts': {
            'day': _shift_stats(day_qs),
            'night': _shift_stats(night_qs),
        },
    }
    return {'vyroba_dashboard': dashboard, 'current_time': timezone.now()}

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
            hmotnost=Sum('hmotnost')/1000 # převod na tuny (z kg)
        )
        data_dict = {
            item['zakazka__kamion_prijem__zakaznik__zkraceny_nazev']: (item['pocet'], item['hmotnost']) for item in data
        }
        total = Bedna.objects.filter(**filter_kwargs).aggregate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')/1000  # také převod na tuny pro řádek CELKEM
        )
        data_dict['CELKEM'] = (
            total['pocet'] or 0,
            (total['hmotnost'] or 0)  # už v tunách
        )
        return data_dict

    kompletni_zakazky = (
        Zakazka.objects
        .annotate(
            pocet_beden_celkem=Count('bedny'),
            pocet_beden_k_expedici=Count(
                'bedny',
                filter=Q(bedny__stav_bedny=StavBednyChoice.K_EXPEDICI),
            ),
        )
        .filter(
            pocet_beden_celkem__gt=0,
            pocet_beden_celkem=F('pocet_beden_k_expedici'),
        )
    )

    stavy = {
        'Nepřijaté': {'stav_bedny': StavBednyChoice.NEPRIJATO},        
        'Surové': {'stav_bedny__in': [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI]},
        '-> K navezení': {'stav_bedny': StavBednyChoice.K_NAVEZENI},
        '-> Navezené': {'stav_bedny': StavBednyChoice.NAVEZENO},
        'Zpracované': {'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO, StavBednyChoice.K_EXPEDICI]},
        '-> Ke kontrole': {'stav_bedny': StavBednyChoice.ZAKALENO},
        '-> K tryskání': {'tryskat': TryskaniChoice.SPINAVA, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},        
        '-> Křivé': {'rovnat': RovnaniChoice.KRIVA, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},
        '-> Koulení': {'rovnat': RovnaniChoice.KOULENI, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},
        '-> Rovná se': {'rovnat': RovnaniChoice.ROVNA_SE, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},
        '-> Zinkovat': {'zinkovat': ZinkovaniChoice.ZINKOVAT, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]},
        '-> V zinkovně': {'zinkovat': ZinkovaniChoice.V_ZINKOVNE},
        '-> K exp. po bednách': {'stav_bedny': StavBednyChoice.K_EXPEDICI},
        '--> K exp. po zakáz.': {'stav_bedny': StavBednyChoice.K_EXPEDICI, 'zakazka__in': kompletni_zakazky},
        'Po exspiraci': {'stav_bedny__in': STAV_BEDNY_SKLADEM, 'zakazka__kamion_prijem__datum__lt': timezone.now().date() - timezone.timedelta(days=28)},
    }

    zakaznici = list(Zakaznik.objects.values_list('zkraceny_nazev', flat=True).order_by('zkraceny_nazev')) + ['CELKEM']
    prehled_beden_zakaznika = {zak: {stav: (0, 0) for stav in stavy} for zak in zakaznici}

    for stav, filter_kwargs in stavy.items():
        stav_data = get_stav_data(filter_kwargs)
        for zak in zakaznici:
            prehled_beden_zakaznika[zak][stav] = stav_data.get(zak, (0, 0))

    stavy_bedny_list = list(stavy.keys())

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


@login_required
def dashboard_vyroba_view(request):
    """
    Včerejší přehledy pro výrobu (TQF_XL1, TQF_XL2).
    """
    # pro ladění předáno konkrétní datum: date(2026,2,19), pro které jsou zadána v db data
    # pro produkci se použije bez parametru, aby se vždy zobrazil včerejší den: date_value=None
    context = _build_vyroba_dashboard_context(date_value=date(2026,2,19)) 
    if request.htmx:
        return render(request, "orders/partials/dashboard_vyroba_content.html", context)
    return render(request, 'orders/dashboard_vyroba.html', context)


def _get_bedny_k_navezeni_groups():
    """Sestaví seskupená data beden k navezení podle pozice a zakázky."""
    qs = (
        Bedna.objects
        .filter(stav_bedny=StavBednyChoice.K_NAVEZENI)
        .select_related('pozice', 'zakazka')
        .order_by('pozice__kod', 'zakazka', 'cislo_bedny')
    )
    bedny = list(qs)

    active_pairs = {
        (bedna.pozice_id, bedna.zakazka_id)
        for bedna in bedny
        if bedna.pozice_id is not None and bedna.zakazka_id is not None
    }
    orders_by_position = {}
    # Keep PoziceZakazkaOrder synced with current bedny state.
    with transaction.atomic():
        existing_orders = list(
            PoziceZakazkaOrder.objects.order_by('pozice_id', 'poradi', 'pk')
        )

        stale_ids = {
            order.pk for order in existing_orders
            if (order.pozice_id, order.zakazka_id) not in active_pairs
        }
        if stale_ids:
            PoziceZakazkaOrder.objects.filter(pk__in=stale_ids).delete()
            existing_orders = [order for order in existing_orders if order.pk not in stale_ids]

        for order in existing_orders:
            if order.pozice_id is None:
                continue
            orders_by_position.setdefault(order.pozice_id, []).append(order)

        for pozice_id, order_list in orders_by_position.items():
            for idx, order in enumerate(order_list, start=1):
                if order.poradi != idx:
                    PoziceZakazkaOrder.objects.filter(pk=order.pk).update(poradi=idx)
                    order.poradi = idx

        seen_pairs = set()
        for bedna in bedny:
            pozice_id = bedna.pozice_id
            zakazka_id = bedna.zakazka_id
            if pozice_id is None or zakazka_id is None:
                continue
            pair = (pozice_id, zakazka_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            order_list = orders_by_position.setdefault(pozice_id, [])
            if not any(order.zakazka_id == zakazka_id for order in order_list):
                poradi = len(order_list) + 1
                new_order = PoziceZakazkaOrder.objects.create(
                    pozice_id=pozice_id,
                    zakazka_id=zakazka_id,
                    poradi=poradi,
                )
                order_list.append(new_order)

    order_map = {}
    for order_list in orders_by_position.values():
        for order in order_list:
            order_map[(order.pozice_id, order.zakazka_id)] = order.poradi

    groups = []
    pozice_map = {}

    for bedna in bedny:
        pozice_kod = bedna.pozice.kod if bedna.pozice else None
        zakazka_id = bedna.zakazka.id if bedna.zakazka else None

        # Najde nebo vytvoří skupinu pro pozici
        if pozice_kod not in pozice_map:
            pozice_group = {'pozice': pozice_kod, 'zakazky_group': []}
            pozice_map[pozice_kod] = pozice_group
            groups.append(pozice_group)
        else:
            pozice_group = pozice_map[pozice_kod]

        # Najde nebo vytvoří podskupinu pro zakázku
        zakazka_group = next((z for z in pozice_group['zakazky_group'] if z['zakazka'].id == zakazka_id), None)
        if not zakazka_group:
            # Získání pořadí z mapy, případně default 0
            poradi = order_map.get((bedna.pozice_id, zakazka_id), 0)
            zakazka_group = {
                'zakazka': bedna.zakazka,
                'bedny': [],
                'poradi': poradi,
                'pozice_id': bedna.pozice_id,
            }
            pozice_group['zakazky_group'].append(zakazka_group)

        # Přidá bednu do správné zakázky
        zakazka_group['bedny'].append(bedna)

    # Seřadí zakázky v rámci každé pozice dle pořadí
    for pozice_group in groups:
        pozice_group['zakazky_group'].sort(
            key=lambda z: (z.get('poradi', 0), z['zakazka'].id)
        )

    return groups


@login_required
def dashboard_bedny_k_navezeni_view(request):
    """
    Zobrazí všechny bedny se stavem K_NAVEZENI, seskupené podle pozice a zakázky.

    Sloupce: artikl, číslo bedny, rozměr (průměr x délka), popis, poznámka.
    Seskupeno podle pozice (kód pozice), setříděno podle pozice a čísla bedny.
    Umožňuje aktualizovat pořadí zakázek v rámci pozice pomocí HTMX POST požadavků.
    """
    # Získání všech kódů pozic a mapování předchozí a následující pozice do šablony
    pozice_kody = list(
        Pozice.objects.values_list('kod', flat=True).order_by('kod')
    )
    pozice_id_by_kod = dict(
        Pozice.objects.values_list('kod', 'id')
    )
    prev_map = {}
    next_map = {}
    for i, kod in enumerate(pozice_kody):
        if i > 0:
            prev_map[kod] = pozice_kody[i - 1]
        if i < len(pozice_kody) - 1:
            next_map[kod] = pozice_kody[i + 1]

    # Umožní aktualizaci pořadí pro konkrétní zakázku v pozici
    if request.method == 'POST':
        try:
            pozice_id = int(request.POST.get('pozice_id'))
            zakazka_id = int(request.POST.get('zakazka_id'))
        except (TypeError, ValueError):
            pozice_id = zakazka_id = None
        move = (request.POST.get('move') or '').lower()
        poradi = request.POST.get('poradi')
        try:
            poradi = int(poradi) if poradi is not None and poradi != '' else 0
        except ValueError:
            poradi = 0

        if pozice_id and zakazka_id:
            with transaction.atomic():
                # Zamkni pořadí pro aktuální pozici
                qs = list(
                    PoziceZakazkaOrder.objects
                    .select_for_update()
                    .filter(pozice_id=pozice_id)
                    .order_by('poradi', 'zakazka_id')
                )

                n = len(qs)
                cur_idx = next((i for i, p in enumerate(qs) if p.zakazka_id == zakazka_id), None)

                moved_between_positions = False
                target_pozice_id = None
                if move == 'up' and cur_idx == 0:
                    # přesun do předchozí pozice na konec
                    pozice_kod = next((k for k, v in pozice_id_by_kod.items() if v == pozice_id), None)
                    prev_kod = prev_map.get(pozice_kod)
                    target_pozice_id = pozice_id_by_kod.get(prev_kod)
                    if target_pozice_id:
                        moved_between_positions = True
                        # uzamkni cílovou pozici
                        dst_orders = list(
                            PoziceZakazkaOrder.objects
                            .select_for_update()
                            .filter(pozice_id=target_pozice_id)
                            .order_by('poradi', 'zakazka_id')
                        )
                        # přesun beden
                        Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id).update(pozice_id=target_pozice_id)
                        # přepiš pořadí ve zdrojové pozici (bez této zakázky)
                        src_ids = [p.zakazka_id for p in qs if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(pozice_id=pozice_id, zakazka_id=zid, poradi=idx)
                            for idx, zid in enumerate(src_ids, start=1)
                        ])
                        # vlož do cílové pozice na konec (bez duplicit, kdyby tam zakázka už byla)
                        dst_ids = [p.zakazka_id for p in dst_orders if p.zakazka_id != zakazka_id] + [zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=target_pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(pozice_id=target_pozice_id, zakazka_id=zid, poradi=idx)
                            for idx, zid in enumerate(dst_ids, start=1)
                        ])

                elif move == 'down' and cur_idx is not None and cur_idx == n - 1:
                    # přesun do následující pozice na začátek
                    pozice_kod = next((k for k, v in pozice_id_by_kod.items() if v == pozice_id), None)
                    next_kod = next_map.get(pozice_kod)
                    target_pozice_id = pozice_id_by_kod.get(next_kod)
                    if target_pozice_id:
                        moved_between_positions = True
                        dst_orders = list(
                            PoziceZakazkaOrder.objects
                            .select_for_update()
                            .filter(pozice_id=target_pozice_id)
                            .order_by('poradi', 'zakazka_id')
                        )
                        Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id).update(pozice_id=target_pozice_id)
                        # zdrojová pozice bez této zakázky
                        src_ids = [p.zakazka_id for p in qs if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(pozice_id=pozice_id, zakazka_id=zid, poradi=idx)
                            for idx, zid in enumerate(src_ids, start=1)
                        ])
                        # cílová pozice: vlož na začátek (bez duplicit)
                        dst_ids = [zakazka_id] + [p.zakazka_id for p in dst_orders if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=target_pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(pozice_id=target_pozice_id, zakazka_id=zid, poradi=idx)
                            for idx, zid in enumerate(dst_ids, start=1)
                        ])

                if not moved_between_positions:
                    # stávající logika přeuspořádání uvnitř pozice
                    if move in ('up', 'down'):
                        n = len(qs)
                        cur_idx = next((i for i, p in enumerate(qs) if p.zakazka_id == zakazka_id), None)
                        if cur_idx is None:
                            poradi = n + 1  # neexistuje -> vlož na konec
                        else:
                            if move == 'up' and cur_idx > 0:
                                poradi = cur_idx  # posun o 1 nahoru
                            elif move == 'down' and cur_idx < n - 1:
                                poradi = cur_idx + 2  # posun o 1 dolů
                            else:
                                poradi = cur_idx + 1  # bez změny (okraj)

                    PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).update(poradi=F('poradi') + 1000)

                    qs_others = [p for p in qs if p.zakazka_id != zakazka_id]
                    count = len(qs_others)
                    desired = poradi if poradi and poradi > 0 else (count + 1)
                    if desired > count + 1:
                        desired = count + 1
                    if desired < 1:
                        desired = 1

                    new_order = []
                    inserted = False
                    for idx, p in enumerate(qs_others, start=1):
                        if not inserted and idx == desired:
                            new_order.append(('CURRENT', zakazka_id))
                            inserted = True
                        new_order.append((p.pk, p.zakazka_id))
                    if not inserted:
                        new_order.append(('CURRENT', zakazka_id))

                    pos = 1
                    for pk, z_id in new_order:
                        if pk == 'CURRENT':
                            PoziceZakazkaOrder.objects.update_or_create(
                                pozice_id=pozice_id,
                                zakazka_id=zakazka_id,
                                defaults={'poradi': pos}
                            )
                        else:
                            PoziceZakazkaOrder.objects.filter(pk=pk).update(poradi=pos)
                        pos += 1

            messages.success(request, "Pořadí bylo upraveno.")
            return redirect('dashboard_bedny_k_navezeni')

        # I při neplatném POSTu přesměruj zpět (PRG), ať se neodesílá formulář znovu po refreshi
        return redirect('dashboard_bedny_k_navezeni')
    
    context = {
        'groups': _get_bedny_k_navezeni_groups(),
        'db_table': 'bedny_k_navezeni',
        'current_time': timezone.now(),
        'pozice_kody': pozice_kody,
        'prev_map': prev_map,
        'next_map': next_map,
    }

    if request.htmx:
        return render(request, "orders/partials/dashboard_bedny_k_navezeni_content.html", context)
    return render(request, 'orders/dashboard_bedny_k_navezeni.html', context)


@login_required
def dashboard_bedny_k_navezeni_poznamka_view(request):
    """HTMX endpoint pro inline úpravu poznámky k navezení pro zakázku v pozici."""
    pozice_id_raw = request.GET.get('pozice_id') or request.POST.get('pozice_id')
    zakazka_id_raw = request.GET.get('zakazka_id') or request.POST.get('zakazka_id')
    mode = (request.GET.get('mode') or request.POST.get('mode') or '').lower()

    try:
        pozice_id = int(pozice_id_raw)
        zakazka_id = int(zakazka_id_raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Neplatné ID pozice nebo zakázky.")

    qs = Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id)
    if not qs.exists():
        return HttpResponseBadRequest("Nebyla nalezena kombinace pozice a zakázky.")

    poznamka = qs.values_list('poznamka_k_navezeni', flat=True).first() or ''

    if request.method == 'POST':
        poznamka = request.POST.get('poznamka') or ''
        with transaction.atomic():
            target_bedna = qs.order_by('cislo_bedny', 'id').first()
            if target_bedna:
                target_bedna.poznamka_k_navezeni = (poznamka or None)
                target_bedna.save(update_fields=['poznamka_k_navezeni'])
        mode = 'display'

    context = {
        'mode': 'form' if mode == 'form' and request.method == 'GET' else 'display',
        'pozice_id': pozice_id,
        'zakazka_id': zakazka_id,
        'poznamka': poznamka,
        'target_id': f"note-{pozice_id}-{zakazka_id}",
    }
    return render(request, "orders/partials/dashboard_bedny_k_navezeni_note.html", context)


@login_required
def dashboard_bedny_k_navezeni_pdf_view(request):
    """PDF verze přehledu beden k navezení (WeasyPrint)."""
    context = {
        'groups': _get_bedny_k_navezeni_groups(),
        'current_time': timezone.now(),
    }
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    html_string = render_to_string('orders/print/bedny_k_navezeni_print.html', context)
    pdf_bytes = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="bedny_k_navezeni.pdf"'
    return response


@login_required
def protokol_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro PDF protokol kamionu (výdej)."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)

    zakazky = kamion.zakazky_vydej.all().order_by('id')
    base_url = getattr(settings, 'WEASYPRINT_BASEURL', None)
    if not base_url:
        base_url = request.build_absolute_uri('/') if request else None

    static_url = settings.STATIC_URL
    if base_url and base_url.startswith('file:'):
        if not static_url.startswith('http://') and not static_url.startswith('https://'):
            static_url = base_url.rstrip('/') + '/'

    context = {
        "kamion": kamion,
        "zakazky": zakazky,
        "generated_at": timezone.now(),
        "issued_by": request.user.get_full_name() if request.user.is_authenticated else "",
        "pdf_static_url": static_url,
    }

    html_string = render_to_string(f"orders/protokol_kamion_vydej_{kamion.zakaznik.zkratka.lower()}.html", context)

    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk protokolu kamionu výdej.")

    pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=stylesheets)

    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"protokol_{cislo_dl}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response['Content-Disposition'] = (
        f"inline; filename=\"{filename}\"; filename*=UTF-8''{filename}"
    )
    response['Content-Length'] = str(len(pdf_bytes))
    return response


@login_required
def dodaci_list_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro dodací list kamionu výdej."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)
    zakaznik_zkratka = getattr(kamion.zakaznik, 'zkratka', None)
    if not zakaznik_zkratka:
        return HttpResponse("Kamion nemá zkratku zákazníka", status=400)

    html_path = f"orders/dodaci_list_{zakaznik_zkratka.lower()}.html"
    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"dodaci_list_{cislo_dl}.pdf"

    response = utilita_tisk_dl_a_proforma_faktury(None, request, kamion, html_path, filename)
    return response


@login_required
def proforma_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro proforma fakturu kamionu výdej."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)
    zakaznik_zkratka = getattr(kamion.zakaznik, 'zkratka', None)
    if not zakaznik_zkratka:
        return HttpResponse("Kamion nemá zkratku zákazníka", status=400)

    if kamion.zakaznik.proforma_po_bednach:
        html_path = "orders/proforma_faktura_po_bednach.html"
    else:
        html_path = "orders/proforma_faktura_po_zakazkach.html"

    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"proforma_faktura_{cislo_dl}.pdf"

    response = utilita_tisk_dl_a_proforma_faktury(None, request, kamion, html_path, filename)
    return response


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