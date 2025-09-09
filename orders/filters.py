from django.contrib.admin import SimpleListFilter
from django.db.models import Exists, OuterRef, Sum
from django.db.models import Q
from django.utils import timezone

from datetime import timedelta

from .models import Zakazka, Bedna, Zakaznik, Kamion, TypHlavy, Predpis, Odberatel
from .choices import StavBednyChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice

stav_bedny_bez_expedice = [stavbedny for stavbedny in StavBednyChoice if stavbedny != StavBednyChoice.EXPEDOVANO]

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


class StavBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu.
    Bedny po expiraci - bedny, které jsou skladem déle než 28 dní.
    """
    title = "Stav bedny"
    parameter_name = "stav_bedny"
    vse = 'Vše skladem'

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(StavBednyChoice.choices)}
        self.label_dict['PE'] = 'Bedny po expiraci'
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
        if value == 'PE':
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
        Pokud není vybrán stav bedny nebo zákazník, nejsou zobrazeny v nabídce žádné délky.
        Jinak v nabídce délky, které mají bedny v tomto stavu, pro daného zákazníka a případné další filtry.
        """
        stav_bedny = request.GET.get('stav_bedny')
        zakaznik = request.GET.get('zakaznik')

        self.label_dict = {}
        if stav_bedny and zakaznik:
            query = Bedna.objects.filter(
                stav_bedny=stav_bedny,
                zakazka__kamion_prijem__zakaznik__zkratka=zakaznik
            )

            # Další možné filtry z requestu
            filter_fields = {
                'skupina':      'zakazka__predpis__skupina',
                'tryskani':     'tryskat',
                'rovnani':      'rovnat',
                'celozavit':    'zakazka__celozavit',
                'typ_hlavy':    'zakazka__typ_hlavy',
                'priorita_bedny': 'zakazka__priorita'
            }

            filter_kwargs = {
                db_field: request.GET.get(param)
                for param, db_field in filter_fields.items()
                if request.GET.get(param) not in (None, '')
            }
            if filter_kwargs:
                query = query.filter(**filter_kwargs)

            if stav_bedny != StavBednyChoice.EXPEDOVANO:
                # Sestavení slovníku délka: popisek
                query_list = (
                    query.values('zakazka__delka')
                    .annotate(celkova_hmotnost=Sum('hmotnost'))
                    .order_by('zakazka__delka')
                )
                self.label_dict = {
                    data['zakazka__delka']: f"{int(data['zakazka__delka'])} <{data['celkova_hmotnost']:.0f} kg>"
                    for data in query_list
                }
            else:
                self.label_dict = {delka: int(delka) for delka in query.values_list('zakazka__delka', flat=True).distinct().order_by('zakazka__delka')}

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
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        return queryset.filter(tryskat=value)
    

class RovnaniFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu rovnání.
    """
    title = "Rovnání"
    parameter_name = "rovnani"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {**dict(RovnaniChoice.choices)}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
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
    

class UvolnenoFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle toho, jestli jsou pozastavené nebo uvolněné.
    """
    title = "Uvolněno"
    parameter_name = "uvolneno"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
        'uvolneno': "Uvolněno",
        'pozastaveno': "Pozastaveno",
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'pozastaveno':
            return queryset.filter(pozastaveno=True)
        elif value == 'uvolneno':
            return queryset.filter(pozastaveno=False)
        return queryset.filter()


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
        self.label_dict = dict(Odberatel.objects.values_list('zkratka', 'zkraceny_nazev').order_by('zkratka'))
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()           

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            odberatel = Odberatel.objects.get(zkratka=value)
            return queryset.filter(Q(kamion_prijem__odberatel=odberatel) | Q(kamion_prijem__odberatel__isnull=True))
        except Odberatel.DoesNotExist:
            return queryset.none()


class ExpedovanaZakazkaFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle stavu expedice.
    """
    title = "Skladem"
    vse = 'Vše skladem'
    parameter_name = "skladem"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {'expedovano': "Expedováno"}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(expedovano=False)
        elif value == 'expedovano':
            return queryset.filter(expedovano=True)
        return queryset


class AktivniPredpisFilter(DynamicTitleFilter):
    """
    Filtrovat zakázky podle aktivního předpisu.
    """
    title = "Aktivní předpis"
    vse = 'Vše aktivní'
    parameter_name = "aktivni_predpis"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {'ne': "Ne"}
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'ne':
            return queryset.filter(aktivni=False)
        return queryset.filter(aktivni=True)
    

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
    

class SkupinaFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle skupiny tepelného zpracování.
    """
    title = "Skupina TZ"
    parameter_name = "skupina"

    def __init__(self, request, params, model, model_admin):
        """
        Pokud je vybrán zákazník, filtruje se podle skupin tepelného zpracování zakázek tohoto zákazníka.
        Pokud je vybrán stav bedny, filtruje se podle skupin tepelného zpracování zakázek, které mají bedny v tomto stavu.
        Pokud není vybrán stav bedny, vrátí se všechny skupiny tepelného zpracování zakázek, které nejsou expedovány.
        """
        zakaznik = request.GET.get('zakaznik', None)
        stav_bedny = request.GET.get('stav_bedny', None)

        query = Predpis.objects.filter(aktivni=True)

        if zakaznik:
            query = query.filter(zakazky__kamion_prijem__zakaznik__zkratka=zakaznik)
        if not stav_bedny:
                query = query.filter(zakazky__bedny__stav_bedny__in=stav_bedny_bez_expedice)
        else:
            query = query.filter(zakazky__bedny__stav_bedny=stav_bedny)

        # Vytvoří slovník s unikátními názvy skupin pro zobrazení ve filtru ve správném formátu
        label_dict = dict(query.values_list('skupina', 'skupina').distinct().order_by('skupina'))
        self.label_dict = {k: f'TZ {v}' for k, v in label_dict.items()}
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
    title = "Typ kamionu"
    parameter_name = "prijem_vydej"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'PB': 'Příjem - Bez zakázek',
            'PS': 'Příjem - Se zakázkami skladem',
            'PV': 'Příjem - Vyexpedovaný',            
            'V': 'Výdej',
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()      
        if not value:
            return queryset
        elif value == 'PB':
            return queryset.filter(prijem_vydej='P', zakazky_prijem__isnull=True)
        elif value == 'PV':
            zakazka_qs = Zakazka.objects.filter(kamion_prijem=OuterRef('pk'), expedovano=False)
            return queryset.filter(prijem_vydej='P', zakazky_prijem__isnull=False).annotate(ma_neexpedovanou=Exists(zakazka_qs)
            ).filter(ma_neexpedovanou=False).distinct()
        elif value == 'PS':
            zakazka_qs = Zakazka.objects.filter(kamion_prijem=OuterRef('pk'), expedovano=False)
            return queryset.filter(prijem_vydej='P',).annotate(ma_neexpedovanou=Exists(zakazka_qs)
            ).filter(ma_neexpedovanou=True)
        elif value == 'V':
            return queryset.filter(prijem_vydej='V')
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
    

class CelozavitBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle druhu závitu.
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
            return queryset.filter(zakazka__celozavit=True)
        elif value == 'ne':
            return queryset.filter(zakazka__celozavit=False)
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