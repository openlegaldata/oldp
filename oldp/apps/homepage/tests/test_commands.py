import gzip
import json
import os
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings, tag

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook


@tag("commands")
class HomepageCommandsTestCase(TestCase):
    def test_render_html_pages(self):
        call_command("render_html_pages", *[], **{})


@tag("commands")
class DumpApiDataTestCase(TestCase):
    """Verify the dump_api_data command's snapshot contract.

    The dump must:
    - Always exclude records with review_status != "accepted"
    - Stream-gzip outputs (.jsonl.gz, not .jsonl)
    - Write a manifest.json with snapshot_date, oldp_version, filters, files
    - Iterate records in stable primary-key order
    - Denormalize book.code into laws.jsonl.gz as `book_code`
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
        "laws/laws.json",
        "cases/cases.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="dump_api_data_test_")
        cls.dump_subdir = "snapshot"
        cls.dump_path = os.path.join(cls.tmp_dir, cls.dump_subdir)

        # Add at least one non-accepted record per filtered model so we can
        # verify the always-on review_status="accepted" filter.
        cls.pending_court = Court.objects.create(
            name="Pending Court",
            code="PCDUMP",
            slug="pending-court-dump",
            state=Court.objects.first().state,
            review_status="pending",
        )

        accepted_book = LawBook.objects.filter(review_status="accepted").first()
        cls.pending_book = LawBook.objects.create(
            code="PendingBook",
            slug="pending-book-dump",
            title="Pending LawBook",
            revision_date="2024-01-01",
            latest=True,
            order=0,
            review_status="pending",
        )
        cls.pending_law = Law.objects.create(
            book=accepted_book,
            title="Pending Law",
            slug="pending-law-dump",
            section="999",
            order=0,
            review_status="pending",
        )
        cls.pending_case = Case.objects.create(
            title="Pending Case",
            slug="pending-case-dump",
            court=Court.objects.filter(review_status="accepted").first(),
            file_number="pending-dump-1",
            type="Urteil",
            content="",
            review_status="pending",
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _read_jsonl_gz(self, name):
        path = os.path.join(self.dump_path, name)
        self.assertTrue(os.path.exists(path), f"Missing dump file: {name}")
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def _run_dump(self):
        with override_settings(WORKING_DIR=self.tmp_dir):
            call_command("dump_api_data", self.dump_subdir, override=True)

    def test_dump_produces_gzip_files_and_manifest(self):
        self._run_dump()

        manifest_path = os.path.join(self.dump_path, "manifest.json")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)

        for key in ("snapshot_date", "oldp_version", "filters", "files"):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["filters"]["review_status"], "accepted")

        # All declared files exist as .jsonl.gz with row counts matching what's
        # actually written.
        for file_name, info in manifest["files"].items():
            self.assertTrue(file_name.endswith(".jsonl.gz"))
            records = self._read_jsonl_gz(file_name)
            self.assertEqual(len(records), info["row_count"])

        # Plain .jsonl files must not exist (only .jsonl.gz).
        for entry in os.listdir(self.dump_path):
            if entry.endswith(".jsonl"):
                self.fail(f"Found uncompressed file: {entry}")

    def test_dump_filters_to_accepted_only(self):
        self._run_dump()

        # The pending records we created in setUpTestData must not appear in
        # any dump file. (The serialized output does not include the
        # review_status field for unauthenticated callers — by design — so we
        # verify filtering by ID exclusion.)
        court_ids = {r["id"] for r in self._read_jsonl_gz("courts.jsonl.gz")}
        self.assertNotIn(self.pending_court.pk, court_ids)

        book_ids = {r["id"] for r in self._read_jsonl_gz("law_books.jsonl.gz")}
        self.assertNotIn(self.pending_book.pk, book_ids)

        law_ids = {r["id"] for r in self._read_jsonl_gz("laws.jsonl.gz")}
        self.assertNotIn(self.pending_law.pk, law_ids)

        case_ids = {r["id"] for r in self._read_jsonl_gz("cases.jsonl.gz")}
        self.assertNotIn(self.pending_case.pk, case_ids)

    def test_dump_records_are_pk_ordered(self):
        self._run_dump()

        for file_name in ("cases.jsonl.gz", "laws.jsonl.gz", "courts.jsonl.gz"):
            records = self._read_jsonl_gz(file_name)
            ids = [r["id"] for r in records]
            self.assertEqual(ids, sorted(ids), f"{file_name} not pk-ordered")

    def test_laws_dump_contains_book_code(self):
        self._run_dump()

        records = self._read_jsonl_gz("laws.jsonl.gz")
        self.assertGreater(len(records), 0)
        for rec in records:
            self.assertIn("book_code", rec)
            self.assertTrue(rec["book_code"], f"Empty book_code on law {rec['id']}")
