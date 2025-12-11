import asyncio
import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection
import threading
import traceback
from collections.abc import AsyncGenerator
from datetime import datetime
from datetime import timezone
from functools import partial
from logging.handlers import QueueHandler
from pathlib import Path

# Ensure onnxruntime stays on CPU to avoid GPU discovery when BabelDOC loads.
try:
    import onnxruntime

    if not getattr(onnxruntime, "_pdf2zh_cpu_only", False):
        def _pdf2zh_cpu_only_providers():
            return ["CPUExecutionProvider"]

        def _pdf2zh_cpu_only_device():
            return "CPU"

        onnxruntime.get_available_providers = _pdf2zh_cpu_only_providers
        onnxruntime.get_device = _pdf2zh_cpu_only_device
        onnxruntime._pdf2zh_cpu_only = True
except ImportError:  # pragma: no cover - onnxruntime required in production
    pass

from babeldoc.docvision.base_doclayout import DocLayoutModel
from babeldoc.docvision.base_doclayout import YoloResult
from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from babeldoc.format.pdf.translation_config import TranslationConfig as BabelDOCConfig
from babeldoc.format.pdf.translation_config import (
    WatermarkOutputMode as BabelDOCWatermarkMode,
)
from babeldoc.glossary import Glossary
from babeldoc.main import create_progress_handler
from rich.logging import RichHandler

from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.translator import get_translator
from pdf2zh_next.utils import asynchronize


# Custom exception classes for structured error handling
class TranslationError(Exception):
    """Base class for all translation-related errors."""

    def __reduce__(self):
        """Support for pickling the exception when passing between processes."""
        return self.__class__, (str(self),)


class BabeldocError(TranslationError):
    """Error originating from the babeldoc library."""

    def __init__(self, message, original_error=None):
        super().__init__(message)
        self.original_error = original_error

    def __reduce__(self):
        """Support for pickling the exception when passing between processes."""
        return self.__class__, (str(self), self.original_error)

    def __str__(self):
        if self.original_error:
            return f"{super().__str__()} - Original error: {self.original_error}"
        return super().__str__()


class SubprocessError(TranslationError):
    """Error occurring in the translation subprocess outside of babeldoc."""

    def __init__(self, message, traceback_str=None):
        self.raw_message = message
        super().__init__(message)
        self.traceback_str = traceback_str

    def __reduce__(self):
        """Support for pickling the exception when passing between processes."""
        return (self.__class__, (self.raw_message, self.traceback_str))

    def __str__(self):
        if self.traceback_str:
            return f"{super().__str__()}\nTraceback: {self.traceback_str}"
        return super().__str__()


class IPCError(TranslationError):
    """Error in inter-process communication."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details

    def __reduce__(self):
        """Support for pickling the exception when passing between processes."""
        return self.__class__, (str(self), self.details)

    def __str__(self):
        if self.details:
            return f"{super().__str__()} - Details: {self.details}"
        return super().__str__()


class SubprocessCrashError(TranslationError):
    """Error occurring when the subprocess crashes unexpectedly."""

    def __init__(self, message, exit_code=None):
        super().__init__(message)
        self.exit_code = exit_code

    def __reduce__(self):
        """Support for pickling the exception when passing between processes."""
        return self.__class__, (str(self), self.exit_code)

    def __str__(self):
        if self.exit_code is not None:
            return f"{super().__str__()} (exit code: {self.exit_code})"
        return super().__str__()


logger = logging.getLogger(__name__)


class LLMOnlyDocLayoutModel(DocLayoutModel):
    """Doc layout stub that skips ONNX models when only LLM translation is needed."""

    def __init__(self):
        self._stride = 32

    @property
    def stride(self) -> int:
        return self._stride

    def handle_document(self, pages, mupdf_doc, translate_config, save_debug_image):
        for page in pages:
            yield page, YoloResult(names=[], boxes=[])


LLM_ONLY_DOC_LAYOUT_MODEL = LLMOnlyDocLayoutModel()


class _ProgressLogHandler(logging.Handler):
    """将子进程日志转成事件回推上层。"""

    def __init__(self, cb: asynchronize.AsyncCallback):
        super().__init__()
        self._cb = cb

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = {
            "type": "log",
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
        }
        try:
            self._cb.step_callback(log_entry)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).debug(
                f"Failed to forward log event: {exc}"
            )


class _ForwardLogHandler(logging.Handler):
    """把子进程日志交给主进程现有 logger 处理，避免重复配置。"""

    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


class TranslateProcessManager:
    """封装翻译子进程、IPC 与日志转发的生命周期管理。"""

    def __init__(self, settings: SettingsModel, file: Path, timeout: int):
        self.settings = settings
        self.file = file
        self.cb = asynchronize.AsyncCallback(timeout=timeout)

        self.pipe_progress_recv, self.pipe_progress_send = multiprocessing.Pipe(
            duplex=False
        )
        self.pipe_cancel_recv, self.pipe_cancel_send = multiprocessing.Pipe(
            duplex=False
        )
        self.logger_queue = multiprocessing.Queue()
        self.cancel_event = threading.Event()

        self.recv_thread: threading.Thread | None = None
        self.queue_listener: logging.handlers.QueueListener | None = None
        self.translate_process: multiprocessing.Process | None = None

    def start(self) -> None:
        self._start_recv_thread()
        self._start_queue_listener()
        self._start_translate_process()

    def _start_translate_process(self) -> None:
        self.translate_process = multiprocessing.Process(
            target=_translate_wrapper,
            args=(
                self.settings,
                self.file,
                self.pipe_progress_send,
                self.pipe_cancel_recv,
                self.logger_queue,
            ),
        )
        self.translate_process.start()

    def _start_queue_listener(self) -> None:
        progress_handler = _ProgressLogHandler(self.cb)
        forward_handler = _ForwardLogHandler()
        self.queue_listener = logging.handlers.QueueListener(
            self.logger_queue,
            progress_handler,
            forward_handler,
        )
        self.queue_listener.start()

    def _start_recv_thread(self) -> None:
        def recv_worker():
            while True:
                if self.cancel_event.is_set():
                    break
                try:
                    event = self.pipe_progress_recv.recv()
                    if event is None:
                        logger.debug("recv none event")
                        self.cb.finished_callback_without_args()
                        break

                    if isinstance(event, TranslationError):
                        logger.error(f"Received error from subprocess: {event}")
                        self.cb.error_callback(event)
                        break
                    if isinstance(event, dict):
                        self.cb.step_callback(event)
                        continue

                    logger.warning(
                        f"Unexpected message type from subprocess: {type(event)}"
                    )
                    error = IPCError(f"Unexpected message type: {type(event)}")
                    self.cb.error_callback(error)
                    break
                except EOFError:
                    logger.debug("recv eof error")
                    error = IPCError("Connection to subprocess was closed unexpectedly")
                    self.cb.error_callback(error)
                    break
                except Exception as e:  # noqa: BLE001
                    if not self.cancel_event.is_set():
                        logger.error(f"Error receiving event: {e}")
                    error = IPCError(f"IPC error: {e}", details=str(e))
                    self.cb.error_callback(error)
                    break

        self.recv_thread = threading.Thread(target=recv_worker, daemon=True)
        self.recv_thread.start()

    async def iter_events(self):
        """异步迭代子进程事件，负责清理资源与错误上抛。"""
        completed_successfully = False
        cancel_flag = False
        try:
            async for event in self.cb:
                if self.cb.has_error():
                    break
                payload = event.args[0]
                yield payload
                try:
                    if isinstance(payload, dict) and payload.get("type") == "finish":
                        completed_successfully = True
                        break
                except Exception:  # noqa: BLE001
                    pass
        except asyncio.CancelledError:
            cancel_flag = True
            logger.info("Process Translation cancelled")
            raise
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received in main process")
        finally:
            crash_error = self._cleanup(completed_successfully, cancel_flag)
            if crash_error:
                raise crash_error

    def _cleanup(self, completed_successfully: bool, cancel_flag: bool):
        logger.debug("send cancel message")
        if not completed_successfully:
            try:
                self.pipe_cancel_send.send(True)
            except (OSError, BrokenPipeError) as e:
                logger.debug(f"Failed to send cancel message: {e}")

        logger.debug("close pipe cancel message")
        try:
            self.pipe_cancel_send.close()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to close pipe_cancel_message_send: {e}")

        try:
            self.pipe_progress_send.send(None)
        except (OSError, BrokenPipeError) as e:
            logger.debug(f"Failed to send None to pipe_progress_send: {e}")

        if not completed_successfully:
            logger.debug("set cancel event")
            self.cancel_event.set()

        # 关闭接收端管道以中断 recv_thread 中的阻塞接收
        try:
            self.pipe_progress_recv.close()
            logger.debug("closed pipe_progress_recv")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to close pipe_progress_recv: {e}")

        # 终止子进程，使用超时防止卡住
        join_timeout = 10
        if completed_successfully and not cancel_flag:
            join_timeout = 30
        if self.translate_process:
            self.translate_process.join(timeout=join_timeout)
            logger.debug("join translate process")
            if self.translate_process.is_alive():
                if completed_successfully and not cancel_flag:
                    logger.info(
                        "Translate process still running after completion, allowing extra time"
                    )
                    self.translate_process.join(timeout=30)
                if self.translate_process.is_alive():
                    logger.info("Translate process did not finish in time, terminate it")
                    self.translate_process.terminate()
                    self.translate_process.join(timeout=5)
                if self.translate_process.is_alive():
                    logger.info("Translate process did not finish in time, killing it")
                    try:
                        self.translate_process.kill()
                        self.translate_process.join(timeout=2)
                        logger.info("Translate process killed")
                    except Exception as e:  # noqa: BLE001
                        logger.exception(f"Error killing translate process: {e}")

        # 等待接收线程，使用超时防止卡住
        logger.debug("join recv thread")
        if self.recv_thread:
            self.recv_thread.join(timeout=2)
            if self.recv_thread.is_alive():
                logger.warning("Recv thread did not finish in time")

        try:
            self.logger_queue.put(None)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to send sentinel to logger_queue: {e}")

        if self.queue_listener:
            try:
                self.queue_listener.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Failed to stop queue listener: {e}")

        try:
            self.logger_queue.close()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to close logger_queue: {e}")

        logger.debug(
            "translate process exit code: %s",
            self.translate_process.exitcode if self.translate_process else None,
        )
        if cancel_flag or completed_successfully:
            return None

        # 如果进程崩溃但 IPC 未捕获错误，补充抛错
        if (
            self.translate_process
            and self.translate_process.exitcode not in (0, None)
            and not self.cb.has_error()
        ):
            return SubprocessCrashError(
                f"Translation subprocess crashed with exit code {self.translate_process.exitcode}",
                exit_code=self.translate_process.exitcode,
            )
        if self.cb.has_error():
            return self.cb.error
        return None


def _translate_wrapper(
    settings: SettingsModel,
    file: Path,
    pipe_progress_send: multiprocessing.connection.Connection,
    pipe_cancel_message_recv: multiprocessing.connection.Connection,
    logger_queue: multiprocessing.Queue,
):
    logger = logging.getLogger(__name__)
    cancel_event = threading.Event()
    try:
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("pdfminer").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("peewee").setLevel(logging.WARNING)

        queue_handler = QueueHandler(logger_queue)
        logging.basicConfig(level=logging.INFO, handlers=[queue_handler])

        config = create_babeldoc_config(settings, file)

        def cancel_recv_thread():
            try:
                pipe_cancel_message_recv.recv()
                logger.debug("Cancel signal received in subprocess")
                cancel_event.set()
                config.cancel_translation()
            except Exception as e:
                logger.error(f"Error in cancel_recv_thread: {e}")

        cancel_t = threading.Thread(target=cancel_recv_thread, daemon=True)
        cancel_t.start()

        async def translate_wrapper_async():
            try:
                async for event in babeldoc_translate(config):
                    logger.debug(f"sub process generate event: {event}")
                    if event["type"] == "error":
                        # Convert babeldoc error to structured exception
                        error_msg = str(event.get("error", "Unknown babeldoc error"))
                        error = BabeldocError(
                            message=f"Babeldoc translation error: {error_msg}",
                            original_error=error_msg,
                        )
                        pipe_progress_send.send(error)
                        break
                    # Send normal progress events as before
                    pipe_progress_send.send(event)
                    if event["type"] == "finish":
                        break
            except Exception as e:
                # Capture non-babeldoc errors during translation
                tb_str = traceback.format_exc()
                if not cancel_event.is_set():
                    logger.error(f"Error in translate_wrapper_async: {e}\n{tb_str}")
                error = SubprocessError(
                    message=f"Error during translation process: {e}",
                    traceback_str=tb_str,
                )
                try:
                    pipe_progress_send.send(error)
                except Exception as pipe_err:
                    if not cancel_event.is_set():
                        logger.error(f"Failed to send error through pipe: {pipe_err}")

        # Run the async translation in the subprocess's event loop
        try:
            asyncio.run(translate_wrapper_async())
        except Exception as e:
            # Capture errors that might occur outside the async context
            tb_str = traceback.format_exc()
            if not cancel_event.is_set():
                logger.error(f"Error running async translation: {e}\n{tb_str}")
            error = SubprocessError(
                message=f"Failed to run translation process: {e}", traceback_str=tb_str
            )
            try:
                pipe_progress_send.send(error)
            except Exception as pipe_err:
                if not cancel_event.is_set():
                    logger.error(f"Failed to send error through pipe: {pipe_err}")
    except Exception as e:
        # Capture any errors during setup or initialization
        tb_str = traceback.format_exc()
        logger.error(f"Subprocess initialization error: {e}\n{tb_str}")
        try:
            error = SubprocessError(
                message=f"Translation subprocess initialization error: {e}",
                traceback_str=tb_str,
            )
            pipe_progress_send.send(error)
        except Exception as pipe_err:
            if not cancel_event.is_set():
                logger.error(f"Failed to send error through pipe: {pipe_err}")
    finally:
        logger.debug("sub process send close")
        try:
            pipe_progress_send.send(None)
            pipe_progress_send.close()
            logger.debug("sub process close pipe progress send")
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Error closing progress pipe: {e}")

        try:
            logging.getLogger().removeHandler(queue_handler)
            logging.getLogger().addHandler(RichHandler())
            logger_queue.put(None)
            logger_queue.close()
        except Exception as e:
            if not cancel_event.is_set():
                logger.error(f"Error closing logger queue: {e}")


async def _translate_in_subprocess(
    settings: SettingsModel,
    file: Path,
):
    manager = TranslateProcessManager(settings, file, timeout=30 * 60)
    manager.start()
    async for payload in manager.iter_events():
        yield payload


def _get_glossaries(settings: SettingsModel) -> list[Glossary] | None:
    glossaries = []
    if not settings.translation.glossaries:
        return None
    for file in settings.translation.glossaries.split(","):
        glossaries.append(
            Glossary.from_csv(Path(file), target_lang_out=settings.translation.lang_out)
        )
    return glossaries


def _map_watermark_mode(mode: str) -> BabelDOCWatermarkMode:
    """将配置值映射为 BabelDOC 水印枚举，默认回退到带水印模式。"""
    watermark_output_mode_maps = {
        "no_watermark": BabelDOCWatermarkMode.NoWatermark,
        "both": BabelDOCWatermarkMode.Both,
        "watermarked": BabelDOCWatermarkMode.Watermarked,
    }
    return watermark_output_mode_maps.get(mode, BabelDOCWatermarkMode.Watermarked)


def _build_split_strategy(settings: SettingsModel):
    """按配置创建分页切割策略；未设置时返回 None。"""
    if settings.pdf.max_pages_per_part:
        return BabelDOCConfig.create_max_pages_per_part_split_strategy(
            settings.pdf.max_pages_per_part
        )
    return None


def _build_table_model(settings: SettingsModel):
    """根据表格翻译配置决定是否初始化 RapidOCR 表格模型。"""
    should_load_rapidocr = (
        settings.pdf.translate_table_text and not settings.pdf.disable_rapidocr
    )
    if should_load_rapidocr:
        logger.info("Table translation enabled; initializing RapidOCR model")
        from babeldoc.docvision.table_detection.rapidocr import RapidOCRModel

        return RapidOCRModel()
    if settings.pdf.translate_table_text and settings.pdf.disable_rapidocr:
        logger.info(
            "Table translation requested but RapidOCR loading disabled; skipping RapidOCR model initialization"
        )
    else:
        logger.info("Table translation disabled; skipping RapidOCR model initialization")
    return None


def _select_doc_layout_model(settings: SettingsModel) -> DocLayoutModel | None:
    """
    选择文档布局模型。
    - 若开启表格翻译且未禁用 RapidOCR，则返回 None 让 BabelDOC 使用默认布局/检测模型。
    - 其他情况使用轻量 LLM-only stub，避免加载 ONNX 布局模型。
    """
    if settings.pdf.translate_table_text and not settings.pdf.disable_rapidocr:
        logger.info("Using default doc layout model for table translation")
        return None
    return LLM_ONLY_DOC_LAYOUT_MODEL


def create_babeldoc_config(settings: SettingsModel, file: Path) -> BabelDOCConfig:
    if not isinstance(settings, SettingsModel):
        raise ValueError(f"{type(settings)} is not SettingsModel")
    translator = get_translator(settings)
    if translator is None:
        raise ValueError("No translator found")

    split_strategy = _build_split_strategy(settings)
    watermark_mode = _map_watermark_mode(settings.pdf.watermark_output_mode)
    table_model = _build_table_model(settings)
    doc_layout_model = _select_doc_layout_model(settings)

    babeldoc_config = BabelDOCConfig(
        input_file=file,
        font=None,
        pages=settings.pdf.pages,
        output_dir=settings.translation.output,
        doc_layout_model=doc_layout_model,
        translator=translator,
        debug=settings.basic.debug,
        lang_in=settings.translation.lang_in,
        lang_out=settings.translation.lang_out,
        no_dual=settings.pdf.no_dual,
        no_mono=settings.pdf.no_mono,
        qps=settings.translation.qps,
        # 传递原来缺失的参数
        formular_font_pattern=settings.pdf.formular_font_pattern,
        formular_char_pattern=settings.pdf.formular_char_pattern,
        split_short_lines=settings.pdf.split_short_lines,
        short_line_split_factor=settings.pdf.short_line_split_factor,
        disable_rich_text_translate=settings.pdf.disable_rich_text_translate,
        dual_translate_first=settings.pdf.dual_translate_first,
        enhance_compatibility=settings.pdf.enhance_compatibility,
        use_alternating_pages_dual=settings.pdf.use_alternating_pages_dual,
        watermark_output_mode=watermark_mode,
        min_text_length=settings.translation.min_text_length,
        report_interval=settings.report_interval,
        skip_clean=settings.pdf.skip_clean,
        # 添加分割策略
        split_strategy=split_strategy,
        # 添加表格模型，仅在需要翻译表格时
        table_model=table_model,
        skip_scanned_detection=settings.pdf.skip_scanned_detection,
        ocr_workaround=settings.pdf.ocr_workaround,
        custom_system_prompt=settings.translation.custom_system_prompt,
        glossaries=_get_glossaries(settings),
        auto_enable_ocr_workaround=settings.pdf.auto_enable_ocr_workaround,
        pool_max_workers=settings.translation.pool_max_workers,
        auto_extract_glossary=not settings.translation.no_auto_extract_glossary,
        primary_font_family=settings.translation.primary_font_family,
        only_include_translated_page=settings.pdf.only_include_translated_page,
        # BabelDOC v0.5.1 new options
        merge_alternating_line_numbers=not settings.pdf.no_merge_alternating_line_numbers,
        remove_non_formula_lines=not settings.pdf.no_remove_non_formula_lines,
        non_formula_line_iou_threshold=settings.pdf.non_formula_line_iou_threshold,
        figure_table_protection_threshold=settings.pdf.figure_table_protection_threshold,
        skip_formula_offset_calculation=settings.pdf.skip_formula_offset_calculation,
    )
    return babeldoc_config


async def do_translate_async_stream(
    settings: SettingsModel, file: Path | str
) -> AsyncGenerator[dict, None]:
    settings.validate_settings()
    if isinstance(file, str):
        file = Path(file)

    if settings.basic.input_files and len(settings.basic.input_files):
        logger.warning(
            "settings.basic.input_files is for cli & config, "
            "pdf2zh_next.highlevel.do_translate_async_stream will ignore this field "
            "and only translate the file pointed to by the file parameter."
        )

    if not file.exists():
        raise FileNotFoundError(f"file {file} not found")

    # 开始翻译
    translate_func = partial(_translate_in_subprocess, settings, file)

    if settings.basic.debug:
        babeldoc_config = create_babeldoc_config(settings, file)
        logger.debug("debug mode, translate in main process")
        translate_func = partial(babeldoc_translate, translation_config=babeldoc_config)
    else:
        logger.info("translate in subprocess")

    try:
        async for event in translate_func():
            yield event
            if settings.basic.debug:
                logger.debug(event)
            if event["type"] == "finish":
                break
    except TranslationError as e:
        # Log and re-raise structured errors
        logger.error(f"Translation error: {e}")
        if isinstance(e, BabeldocError) and e.original_error:
            logger.error(f"Original babeldoc error: {e.original_error}")
        elif isinstance(e, SubprocessError) and e.traceback_str:
            logger.error(f"Subprocess traceback: {e.traceback_str}")
        # Create an error event to yield to client code
        error_event = {
            "type": "error",
            "error": str(e) if not isinstance(e, SubprocessError) else e.raw_message,
            "error_type": e.__class__.__name__,
            "details": getattr(e, "original_error", "")
            or getattr(e, "traceback_str", "")
            or "",
        }
        yield error_event
        raise  # Re-raise the exception so that the caller can handle it if needed


async def do_translate_file_async(
    settings: SettingsModel, ignore_error: bool = False
) -> int:
    rich_pbar_config = BabelDOCConfig(
        translator=None,
        lang_in=None,
        lang_out=None,
        input_file=None,
        font=None,
        pages=None,
        output_dir=None,
        doc_layout_model=1,
        use_rich_pbar=True,
    )
    progress_context, progress_handler = create_progress_handler(rich_pbar_config)
    input_files = settings.basic.input_files
    assert len(input_files) >= 1, "At least one input file is required"
    settings.basic.input_files = set()

    error_count = 0

    for file in input_files:
        logger.info(f"translate file: {file}")
        # 开始翻译
        with progress_context:
            try:
                async for event in do_translate_async_stream(settings, file):
                    progress_handler(event)
                    if settings.basic.debug:
                        logger.debug(event)
                    if event["type"] == "finish":
                        result = event["translate_result"]
                        logger.info("Translation Result:")
                        logger.info(f"  Original PDF: {result.original_pdf_path}")
                        logger.info(f"  Time Cost: {result.total_seconds:.2f}s")
                        logger.info(f"  Mono PDF: {result.mono_pdf_path or 'None'}")
                        logger.info(f"  Dual PDF: {result.dual_pdf_path or 'None'}")
                        break
                    if event["type"] == "error":
                        error_msg = event.get("error", "Unknown error")
                        error_type = event.get("error_type", "UnknownError")
                        details = event.get("details", "")

                        logger.error(f"Error translating file {file}: {error_msg}")
                        logger.error(f"Error type: {error_type}")
                        if details:
                            logger.error(f"Error details: {details}")

                        error_count += 1
                        if not ignore_error:
                            raise RuntimeError(f"Translation error: {error_msg}")
                        break
            except TranslationError as e:
                # Already logged in do_translate_async_stream
                error_count += 1
                if not ignore_error:
                    raise
            except Exception as e:
                logger.error(f"Error translating file {file}: {e}")
                error_count += 1
                if not ignore_error:
                    raise

    return error_count


def do_translate_file(settings: SettingsModel, ignore_error: bool = False) -> int:
    """
    Translate files synchronously, returning the number of errors encountered.

    Args:
        settings: Translation settings
        ignore_error: If True, continue translating other files when an error occurs

    Returns:
        Number of errors encountered during translation

    Raises:
        TranslationError: If a translation error occurs and ignore_error is False
        Exception: For other errors if ignore_error is False
    """
    try:
        return asyncio.run(do_translate_file_async(settings, ignore_error))
    except KeyboardInterrupt:
        logger.info("Translation interrupted by user (Ctrl+C)")
        return 1  # Return error count = 1 to indicate interruption
    except RuntimeError as e:
        # Handle the case where run() is called from a running event loop
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            try:
                return loop.run_until_complete(
                    do_translate_file_async(settings, ignore_error)
                )
            except KeyboardInterrupt:
                logger.info("Translation interrupted by user (Ctrl+C) in event loop")
                return 1  # Return error count = 1 to indicate interruption
        else:
            raise
