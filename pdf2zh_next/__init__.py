import warnings

warnings.filterwarnings(
    "ignore",
    message=r"builtin type (SwigPyPacked|SwigPyObject|swigvarlink) has no __module__ attribute",
    category=DeprecationWarning,
)

from pdf2zh_next.config import AnythingLLMSettings
from pdf2zh_next.config import AzureOpenAISettings
from pdf2zh_next.config import AzureSettings
from pdf2zh_next.config import BingSettings
from pdf2zh_next.config import DeepLSettings
from pdf2zh_next.config import DeepSeekSettings
from pdf2zh_next.config import DifySettings
from pdf2zh_next.config import GeminiSettings
from pdf2zh_next.config import GoogleSettings
from pdf2zh_next.config import GrokSettings
from pdf2zh_next.config import GroqSettings
from pdf2zh_next.config import ModelScopeSettings
from pdf2zh_next.config import OllamaSettings
from pdf2zh_next.config import OpenAISettings
from pdf2zh_next.config import QwenMtSettings
from pdf2zh_next.config import SiliconFlowSettings
from pdf2zh_next.config import TencentSettings
from pdf2zh_next.config import XinferenceSettings
from pdf2zh_next.config import ZhipuSettings
from pdf2zh_next.config.main import ConfigManager
from pdf2zh_next.config.model import BasicSettings
from pdf2zh_next.config.model import PDFSettings
from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.config.model import TranslationSettings
from pdf2zh_next.config.model import WatermarkOutputMode
from pdf2zh_next.high_level import create_babeldoc_config
from pdf2zh_next.high_level import do_translate_async_stream
from pdf2zh_next.high_level import do_translate_file
from pdf2zh_next.high_level import do_translate_file_async

# from pdf2zh_next.high_level import translate, translate_stream

__version__ = "2.6.4"
__author__ = "Byaidu, awwaawwa"
__license__ = "AGPL-3.0"
__maintainer__ = "awwaawwa"
__email__ = "aw@funstory.ai"

__all__ = [
    "SettingsModel",
    "BasicSettings",
    "OpenAISettings",
    "BingSettings",
    "GoogleSettings",
    "DeepLSettings",
    "DeepSeekSettings",
    "OllamaSettings",
    "XinferenceSettings",
    "AzureOpenAISettings",
    "ModelScopeSettings",
    "ZhipuSettings",
    "SiliconFlowSettings",
    "TencentSettings",
    "GeminiSettings",
    "AzureSettings",
    "AnythingLLMSettings",
    "DifySettings",
    "GrokSettings",
    "GroqSettings",
    "QwenMtSettings",
    "PDFSettings",
    "TranslationSettings",
    "WatermarkOutputMode",
    "do_translate_file_async",
    "do_translate_file",
    "do_translate_async_stream",
    "create_babeldoc_config",
    "ConfigManager",
    "ClaudeCodeSettings",
]
