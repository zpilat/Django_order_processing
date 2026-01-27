import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Any

import pandas as pd
from django.contrib import messages
from .choices import PrioritaChoice
from .models import Predpis, Zakaznik, TypHlavy

logger = logging.getLogger('orders')


class BaseImportStrategy:
    """
    Rozhraní pro import zakázek z Excelu. Konkrétní strategie převede Excel
    na dataframe připravený k uložení a vrátí náhled + seznam povinných polí.
    """

    name = "BASE"
    required_fields: list[str] = []

    def parse_excel(self, excel_stream, request, kamion) -> Tuple[pd.DataFrame, List[dict], List[str], List[str], List[str]]:
        """
        Vrátí tuple (df, preview, errors, warnings, required_fields).
        Musí naplnit dataframe se sloupci použitelnými pro uložení.
        """
        raise NotImplementedError("Strategy must implement parse_excel")

    def get_required_fields(self) -> List[str]:
        raise NotImplementedError

    def get_cache_key(self, row: Any):
        raise NotImplementedError

    def map_row_to_zakazka_kwargs(self, row: Any, kamion, warnings: List[str]):
        raise NotImplementedError

    def map_row_to_bedna_kwargs(self, row: Any):
        raise NotImplementedError


class EURImportStrategy(BaseImportStrategy):
    name = "EUR"
    required_fields = [
        'sarze', 'popis', 'prumer', 'delka', 'artikl', 'predpis', 'typ_hlavy', 'material',
        'behalter_nr', 'hmotnost', 'tara', 'mnozstvi', 'datum',
    ]

    def parse_excel(self, excel_stream, request, kamion):
        errors: List[str] = []
        warnings: List[str] = []

        df = pd.read_excel(
            excel_stream,
            nrows=200,
            engine="openpyxl",
            dtype={
                'Artikel- nummer': str,
                'Vorgang+': str,
            },
        )

        # Najde první úplně prázdný řádek
        first_empty_index = df[df.isnull().all(axis=1)].index.min()
        if pd.notna(first_empty_index):
            df = df.loc[:first_empty_index - 1]

        # Odstraní prázdné sloupce
        df.dropna(axis=1, how='all', inplace=True)

        # Pro debug vytisknout názvy sloupců a první řádek dat
        logger.debug(f"Import - názvy sloupců: {df.columns.tolist()}")
        if not df.empty:
            logger.debug(f"Import - první řádek dat: {df.iloc[0].tolist()}")

        # Jednorázové mapování zdrojových názvů na interní názvy
        column_mapping = {
            'Unnamed: 6': 'typ_hlavy',
            'Unnamed: 7': 'rozmer',
            'Abhol- datum': 'datum',
            'Material- charge': 'sarze',
            'Artikel- nummer': 'artikl',
            'Be-schich-tung': 'vrstva',
            'Bezeichnung': 'popis',
            'n. Zg. / \nas drg': 'predpis',
            'Material': 'material',
            'Ober- fläche': 'povrch',
            'Gewicht in kg': 'hmotnost',
            'Tara kg': 'tara',
            'Behälter-Nr.:': 'behalter_nr',
            'Sonder / Zusatzinfo': 'dodatecne_info',
            'Lief.': 'dodavatel_materialu',
            'Fertigungs- auftrags Nr.': 'vyrobni_zakazka',
            'Vorgang+': 'prubeh',
            'Menge       ': 'mnozstvi',
            'Gew.': 'hmotnost_ks',
        }
        df.rename(columns=column_mapping, inplace=True)

        # Povinné zdrojové sloupce dle specifikace
        required_src = [
            'sarze', 'popis', 'rozmer', 'artikl', 'predpis', 'typ_hlavy', 'material', 'behalter_nr',
            'hmotnost', 'tara', 'hmotnost_ks', 'datum', 'dodatecne_info'
        ]
        missing = [c for c in required_src if c not in df.columns]
        if missing:
            errors.append(f"Chyba: V Excelu chybí povinné sloupce: {', '.join(missing)}")
            return df, [], errors, warnings, []

        # Zkontroluje datumy ve sloupci 'datum' – při různosti pouze varování
        if 'datum' in df.columns and not df['datum'].isnull().all():
            unique_dates = df['datum'].dropna().unique()
            if len(unique_dates) > 1:
                warnings.append("Upozornění: Sloupec 'datum' obsahuje různé hodnoty. Import pokračuje.")
            if len(unique_dates) == 1 and pd.notna(unique_dates[0]) and kamion:
                excel_date = pd.to_datetime(unique_dates[0]).date()
                if excel_date != kamion.datum:
                    warnings.append(
                        f"Upozornění: Datum v souboru ({excel_date.strftime('%d.%m.%Y')}) "
                        f"neodpovídá datumu kamionu ({kamion.datum.strftime('%d.%m.%Y')}). Import pokračuje."
                    )

        # Přidání prumer a delka rozdělením sloupce rozmer
        def rozdel_rozmer(row):
            try:
                text = str(row.get('rozmer', '') or '')
                text = text.replace('×', 'x').replace('X', 'x')
                prumer_str, delka_str = text.replace(',', '.').split('x')
                return Decimal(prumer_str.strip()), Decimal(delka_str.strip())
            except Exception:
                messages.info(request, "Chyba: Sloupec 'Abmessung' musí obsahovat hodnoty ve formátu 'prumer x delka'.")
                errors.append("Chyba: Sloupec 'Abmessung' musí obsahovat hodnoty ve formátu 'prumer x delka'.")
                return None, None

        df[['prumer', 'delka']] = df.apply(
            lambda row: pd.Series(rozdel_rozmer(row)), axis=1
        )

        # Vytvoří se nový sloupec 'priorita' podle textu v dodatecne_info
        def priorita(row):
            if pd.notna(row['dodatecne_info']) and 'sehr eilig' in row['dodatecne_info'].lower():
                return PrioritaChoice.VYSOKA
            elif pd.notna(row['dodatecne_info']) and 'eilig' in row['dodatecne_info'].lower():
                return PrioritaChoice.STREDNI
            return PrioritaChoice.NIZKA
        df['priorita'] = df.apply(priorita, axis=1)

        # Celozávit dle popisu
        def celozavit(row):
            if pd.notna(row['popis']) and 'konstrux' in row['popis'].lower():
                return True
            return False
        df['celozavit'] = df.apply(celozavit, axis=1)

        # Odfosfatovat dle dodatečných informací
        def odfosfatovat(row):
            if pd.notna(row['dodatecne_info']) and 'muss entphosphatiert werden' in row['dodatecne_info'].lower():
                return True
            return False
        df['odfosfatovat'] = df.apply(odfosfatovat, axis=1)

        # Výpočet množství v bedně dle hmotnost / hmotnost_ks
        def vypocet_mnozstvi_v_bedne(row):
            try:
                hmotnost = row.get('hmotnost')
                hmotnost_ks = row.get('hmotnost_ks')
                if pd.isna(hmotnost) or pd.isna(hmotnost_ks) or hmotnost_ks == 0:
                    return 1
                mnozstvi = int(hmotnost / hmotnost_ks)
                return max(mnozstvi, 1)
            except Exception:
                return 1
        df['mnozstvi'] = df.apply(vypocet_mnozstvi_v_bedne, axis=1)

        # Odstranění nepotřebných sloupců
        df.drop(columns=[
            'Unnamed: 0', 'rozmer', 'Gew + Tara', 'VPE', 'Box', 'Anzahl Boxen pro Behälter',
            'Härterei', 'Prod. Datum', 'hmotnost_ks', 'von Härterei \nnach Galvanik', 'Galvanik',
            'vom Galvanik nach Eurotec',
        ], inplace=True, errors='ignore')

        # Setřídění podle sloupce prumer, delka, predpis, artikl, sarze, behalter_nr
        df.sort_values(by=['prumer', 'delka', 'predpis', 'artikl', 'sarze', 'behalter_nr'], inplace=True)
        logger.info(f"Uživatel {request.user} úspěšně načetl data z Excel souboru pro import zakázek.")

        # Připravení náhledu
        error_values = '!!!!!!'
        preview = []
        for _, r in df.iterrows():
            raw_datum = r.get('datum')
            datum_fmt = error_values
            if pd.notna(raw_datum):
                try:
                    if hasattr(raw_datum, 'strftime'):
                        datum_fmt = raw_datum.strftime('%d.%m.%Y')
                    else:
                        dconv = pd.to_datetime(raw_datum, errors='coerce')
                        if pd.notna(dconv):
                            datum_fmt = dconv.strftime('%d.%m.%Y')
                except Exception:
                    datum_fmt = error_values
            try:
                beh_nr = int(r.get('behalter_nr')) if pd.notna(r.get('behalter_nr')) else error_values
            except Exception:
                beh_nr = error_values
            try:
                predpis_val = int(r.get('predpis')) if pd.notna(r.get('predpis')) else error_values
            except Exception:
                predpis_val = error_values
            preview.append({
                'datum': datum_fmt,
                'behalter_nr': beh_nr,
                'artikl': r.get('artikl') if pd.notna(r.get('artikl')) else error_values,
                'prumer': r.get('prumer') if pd.notna(r.get('prumer')) else error_values,
                'delka': r.get('delka') if pd.notna(r.get('delka')) else error_values,
                'predpis': predpis_val,
                'vyrobni_zakazka': r.get('vyrobni_zakazka') if pd.notna(r.get('vyrobni_zakazka')) else error_values,
                'typ_hlavy': r.get('typ_hlavy') if pd.notna(r.get('typ_hlavy')) else error_values,
                'popis': r.get('popis') if pd.notna(r.get('popis')) else error_values,
                'material': r.get('material') if pd.notna(r.get('material')) else error_values,
                'sarze': r.get('sarze') if pd.notna(r.get('sarze')) else error_values,
                'hmotnost': r.get('hmotnost') if pd.notna(r.get('hmotnost')) else error_values,
                'mnozstvi': r.get('mnozstvi') if pd.notna(r.get('mnozstvi')) else error_values,
                'tara': r.get('tara') if pd.notna(r.get('tara')) else error_values,
            })

        return df, preview, errors, warnings, list(self.required_fields)

    # --- Hooky pro ukládání ---
    def get_required_fields(self) -> List[str]:
        return list(self.required_fields)

    def get_cache_key(self, row: Any):
        artikl = row['artikl']
        sarze_raw = row.get('sarze')
        sarze_key = None if pd.isna(sarze_raw) else str(sarze_raw).strip()
        return (artikl, sarze_key)

    def map_row_to_zakazka_kwargs(self, row: Any, kamion, warnings: List[str]):
        prumer = row.get('prumer')
        if prumer == prumer.to_integral():
            retezec_prumer = str(int(prumer))
        else:
            retezec_prumer = str(prumer).replace('.', ',')

        try:
            cislo_predpisu = int(row['predpis'])
            nazev_predpis = f"{cislo_predpisu:05d}_Ø{retezec_prumer}"
        except (ValueError, TypeError):
            nazev_predpis = f"{row['predpis']}_Ø{retezec_prumer}"

        predpis = Predpis.objects.filter(nazev=nazev_predpis, aktivni=True).first()
        if not predpis:
            eurotec = Zakaznik.objects.filter(zkratka='EUR').only('id').first()
            predpis, created = Predpis.objects.get_or_create(
                nazev='Neznámý předpis',
                zakaznik=eurotec,
                defaults={'aktivni': True},
            )
            if not created and not predpis.aktivni:
                predpis.aktivni = True
                predpis.save()
            warnings.append(
                f"Varování: Předpis „{nazev_predpis}“ neexistuje. Použit předpis 'Neznámý předpis'."
            )
            logger.warning(
                f"Varování při importu: Předpis „{nazev_predpis}“ neexistuje. Použit předpis 'Neznámý předpis'."
            )

        typ_hlavy_excel = row.get('typ_hlavy', None)
        if pd.isna(typ_hlavy_excel) or not str(typ_hlavy_excel).strip():
            logger.error("Chyba: Sloupec s typem hlavy nesmí být prázdný.")
            raise ValueError("Chyba: Sloupec s typem hlavy nesmí být prázdný.")
        typ_hlavy_excel = str(typ_hlavy_excel).strip()
        typ_hlavy_qs = TypHlavy.objects.filter(nazev=typ_hlavy_excel)
        typ_hlavy = typ_hlavy_qs.first() if typ_hlavy_qs.exists() else None
        if not typ_hlavy:
            logger.error(f"Typ hlavy „{typ_hlavy_excel}“ neexistuje.")
            raise ValueError(f"Typ hlavy „{typ_hlavy_excel}“ neexistuje.")

        return {
            'kamion_prijem': kamion,
            'artikl': row['artikl'],
            'prumer': prumer,
            'delka': row.get('delka'),
            'predpis': predpis,
            'typ_hlavy': typ_hlavy,
            'celozavit': row.get('celozavit', False),
            'priorita': row.get('priorita', PrioritaChoice.NIZKA),
            'popis': row.get('popis'),
            'vrstva': row.get('vrstva'),
            'povrch': row.get('povrch'),
            'prubeh': row.get('prubeh'),
        }

    def map_row_to_bedna_kwargs(self, row: Any):
        return {
            'hmotnost': row.get('hmotnost'),
            'tara': row.get('tara'),
            'mnozstvi': row.get('mnozstvi', 1),
            'material': row.get('material'),
            'sarze': row.get('sarze'),
            'behalter_nr': row.get('behalter_nr'),
            'dodatecne_info': row.get('dodatecne_info'),
            'dodavatel_materialu': row.get('dodavatel_materialu'),
            'vyrobni_zakazka': row.get('vyrobni_zakazka'),
            'odfosfatovat': row.get('odfosfatovat'),
        }

class SPXImportStrategy(BaseImportStrategy):
    name = "SPX"
    required_fields = [
        'vyrobni_zakazka', 'artikl', 'popis', 'mnozstvi', 'hmotnost', 'tara', 'prumer', 'delka',
    ] 

    def parse_excel(self, excel_stream, request, kamion):
        errors: List[str] = []
        warnings: List[str] = []

        df = pd.read_excel(
            excel_stream,
            engine="openpyxl",
            skiprows=range(5), 
            nrows=300,
            header=0,
            dtype={
                'Bestellnr.': str,
                'Material': str,
            },
            keep_default_na=False,
        )

        # Najde první úplně prázdný řádek
        first_empty_index = df[df.isnull().all(axis=1)].index.min()
        if pd.notna(first_empty_index):
            df = df.loc[:first_empty_index - 1]

        # Odstraní prázdné sloupce
        df.dropna(axis=1, how='all', inplace=True)

        # Pro debug vytisknout názvy sloupců a první dva řádky dat
        logger.debug(f"Import - názvy sloupců: {df.columns.tolist()}")
        if not df.empty:
            logger.debug(f"Import - první dva řádky dat: {df.head(2).to_dict(orient='records')}")

        # Jednorázové mapování zdrojových názvů na interní názvy
        column_mapping = {
            'Bestellnr.': 'vyrobni_zakazka',
            'Material': 'artikl',
            'Kurztext': 'popis',
            'Menge': 'mnozstvi',
            'ME Gewicht': 'hmotnost',
            'GE': 'brutto',
        }
        df.rename(columns=column_mapping, inplace=True)

        # Kontrola sudého počtu řádků
        if len(df) % 2 != 0:
            errors.append("Chyba: Počet řádků v Excelu musí být sudý, každý pár řádků tvoří jednu bednu.")
            return df, [], errors, warnings, []
        
        # Rozdělení na dvojice řádků - top a bottom, které se spojí dohromady - obsahují různé informace o jedné bedně
        top_rows = df.iloc[::2].reset_index(drop=True)
        bottom_rows = df.iloc[1::2].reset_index(drop=True)

        top_rows['rozmer'] = bottom_rows.iloc[:, 2]
        df = top_rows

        # Povinné zdrojové sloupce dle specifikace
        required_src = [
        'vyrobni_zakazka', 'artikl', 'popis', 'mnozstvi', 'hmotnost', 'brutto', 'rozmer',
        ] 
        missing = [c for c in required_src if c not in df.columns]
        if missing:
            errors.append(f"Chyba: V Excelu chybí povinné sloupce: {', '.join(missing)}")
            return df, [], errors, warnings, []

        # Vyčistí množství/hmotnosti
        def parse_int_mnozstvi(value):
            text = str(value or "").strip()
            digits = re.sub(r"\D", "", text)
            if not digits:
                errors.append("Chyba: Nelze přečíst množství (mnozstvi).")
                return None
            return int(digits)

        def parse_decimal_one(value, label):
            text = str(value or "").replace(',', '.').strip()
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
            if not match:
                errors.append(f"Chyba: Nelze přečíst hodnotu ve sloupci {label}.")
                return None
            try:
                return Decimal(match.group(1)).quantize(Decimal('0.0'), rounding=ROUND_HALF_UP)
            except Exception:
                errors.append(f"Chyba: Nelze převést hodnotu ve sloupci {label} na číslo.")
                return None

        df['mnozstvi'] = df['mnozstvi'].apply(parse_int_mnozstvi)
        df['hmotnost'] = df['hmotnost'].apply(lambda v: parse_decimal_one(v, 'hmotnost'))
        df['brutto'] = df['brutto'].apply(lambda v: parse_decimal_one(v, 'brutto'))

        # Vypočti tara = brutto - hmotnost (obě s 1 desetinným místem)
        def compute_tara(row):
            brutto_val = row.get('brutto')
            hmotnost_val = row.get('hmotnost')
            if brutto_val is None or hmotnost_val is None or hmotnost_val == 0 or brutto_val == 0 or brutto_val <= hmotnost_val:
                errors.append("Chyba: Nelze spočítat taru, chybí brutto nebo hmotnost.")
                return None
            try:
                return (brutto_val - hmotnost_val).quantize(Decimal('0.0'), rounding=ROUND_HALF_UP)
            except Exception:
                errors.append("Chyba: Nelze spočítat taru.")
                return None

        df['tara'] = df.apply(compute_tara, axis=1)

        # Rozparsuje sloupec rozmer: např. "TG 6,0*160,00" nebo "6,0*160,00" -> prefix (pokud je) přidá k popisu, čísla do prumer/delka
        rozmer_pattern = re.compile(r"^(?:(?P<prefix>.*?)\s+)?(?P<prumer>[0-9]+[.,]?[0-9]*)\*(?P<delka>[0-9]+[.,]?[0-9]*)")

        def rozdel_rozmer(row):
            text = str(row.get('rozmer', '') or '').replace('×', '*').replace('X', '*').strip()
            if not text:
                errors.append("Chyba: Sloupec s rozměrem je prázdný.")
                return None, None, None

            match = rozmer_pattern.match(text)
            if not match:
                errors.append("Chyba: Sloupec s rozměrem musí být ve formátu 'prumer*delka' nebo 'prefix prumer*delka'.")
                return None, None, None

            prefix_raw = match.group('prefix') or ''
            prefix = prefix_raw.strip()
            try:
                prumer_val = Decimal(match.group('prumer').replace(',', '.')).quantize(Decimal('0.0'), rounding=ROUND_HALF_UP)
                delka_val = Decimal(match.group('delka').replace(',', '.')).quantize(Decimal('0.0'), rounding=ROUND_HALF_UP)
            except Exception:
                errors.append("Chyba: Nelze převést hodnoty průměru nebo délky na číslo.")
                return prefix, None, None

            return prefix, prumer_val, delka_val

        df[['rozmer_prefix', 'prumer', 'delka']] = df.apply(
            lambda row: pd.Series(rozdel_rozmer(row)), axis=1
        )

        # Přidej prefix z rozměru na konec popisu, pokud existuje
        df['popis'] = df.apply(
            lambda row: f"{row.get('popis', '').strip()} {row['rozmer_prefix']}".strip()
            if pd.notna(row.get('rozmer_prefix')) and str(row.get('rozmer_prefix')).strip()
            else row.get('popis', '').strip(),
            axis=1,
        )

        df.drop(columns=['rozmer_prefix', 'rozmer', 'brutto'], inplace=True)

        logger.debug(f"Import - sloučené a upravené řádky dat: {df.head(2).to_dict(orient='records')}")     

        # Setřídění podle sloupce prumer, delka, artikl
        df.sort_values(by=['prumer', 'delka', 'artikl'], inplace=True)
        logger.info(f"Uživatel {request.user} úspěšně načetl data z Excel souboru pro import zakázek.")

        # Připravení náhledu
        error_values = '!!!!!!'
        preview = []
        for _, r in df.iterrows():
            preview.append({
                'artikl': r.get('artikl') if pd.notna(r.get('artikl')) else error_values,
                'prumer': r.get('prumer') if pd.notna(r.get('prumer')) else error_values,
                'delka': r.get('delka') if pd.notna(r.get('delka')) else error_values,
                'popis': r.get('popis') if pd.notna(r.get('popis')) else error_values,
                'vyrobni_zakazka': r.get('vyrobni_zakazka') if pd.notna(r.get('vyrobni_zakazka')) else error_values,
                'hmotnost': r.get('hmotnost') if pd.notna(r.get('hmotnost')) else error_values,
                'mnozstvi': r.get('mnozstvi') if pd.notna(r.get('mnozstvi')) else error_values,
                'tara': r.get('tara') if pd.notna(r.get('tara')) else error_values,
            })

        return df, preview, errors, warnings, list(self.required_fields)