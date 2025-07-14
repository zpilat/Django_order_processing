from django.db import models
from django.utils.translation import gettext_lazy as _

class StavBednyChoice(models.TextChoices):
    PRIJATO = 'PR', 'Přijato'
    K_NAVEZENI = 'KN', 'K navezení'
    NAVEZENO = 'NA', 'Navezeno'
    DO_ZPRACOVANI = 'DZ', 'Do zpracování'
    ZAKALENO = 'ZA', 'Zakaleno'
    ZKONTROLOVANO = 'ZK', 'Zkontrolováno'
    K_EXPEDICI = 'KE', 'K expedici'
    EXPEDOVANO = 'EX', 'Expedováno'

class RovnaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    ROVNA = 'RO', 'Rovná'
    KRIVA = 'KR', 'Křivá'
    VYROVNANA = 'VY', 'Vyrovnaná'

class TryskaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    CISTA = 'CI', 'Čistá'
    SPINAVA = 'SP', 'Špinavá'
    OTRYSKANA = 'OT', 'Otryskaná'

class PrioritaChoice(models.TextChoices):
    VYSOKA = 'P1', 'P1'
    STREDNI = 'P2', 'P2'
    NIZKA = 'P3', '-'

class KamionChoice(models.TextChoices):
    PRIJEM = 'P', 'Přijem'
    VYDEJ = 'V', 'Výdej'