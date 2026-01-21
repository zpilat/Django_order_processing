from django.contrib.admin import SimpleListFilter
from django.db.models import Exists, OuterRef, Sum
from django.db.models import Q
from django.utils import timezone

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from .models import Zakazka, Bedna, Zakaznik, Kamion, TypHlavy, Predpis, Odberatel
from .choices import (
    StavBednyChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice, PrijemVydejChoice, SklademZakazkyChoice,
    STAV_BEDNY_ROZPRACOVANOST, STAV_BEDNY_SKLADEM,
)

class DynamicTitleFilter(SimpleListFilter):
    """
    Dynamický filtr, který mění svůj název podle vybraného filtru.
    Používá se pro filtry, které mají více možností a jejich název se mění podle vybraného filtru.
    Parametr vse se zobrazuje, pokud vybrán žádný filtr.
    """
    title = "Filtr"
    vse = 'Vše'
    collapsible = True

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        label_dict = getattr(self, "label_dict", {})
        value = self.value()
        label = label_dict.get(value, value) if value else self.vse
        self.title = f"{self.title}: {label}"

# filtry pro Bedny

class StavBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu.
    Bedny po exspiraci - bedny, které jsou skladem déle než 28 dní.
    """
    title = "Stav bedny"
    parameter_name = "stav_bedny"
    vse = 'Vše skladem'

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(StavBednyChoice.choices)}
        self.label_dict['RO'] = 'Rozpracováno'
        self.label_dict['PE'] = 'Po exspiraci'
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def choices(self, changelist):
        """
        Přepíše defaultní text první volby (All) na hodnotu z `self.vse`.
        """
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': self.vse,  # "Vše skladem"
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(stav_bedny__in=STAV_BEDNY_SKLADEM)
        elif value == 'RO':
            return queryset.filter(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST)
        elif value == 'PE':
            expiration_date = timezone.localdate() - timedelta(days=28)
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO).filter(zakazka__kamion_prijem__datum__lt=expiration_date)
        return queryset.filter(stav_bedny=value)


class DelkaFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle délky.
    """
    title = "Délka"
    parameter_name = "delka"

    def __init__(self, request, params, model, model_admin):
        """
        Využije ostatní aktivní filtry (kromě délky) pro získání dostupných délek a celkových hmotností a množství a
        počtu beden pro zobrazení v lookupech.
        """
        self.label_dict = {}
        # Pokud není aktivován filtr stav_bedny nebo není vybrán "Neprijato" či "Prijato", filtr DelkaFilter se neaplikuje
        stav_bedny = request.GET.get('stav_bedny', None)
        if not stav_bedny or stav_bedny not in (StavBednyChoice.NEPRIJATO, StavBednyChoice.PRIJATO):
            return
        
        # Základní queryset pro přijaté bedny, vyfiltrovaný dle filtru stav_bedny v requestu
        base_qs = model.objects.filter(stav_bedny=stav_bedny)
        
        # Aplikace ostatních filtrů z request.GET (kromě filtru délky)
        other_filters = {k: v for k, v in request.GET.items() if k != self.parameter_name}
        
        # Mapování URL parametrů na databázová pole
        field_map = {
            'zakaznik': 'zakazka__kamion_prijem__zakaznik__zkratka',
            'tryskani': 'tryskat',
            'rovnani': 'rovnat',
            'celozavit': 'zakazka__celozavit',
            'typ_hlavy': 'zakazka__typ_hlavy__nazev',
            'priorita_bedny': 'zakazka__priorita',
            'pozastaveno': 'pozastaveno',
            'skupina': 'zakazka__predpis__skupina',
        }
        
        # Sestavení filter_kwargs z ostatních aktivních filtrů
        filter_kwargs = {}
        for param, db_field in field_map.items():
            raw_val = other_filters.get(param)
            if raw_val in (None, ''):
                continue
            
            # Konverze typů pro vybraná pole
            if param in ('pozastaveno', 'celozavit'):
                if raw_val == 'True':
                    val = True
                elif raw_val == 'False':
                    val = False
                else:
                    continue
            elif param == 'skupina':
                try:
                    val = int(raw_val)
                except (TypeError, ValueError):
                    continue
            else:
                val = raw_val
            
            filter_kwargs[db_field] = val
        
        # Aplikace filtrů na queryset
        query = base_qs.filter(**filter_kwargs) if filter_kwargs else base_qs

        # Agregační dotaz pro délky s celkovou hmotností a množstvím
        query_list = list(
            query.values('zakazka__delka')
            .exclude(zakazka__delka__isnull=True)
            .annotate(celkova_hmotnost=Sum('hmotnost'), celkove_mnozstvi=Sum('mnozstvi'), pocet_beden=Sum(1))
            .order_by('zakazka__delka')
        )
        
        # Uložení dostupných délek (Decimal pro přesné porovnání)
        self.available_delky = {
            Decimal(str(row['zakazka__delka']))
            for row in query_list
            if row['zakazka__delka'] is not None
        }
        
        # Kontrola, zda je aktuálně vybraná délka stále dostupná
        current_value = params.get(self.parameter_name)
        # Pokud je hodnota list/tuple, vezmi první prvek
        if isinstance(current_value, (list, tuple)):
            current_value = current_value[0] if current_value else None
        if current_value not in (None, ''):
            try:
                selected_delka_dec = Decimal(str(current_value))
                if selected_delka_dec not in self.available_delky:
                    # Odstranění neplatné hodnoty z params
                    params.pop(self.parameter_name, None)
            except (InvalidOperation, ValueError, TypeError):
                params.pop(self.parameter_name, None)
        
        # Sestavení label_dict podle dostupnosti množství a hmnotnosti
        all_have_mnozstvi = bool(query_list) and all(row['celkove_mnozstvi'] for row in query_list)
        all_have_hmotnost = bool(query_list) and all(row['celkova_hmotnost'] for row in query_list)

        if all_have_mnozstvi and all_have_hmotnost:
            self.label_dict = {
                row['zakazka__delka']: f"{int(row['zakazka__delka'])} ({row['celkova_hmotnost']:.0f} kg | {row['celkove_mnozstvi']:.0f} ks | #{row['pocet_beden']})"
                for row in query_list
            }
        elif all_have_hmotnost:
            self.label_dict = {
                row['zakazka__delka']: f"{int(row['zakazka__delka'])} ({row['celkova_hmotnost']:.0f} kg | #{row['pocet_beden']})"
                for row in query_list
            }
        elif all_have_mnozstvi:
            self.label_dict = {
                row['zakazka__delka']: f"{int(row['zakazka__delka'])} ({row['celkove_mnozstvi']:.0f} ks | #{row['pocet_beden']})"
                for row in query_list
            }
        else:
            self.label_dict = {
                row['zakazka__delka']: f"{int(row['zakazka__delka'])} (#{row['pocet_beden']})"
                for row in query_list
            }
        
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(zakazka__delka=value)
    

class TryskaniFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu tryskání.
    """
    title = "Tryskání"
    parameter_name = "tryskani"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(TryskaniChoice.choices)}
        self.label_dict.pop(TryskaniChoice.CISTA)  # Odstraní čistá z možností filtru
        self.label_dict.pop(TryskaniChoice.OTRYSKANA)  # Odstraní otryskaná z možností filtru
        self.label_dict[TryskaniChoice.NEZADANO] = 'Nezadáno'
        self.label_dict['hotovo'] = 'Čistá & Otryskaná'
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return [(k, v) for k, v in self.label_dict.items()]

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        if value == 'hotovo':
            return queryset.filter(tryskat__in=(TryskaniChoice.OTRYSKANA, TryskaniChoice.CISTA))
        return queryset.filter(tryskat=value)
    

class RovnaniFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu rovnání.
    """
    title = "Rovnání"
    parameter_name = "rovnani"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(RovnaniChoice.choices)}
        self.label_dict.pop(RovnaniChoice.ROVNA)  # Odstraní rovná z možností filtru
        self.label_dict.pop(RovnaniChoice.VYROVNANA)  # Odstraní vyrovnaná z možností filtru
        self.label_dict[RovnaniChoice.NEZADANO] = 'Nezadáno'
        self.label_dict['k_vyrovnani'] = 'Křivá & Rovná se'
        self.label_dict['hotovo'] = 'Rovná & Vyrovnaná'
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return [(k, v) for k, v in self.label_dict.items()]

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        if value == 'k_vyrovnani':
            return queryset.filter(rovnat__in=(RovnaniChoice.KRIVA, RovnaniChoice.ROVNA_SE))
        if value == 'hotovo':
            return queryset.filter(rovnat__in=(RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA))
        return queryset.filter(rovnat=value)


class PrioritaBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle priority.
    """
    title = "Priorita"
    parameter_name = "priorita_bedny"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(PrioritaChoice.choices)}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        return queryset.filter(zakazka__priorita=value)
    

class PozastavenoFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle toho, jestli jsou pozastavené nebo uvolněné.
    """
    title = "Pozastaveno"
    parameter_name = "pozastaveno"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
        'True': "Ano",            
        'False': "Ne",
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'True':
            return queryset.filter(pozastaveno=True)
        elif value == 'False':
            return queryset.filter(pozastaveno=False)
        return queryset.filter()


class SkupinaFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle skupiny tepelného zpracování.
    """
    title = "Skupina TZ"
    parameter_name = "skupina"

    def __init__(self, request, params, model, model_admin):
        """
        Pro zobrazení vždy vrátí pouze skupiny tepelného zpracování zakázek, které jsou skladem.
        Pokud je navíc vybrán zákazník, filtruje se ještě podle skupin tepelného zpracování zakázek tohoto zákazníka.
        Pokud je navíc vybrán stav bedny, filtruje se podle skupin tepelného zpracování zakázek, které mají bedny v tomto stavu.
        """
        zakaznik = request.GET.get('zakaznik', None)
        stav_bedny = request.GET.get('stav_bedny', None)

        query = Predpis.objects.filter(aktivni=True)

        query = query.filter(zakazky__expedovano=False)

        if zakaznik:
            query = query.filter(zakazky__kamion_prijem__zakaznik__zkratka=zakaznik)
        if stav_bedny and stav_bedny not in ('RO', 'PE'):
            query = query.filter(zakazky__bedny__stav_bedny=stav_bedny)

        # Vytvoří slovník s unikátními názvy skupin pro zobrazení ve filtru ve správném formátu
        label_dict = dict(query.values_list('skupina', 'skupina').distinct().order_by('skupina'))
        self.label_dict = {k: f'SK{v}' for k, v in label_dict.items()}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()       

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            return queryset.filter(zakazka__predpis__skupina=int(value))
        except (ValueError, TypeError):
            return queryset.none()


class ZakaznikBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle zákazníka.
    """
    title = "Zákazník"
    parameter_name = "zakaznik"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(Zakaznik.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()           

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            zakaznik = Zakaznik.objects.get(zkratka=value)
            return queryset.filter(zakazka__kamion_prijem__zakaznik=zakaznik)
        except Zakaznik.DoesNotExist:
            return queryset.none()        


class TypHlavyBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle typu hlavy.
    """
    title = "Typ hlavy"
    parameter_name = "typ_hlavy"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(TypHlavy.objects.values_list('nazev', 'nazev').order_by('nazev'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()           

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            typ_hlavy = TypHlavy.objects.get(nazev=value)
            return queryset.filter(zakazka__typ_hlavy=typ_hlavy)
        except TypHlavy.DoesNotExist:
            return queryset.none()
        

class CelozavitBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle druhu závitu.
    """
    title = "Celozávit"
    parameter_name = "celozavit"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'True': 'Ano',
            'False': 'Ne'
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        elif value == 'True':
            return queryset.filter(zakazka__celozavit=True)
        elif value == 'False':
            return queryset.filter(zakazka__celozavit=False)
        return queryset.none()
    

# filtry pro Zakázky

class PrioritaZakazkyFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle priority.
    """
    title = "Priorita"
    parameter_name = "priorita_zakazky"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(PrioritaChoice.choices)}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        return queryset.filter(priorita=value)
    

class OdberatelFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle odběratele. Pokud je vybrán odběratel, 
    filtruje se podle tohoto odběratele + všechny zakázky, které nemají odběratele (null).
    """
    title = "Odběratel"
    parameter_name = "odberatel"

    def __init__(self, request, params, model, model_admin):
        label_list = Odberatel.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka')
        self.label_dict = {key: f"{value} + bez odběratele" for key, value in label_list}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            odberatel = Odberatel.objects.get(zkratka=value)
            return queryset.filter(Q(odberatel=odberatel) | Q(odberatel__isnull=True))
        except Odberatel.DoesNotExist:
            return queryset.none()


class SklademZakazkaFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle stavu expedice.
    """
    title = "Skladem"
    vse = 'Vše skladem'
    parameter_name = "skladem"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(SklademZakazkyChoice.choices)}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def choices(self, changelist):
        """
        Přepíše defaultní text první volby (All) na hodnotu z `self.vse`.
        """
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': self.vse,  # "Vše skladem"
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }    

    def queryset(self, request, queryset):
        value = self.value()
        # Subquery pro kontrolu, zda zakázka má nějakou bednu ve stavu NEPRIJATO
        neprijato_subquery = Bedna.objects.filter(
            zakazka=OuterRef('pk'),
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        # Subquery pro kontrolu, zda zakázka má aspoň jednu bednu s jiným stavem než NEPRIJATO
        non_neprijato_subquery = Bedna.objects.filter(
            zakazka=OuterRef('pk'),
        ).exclude(stav_bedny=StavBednyChoice.NEPRIJATO)

        if value is None:
            # "Vše skladem": neexpedováno AND existuje aspoň jedna bedna, která není NEPRIJATO.
            # Tím se automaticky vyřadí expedované, bez beden i zakázky, kde jsou všechny bedny NEPRIJATO.
            return queryset.filter(
                expedovano=False,
            ).filter(
                Exists(non_neprijato_subquery)
            ).distinct()
        elif value == SklademZakazkyChoice.NEPRIJATO:
            # Zakázky, které mají aspoň jednu bednu ve stavu NEPRIJATO
            return queryset.filter(Exists(neprijato_subquery))
        elif value == SklademZakazkyChoice.BEZ_BEDEN:
            return queryset.filter(bedny__isnull=True)
        elif value == SklademZakazkyChoice.EXPEDOVANO:
            return queryset.filter(expedovano=True)
        elif value == SklademZakazkyChoice.PO_EXSPIRACI:
            expiration_date = timezone.localdate() - timedelta(days=28)
            # Zakázky, které mají alespoň jednu bednu, která není expedována a není ve stavu NEPRIJATO
            # a zároveň datum příjmu kamionu je starší než 28 dní
            return queryset.filter(
                Exists(non_neprijato_subquery),
                expedovano=False,
                kamion_prijem__datum__lt=expiration_date
            ).distinct()
        return queryset
      

class KompletZakazkaFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle rozpracovanosti a kompletnosti.
    """
    title = "Kompletní"
    parameter_name = "komplet"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'kompletni': "Kompletní",
            'k_expedici': "K expedici"
            }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()       

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'kompletni':
            # Vrátí zakázky, jejichž všechny bedny jsou ve stavu K expedici nebo Expedováno
            for zakazka in queryset:
                # Zkontroluje, zda má zakázka nějaké bedny a zda všechny bedny v zakázce jsou ve stavu K expedici nebo Expedováno
                if not zakazka.bedny.exists() or not all(bedna.stav_bedny in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO)
                                                         for bedna in zakazka.bedny.all()):
                    queryset = queryset.exclude(id=zakazka.id)
        elif value == 'k_expedici':
            # Vrátí zakázky, které mají alespoň jednu bednu ve stavu K expedici
            queryset = queryset.filter(bedny__stav_bedny=StavBednyChoice.K_EXPEDICI).distinct()
        return queryset
    

class ZakaznikZakazkyFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle zákazníka.
    """
    title = "Zákazník"
    parameter_name = "zakaznik"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(Zakaznik.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            zakaznik = Zakaznik.objects.get(zkratka=value)
            return queryset.filter(kamion_prijem__zakaznik=zakaznik)
        except Zakaznik.DoesNotExist:
            return queryset.none()
        

class TypHlavyZakazkyFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle typu hlavy.
    """
    title = "Typ hlavy"
    parameter_name = "typ_hlavy"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(TypHlavy.objects.values_list('nazev', 'nazev').order_by('nazev'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            typ_hlavy = TypHlavy.objects.get(nazev=value)
            return queryset.filter(typ_hlavy=typ_hlavy)
        except TypHlavy.DoesNotExist:
            return queryset.none()
        

class CelozavitZakazkyFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle druhu závitu.
    """
    title = "Celozávit"
    parameter_name = "celozavit"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'ano': 'Ano',
            'ne': 'Ne'
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        elif value == 'ano':
            return queryset.filter(celozavit=True)
        elif value == 'ne':
            return queryset.filter(celozavit=False)
        return queryset.none()
    

class OberflacheFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle povrchu.
    """
    title = "Povrch"
    parameter_name = "povrch"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(Zakazka.objects.filter(povrch__isnull=False).values_list('povrch', 'povrch').distinct().order_by('povrch'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(povrch=value)

# filtry pro Kamiony

class ZakaznikKamionuFilter(DynamicTitleFilter):
    """
    Filtrovat kamiony podle zákazníka.
    """
    title = "Zákazník"
    parameter_name = "zakaznik"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(Zakaznik.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            zakaznik = Zakaznik.objects.get(zkratka=value)
            return queryset.filter(zakaznik=zakaznik)
        except Zakaznik.DoesNotExist:
            return queryset.none()        


class PrijemVydejFilter(DynamicTitleFilter):
    """
    Filtrovat kamiony podle typu (příjem - bez zakázek, příjem - se zakázkami skladem, příjem - vyexpedovaný, výdej).
    """
    title = "Typ kamiónu"
    parameter_name = "prijem_vydej"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(PrijemVydejChoice.choices)}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()      
        if not value:
            return queryset
        # PB Bez zakázek - kamion, který je typu příjem a nemá žádné zakázky
        elif value == PrijemVydejChoice.PRIJEM_BEZ_ZAKAZEK:
            return queryset.filter(prijem_vydej='P', zakazky_prijem__isnull=True)
        # PN Nepřijatý - kamion, který obsahuje bedny, ale aspoň jedna bedna je ve stavu StavBednyChoices.NEPRIJATO
        elif value == PrijemVydejChoice.PRIJEM_NEPRIJATY:
            return queryset.filter(prijem_vydej='P', zakazky_prijem__bedny__stav_bedny=StavBednyChoice.NEPRIJATO).distinct()
        # PK Komplet přijatý - kamion, který neobsahuje ani jednu bednu ve stavu StavBednyChoices.NEPRIJATO
    # a alespoň jedna bedna je ve stavu uvedeném ve STAV_BEDNY_SKLADEM.
        elif value == PrijemVydejChoice.PRIJEM_KOMPLET_PRIJATY:
            return queryset.filter(prijem_vydej='P', zakazky_prijem__isnull=False
            ).exclude(zakazky_prijem__bedny__stav_bedny=StavBednyChoice.NEPRIJATO
            ).filter(zakazky_prijem__bedny__stav_bedny__in=STAV_BEDNY_SKLADEM).distinct()  
        # PV Vyexpedovaný - kamion, který má všechny zakázky ve stavu expedovano=True      
        elif value == PrijemVydejChoice.PRIJEM_VYEXPEDOVANY:
            return queryset.filter(prijem_vydej='P', zakazky_prijem__isnull=False
            ).exclude(zakazky_prijem__expedovano=False).distinct()
        # V Výdej - kamion, který je typu výdej
        elif value == PrijemVydejChoice.VYDEJ:
            return queryset.filter(prijem_vydej='V')
        return queryset.none()    
          
# filtry pro Předpisy

class AktivniPredpisFilter(DynamicTitleFilter):
    """
    Filtrovat předpisy - jestli jsou aktivní nebo ne.
    """
    title = "Aktivní předpis"
    vse = 'Vše aktivní'
    parameter_name = "aktivni_predpis"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {'ne': "Neaktivní"}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    
    
    def choices(self, changelist):
        """
        Přepíše defaultní text první volby (All) na hodnotu z `self.vse`.
        """
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': self.vse,  # "Vše skladem"
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }    

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'ne':
            return queryset.filter(aktivni=False)
        return queryset.filter(aktivni=True)    

class ZakaznikPredpisFilter(DynamicTitleFilter):
    """
    Filtrovat předpisy podle zákazníka.
    """
    title = "Zákazník"
    parameter_name = "zakaznik"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = dict(Zakaznik.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            zakaznik = Zakaznik.objects.get(zkratka=value)
            return queryset.filter(zakaznik=zakaznik)
        except Zakaznik.DoesNotExist:
            return queryset.none()