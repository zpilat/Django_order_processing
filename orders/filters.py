from django.contrib.admin import SimpleListFilter
from .models import Zakazka, Bedna, Zakaznik, Kamion, TypHlavy
from .choices import StavBednyChoice, TryskaniChoice, RovnaniChoice, PrioritaChoice
from django.db.models import Exists, OuterRef

class DynamicTitleFilter(SimpleListFilter):
    """
    Dynamický filtr, který mění svůj název podle vybraného filtru.
    Používá se pro filtry, které mají více možností a jejich název se mění podle vybraného filtru.
    Parametr vse se zobrazuje, pokud vybrán žádný filtr.
    """
    title = "Filtr"
    vse = 'Vše'

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        label = getattr(self, "label_dict", {}).get(self.value(), self.value()) if self.value() else self.vse
        self.title = f"{self.title}: {label}"


class StavBednyFilter(DynamicTitleFilter):
    """
    Filtrovat bedny podle stavu.
    """
    title = "Stav bedny"
    parameter_name = "stav_bedny_vlastni"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'NEZAKALENO': "Nezakaleno",
            **dict(StavBednyChoice.choices),
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
        elif value == 'NEZAKALENO':
            return queryset.filter(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.NAVEZENO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.DO_ZPRACOVANI])
        return queryset.filter(stav_bedny=value)


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
    Filtrovat zakázky podle skupiny tepelného zpracování.
    """
    title = "Skupina TZ"
    parameter_name = "skupina"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            '1': 'TZ 1',
            '2': 'TZ 2',
            '3': 'TZ 3',
            '4': 'TZ 4',
            '5': 'TZ 5',
            'ostatni': 'Ostatní'
            }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()        

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        elif value == 'ostatni':
            return queryset.exclude(zakazka__predpis__skupina__in=[1, 2, 3, 4, 5])
        else:
            try:
                return queryset.filter(zakazka__predpis__skupina=int(value))
            except (ValueError, TypeError):
                return queryset.none()


class ZakaznikBednyFilter(DynamicTitleFilter):
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
            return queryset.filter(zakaznik=zakaznik)
        except Zakaznik.DoesNotExist:
            return queryset.none()        
        

class PrijemVydejFilter(DynamicTitleFilter):
    """
    Filtrovat kamiony podle typu (příjem - vše, příjem - skladm, výdej).
    """
    title = "Typ kamionu"
    parameter_name = "prijem_vydej"

    def __init__(self, request, params, model, model_admin):
        self.label_dict = {
            'PS': 'Příjem - Se zakázkami skladem',
            'PV': 'Příjem - Vše',
            'V': 'Výdej'
        }
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return self.label_dict.items()    

    def queryset(self, request, queryset):
        value = self.value()      
        if not value:
            return queryset
        elif value == 'PV':
            return queryset.filter(prijem_vydej='P')
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