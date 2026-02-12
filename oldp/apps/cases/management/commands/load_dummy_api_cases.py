import logging

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from oldp.apps.accounts.models import (
    APIToken,
    APITokenPermission,
    APITokenPermissionGroup,
)
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court

logger = logging.getLogger(__name__)

DUMMY_API_CASES = [
    {
        "title": "",
        "slug": "bgh-2024-03-15-i-zr-42-23",
        "court_code": "BGH",
        "court_chamber": None,
        "date": "2024-03-15",
        "file_number": "I ZR 42/23",
        "type": "Urteil",
        "ecli": "ECLI:DE:BGH:2024:150324UIZR42.23.0",
        "content": (
            "<h2>Tenor</h2>"
            "<p>Die Revision des Beklagten gegen das Urteil des 6. Zivilsenats "
            "des Oberlandesgerichts Köln vom 15. Dezember 2023 wird "
            "zurückgewiesen.</p>"
            "<h2>Gründe</h2>"
            "<p>I. Der Kläger nimmt den Beklagten auf Schadensersatz wegen "
            "Verletzung von Verkehrssicherungspflichten in Anspruch. "
            "Das Berufungsgericht hat der Klage stattgegeben. "
            "Hiergegen wendet sich die Revision des Beklagten.</p>"
            "<p>II. Die Revision ist unbegründet. Das Berufungsgericht hat "
            "zutreffend einen Anspruch des Klägers aus § 823 Abs. 1 BGB "
            "bejaht. Der Beklagte hat die ihm obliegenden "
            "Verkehrssicherungspflichten schuldhaft verletzt.</p>"
        ),
        "abstract": (
            "<p>Zur Haftung bei Verletzung von Verkehrssicherungspflichten "
            "im Zusammenhang mit der Instandhaltung von Gehwegen.</p>"
        ),
        "source_url": "https://api.example.com/cases/bgh-i-zr-42-23",
    },
    {
        "title": "",
        "slug": "bverfg-2024-06-20-1-bvr-567-23",
        "court_code": "BVerfG",
        "court_chamber": "1. Senat",
        "date": "2024-06-20",
        "file_number": "1 BvR 567/23",
        "type": "Beschluss",
        "ecli": "ECLI:DE:BVerfG:2024:rs20240620.1bvr056723",
        "content": (
            "<h2>Tenor</h2>"
            "<p>Die Verfassungsbeschwerde wird nicht zur Entscheidung "
            "angenommen.</p>"
            "<h2>Gründe</h2>"
            "<p>Die Verfassungsbeschwerde ist nicht zur Entscheidung "
            "anzunehmen, weil die Annahmevoraussetzungen des § 93a Abs. 2 "
            "BVerfGG nicht vorliegen. Die Verfassungsbeschwerde hat keine "
            "grundsätzliche verfassungsrechtliche Bedeutung im Sinne des "
            "Art. 14 Abs. 1 GG.</p>"
        ),
        "abstract": None,
        "source_url": "https://api.example.com/cases/bverfg-1-bvr-567-23",
    },
    {
        "title": "",
        "slug": "bgh-2024-09-10-viii-zr-88-24",
        "court_code": "BGH",
        "court_chamber": "VIII. Zivilsenat",
        "date": "2024-09-10",
        "file_number": "VIII ZR 88/24",
        "type": "Urteil",
        "ecli": "ECLI:DE:BGH:2024:100924UVIIIZR88.24.0",
        "content": (
            "<h2>Tenor</h2>"
            "<p>Auf die Revision der Klägerin wird das Urteil der "
            "8. Zivilkammer des Landgerichts München I vom 5. Mai 2024 "
            "aufgehoben.</p>"
            "<p>Die Sache wird zur neuen Verhandlung und Entscheidung, "
            "auch über die Kosten des Revisionsverfahrens, an das "
            "Berufungsgericht zurückverwiesen.</p>"
            "<h2>Gründe</h2>"
            "<p>I. Die Klägerin verlangt von dem Beklagten die Rückzahlung "
            "einer Mietkaution nach Beendigung des Mietverhältnisses.</p>"
            "<p>II. Das Berufungsgericht hat die Klage abgewiesen. "
            "Dies hält der rechtlichen Nachprüfung nicht stand.</p>"
            "<p>Nach § 551 Abs. 3 BGB hat der Vermieter die Kaution "
            "getrennt von seinem Vermögen anzulegen. Der Rückzahlungsanspruch "
            "ergibt sich aus § 812 Abs. 1 Satz 1 BGB.</p>"
        ),
        "abstract": (
            "<p>Zum Rückzahlungsanspruch des Mieters hinsichtlich der "
            "Mietkaution nach Beendigung des Mietverhältnisses.</p>"
        ),
        "source_url": "https://api.example.com/cases/bgh-viii-zr-88-24",
    },
]


class Command(BaseCommand):
    help = "Load dummy cases created via the API (with API token tracking)"

    def handle(self, *args, **options):
        if Case.objects.filter(
            created_by_token__isnull=False,
            slug__in=[c["slug"] for c in DUMMY_API_CASES],
        ).exists():
            raise CommandError(
                "Dummy API cases already exist. "
                "Delete them first if you want to reload."
            )

        # Get or create a user for the API token
        user, created = User.objects.get_or_create(
            username="api-scraper",
            defaults={"email": "scraper@example.com", "is_active": True},
        )
        if created:
            user.set_unusable_password()
            user.save()
            logger.info("Created api-scraper user")

        # Create permission: cases:write
        permission, _ = APITokenPermission.objects.get_or_create(
            resource="cases",
            action="write",
            defaults={"description": "Allows creating new cases via the API"},
        )

        # Create permission group
        group, group_created = APITokenPermissionGroup.objects.get_or_create(
            name="Case Writer",
            defaults={"description": "Permission group for submitting cases via API"},
        )
        if group_created:
            group.permissions.add(permission)
            logger.info("Created 'Case Writer' permission group")

        # Create API token
        token, token_created = APIToken.objects.get_or_create(
            user=user,
            name="Dummy Scraper Token",
            defaults={
                "is_active": True,
                "permission_group": group,
            },
        )
        if token_created:
            logger.info(
                "Created API token '%s' for user '%s'", token.name, user.username
            )

        # Resolve courts by code
        court_cache = {}
        for case_data in DUMMY_API_CASES:
            code = case_data["court_code"]
            if code not in court_cache:
                try:
                    court_cache[code] = Court.objects.get(code=code)
                except Court.DoesNotExist:
                    raise CommandError(
                        f"Court with code '{code}' not found. "
                        "Make sure court fixtures are loaded first."
                    )

        # Create cases
        created_count = 0
        for case_data in DUMMY_API_CASES:
            court = court_cache[case_data["court_code"]]

            if Case.objects.filter(
                court=court, file_number=case_data["file_number"]
            ).exists():
                logger.warning(
                    "Skipping duplicate case: %s %s",
                    case_data["court_code"],
                    case_data["file_number"],
                )
                continue

            Case.objects.create(
                title=case_data["title"],
                slug=case_data["slug"],
                court=court,
                court_raw=f'{{"name":"{case_data["court_code"]}"}}',
                court_chamber=case_data["court_chamber"],
                date=case_data["date"],
                file_number=case_data["file_number"],
                type=case_data["type"],
                ecli=case_data["ecli"],
                content=case_data["content"],
                abstract=case_data.get("abstract"),
                source_url=case_data["source_url"],
                review_status="pending",
                created_by_token=token,
            )
            created_count += 1
            logger.info("Created API case: %s", case_data["slug"])

        logger.info("Loaded %d dummy API cases (review_status=pending)", created_count)
