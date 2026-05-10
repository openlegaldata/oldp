import logging
import os
from json import JSONDecodeError

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import (
    DataError,
    IntegrityError,
    OperationalError,
    connection,
    transaction,
)
from django.utils import timezone

from oldp.apps.cases.models import Case
from oldp.apps.processing.content_processor import (
    ContentProcessor,
    InputHandlerDB,
    InputHandlerFS,
    ItemProcessingTimeout,
    item_timeout,
)
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import CaseReferenceMarker

logger = logging.getLogger(__name__)


class CaseProcessor(ContentProcessor):
    model = Case

    def __init__(self):
        super().__init__()

        self.es_type = "case"
        self.db_models = [Case, CaseReferenceMarker]
        self.input_path = os.path.join(self.working_dir, "cases")

    def empty_content(self):
        Case.objects.all().delete()

    def process_content_item(self, content: Case) -> Case:
        ok = False
        try:
            # ``item_timeout`` raises ``ItemProcessingTimeout`` from
            # inside the ``transaction.atomic`` block when a single
            # case (e.g. an EuGH judgment with refex-pathological text)
            # exceeds the per-item budget. Because the exception
            # propagates through ``atomic()``, the marker delete +
            # re-insert is rolled back automatically — no half-written
            # references survive the timeout.
            with item_timeout(self.item_timeout):
                # Wrap the marker delete + re-extract + re-save in a single
                # transaction so concurrent readers never see the
                # mid-flight "case has zero references" state. Without this,
                # the case-detail view briefly renders an empty references
                # panel between the marker delete and the re-insert during
                # backfill.
                with transaction.atomic():
                    # First save (some processing steps require ids)
                    # content.full_clean()  # Validate model
                    content.save()

                    self.call_processing_steps(content)

                    # Save again
                    content.save()

            logger.debug("Completed: %s" % content)

            self.doc_counter += 1
            self.processed_content.append(content)
            ok = True

        except ItemProcessingTimeout as e:
            # The atomic() block above already rolled back, so no
            # half-written refs remain. Log enough to find the row in
            # triage (the Case __str__ includes pk, court code, file
            # number) and continue with the next item.
            logger.warning(
                "Item timed out after %.1fs, skipping: %s", e.timeout, content
            )
            self.timed_out_counter += 1
            self.doc_failed_counter += 1

        except (
            ValidationError,
            DataError,
            OperationalError,
            IntegrityError,
            ProcessingError,
        ) as e:
            logger.error("Cannot process case: %s; %s" % (content, e))
            self.processing_errors.append(e)
            self.doc_failed_counter += 1

        except Exception as e:  # noqa: BLE001
            # Catch-all for unhandled per-case crashes (refex IndexError on
            # malformed HTML, MySQLdb ProgrammingError "Commands out of sync"
            # when SIGALRM interrupts mid-cursor, etc.). Without this, a
            # single bad case kills the whole run.
            logger.warning(
                "Item failed with %s: %s; skipping: %s",
                type(e).__name__,
                e,
                content,
            )
            self.processing_errors.append(e)
            self.doc_failed_counter += 1
            # Mark the case as "tried" so a backfill driven by
            # ``references_extracted_at__isnull=True`` doesn't keep
            # re-finding (and re-crashing on) the same broken row in
            # every chunk. Save only this one field — ``content`` may
            # carry partial mutations from a half-run extraction step,
            # and we don't want those persisted. Operators can identify
            # "tried but failed" cases later by joining against the run
            # logs (the WARNING above carries the case identifier).
            try:
                content.references_extracted_at = timezone.now()
                content.save(update_fields=["references_extracted_at"])
            except Exception:  # noqa: BLE001
                pass
            # If the DB connection was left in a bad state by the failure
            # (typical signature: SIGALRM during MySQLdb network read), close
            # it so the next case opens a fresh one.
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

        if self._progress is not None:
            self._progress.tick(ok=ok)
        return content

    _progress = None

    def process_content(self):
        if (
            isinstance(self.input_handler, InputHandlerDB)
            and self.input_handler.input_limit > self.input_handler.per_page
        ):
            # Use pagination if supported and no limit set
            logger.debug("Use pagination (per_page=%i)" % self.input_handler.per_page)

            paginator = Paginator(
                self.pre_processed_content, self.input_handler.per_page
            )
            self._progress = self.make_progress_tracker(total=paginator.count)
            for page in range(1, paginator.num_pages + 1):
                logger.debug("Page %i / %i" % (page, paginator.num_pages))

                for item in paginator.page(page).object_list:
                    self.process_content_item(item)

        else:
            self._progress = self.make_progress_tracker(
                total=_safe_total(self.pre_processed_content)
            )
            for content in self.pre_processed_content:
                self.process_content_item(content)

        self._progress.finish()
        self._progress = None


def _safe_total(items) -> int | None:
    """Return a count for ``items`` without forcing a queryset to materialise.

    Tries ``QuerySet.count()`` (cheap COUNT query); falls back to ``len`` if
    available; returns None when neither is callable cheaply (e.g. a generator).
    """
    counter = getattr(items, "count", None)
    if callable(counter):
        try:
            return counter()
        except Exception:  # noqa: BLE001
            pass
    try:
        return len(items)
    except TypeError:
        return None


class CaseInputHandlerDB(InputHandlerDB):
    def get_model(self):
        return Case


class CaseInputHandlerFS(InputHandlerFS):
    """Read cases for initial processing from file system"""

    dir_selector = "/*.json"

    def handle_input(self, input_content):
        try:
            logger.debug("Reading case JSON from %s" % input_content)

            case = Case.from_json_file(input_content)
            case.source_path = input_content

            self.pre_processed_content.append(case)

        except JSONDecodeError:
            raise ProcessingError("Cannot parse JSON from %s" % input_content)


if __name__ == "__main__":
    print(
        "Do not call CaseProcessor directly. Run django command: ./manage.py process_cases"
    )
