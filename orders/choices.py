from django.db import models
from django.utils.translation import gettext_lazy as _

class StavBednyChoice(models.TextChoices):
    NEPRIJATO = 'NE', 'Nepřijato'
    PRIJATO = 'PR', 'Přijato'
    K_NAVEZENI = 'KN', 'K navezení'
    NAVEZENO = 'NA', 'Navezeno'
    DO_ZPRACOVANI = 'DZ', 'Do zpracování'
    ZAKALENO = 'ZA', 'Zakaleno'
    ZKONTROLOVANO = 'ZK', 'Zkontrolováno'
    K_EXPEDICI = 'KE', 'K expedici'
    EXPEDOVANO = 'EX', 'Expedováno'

STAV_BEDNY_SKLADEM = [
    stavbedny for stavbedny in StavBednyChoice if stavbedny not in (StavBednyChoice.NEPRIJATO, StavBednyChoice.EXPEDOVANO)
]

STAV_BEDNY_ROZPRACOVANOST = [
    StavBednyChoice.NAVEZENO,
    StavBednyChoice.DO_ZPRACOVANI,
    StavBednyChoice.ZAKALENO,
    StavBednyChoice.ZKONTROLOVANO,
]

STAV_BEDNY_PRO_NAVEZENI = [
    StavBednyChoice.PRIJATO,
    StavBednyChoice.K_NAVEZENI,
    StavBednyChoice.NAVEZENO,
]

class RovnaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    ROVNA = 'RO', 'Rovná'
    KRIVA = 'KR', 'Křivá'
    ROVNA_SE = 'RS', 'Rovná se'
    VYROVNANA = 'VY', 'Vyrovnaná'

class TryskaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    CISTA = 'CI', 'Čistá'
    SPINAVA = 'SP', 'Špinavá'
    OTRYSKANA = 'OT', 'Otryskaná'

class PrioritaChoice(models.TextChoices):
    VYSOKA = 'P1', 'P1'
    STREDNI = 'P2', 'P2'
    NIZKA = 'P3', '--'

class KamionChoice(models.TextChoices):
    PRIJEM = 'P', 'Přijem'
    VYDEJ = 'V', 'Výdej'

class AlphabetChoice(models.TextChoices):
    A = 'A', 'A'
    B = 'B', 'B'
    C = 'C', 'C'
    D = 'D', 'D'
    E = 'E', 'E'
    F = 'F', 'F'
    G = 'G', 'G'
    H = 'H', 'H'
    I = 'I', 'I'
    J = 'J', 'J'
    K = 'K', 'K'
    L = 'L', 'L'
    M = 'M', 'M'
    N = 'N', 'N'
    O = 'O', 'O'
    P = 'P', 'P'
    Q = 'Q', 'Q'
    R = 'R', 'R'
    S = 'S', 'S'
    T = 'T', 'T'
    U = 'U', 'U'
    V = 'V', 'V'
    W = 'W', 'W'
    X = 'X', 'X'
    Y = 'Y', 'Y'
    Z = 'Z', 'Z'

class PrijemVydejChoice(models.TextChoices):
    PRIJEM_BEZ_ZAKAZEK = 'PB', 'Příjem - Bez zakázek'
    PRIJEM_NEPRIJATY = 'PN', 'Příjem - Nepřijatý'
    PRIJEM_KOMPLET_PRIJATY = 'PK', 'Příjem - Komplet přijatý'
    PRIJEM_VYEXPEDOVANY = 'PV', 'Příjem - Vyexpedovaný'
    VYDEJ = 'V', 'Výdej'

class SklademZakazkyChoice(models.TextChoices):
    NEPRIJATO = 'neprijato', 'Nepřijato'
    BEZ_BEDEN = 'bez_beden', 'Bez beden'
    PO_EXSPIRACI = 'po_exspiraci', 'Po exspiraci'
    EXPEDOVANO = 'expedovano', 'Expedováno'