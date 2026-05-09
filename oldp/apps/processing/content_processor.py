import contextlib
import glob
import logging.config
import os
import signal
import time
from enum import Enum
from importlib import import_module
from typing import List, Optional
from urllib.parse import parse_qsl

from django.conf import settings

from oldp.apps.processing.errors import ProcessingError
from oldp.apps.processing.processing_steps import BaseProcessingStep

ContentStorage = Enum("ContentStorage", "ES FS DB")

logger = logging.getLogger(__name__)


class ItemProcessingTimeout(Exception):
    """Raised when per-item processing exceeds the configured wall-clock budget.

    Carries the (unrounded) timeout value in seconds so callers can include
    it in the warning log without re-reading processor state.
    """

    def __init__(self, timeout: float):
        super().__init__(f"item processing exceeded {timeout:.1f}s timeout")
        self.timeout = timeout


@contextlib.contextmanager
def item_timeout(seconds: float):
    """Abort the wrapped block after ``seconds`` wall-clock seconds via SIGALRM.

    A non-positive ``seconds`` disables the alarm — the block runs to
    completion. The alarm is always cleared on exit (success, exception, or
    timeout itself) so the next iteration starts from a clean signal state.

    Caveats:

    * ``signal.alarm`` is Unix-only and must run on the main thread of the
      main interpreter. The processing pipeline always runs synchronously
      in the main thread of a single ``manage.py`` process, so this is the
      lowest-overhead option (no extra thread / process / event loop).
    * The alarm fires between Python bytecode instructions, so a C
      extension that doesn't release the GIL or check signals (e.g. a
      blocking ``re`` match) will still be interrupted: CPython's regex
      engine checks for pending signals between matches, which is exactly
      the refex / pathological-backtracking failure mode this guard exists
      to bound.
    """
    if seconds is None or seconds <= 0:
        # Disabled — no alarm, no signal handler swap. Yield bare.
        yield
        return

    def _handler(signum, frame):  # noqa: ARG001 - signature mandated by signal
        raise ItemProcessingTimeout(seconds)

    # ``signal.alarm`` only accepts whole seconds; round up so a 0.4s
    # request still fires after the next full second instead of silently
    # disabling the alarm. Callers asking for sub-second budgets in tests
    # accept that the actual fire is on a 1s tick.
    alarm_seconds = max(1, int(seconds + 0.999))
    previous_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(alarm_seconds)
    try:
        yield
    finally:
        # Always cancel the alarm and restore the previous handler so a
        # later iteration (or surrounding code path) doesn't inherit a
        # stale alarm or our handler.
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _format_eta(seconds: float) -> str:
    """Format seconds as ``Hh Mm Ss``, dropping leading zero units."""
    seconds = int(seconds)
    if seconds < 0:
        return "?"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class ProgressTracker(object):
    """Periodic INFO-level progress reporter for long-running processors.

    Long-running backfills (``manage.py process_cases extract_refs`` over
    the full ~420k corpus) emit a single end-of-run line and are
    otherwise silent at INFO. Without progress markers a stalled or
    long-tailed run is indistinguishable from a healthy one.

    The tracker logs:

    - one line on the first item (sanity check that the loop has begun);
    - one line every ``log_every`` items (default 100);
    - one final summary line via :meth:`finish`.

    When the total is known, lines include percentage complete and an
    ETA computed from a wall-clock rate. ETA is intentionally simple
    (``remaining / rate`` over the *whole run so far*); a windowed rate
    would react faster to slowdowns but isn't worth the complexity for
    operational visibility.

    Construct one per processor run; call :meth:`tick` per item and
    :meth:`finish` once the loop ends.
    """

    def __init__(self, total: Optional[int] = None, log_every: int = 100):
        self.total = total
        self.log_every = max(1, int(log_every))
        self.ok = 0
        self.failed = 0
        self._start = time.monotonic()

    def tick(self, ok: bool = True) -> None:
        if ok:
            self.ok += 1
        else:
            self.failed += 1
        done = self.ok + self.failed
        if done == 1 or done % self.log_every == 0:
            self._log(done)

    def finish(self) -> None:
        done = self.ok + self.failed
        self._log(done, final=True)

    def _log(self, done: int, final: bool = False) -> None:
        elapsed = max(time.monotonic() - self._start, 1e-9)
        rate = done / elapsed
        prefix = "Progress (final)" if final else "Progress"
        if self.total:
            pct = 100.0 * done / self.total
            eta = _format_eta((self.total - done) / rate) if rate > 0 else "?"
            logger.info(
                "%s: %d/%d (%.1f%%) ok=%d failed=%d %.1f items/s eta=%s",
                prefix,
                done,
                self.total,
                pct,
                self.ok,
                self.failed,
                rate,
                eta,
            )
        else:
            logger.info(
                "%s: %d ok=%d failed=%d %.1f items/s",
                prefix,
                done,
                self.ok,
                self.failed,
                rate,
            )


class InputHandler(object):
    input_selector = None  # Can be single, list, ... depends on get_content
    input_limit = 0  # 0 = unlimited
    input_start = 0
    skip_pre_processing = False
    pre_processed_content = []

    def __init__(self, limit=0, start=0, selector=None, *args, **kwargs):
        self.input_limit = limit
        self.input_selector = selector
        self.input_start = start

    def handle_input(self, input_content) -> None:
        raise NotImplementedError()

    def get_input(self) -> list:
        raise NotImplementedError()


class InputHandlerDB(InputHandler):
    """Read objects for re-processing from db"""

    skip_pre_processing = True
    per_page = 1000

    def __init__(
        self,
        order_by: str = "updated_date",
        filter_qs=None,
        exclude_qs=None,
        shards: int = 0,
        shard_index: int = 0,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # TODO Validate order_by (must exist as model field)
        self.order_by = order_by
        self.filter_qs = filter_qs
        self.exclude_qs = exclude_qs
        # Normalise the count (negative / falsy → "no sharding"); preserve
        # the raw shard_index so the bounds check below catches negative
        # values instead of silently clamping them to 0.
        self.shards = int(shards) if shards else 0
        if self.shards < 0:
            self.shards = 0
        self.shard_index = int(shard_index or 0)
        if self.shards and not (0 <= self.shard_index < self.shards):
            raise ValueError(
                f"shard-index ({self.shard_index}) must be in [0, {self.shards})"
            )

        if (
            "per_page" in kwargs
            and kwargs["per_page"] is not None
            and kwargs["per_page"] > 0
        ):
            self.per_page = kwargs["per_page"]

    @staticmethod
    def set_parser_arguments(parser):
        parser.add_argument(
            "--order-by",
            type=str,
            default="updated_date",
            help="Order items when reading from DB",
        )
        parser.add_argument(
            "--filter",
            type=str,
            help="Filter items with Django query language when reading from DB",
        )
        parser.add_argument(
            "--exclude",
            type=str,
            help="Exclude items with Django query language when reading from DB",
        )
        parser.add_argument(
            "--per-page", type=int, help="Number of items per page used for pagination"
        )
        parser.add_argument(
            "--shards",
            type=int,
            default=0,
            help=(
                "Total number of parallel shards (default 0 = no sharding). "
                "Used together with --shard-index to split the input across "
                "concurrent worker processes; each worker processes only the "
                "rows where pk MOD shards == shard-index. The pk-based split "
                "is stable across re-runs and doesn't require coordination "
                "between workers."
            ),
        )
        parser.add_argument(
            "--shard-index",
            type=int,
            default=0,
            help=(
                "0-based shard index in [0, --shards). One worker per index. "
                "Has no effect when --shards is 0."
            ),
        )

    def get_model(self):
        raise NotImplementedError()

    @staticmethod
    def parse_qs_args(kwargs):
        # Filter is provided as form-encoded data
        kwargs_dict = dict(parse_qsl(kwargs))

        for key in kwargs_dict:
            val = kwargs_dict[key]

            # Convert special values
            if val == "True":
                val = True
            elif val == "False":
                val = False
            elif val.isdigit():
                val = float(val)

            kwargs_dict[key] = val

        return kwargs_dict

    def get_queryset(self):
        return self.get_model().objects.all()

    def get_input(self):
        res = self.get_queryset().order_by(self.order_by)

        # Filter
        if self.filter_qs is not None:
            # Filter is provided as form-encoded data
            res = res.filter(**self.parse_qs_args(self.filter_qs))

        if self.exclude_qs is not None:
            # Exclude is provided as form-encoded data
            res = res.filter(**self.parse_qs_args(self.exclude_qs))

        # Sharding: deterministically partition the input by primary key
        # so concurrent worker processes can each take an exclusive
        # subset without coordinating. ``pk MOD shards == shard_index``
        # is index-friendly on integer PKs (no per-row computation
        # beyond the modulo) and stable across re-runs, so a worker
        # that crashes mid-shard can resume on the same partition.
        if self.shards:
            from django.db.models import F
            from django.db.models.functions import Mod

            res = res.annotate(_shard_bucket=Mod(F("pk"), self.shards)).filter(
                _shard_bucket=self.shard_index
            )

        # Set offset
        res = res[self.input_start :]

        # Set limit
        if self.input_limit > 0:
            return res[: self.input_limit]

        return res

    def handle_input(self, input_content):
        self.pre_processed_content.append(input_content)


class InputHandlerFS(InputHandler):
    """Read content files for initial processing from file system"""

    dir_selector = "/*"

    def get_input_content_from_selector(self, selector) -> list:
        content = []

        if isinstance(selector, str):
            if os.path.isdir(selector):
                # Get all files recursive
                content.extend(
                    sorted(
                        file
                        for file in glob.glob(
                            selector + self.dir_selector, recursive=True
                        )
                    )
                )
            elif os.path.isfile(selector):
                # Selector is specific file
                content.append(selector)
        elif isinstance(selector, list):
            # List of selectors
            for s in selector:
                content.extend(self.get_input_content_from_selector(s))
        return content

    def get_input(self) -> List[str]:
        """Select files from input_selector recursively and from directory with dir_selector"""
        if self.input_selector is None:
            raise ProcessingError("input_selector is not set")

        content_list = self.get_input_content_from_selector(self.input_selector)[
            self.input_start :
        ]

        if len(content_list) < 1:
            raise ProcessingError("Input selector is empty: %s" % self.input_selector)

        if self.input_limit > 0:
            content_list = content_list[: self.input_limit]

        return content_list

    def handle_input(self, input_content: str) -> None:
        raise NotImplementedError()


class ContentProcessor(object):
    """Base class for content processing pipeline

    Methods are called in the following order:

    1. get_input: returns list of input objects (fs: file path, db: model instance)
        - fs: set_input: list of dirs or files
        - db: set_input: db.queryset
    2. handle_input: handles input objects and transforms them to processing objects (fs: file path > model instance
        + save instance, db: keep model instance); write to self.pre_processed_content
    3. process: iterate over all processing steps (model instance > model instance), save processed model (in db
        + self.processed_content)
    4. post_process: iterate over all post processing steps (e.g. write to ES)

    """

    model = None  # type: Model
    working_dir = os.path.join(settings.BASE_DIR, "workingdir")

    input_handler = None  # type: InputHandler

    processed_content = []
    pre_processed_content = []
    available_processing_steps = None  # type: dict
    processing_steps = []
    post_processing_steps = []

    # Errors
    pre_processing_errors = []
    post_processing_errors = []
    processing_errors = []

    # Storage
    # output_path = 'http://localhost:9200'

    # DB settings (Django db models to be deleted on setup)
    # db_models = []

    # Stats
    file_counter = 0
    file_failed_counter = 0
    doc_counter = 0
    doc_failed_counter = 0
    timed_out_counter = 0

    # Per-item wall-clock timeout (seconds). 0 or negative disables the
    # alarm. Set from the ``--item-timeout`` CLI flag in ``set_options``.
    item_timeout = 30.0

    def __init__(self):
        # Working dir
        self.processing_steps = []  # type: List[BaseProcessingStep]
        self.processed_content = []
        self.pre_processed_content = []
        self.pre_processing_errors = []
        self.post_processing_errors = []
        self.processing_errors = []
        self.timed_out_counter = 0

    def set_parser_arguments(self, parser):
        # Enable arguments that are used by all children
        parser.add_argument(
            "--verbose", action="store_true", default=False, help="Show debug messages"
        )

        parser.add_argument(
            "step",
            nargs="*",
            type=str,
            help='Processing steps (use: "all" for all available steps)',
            default="all",
            choices=list(self.get_available_processing_steps().keys()) + ["all"],
        )

        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Limits the number of items to be processed (0=unlimited)",
        )
        parser.add_argument(
            "--start",
            type=int,
            default=0,
            help="Skip the number of items before processing",
        )
        parser.add_argument(
            "--log-every",
            type=int,
            default=100,
            help="Log a progress line every N processed items (default 100)",
        )
        parser.add_argument(
            "--item-timeout",
            type=float,
            default=30.0,
            help=(
                "Per-item wall-clock timeout in seconds (default 30). "
                "An item that exceeds this budget is aborted, its DB "
                "transaction rolled back, logged as a WARNING, and the "
                "run continues with the next item. Pass 0 (or a negative "
                "value) to disable the timeout entirely."
            ),
        )

    def set_options(self, options):
        # Set options according to parser options
        # self.output_path = options['output']

        if options["verbose"]:
            logger.setLevel(logging.DEBUG)
        # Stash the progress-logging interval so processors can read it
        # when constructing their ProgressTracker.
        self.log_every = int(options.get("log_every", 100) or 100)
        # Per-item timeout (seconds). Subclasses inherit this without
        # any extra wiring — they read ``self.item_timeout`` when
        # wrapping the per-item work in ``item_timeout(...)``.
        raw_timeout = options.get("item_timeout", self.item_timeout)
        try:
            self.item_timeout = float(raw_timeout) if raw_timeout is not None else 0.0
        except (TypeError, ValueError):
            self.item_timeout = 0.0

    log_every = 100

    def make_progress_tracker(self, total: Optional[int] = None) -> "ProgressTracker":
        """Build a tracker honoring the parser-supplied ``--log-every`` value."""
        return ProgressTracker(total=total, log_every=self.log_every)

    def empty_content(self):
        raise NotImplementedError()

    def set_input_handler(self, handler: InputHandler):
        self.input_handler = handler

    def call_processing_steps(self, content):
        """Call each processing step one by one"""
        for step in self.processing_steps:  # type: BaseProcessingStep
            try:
                content = step.process(content)
            except ProcessingError as e:
                logger.error("Failed to call processing step (%s): %s" % (step, e))
                self.processing_errors.append(e)
        return content

    def set_processing_steps(self, step_list):
        """Selects processing steps from available dict"""
        # Unset old steps and load available steps
        self.processing_steps = []
        self.get_available_processing_steps()

        if not isinstance(step_list, List):
            step_list = [step_list]

        if "all" in step_list:
            return self.available_processing_steps.values()

        for step in step_list:
            if step in self.available_processing_steps:
                self.processing_steps.append(self.available_processing_steps[step])
            else:
                raise ProcessingError("Requested step is not available: %s" % step)

    def get_available_processing_steps(self) -> dict:
        """Loads available processing steps based on package names in settings"""
        if self.available_processing_steps is None:
            self.available_processing_steps = {}

            # Get packages for model type
            if self.model.__name__ in settings.PROCESSING_STEPS:
                for step_package in settings.PROCESSING_STEPS[self.model.__name__]:  # type: str
                    module = import_module(step_package)

                    if "ProcessingStep" not in module.__dict__:
                        raise ProcessingError(
                            'Processing step package does not contain "ProcessingStep" class: %s'
                            % step_package
                        )

                    step_cls = module.ProcessingStep()  # type: BaseProcessingStep

                    if not isinstance(step_cls, BaseProcessingStep):
                        raise ProcessingError(
                            "Processing step needs to inherit from BaseProcessingStep: %s"
                            % step_package
                        )

                    step_name = step_package.split(".")[
                        -1
                    ]  # last module name from package path

                    # Write to dict
                    self.available_processing_steps[step_name] = step_cls
            else:
                raise ValueError(
                    "Model `%s` is missing settings.PROCESSING_STEPS."
                    % self.model.__name__
                )

        return self.available_processing_steps

    def process(self):
        # Reset queues
        self.pre_processed_content = []
        self.processed_content = []

        if self.input_handler.skip_pre_processing:
            # Send input directly to content queue
            self.pre_processed_content = self.input_handler.get_input()
        else:
            # Separate input handling and processing (processing needs to access previous items)
            self.input_handler.pre_processed_content = []
            for input_content in self.input_handler.get_input():
                try:
                    self.input_handler.handle_input(input_content)
                except ProcessingError as e:
                    logger.error(
                        "Failed to process content (%s): %s" % (input_content, e)
                    )
                    self.pre_processing_errors.append(e)
            self.pre_processed_content = self.input_handler.pre_processed_content

            logger.debug("Pre-processed content: %i" % len(self.pre_processed_content))

        # Start actual processing
        self.process_content()

        # Call post processing steps (each with whole content queue)
        for step in self.post_processing_steps:
            try:
                step.process(self.processed_content)
            except ProcessingError as e:
                logger.error("Failed to call post processing step (%s): %s" % (step, e))
                self.post_processing_errors.append(e)

    def process_content(self):
        raise NotImplementedError("Child class instead to implement this method.")

    def log_stats(self):
        logger.info("Processing stats:")
        logger.info(
            "- Successful files: %i (failed: %i)"
            % (self.file_counter, self.file_failed_counter)
        )
        logger.info(
            "- Successful documents: %i (failed: %i)"
            % (self.doc_counter, self.doc_failed_counter)
        )
        # Only report timeouts when at least one item hit the budget,
        # mirroring how ``pre_processing_errors`` / ``processing_errors``
        # stay quiet on clean runs.
        if self.timed_out_counter > 0:
            logger.info("- Timed-out documents: %i" % self.timed_out_counter)

        for step in self.post_processing_steps:
            if hasattr(step, "log_stats"):
                step.log_stats()

        if len(self.pre_processing_errors) > 0:
            logger.warning(
                "Pre-processing errors: %i" % len(self.pre_processing_errors)
            )
            logger.debug("Pre-processing errors: %s" % self.pre_processing_errors)

        if len(self.processing_errors) > 0:
            logger.warning("Processing errors: %i" % len(self.processing_errors))
            logger.debug("Processing errors: %s" % self.processing_errors)

        if len(self.post_processing_errors) > 0:
            logger.warning(
                "Post-processing errors: %i" % len(self.post_processing_errors)
            )
            logger.debug("Post-processing errors: %s" % self.post_processing_errors)
