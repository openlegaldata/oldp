import time

from django.core.management import BaseCommand

from oldp.apps.lib.sitemaps import generate_sitemaps


class Command(BaseCommand):
    help = (
        "Render the XML sitemaps (index + one file per page) to SITEMAP_ROOT. "
        "Run once a day; see docs/sitemap-xml.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--root", help="Output directory (default: settings.SITEMAP_ROOT)"
        )
        parser.add_argument(
            "--protocol",
            default="https",
            choices=["https", "http"],
            help="Protocol of the URLs in the sitemaps (default: https)",
        )

    def handle(self, *args, **options):
        started = time.monotonic()
        log = self.stdout.write if options["verbosity"] > 1 else None
        summary = generate_sitemaps(
            root=options["root"], protocol=options["protocol"], log=log
        )
        for section, (items, pages) in summary.items():
            self.stdout.write(f"{section}: {items} items in {pages} page(s)")
        self.stdout.write(f"done in {time.monotonic() - started:.1f}s")
