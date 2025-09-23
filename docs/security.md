# 🔒 Bezpečnostní výhody Djanga

Django je navrženo s důrazem na bezpečnost – spoustu hrozeb řeší už v základu:

## Ochrana proti SQL Injection
Díky ORM se dotazy generují bezpečně, není potřeba skládat vlastní SQL.  
📖 [QuerySets jsou bezpečné proti SQL injection](https://docs.djangoproject.com/en/5.2/topics/db/queries/#querysets-are-safe)

## Ochrana proti Cross-Site Scripting (XSS)
Šablonovací systém automaticky escapuje nebezpečný HTML kód.  
📖 [Ochrana proti XSS](https://docs.djangoproject.com/en/5.2/topics/security/#cross-site-scripting-xss-protection)

## Ochrana proti Cross-Site Request Forgery (CSRF)
Django přidává CSRF tokeny do formulářů a kontroluje je na serveru.  
📖 [CSRF reference](https://docs.djangoproject.com/en/5.2/ref/csrf/)  
📖 [Jak používat CSRF ochranu](https://docs.djangoproject.com/en/5.2/howto/csrf/)

## Ochrana proti Clickjacking
Middleware nastavuje HTTP hlavičky (např. `X-Frame-Options`).  
📖 [Clickjacking ochrana](https://docs.djangoproject.com/en/5.2/ref/clickjacking/)

## Bezpečné ukládání hesel
- Hesla se ukládají pomocí **PBKDF2**, **bcrypt**, **Argon2** nebo **SHA256** s použitím *salt*.  
- Možnost snadno změnit hashovací algoritmus.  
📖 [Správa hesel](https://docs.djangoproject.com/en/5.2/topics/auth/passwords/)

## Bezpečný autentizační systém
- Vestavěné ověřování uživatelů, session management.  
- Podpora dvoufaktorové autentizace (přes rozšíření).  
📖 [Autentizace uživatelů](https://docs.djangoproject.com/en/5.2/topics/auth/)

## Bezpečné spravování souborů a statik
Oddělení uživatelských nahrávek od kódu aplikace, prevence přímého spuštění.  
📖 [Bezpečnost – uživatelsky nahraný obsah](https://docs.djangoproject.com/en/5.2/topics/security/#user-uploaded-content)
