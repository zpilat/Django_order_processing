from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.templatetags.static import static
from django.urls import reverse

from orders.documentation import (
    DOCUMENTATION_GUIDES, DOCUMENTS_BY_SLUG, render_documentation,
)


class DocumentHTML(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids = set()
        self.links = []
        self.link_attributes = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
            self.link_attributes.append(attrs)


class DocumentationRenderingTests(SimpleTestCase):
    def test_tables_czech_anchors_and_duplicate_headings(self):
        html, contents = render_documentation(
            '# Návod\n\n## Měření\n\n## Měření\n\n'
            '| Stav | Výsledek |\n| --- | --- |\n| Čistota | OK |\n',
            'docs/manual_bedna.md',
        )
        self.assertIn('<table>', html)
        self.assertEqual(contents, [
            {'id': 'měření', 'title': 'Měření'},
            {'id': 'měření-1', 'title': 'Měření'},
        ])
        self.assertIn('id="měření"', html)
        self.assertIn('id="měření-1"', html)

    def test_html_and_unsafe_links_are_not_executable(self):
        html, _ = render_documentation(
            '<script>alert(1)</script>\n\n'
            '[Odkaz](javascript:alert(1))\n\n'
            '[Externí](https://example.org/)\n\n'
            '[Zdroj](../order_processing/settings.py)',
            'docs/manual_bedna.md',
        )
        self.assertNotIn('<script>', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('href="https://example.org/"', html)
        self.assertNotIn('href="../order_processing/settings.py"', html)

    def test_repository_document_links_and_fragments_resolve(self):
        documents = {}
        for document in DOCUMENTS_BY_SLUG.values():
            html, _ = render_documentation(
                (settings.BASE_DIR / document['path']).read_text(encoding='utf-8'),
                document['path'],
            )
            documents[reverse('admin_documentation', args=[document['slug']])] = DocumentHTML(html)

        for url, document in documents.items():
            for href in document.links:
                with self.subTest(document=url, link=href):
                    parts = urlsplit(href)
                    if parts.scheme or parts.netloc:
                        continue
                    self.assertFalse(parts.path.endswith('.md'), href)
                    target = documents.get(parts.path or url)
                    if parts.fragment and target:
                        self.assertIn(unquote(parts.fragment), target.ids)


@override_settings(SECURE_SSL_REDIRECT=False)
class DocumentationViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user('manual-reader', is_staff=True)
        cls.nonstaff = get_user_model().objects.create_user('operator')
        cls.inactive = get_user_model().objects.create_user(
            'inactive-reader', is_staff=True, is_active=False,
        )

    def setUp(self):
        self.url = reverse('admin_documentation', args=['kontrola-beden'])

    def test_anonymous_nonstaff_and_inactive_users_cannot_read_manuals(self):
        for user in (None, self.nonstaff, self.inactive):
            with self.subTest(user=user):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                response = self.client.get(self.url)
                self.assertRedirects(
                    response, f'{reverse("admin:login")}?next={self.url}',
                    fetch_redirect_response=False,
                )

    def test_staff_without_model_permissions_can_read_all_documents(self):
        """Všechny návody jsou čitelné a načítají ovládání postranního panelu."""
        self.client.force_login(self.staff)
        self.assertFalse(self.staff.get_all_permissions())
        for document in DOCUMENTS_BY_SLUG.values():
            with self.subTest(slug=document['slug']):
                response = self.client.get(reverse('admin_documentation', args=[document['slug']]))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'admin/documentation.html')
                self.assertContains(response, 'Obsah návodu')
                self.assertContains(response, 'Zpět na seznam návodů')
                self.assertContains(
                    response,
                    f'<script src="{static("orders/js/documentation.js")}" defer></script>',
                    html=True,
                )

    def test_documentation_block_follows_existing_admin_sections(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'id="documentation-links"')
        self.assertNotContains(response, static('orders/js/documentation.js'))
        content = response.content.decode()
        self.assertGreater(content.index('app-dokumentace'), content.index('Přehledy výroby'))
        for guide in DOCUMENTATION_GUIDES:
            self.assertContains(
                response,
                f'<a href="{reverse("admin_documentation", args=[guide["slug"]])}" '
                f'target="_blank" rel="noopener">{guide["title"]}</a>',
                html=True,
            )

    def test_manual_contains_links_to_other_manuals_and_czech_sections(self):
        """Odkazy v otevřeném návodu zachovají panel i správné kotvy kapitol."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_documentation', args=['provozni-tahak']))
        html = DocumentHTML(response.content.decode())
        self.assertIn(
            f'{self.url}#5-potvrzení-výrobního-stavu',
            [unquote(link) for link in html.links],
        )
        guide_urls = {
            reverse('admin_documentation', args=[guide['slug']])
            for guide in DOCUMENTATION_GUIDES
        }
        sidebar_urls = {
            link['href'] for link in html.link_attributes
            if link['href'] in guide_urls
        }
        self.assertEqual(sidebar_urls, guide_urls)
        for link in html.link_attributes:
            if urlsplit(link['href']).path in guide_urls:
                self.assertNotIn('target', link)
        response = self.client.get(self.url)
        self.assertContains(response, 'id="5-potvrzení-výrobního-stavu"')

    def test_unknown_documents_and_file_paths_are_not_served(self):
        self.client.force_login(self.staff)
        for path in ('neznamy', 'settings', '..%2F..%2F.env', '..%5C..%5C.env'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f'/admin/navody/{path}/').status_code, 404)

    def test_missing_deployed_document_returns_404(self):
        self.client.force_login(self.staff)
        with TemporaryDirectory() as directory:
            with self.settings(BASE_DIR=Path(directory)):
                self.assertEqual(self.client.get(self.url).status_code, 404)
