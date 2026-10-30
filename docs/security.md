# Bezpečnost a audit aplikace

Tento dokument popisuje ochrany použité v projektu a nastavení pro jeho provoz. Zdrojové nastavení je v [settings.py](../order_processing/settings.py), řízení operací v adminu, views a formulářích aplikace `orders`.

Aktualizováno 23. října 2026 podle repozitáře, provozních ověření z 6.–7. a 21. října 2026 a následné dohody o ponechání konfigurace. Nastavení v kódu, skutečné nasazení a plánované změny jsou níže rozlišené. Aktuální konfiguraci serveru, distribuci CA na všechna zařízení ani běh naplánovaných úloh nelze potvrdit jen z repozitáře.

## Přihlášení a oprávnění

Projekt používá autentizaci a relace Djanga. Administrace vyžaduje účet s příznakem staff a příslušná oprávnění; provozní obrazovky jsou dostupné přihlášeným uživatelům podle oprávnění dané operace.

Speciální oprávnění řídí úpravy expedovaných a pozastavených beden, nepřijatých beden a jejich poznámek, navezení, označení jako zakalené či zkontrolované a řízení šarží. Podrobnosti jsou v [manuálu beden](manual_bedna.md), [kontroly](manual_kontrola_beden.md) a [rychlého založení šarže](manual_rychle_zalozeni_sarze.md).

Hesla spravuje Django; projekt nemá vlastní `PASSWORD_HASHERS`, používá tedy výchozí konfiguraci s PBKDF2. Instalované knihovny Argon2 či bcrypt samy nezmění zvolený algoritmus. Projekt má zapnuté validátory podobnosti hesla, minimální délky, běžných hesel a čistě číselných hesel. Viz [správa hesel v Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/passwords/).

Evidence neshod a její detaily jsou pouze v administraci (`/admin/orders/zaznamneshody/`). Vyžadují aktivní staff účet a `orders.view_zaznamneshody`, případně účet správce; samotné oprávnění ke kontrole bedny nestačí. Odkazy z kontroly bedny a nabídky přehledů respektují tento přístup. Záznam vzniká při přechodu kontroly do Neshody ve stejné transakci pod zámkem bedny. Admin poskytuje pouze čtení a neumožňuje ruční přidání, úpravu ani smazání snapshotu; uložení existujícího snapshotu přes model je odmítnuto. Pozdější změny kontroly a měření nepřepisují zachycený stav. Viz [Evidence neshod](manual_evidence_neshod.md).

## Ochrany požadavků a šablon

- ORM parametrizuje běžné databázové dotazy.
- Django šablony standardně escapují hodnoty při výstupu do HTML; vlastní použití `safe` a `mark_safe` vyžaduje správné zacházení s obsahem.
- `CsrfViewMiddleware` a tokeny ve formulářích chrání změnové požadavky.
- `XFrameOptionsMiddleware` nastavuje ochranu proti vložení stránky do rámce.
- `SecurityMiddleware` zajišťuje nastavené bezpečnostní hlavičky a přesměrování.
- `AdminNoCacheMiddleware` přidává odpovědím pod `/admin/` hlavičky zakazující ukládání do cache. Toto opatření se nevztahuje automaticky na všechny provozní obrazovky.

Principy a meze těchto ochran popisuje [bezpečnostní dokumentace Django 5.2](https://docs.djangoproject.com/en/5.2/topics/security/).

## Produkční nastavení

Konfigurace se načítá z prostředí a lokálního `.env`. Skutečné klíče a hesla do dokumentace ani repozitáře nevkládejte.

| Nastavení | Použití |
| --- | --- |
| `DJANGO_SECRET_KEY` | Vlastní tajný klíč prostředí; kód nemá pevně zadaný náhradní klíč. |
| `DJANGO_DEBUG=False` | Produkční režim. |
| `DJANGO_ALLOWED_HOSTS` | Povolené hosty oddělené čárkou. |
| `DJANGO_DB_ENGINE=postgres`, `POSTGRES_*` | PostgreSQL v produkci i lokálně; explicitní volba brání přepnutí na SQLite v debug režimu. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Důvěryhodné originy včetně schématu, oddělené čárkou. |
| `DJANGO_SECURE_SSL_REDIRECT` | Při vypnutém debug režimu výchozí `True`. |
| `DJANGO_SECURE_HSTS_SECONDS` | Výchozí 0; HSTS se zapíná výslovně podle nasazení. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SECURE_HSTS_PRELOAD` | Výchozí `False`. |
| `DJANGO_X_FRAME_OPTIONS` | V produkci výchozí `DENY`. |
| `DJANGO_SECURE_REFERRER_POLICY` | V produkci výchozí `strict-origin-when-cross-origin`. |

V produkci jsou zapnuté `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` a `SECURE_CONTENT_TYPE_NOSNIFF`. Cookies mají názvy `sessionid_orders` a `csrftoken_orders`.

Nastavení důvěřuje `X-Forwarded-Proto: https` prostřednictvím `SECURE_PROXY_SSL_HEADER`. Reverzní proxy musí tuto hlavičku řídit, aby ji klient nemohl podvrhnout. Před nasazením spusťte z virtuálního prostředí `manage.py check --deploy` nad konfigurací příslušného prostředí.

Na Nginxu předávejte skutečné schéma klientského spojení, například `proxy_set_header X-Forwarded-Proto $scheme;`, a správný `Host`. Aplikační port zpřístupněte pouze proxy a oprávněným správcům; Django nesmí důvěřovat podvržené hlavičce při přímém přístupu z LAN. Podmínky nastavení popisuje [dokumentace SECURE_PROXY_SSL_HEADER](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).

Výchozí hodnoty v této tabulce nejsou potvrzením aktuálního serverového `.env`. Zvlášť ověřte soulad přesměrování v Django a Nginxu. Cookies označené `Secure` se přes HTTP neposílají, takže samotná dostupnost HTTP stránky nezaručuje funkční přihlášení. Kvůli nouzovému HTTP přístupu nepředávejte nešifrované požadavky jako HTTPS a nevypínejte zabezpečení cookies. HSTS zapínejte až po ověření spolehlivého HTTPS a distribuci důvěryhodné CA; prohlížeč s platnou HSTS politikou HTTP jako nouzovou cestu nepoužije.

## HTTPS a interní certifikační autorita

### Potvrzený stav a plán

- Dne 6. října 2026 byl původní prošlý self-signed certifikát pro `srv-warehouse` nahrazen serverovým certifikátem podepsaným interní Root CA. Proběhl test a reload Nginxu, ověření serverového certifikátu proti CA i kontrola jména; živé TLS spojení skončilo `Verify return code: 0 (ok)`.
- HTTPS ukončuje Nginx. Aplikace Django Orders je podle posledního popsaného nasazení dostupná za proxy na `127.0.0.1:8050`. Samotná výměna certifikátu vyžaduje reload Nginxu, nikoli restart Djanga.
- Přístupový název je `https://srv-warehouse/`; certifikát obsahuje SAN `DNS:srv-warehouse`. Nepokrývá přístup přes IP adresu ani jméno `django-warehouse`. Klientská zařízení musí název správně přeložit na adresu serveru, typicky pomocí interního DNS.
- HTTP na portu 80 mělo původně sloužit jako přechodný přístup pro zařízení bez CA. Dne 21. října 2026 však `curl -I http://srv-warehouse/` vrátil `301 Moved Permanently` a `Location: https://srv-warehouse/`. Pro tento požadavek tedy HTTP již přesměrovává; nejde o ověření všech cest nebo přístupu přes IP adresu.
- Výpis `nginx -T` a následně celý `/etc/nginx/sites-enabled/django-orders` ukázaly HTTP blok s `server_name srv-warehouse`, `proxy_pass http://127.0.0.1:8050` a `X-Forwarded-Proto $scheme`. Běžné HTTP požadavky tedy Nginx předává Djangu, které zajišťuje přesměrování. Samostatná HTTP cesta `/.well-known/acme-challenge/` obsluhuje soubory z `/var/www/html`.
- Dne 23. října 2026 bylo dohodnuto současnou konfiguraci ponechat. Přesměrování přes Django je podporovaný postup; zachovejte zapnuté `SECURE_SSL_REDIRECT` a správné předávání schématu z proxy. Přesun přesměrování přímo do Nginxu je volitelné provozní zjednodušení, nikoli nutná oprava ověřeného stavu. Viz [SECURE_SSL_REDIRECT](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-ssl-redirect).
- Druhá aplikace byla popsaná na `http://192.168.1.207:8000/`. Jméno `django-warehouse`, samostatný certifikát ze stejné CA a proxy z HTTPS na `127.0.0.1:8000` jsou plán. Jejich nasazení ani uzavření přímého přístupu z LAN na port 8000 nebylo potvrzeno.

### Přístup z internetu přes OpenVPN

Podle informace správce z 23. října 2026 se k interní aplikaci z internetu přistupuje z Androidu přes OpenVPN Connect. VPN zajišťuje Sophos spravovaný externím správcem sítě Calyx; konkrétní produkt, verze a konfigurace nebyly ověřeny. Na Androidu přes VPN funguje přístup pomocí IP adresy `192.168.1.207`, ale jméno `srv-warehouse` se nepřeloží. Na notebooku přes VPN přístup pomocí jména podle správce funguje.

Výstup `nslookup srv-warehouse` z notebooku ukázal DNS server `VM-DC.hpmheat.local` na `192.168.1.202` a překlad `srv-warehouse.hpmheat.local` na `192.168.1.207`. DNS záznam tedy existuje a na notebooku funguje dohledání krátkého jména v doméně `hpmheat.local`. Je potřeba ověřit rozdíl v předávání a používání DNS a vyhledávací přípony na Androidu; jeho aktuální DNS nastavení a dostupnost DNS serveru přes tunel zatím nebyly ověřeny.

VPN musí zajistit jak cestu k serveru, tak překlad používaného jména. Prohlížeč má dál otevírat `https://srv-warehouse/`: současný certifikát má SAN pouze pro toto DNS jméno a při použití IP adresy neodpovídá adrese v prohlížeči. Samotná instalace Root CA tento nesoulad jména nevyřeší.

Možnosti řešení před změnou konfigurace:

- **Centrálně přes DNS pro VPN:** interní DNS musí umět přeložit `srv-warehouse` na adresu dostupnou přes tunel; OpenVPN předá vhodné DNS nastavení klientům. DNS server musí být přes VPN dostupný a klient musí nastavení skutečně používat. U krátkého jména ověřte také DNS příponu a vyhledávání domén. Konkrétní možnosti závisejí na VPN serveru a klientovi; [OpenVPN popisuje předávání DNS pomocí DHCP options](https://openvpn.net/community-docs/pushing-dhcp-options-to-clients.html).
- **Místně pro jednotlivý počítač s Windows:** soubor `C:\Windows\System32\drivers\etc\hosts` může mapovat skutečnou, přes VPN dostupnou IP serveru na `srv-warehouse`. Nevyžaduje změnu aplikace ani certifikátu, ale mapování se spravuje na každém počítači a při změně IP se musí opravit. Zápis vyžaduje práva správce; [postup Microsoftu](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/cannot-modify-hosts-lmhosts-files). Na běžném Androidu nejde o standardní uživatelský postup.

Oprava překladu jména na Androidu zatím nebyla potvrzena. Správci Calyx předejte požadavek na ověření předávání a použití DNS serveru `192.168.1.202` a vyhledávací domény `hpmheat.local` v OpenVPN Connect na Androidu a na povolení DNS dotazů přes VPN. Konkrétní nastavení a podporu vyhledávací domény ověřte na používaném klientovi. Výsledek ověřte otevřením přesného jména `https://srv-warehouse/` z mobilní sítě po připojení VPN; správce podle konfigurace určí, zda je potřeba nový profil `.ovpn`. Aplikace má zůstat dostupná z internetu přes VPN. Na vzdáleném zařízení musí být důvěryhodná také Warehouse Internal Root CA. Samotné doplnění DNS přípony při vyhledávání nemění jméno v HTTPS adrese. Pokud se později začne v prohlížeči používat plné jméno `srv-warehouse.hpmheat.local`, musí být zahrnuto v SAN serverového certifikátu a v odpovídajícím nastavení Nginxu a Djanga; současný certifikát ho nepokrývá.

### Evidence certifikátů a klíčů

Platnosti v tabulce jsou v UTC. Před každou obnovou je znovu ověřte přímo ze souborů; tento přehled nenahrazuje sledování expirace.

| Položka | Hodnota / umístění |
| --- | --- |
| Root CA | `C=CZ, O=HPM, CN=Warehouse Internal Root CA`; certifikát s `CA:TRUE`. |
| Platnost Root CA | 17. 7. 2026 08:55:38 až 14. 7. 2036 08:55:38 UTC. |
| Veřejný certifikát CA, PEM | `/root/internal-ca/warehouse-root-ca.crt` |
| Veřejný certifikát CA, DER | `/root/internal-ca/warehouse-root-ca.cer` — tento soubor se distribuuje na klientská zařízení. |
| Soukromý klíč CA | `/root/internal-ca/warehouse-root-ca.key`, chráněný heslem; používá se k podpisu serverových certifikátů. |
| Serverový certifikát | `/etc/nginx/ssl/django-orders.crt`, vydavatel `Warehouse Internal Root CA`, SAN `DNS:srv-warehouse`. |
| Platnost serverového certifikátu | 6. 10. 2026 08:54:09 až 6. 10. 2027 08:54:09 UTC. |
| Soukromý klíč webového serveru | `/etc/nginx/ssl/django-orders.key`; odlišný od klíče CA. |
| Pracovní adresář vydaného certifikátu | `/root/internal-ca/issued/srv-warehouse-20261006-085302/` při nasazení 6. 10. 2026. |

Root CA je sama podepsaná sebou; důvěra vzniká instalací jejího veřejného certifikátu do správného úložiště zařízení. Serverový certifikát je podepsaný touto CA. Nginx pro běžné poskytování HTTPS nepotřebuje soukromý klíč CA.

Soukromé klíče, jejich zálohy a hesla nepatří do Gitu, klientských zařízení, veřejných adresářů ani logů. Na serveru omezte přístup ke klíči CA na správce, například soubor na `root:root` s právy `0600` a adresář na `0700`. Klíč Nginxu chraňte podle účtu, pod kterým ho server načítá. Heslo CA ukládejte do správce hesel; nepředávejte ho jako viditelný argument příkazu.

### Instalace důvěry na Windows a Android

Distribuujte pouze `warehouse-root-ca.cer` z důvěryhodného zdroje, například přenosem přes SSH/SCP nebo USB ze správcovského počítače. Soukromý klíč CA ani serveru se nepřenáší. Před importem lze porovnat otisk DER souboru: na serveru `sha256sum /root/internal-ca/warehouse-root-ca.cer`, na Windows `certutil -hashfile "C:\cesta\warehouse-root-ca.cer" SHA256`.

**Windows:** importujte certifikát do **Místní počítač → Důvěryhodné kořenové certifikační autority → Certifikáty**. Zápis vyžaduje práva správce. V PowerShellu spuštěném jako správce lze použít:

```powershell
certutil -addstore Root "C:\cesta\warehouse-root-ca.cer"
```

Zástupnou cestu nahraďte skutečným umístěním souboru. Pokud konzole běží pod jiným administrátorským účtem, jeho složka Downloads je jiná. Import musí skončit úspěšně a v úložišti má být `Warehouse Internal Root CA`. Postup a rozsah úložiště popisuje [správa certifikátů Windows](https://learn.microsoft.com/en-us/windows-server/identity/ad-cs/inspect-certificates-manage-certificate-stores) a [certutil](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/certutil).

**Android:** uložte `.cer` do telefonu nebo čtečky a v systémovém nastavení vyberte přibližně **Zabezpečení a ochrana soukromí → Další nastavení zabezpečení → Šifrování a přihlašovací údaje → Instalovat certifikát → Certifikát CA / Certifikát CÚ**. Názvy závisejí na výrobci a verzi Androidu. Potvrďte instalaci a případně PIN či heslo zařízení. Jde o důvěryhodnou CA, nikoli uživatelský certifikát pro VPN a aplikace nebo certifikát Wi-Fi. Požadavek na soukromý klíč obvykle znamená nesprávný typ importu nebo soubor. Heslo soukromého klíče CA se do Androidu nezadává.

Po importu znovu spusťte prohlížeč a na firemní síti ověřte `https://srv-warehouse/` bez výjimky z ověření certifikátu. Instalace CA v systému nezaručuje důvěru ve všech samostatných aplikacích; jejich vlastní úložiště a pravidla se mohou lišit. Distribuce CA na všechna firemní zařízení zatím není v této dokumentaci potvrzená.

Při roční obnově serverového certifikátu podepsaného stejnou platnou CA se na zařízeních nic neinstaluje. Před vypršením nebo výměnou samotné CA naplánujte včasnou distribuci nové důvěry.

### Obnova serverového certifikátu

Současný serverový certifikát obnovte před **6. říjnem 2027**; provozní termín byl navržen na konec září 2027. Připomenutí je nutné skutečně uložit do kalendáře nebo monitoringu. Naplánované upozornění ani funkční automatická obnova nebyly potvrzeny. Pro další obnovy ponechte rezervu alespoň několika týdnů.

Původně popsaný obnovovací skript vytvářel self-signed serverový certifikát. Takový skript nesmí přepsat aktuální certifikát vydaný interní CA. Jeho umístění a případné naplánování nebyly dohledané: při kontrole 6. října root neměl vlastní crontab a ve výpisu časovačů nebyla zjevná obnova. To nevylučuje systémový cron, jiného uživatele nebo ruční spouštění; tyto cesty je ještě potřeba ověřit.

Následující příkazy jsou pro **Bash na linuxovém serveru po `sudo -i`**, nikoli pro lokální PowerShell. Jednotlivé bloky provádějte ve stejném shellu; při chybě nepokračujte k nasazení. Tento postup používá existující klíč webového serveru. Vygenerování nového klíče vyžaduje také odpovídající výměnu klíče v Nginxu.

1. Zkontrolujte čas serveru, platnost CA i aktivního certifikátu a vytvořte chráněný pracovní adresář mimo aktivní cestu Nginxu:

   ```bash
   date -Is
   openssl x509 -in /root/internal-ca/warehouse-root-ca.crt -noout -subject -dates
   openssl x509 -in /etc/nginx/ssl/django-orders.crt -noout -issuer -dates

   umask 077
   install -d -m 0700 /root/internal-ca/issued
   RENEW_DIR=$(mktemp -d /root/internal-ca/issued/srv-warehouse-XXXXXXXX)
   ```

2. Vytvořte žádost a parametry serverového certifikátu:

   ```bash
   openssl req -new \
     -key /etc/nginx/ssl/django-orders.key \
     -out "$RENEW_DIR/srv-warehouse.csr" \
     -subj "/O=HPM/CN=srv-warehouse"

   cat > "$RENEW_DIR/server.ext" <<'EOF'
   [server_cert]
   basicConstraints = critical,CA:FALSE
   keyUsage = critical,digitalSignature,keyEncipherment
   extendedKeyUsage = serverAuth
   subjectAltName = DNS:srv-warehouse
   subjectKeyIdentifier = hash
   authorityKeyIdentifier = keyid,issuer
   EOF
   ```

3. Podepište žádost existující CA. Při výzvě zadejte heslo klíče CA přímo do terminálu:

   ```bash
   openssl x509 -req \
     -in "$RENEW_DIR/srv-warehouse.csr" \
     -CA /root/internal-ca/warehouse-root-ca.crt \
     -CAkey /root/internal-ca/warehouse-root-ca.key \
     -CAserial /root/internal-ca/warehouse-root-ca.srl \
     -CAcreateserial \
     -out "$RENEW_DIR/srv-warehouse.crt" \
     -days 365 -sha256 \
     -extfile "$RENEW_DIR/server.ext" -extensions server_cert
   ```

   Podpisy se stejným souborem sériových čísel neprovádějte souběžně. Serverový certifikát nesmí pro plánované použití přesahovat platnost CA. Postup vydání popisuje [openssl x509](https://docs.openssl.org/3.0/man1/openssl-x509/).

4. Ověřte řetězec, platnost, jméno a použití pro TLS server. První příkaz musí skončit `OK`; druhý vypíše novou platnost a SAN:

   ```bash
   openssl verify \
     -CAfile /root/internal-ca/warehouse-root-ca.crt \
     -purpose sslserver -verify_hostname srv-warehouse \
     "$RENEW_DIR/srv-warehouse.crt"

   openssl x509 -in "$RENEW_DIR/srv-warehouse.crt" \
     -noout -subject -issuer -dates -ext subjectAltName
   ```

   Dále porovnejte veřejnou část nového certifikátu s klíčem Nginxu. Vznikají jen soubory s veřejnými klíči:

   ```bash
   openssl x509 -in "$RENEW_DIR/srv-warehouse.crt" -pubkey -noout \
     > "$RENEW_DIR/cert.pub.pem" &&
   openssl pkey -pubin -in "$RENEW_DIR/cert.pub.pem" \
     -outform DER -out "$RENEW_DIR/cert.pub.der" &&
   openssl pkey -in /etc/nginx/ssl/django-orders.key -pubout \
     -outform DER -out "$RENEW_DIR/key.pub.der" &&
   cmp "$RENEW_DIR/cert.pub.der" "$RENEW_DIR/key.pub.der" &&
   echo "OK: certifikat odpovida klici Nginxu"
   ```

   Při neshodě nebo chybě certifikát nenasazujte. Možnosti ověření popisuje [openssl verify](https://docs.openssl.org/3.0/man1/openssl-verify/).

5. Po úspěšných kontrolách proveďte zálohu a výměnu certifikátu při plánovaném přepnutí. Nejprve ověřte, že Nginx skutečně používá uvedené cesty; pokud jsou řešené symbolickými odkazy nebo jinou automatizací, postup přizpůsobte tomuto nasazení:

   ```bash
   CERT_BACKUP="/etc/nginx/ssl/django-orders.crt.bak.$(date +%Y%m%d-%H%M%S)"

   cp -a /etc/nginx/ssl/django-orders.crt "$CERT_BACKUP" &&
   install -o root -g root -m 0644 \
     "$RENEW_DIR/srv-warehouse.crt" /etc/nginx/ssl/django-orders.crt &&
   nginx -t && systemctl reload nginx
   ```

   Při neúspěšném testu se reload neprovede. Pokud výměna proběhla, ale test nebo reload selhal, vraťte v témže shellu zálohu příkazem `cp -a "$CERT_BACKUP" /etc/nginx/ssl/django-orders.crt` a znovu proveďte `nginx -t && systemctl reload nginx`. Původní certifikát po návratu musí být stále platný, jinak návrat důvěryhodné HTTPS neobnoví. Reload a jeho chování popisuje [dokumentace Nginxu](https://nginx.org/en/docs/control.html).

6. Ověřte skutečně poskytovaný certifikát a přístup z klienta:

   ```bash
   openssl s_client \
     -connect 127.0.0.1:443 -servername srv-warehouse \
     -CAfile /root/internal-ca/warehouse-root-ca.crt \
     -verify_hostname srv-warehouse -verify_return_error </dev/null
   ```

   Očekávejte `Verify return code: 0 (ok)`; samotné závěrečné `DONE` úspěch ověření nepotvrzuje. Z klientského zařízení s CA otevřete `https://srv-warehouse/` a zkontrolujte také novou platnost certifikátu. Aktualizujte evidenci a termín další obnovy.

Klíč CA je chráněný heslem, proto tento postup vyžaduje interaktivní podpis. Automatické sledování expirace lze provozovat bez odemčení klíče. Plně automatické vydávání vyžaduje samostatný návrh správy podpisového klíče; samotný cron heslo nevyřeší.

### Heslo a záloha klíče CA

Změna hesla pouze znovu zašifruje stejný soukromý klíč. Nemění veřejný certifikát CA, již vydané serverové certifikáty ani důvěru klientských zařízení. Provedení změny hesla v dosavadním provozu nebylo potvrzeno.

Při změně nejprve vytvořte kopii v chráněném adresáři pomocí `openssl pkey -in PUVODNI_KLIC -aes-256-cbc -out NOVY_SOUBOR`. Vstup a výstup musí být různé soubory. Zadejte současné heslo a dvakrát nové heslo, potom zkontrolujte novou kopii pomocí `openssl pkey -in NOVY_SOUBOR -check -noout` a porovnejte její veřejný klíč s certifikátem CA. Teprve po úspěšném ověření nahraďte aktivní klíč, zachovejte práva `0600` a aktualizujte bezpečnou zálohu. Starší kopie zůstávají chráněné původním heslem. Viz [openssl pkey](https://docs.openssl.org/3.0/man1/openssl-pkey/).

Zálohujte šifrovaný klíč CA, veřejné certifikáty, evidenci vydaných certifikátů a soubor sériových čísel také mimo tento server, s omezeným přístupem. Heslo uchovávejte odděleně od zálohy. Bez klíče CA a jeho hesla nelze podepisovat další certifikáty stejnou autoritou. Změna hesla neřeší únik samotného klíče; při kompromitaci je potřeba řešit výměnu dotčených klíčů, certifikátů a případně klientské důvěry.

### Provozní potíže ověřené na zařízeních

- **Windows, import do úložiště jen pro čtení:** v řešeném případě pomohl import `certutil -addstore Root ...` z konzole spuštěné jako správce.
- **Chrome hlásí nezabezpečeno, anonymní okno je v pořádku:** v řešeném případě byl problém v běžném profilu či uloženém stavu prohlížeče. Nejprve ověřte adresu, vydavatele a platnost certifikátu a úplně restartujte prohlížeč. Anonymní okno pomáhá při diagnostice, nenahrazuje opravu důvěry.
- **CILICO C6, pád celého Chromu při otevření HTTPS:** dne 7. října 2026 pomohla instalace aktuálního Chromu. Verze Androidu ani přesné původní číslo Chromu nebyly zaznamenané; nejde o potvrzení konkrétní chyby všech C6. U dalších čteček ověřte dostupné aktualizace a následně otevření webu bez certifikátového varování.

Při dalších potížích rozlišujte selhání překladu jména, nedůvěryhodnou CA, prošlý certifikát, nesoulad jména, obsah načítaný přes HTTP a pád prohlížeče. Neobcházejte kontrolu certifikátu jako trvalé řešení.

## Integrita dat a historie

`django-simple-history` a middleware historie evidují změny sledovaných modelů a uživatele. Kontroly a měření beden mají historii; rozhodnutí o uvolnění má také aktuálního autora a čas.

Zápis kontroly i jednotlivých měření porovnává odeslaný stav s aktuálním záznamem. Při souběžné změně jiným uživatelem se uložení odmítne a obsluha načte aktuální údaje. Zápis používá transakce a uzamčení bedny.

Validace hlídá povinné údaje, povolené kombinace stavů, pozastavení beden, podíly pater a datum i čas konce kroku. Mazání je omezené podle výrobního stavu a souvisejících záznamů. Historie doplňuje provozní dohledatelnost; obnovu dat zajišťují zálohy databáze.

## Importy a soubory

XLSX import má náhled, validaci a atomické uložení. Velikost omezuje `EXCEL_UPLOAD_MAX_SIZE_MB` (výchozí 10 MB); limit na reverzní proxy nastavte v souladu s aplikací.

Chemický import pracuje s adresáři `CHEMISTRY_INCOMING_DIR` a `CHEMISTRY_ARCHIVE_DIR`. Synchronizace a kontrola dostupnosti Vanta používají nastavení `VANTA_SMB_*` a soubor přístupových údajů. Přístup k těmto souborům, archivu a provozním logům přidělte podle potřeb služby a správců.

Statické soubory obsluhuje WhiteNoise z výstupu `collectstatic`. Na produkci načítá PDF statické prostředky přes `WEASYPRINT_BASEURL` odvozené ze `STATIC_ROOT`.

## Zálohy, logy a provozní kontroly

Repozitář obsahuje [skript zálohy PostgreSQL](../deploy/backup-orders.sh) a [návod na jeho nasazení a obnovu](zalohy.md). Skript při naplánování každou hodinu vytváří dump `orders_prod`, ověří čitelnost jeho obsahu a po úspěchu odstraňuje dokončené automatické dumpy staré alespoň 72 hodin. Používá `umask 077`, zámek proti souběhu a dočasný soubor před dokončením zálohy. Existence skriptu sama nepotvrzuje jeho nasazení v cronu ani úspěšné běhy.

Zálohy databáze neobsahují automaticky role PostgreSQL, `.env`, konfiguraci Nginxu, certifikáty, klíče CA či serveru ani soubory mimo databázi. Tyto položky zálohujte samostatně. Pravidelně zkoušejte obnovu do oddělené testovací databáze a uchovávejte chráněnou kopii mimo server. `pg_restore --list` potvrzuje čitelnost seznamu obsahu, nikoli úplnou obnovitelnost.

Produkční logger `orders` zapisuje do `orders/orders.log` na úrovni `DEBUG`. Některé importy logují názvy sloupců a ukázky vstupních řádků; s logem proto zacházejte jako s provozními daty, omezte přístup a nastavte rotaci a dobu uchování. Logger není úplný bezpečnostní audit a historie modelů nenahrazuje zálohy. Do logů nepřidávejte hesla, soukromé klíče ani celé autentizační údaje.

Před nasazením a při pravidelné údržbě kontrolujte produkční konfiguraci pomocí `manage.py check --deploy`, dostupné bezpečnostní aktualizace závislostí, úspěšnost záloh a jejich obnovu, expirace certifikátů a přístupy uživatelů. `pip_audit` je v závislostech, ale automatické spouštění auditu, sledování expirace, vícefaktorové přihlášení a omezení četnosti přihlašovacích pokusů nejsou v projektové konfiguraci doložené; nepovažujte je za aktivní ochrany bez samostatného ověření nasazení.

## Související dokumentace

[Instalace a testy](../README.md) · [Zálohy a obnova](zalohy.md) · [Kamiony a importy](manual_kamion.md) · [Kontrola beden](manual_kontrola_beden.md)
