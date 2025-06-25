from django.contrib import admin
from .models import StavBednyChoice, Zakazka, Bedna

class StavBednyFilter(admin.SimpleListFilter):
    """
    Filtrovat bedny podle stavu.
    """
    title = "Stav bedny"
    parameter_name = "stav_bedny_vlastni"

    def lookups(self, request, model_admin):
        self.label_dict = {
            'NEZAKALENO': "Nezakaleno",
            **dict(StavBednyChoice.choices),
        }
        return self.label_dict.items()

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            self.title = "Stav bedny: Skladem"
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
        elif value == 'NEZAKALENO':
            self.title = "Stav bedny: Nezakaleno"
            return queryset.filter(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.NAVEZENO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.DO_ZPRACOVANI])

        self.title = f"Stav bedny: {self.label_dict.get(value, value)}"
        return queryset.filter(stav_bedny=value)
        

class ExpedovanaZakazkaFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle stavu expedice.
    """
    title = "Skladem"
    parameter_name = "skladem"

    def lookups(self, request, model_admin):
        return (
            ('expedovano', 'Expedováno'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(expedovano=False)
        elif value == 'expedovano':
            return queryset.filter(expedovano=True)
        return queryset


class AktivniPredpisFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle aktivního předpisu.
    """
    title = "Aktivní předpis"
    parameter_name = "aktivni_predpis"

    def lookups(self, request, model_admin):
        return (
            ('ne', 'Ne'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'ne':
            return queryset.filter(aktivni=False)
        return queryset.filter(aktivni=True)
    

class KompletZakazkaFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle rozpracovanosti a kompletnosti.
    """
    title = "Kompletní"
    parameter_name = "komplet"

    def lookups(self, request, model_admin):
        self.label_dict = {
            'kompletni': "Kompletní",
            'k_expedici': "K expedici",
        }
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
        self.title = f"Kompletní: {self.label_dict.get(value, value)}" if value else "Kompletní: Vše"
        return queryset