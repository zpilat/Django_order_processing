"""Read-only documentation backed by an explicit list of repository files."""

import posixpath
from urllib.parse import unquote, urlsplit, urlunsplit

from django.conf import settings
from django.contrib import admin
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.text import slugify
from markdown_it import MarkdownIt


DOCUMENTATION_GUIDES = (
    {'slug': 'provozni-tahak', 'title': 'Provozní tahák', 'path': 'docs/provozni_tahak.md'},
    {'slug': 'bedny', 'title': 'Bedny', 'path': 'docs/manual_bedna.md'},
    {'slug': 'zakazky', 'title': 'Zakázky', 'path': 'docs/manual_zakazka.md'},
    {'slug': 'kamiony', 'title': 'Kamiony', 'path': 'docs/manual_kamion.md'},
    {'slug': 'denik', 'title': 'Deník beden v krocích šarže', 'path': 'docs/manual_denik_pece.md'},
    {'slug': 'pruchod-sarze', 'title': 'Průchod šarže výrobou', 'path': 'docs/manual_pruchod_sarze.md'},
    {'slug': 'rychle-zalozeni-sarze', 'title': 'Rychlé založení šarže', 'path': 'docs/manual_rychle_zalozeni_sarze.md'},
    {'slug': 'kontrola-beden', 'title': 'Kontrola beden', 'path': 'docs/manual_kontrola_beden.md'},
    {'slug': 'evidence-neshod', 'title': 'Evidence neshod', 'path': 'docs/manual_evidence_neshod.md'},
    {'slug': 'ciselniky', 'title': 'Číselníky a nastavení zákazníka', 'path': 'docs/manual_ciselniky.md'},
    {'slug': 'prehledy-a-ukazatele', 'title': 'Přehledy a význam ukazatelů', 'path': 'docs/manual_prehledy_a_ukazatele.md'},
    {'slug': 'mimoradne-situace', 'title': 'Mimořádné situace a opravy', 'path': 'docs/manual_mimoradne_situace.md'},
    {'slug': 'stavy-a-pravidla', 'title': 'Stavy a automatická pravidla', 'path': 'docs/manual_stavy_a_pravidla.md'},
    {'slug': 'role-a-opravneni', 'title': 'Role a oprávnění', 'path': 'docs/manual_role_a_opravneni.md'},
)

# These documents are linked from manuals, but do not clutter the operator menu.
SUPPLEMENTARY_DOCUMENTS = (
    {'slug': 'readme', 'title': 'O aplikaci a instalaci', 'path': 'README.md'},
    {'slug': 'prezentace', 'title': 'Prezentace', 'path': 'docs/prezentace.md'},
    {'slug': 'bezpecnost', 'title': 'Bezpečnost', 'path': 'docs/security.md'},
    {'slug': 'zalohy', 'title': 'Zálohy a obnova', 'path': 'docs/zalohy.md'},
)

DOCUMENTS_BY_SLUG = {
    document['slug']: document
    for document in (*DOCUMENTATION_GUIDES, *SUPPLEMENTARY_DOCUMENTS)
}
DOCUMENTS_BY_PATH = {document['path']: document for document in DOCUMENTS_BY_SLUG.values()}


def render_documentation(source, source_path):
    """Render trusted Markdown with HTML disabled and local manual links resolved."""
    markdown = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = markdown.parse(source)
    contents = []
    heading_ids = set()
    for index, token in enumerate(tokens):
        if token.type == 'heading_open':
            inline = tokens[index + 1]
            title = ''.join(
                child.content for child in inline.children or []
                if child.type in {'text', 'code_inline'}
            )
            base_id = slugify(title, allow_unicode=True) or 'kapitola'
            heading_id = base_id
            suffix = 0
            while heading_id in heading_ids:
                suffix += 1
                heading_id = f'{base_id}-{suffix}'
            heading_ids.add(heading_id)
            token.attrSet('id', heading_id)
            if token.tag == 'h2':
                contents.append({'id': heading_id, 'title': title})

        for child in token.children or []:
            if child.type != 'link_open':
                continue
            href = child.attrGet('href') or ''
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or not parts.path or parts.path.startswith('/'):
                continue
            linked_path = posixpath.normpath(posixpath.join(
                posixpath.dirname(source_path), unquote(parts.path),
            ))
            document = DOCUMENTS_BY_PATH.get(linked_path)
            if document:
                child.attrSet('href', urlunsplit((
                    '', '', reverse('admin_documentation', args=[document['slug']]),
                    parts.query, parts.fragment,
                )))
            else:
                # Source-code links are useful in the repository, but there is
                # deliberately no file browser in the application.
                child.attrs.pop('href', None)
                child.attrSet('title', f'Soubor v repozitáři: {parts.path}')

    return markdown.renderer.render(tokens, markdown.options, {}), contents


def documentation_view(request, slug):
    # Access is enforced by admin.site.admin_view in the URL configuration.
    document = DOCUMENTS_BY_SLUG.get(slug)
    if document is None:
        raise Http404('Návod nebyl nalezen.')
    try:
        source = (settings.BASE_DIR / document['path']).read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise Http404('Soubor návodu není dostupný.') from exc
    content, contents = render_documentation(source, document['path'])
    context = {
        **admin.site.each_context(request),
        'title': document['title'],
        'document': document,
        'document_content': content,
        'document_contents': contents,
    }
    return TemplateResponse(request, 'admin/documentation.html', context)
