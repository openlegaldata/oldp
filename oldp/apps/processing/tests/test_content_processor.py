import logging
import time

from django.test import TestCase

from oldp.apps.laws.models import LawBook
from oldp.apps.processing.content_processor import (
    ContentProcessor,
    ItemProcessingTimeout,
    item_timeout,
)
from oldp.apps.processing.processing_steps import BaseProcessingStep


class ContentProcessorTestCase(TestCase):
    def test_load_processing_steps(self):
        cp = ContentProcessor()
        cp.model = LawBook

        steps = cp.get_available_processing_steps()
        self.assertEqual(3, len(steps), "Invalid number of steps")


class _SleepStep(BaseProcessingStep):
    """In-test processing step that sleeps for ``seconds`` then returns content.

    Used to simulate a pathologically slow per-item operation (e.g. refex
    catastrophic backtracking) without importing any heavy machinery.
    """

    description = "Test-only sleeping step"

    def __init__(self, seconds: float):
        self.seconds = seconds

    def process(self, content):
        time.sleep(self.seconds)
        return content


class _FakeItemProcessor:
    """Tiny harness that mirrors the per-item shape of CaseProcessor /
    LawProcessor (item_timeout(...) + transaction.atomic()) without
    touching the Django ORM.

    Drives ``item_timeout`` end-to-end so the unit tests can assert the
    public contract: a timed-out item is logged at WARNING, increments
    the timed-out counter, and the loop continues to the next item.
    """

    def __init__(self, item_timeout_seconds: float):
        self.item_timeout = item_timeout_seconds
        self.doc_counter = 0
        self.doc_failed_counter = 0
        self.timed_out_counter = 0
        self.processed_ids = []

    def run(self, items, step):
        logger = logging.getLogger("oldp.apps.processing.tests.fake")
        for item in items:
            try:
                with item_timeout(self.item_timeout):
                    step.process(item)
                self.doc_counter += 1
                self.processed_ids.append(item)
            except ItemProcessingTimeout as e:
                logger.warning(
                    "Item timed out after %.1fs, skipping: %s", e.timeout, item
                )
                self.timed_out_counter += 1
                self.doc_failed_counter += 1


class ItemTimeoutTestCase(TestCase):
    """Cover the ``--item-timeout`` contract end-to-end without ORM/refex.

    Sleep budgets are deliberately tiny (the alarm fires on a 1s tick,
    so the timed-out item costs ~1s wall-clock and the disabled-timeout
    case sleeps just long enough to prove no abort happens).
    """

    def test_timed_out_item_is_logged_and_counter_increments(self):
        # 1s budget (lowest meaningful SIGALRM tick). The slow step
        # would sleep 5s; the fast step finishes near-instantly.
        slow = _SleepStep(seconds=5.0)
        fast = _SleepStep(seconds=0.0)
        proc = _FakeItemProcessor(item_timeout_seconds=1.0)

        with self.assertLogs("oldp.apps.processing.tests.fake", level="WARNING") as cm:
            # First item times out, second still runs to completion.
            proc.run(items=["slow-item"], step=slow)
            proc.run(items=["fast-item"], step=fast)

        # a) WARNING log carries the item id
        self.assertTrue(
            any("slow-item" in msg for msg in cm.output),
            f"expected timeout warning to mention slow-item, got: {cm.output}",
        )
        self.assertTrue(
            any("timed out" in msg.lower() for msg in cm.output),
            f"expected 'timed out' in warning, got: {cm.output}",
        )
        # b) counter increments on the timed-out item only
        self.assertEqual(proc.timed_out_counter, 1)
        # c) the run continued: the fast item went through
        self.assertEqual(proc.doc_counter, 1)
        self.assertEqual(proc.processed_ids, ["fast-item"])

    def test_timed_out_item_appears_in_log_stats(self):
        cp = ContentProcessor()
        cp.timed_out_counter = 1

        with self.assertLogs(
            "oldp.apps.processing.content_processor", level="INFO"
        ) as cm:
            cp.log_stats()

        self.assertTrue(
            any("Timed-out documents: 1" in msg for msg in cm.output),
            f"expected 'Timed-out documents: 1' line, got: {cm.output}",
        )

    def test_log_stats_omits_timeout_line_when_zero(self):
        cp = ContentProcessor()
        # default counter is 0
        with self.assertLogs(
            "oldp.apps.processing.content_processor", level="INFO"
        ) as cm:
            cp.log_stats()

        self.assertFalse(
            any("Timed-out documents" in msg for msg in cm.output),
            "log_stats() should not mention timeouts when none occurred",
        )

    def test_disabled_timeout_does_not_abort_long_item(self):
        # 0 = disabled. A 0.2s sleep must complete normally.
        step = _SleepStep(seconds=0.2)
        proc = _FakeItemProcessor(item_timeout_seconds=0)
        proc.run(items=["item-1"], step=step)

        self.assertEqual(proc.timed_out_counter, 0)
        self.assertEqual(proc.doc_counter, 1)
        self.assertEqual(proc.processed_ids, ["item-1"])

    def test_set_options_reads_item_timeout(self):
        cp = ContentProcessor()
        cp.set_options({"verbose": False, "log_every": 100, "item_timeout": 7.5})
        self.assertEqual(cp.item_timeout, 7.5)

        cp.set_options({"verbose": False, "log_every": 100, "item_timeout": 0})
        self.assertEqual(cp.item_timeout, 0.0)

    def test_set_options_handles_missing_item_timeout(self):
        # If the option is missing entirely (e.g. legacy callers),
        # ``set_options`` should keep the class default rather than
        # crash.
        cp = ContentProcessor()
        cp.set_options({"verbose": False, "log_every": 100})
        self.assertEqual(cp.item_timeout, 30.0)
