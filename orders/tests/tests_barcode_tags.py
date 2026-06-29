from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import reverse

from orders.templatetags.barcode_tags import (
    bedna_code128_svg,
    bedna_qr_svg,
    bedna_scan_url,
    sarze_code128_svg,
)


class BarcodeTagsTests(SimpleTestCase):
    def test_bedna_qr_svg_uses_scan_url(self):
        bedna = SimpleNamespace(cislo_bedny=123456)
        context = {"barcode_base_url": "https://example.test/"}

        svg = str(bedna_qr_svg(context, bedna)).lstrip()
        scan_url = str(bedna_scan_url(context, bedna))

        self.assertTrue(svg.startswith("<svg"))
        self.assertEqual(
            scan_url,
            f"https://example.test{reverse('bedna_scan', args=[bedna.cislo_bedny])}",
        )

    def test_bedna_code128_svg_contains_inline_svg(self):
        bedna = SimpleNamespace(cislo_bedny=123456)

        svg = str(bedna_code128_svg(bedna)).lstrip()

        self.assertTrue(svg.startswith("<svg"))

    def test_sarze_code128_svg_contains_inline_svg(self):
        class SarzeStub:
            cislo_sarze = 42

            def __str__(self):
                return "S00042"

        sarze = SarzeStub()

        svg = str(sarze_code128_svg(sarze)).lstrip()

        self.assertTrue(svg.startswith("<svg"))
