"""
SwiftUI to ArkTS Template Converter
基于 SourceKitten 的 SwiftUI AST 解析和模板转换

这是 Critical Path 2 的核心实现
"""

__version__ = "1.0.0-alpha"
__author__ = "iOS Migration Team"

from .parser import SwiftUIParser
from .template_mapper import TemplateMapper
from .code_generator import ArkTSCodeGenerator
from .batch_converter import SwiftUIToArkTSConverter

__all__ = [
    'SwiftUIParser',
    'TemplateMapper',
    'ArkTSCodeGenerator',
    'SwiftUIToArkTSConverter',
]
