#!/usr/bin/env python3
"""
SwiftUI to ArkTS 批量转换器

集成解析器、映射器和代码生成器，提供完整的转换流程
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import sys

from simple_parser import SimpleSwiftUIParser, SwiftUIViewInfo
from template_mapper import TemplateMapper, ConversionResult
from code_generator import ArkTSCodeGenerator


def simple_progress(iterable, desc="Processing", total=None):
    """简单的进度显示（不依赖 tqdm）"""
    if total is None:
        total = len(list(iterable))

    for i, item in enumerate(iterable, 1):
        percent = (i / total) * 100
        bar_length = 40
        filled = int(bar_length * i / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\r{desc}: [{bar}] {i}/{total} ({percent:.1f}%)", end='', flush=True)
        yield item
    print()  # 换行


@dataclass
class FileConversionResult:
    """单个文件的转换结果"""
    success: bool
    input_file: Path
    output_file: Path
    view_name: str = ""
    properties_count: int = 0
    auto_converted_percent: float = 0.0
    warnings: List[str] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    error: Optional[str] = None
    conversion_time: float = 0.0


@dataclass
class BatchConversionReport:
    """批量转换报告"""
    total_files: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    total_time: float = 0.0
    avg_auto_percent: float = 0.0
    results: List[FileConversionResult] = field(default_factory=list)


class SwiftUIToArkTSConverter:
    """SwiftUI → ArkTS 完整转换器"""

    def __init__(self, mappings_file: Path):
        """
        初始化转换器

        Args:
            mappings_file: 映射规则文件路径
        """
        self.parser = SimpleSwiftUIParser()
        self.mapper = TemplateMapper(mappings_file)
        self.generator = ArkTSCodeGenerator()

        print("✅ SwiftUI to ArkTS Converter initialized")

    def convert_file(self,
                     swift_file: Path,
                     output_file: Path,
                     is_entry: bool = False) -> FileConversionResult:
        """
        转换单个 SwiftUI 文件

        Args:
            swift_file: 输入 .swift 文件
            output_file: 输出 .ets 文件
            is_entry: 是否是入口组件（添加 @Entry）

        Returns:
            FileConversionResult
        """
        start_time = time.time()

        try:
            # 1. 解析 SwiftUI 文件
            view_info = self.parser.parse_file(swift_file)

            if not view_info:
                return FileConversionResult(
                    success=False,
                    input_file=swift_file,
                    output_file=output_file,
                    error="Not a SwiftUI View file",
                    conversion_time=time.time() - start_time
                )

            # 2. 模板映射（转换 body）
            mapping_result = self.mapper.convert_simple_body(view_info.body_source)

            # 3. 生成 ArkTS 代码
            arkts_code = self.generator.generate_from_swiftui(
                view_name=view_info.name,
                properties=[vars(prop) for prop in view_info.properties],
                body_source=mapping_result.arkts_code,
                is_entry=is_entry
            )

            # 4. 写入输出文件
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(arkts_code, encoding='utf-8')

            # 5. 返回结果
            return FileConversionResult(
                success=True,
                input_file=swift_file,
                output_file=output_file,
                view_name=view_info.name,
                properties_count=len(view_info.properties),
                auto_converted_percent=mapping_result.auto_converted_percent,
                warnings=mapping_result.warnings,
                todos=mapping_result.todos,
                conversion_time=time.time() - start_time
            )

        except Exception as e:
            return FileConversionResult(
                success=False,
                input_file=swift_file,
                output_file=output_file,
                error=str(e),
                conversion_time=time.time() - start_time
            )

    def convert_directory(self,
                         input_dir: Path,
                         output_dir: Path,
                         recursive: bool = True,
                         parallel: bool = True,
                         max_workers: int = 8) -> BatchConversionReport:
        """
        批量转换目录中的所有 SwiftUI 文件

        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            recursive: 是否递归子目录
            parallel: 是否并行转换
            max_workers: 最大并发数

        Returns:
            BatchConversionReport
        """
        start_time = time.time()

        # 1. 查找所有 Swift 文件
        if recursive:
            swift_files = list(input_dir.rglob("*.swift"))
        else:
            swift_files = list(input_dir.glob("*.swift"))

        print(f"\n📁 Found {len(swift_files)} Swift files in {input_dir}")

        # 2. 过滤出 SwiftUI View 文件
        print("🔍 Filtering SwiftUI View files...")
        view_files = []
        for swift_file in swift_files:
            if self._is_swiftui_view_file(swift_file):
                view_files.append(swift_file)

        print(f"✅ Found {len(view_files)} SwiftUI View files")

        if not view_files:
            return BatchConversionReport(
                total_files=len(swift_files),
                skipped_count=len(swift_files),
                total_time=time.time() - start_time
            )

        # 3. 转换文件
        results = []

        if parallel and len(view_files) > 1:
            # 并行转换
            results = self._convert_parallel(
                view_files,
                input_dir,
                output_dir,
                max_workers
            )
        else:
            # 串行转换
            results = self._convert_serial(
                view_files,
                input_dir,
                output_dir
            )

        # 4. 生成报告
        report = self._generate_report(results, swift_files, start_time)

        return report

    def _is_swiftui_view_file(self, swift_file: Path) -> bool:
        """快速判断是否是 SwiftUI View 文件"""
        try:
            content = swift_file.read_text(encoding='utf-8')
            return (
                'import SwiftUI' in content and
                ': View' in content and
                'var body' in content
            )
        except Exception:
            return False

    def _convert_parallel(self,
                         view_files: List[Path],
                         input_dir: Path,
                         output_dir: Path,
                         max_workers: int) -> List[FileConversionResult]:
        """并行转换"""
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {}
            for swift_file in view_files:
                # 计算输出路径
                rel_path = swift_file.relative_to(input_dir)
                output_file = output_dir / rel_path.with_suffix('.ets')

                future = executor.submit(
                    self.convert_file,
                    swift_file,
                    output_file
                )
                futures[future] = swift_file

            # 收集结果（带进度条）
            print(f"\n🚀 Converting {len(view_files)} files (parallel, {max_workers} workers)...")
            completed = 0
            for future in simple_progress(as_completed(futures), desc="Converting", total=len(futures)):
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    swift_file = futures[future]
                    print(f"\n❌ Error converting {swift_file}: {e}")

        return results

    def _convert_serial(self,
                       view_files: List[Path],
                       input_dir: Path,
                       output_dir: Path) -> List[FileConversionResult]:
        """串行转换"""
        results = []

        print(f"\n🚀 Converting {len(view_files)} files (serial)...")
        for swift_file in simple_progress(view_files, desc="Converting"):
            # 计算输出路径
            rel_path = swift_file.relative_to(input_dir)
            output_file = output_dir / rel_path.with_suffix('.ets')

            try:
                result = self.convert_file(swift_file, output_file)
                results.append(result)
            except Exception as e:
                print(f"\n❌ Error converting {swift_file}: {e}")

        return results

    def _generate_report(self,
                        results: List[FileConversionResult],
                        all_files: List[Path],
                        start_time: float) -> BatchConversionReport:
        """生成转换报告"""
        success_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        # 计算平均自动转换率
        avg_auto = 0.0
        if success_results:
            avg_auto = sum(r.auto_converted_percent for r in success_results) / len(success_results)

        report = BatchConversionReport(
            total_files=len(all_files),
            success_count=len(success_results),
            failed_count=len(failed_results),
            skipped_count=len(all_files) - len(results),
            total_time=time.time() - start_time,
            avg_auto_percent=avg_auto,
            results=results
        )

        return report

    def print_report(self, report: BatchConversionReport):
        """打印转换报告"""
        print("\n" + "=" * 60)
        print("📊 Conversion Report")
        print("=" * 60)
        print(f"Total files scanned:  {report.total_files}")
        print(f"SwiftUI View files:   {report.success_count + report.failed_count}")
        print(f"Skipped:              {report.skipped_count}")
        print(f"")
        print(f"✅ Success:           {report.success_count}")
        print(f"❌ Failed:            {report.failed_count}")
        print(f"")
        print(f"⏱️  Total time:        {report.total_time:.1f}s")
        print(f"📈 Avg auto-convert:  {report.avg_auto_percent:.1f}%")
        print("=" * 60)

        # 失败文件列表
        if report.failed_count > 0:
            print(f"\n❌ Failed files ({report.failed_count}):")
            failed = [r for r in report.results if not r.success]
            for result in failed[:10]:  # 显示前10个
                print(f"  - {result.input_file}: {result.error}")
            if len(failed) > 10:
                print(f"  ... and {len(failed) - 10} more")

        # 需要人工检查的文件
        needs_review = [r for r in report.results if r.success and r.auto_converted_percent < 80]
        if needs_review:
            print(f"\n⚠️  Files need manual review ({len(needs_review)}):")
            for result in needs_review[:10]:
                print(f"  - {result.input_file.name}: {result.auto_converted_percent:.1f}%")
                if result.todos:
                    for todo in result.todos[:3]:
                        print(f"      • {todo}")

        # 统计信息
        if report.success_count > 0:
            total_properties = sum(r.properties_count for r in report.results if r.success)
            total_warnings = sum(len(r.warnings) for r in report.results if r.success)
            total_todos = sum(len(r.todos) for r in report.results if r.success)

            print(f"\n📊 Statistics:")
            print(f"  Properties converted: {total_properties}")
            print(f"  Warnings:             {total_warnings}")
            print(f"  TODOs:                {total_todos}")


def main():
    """测试函数"""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python batch_converter.py <input_dir> <output_dir> [--parallel]")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    parallel = '--parallel' in sys.argv

    if not input_dir.exists():
        print(f"❌ Input directory not found: {input_dir}")
        sys.exit(1)

    # 映射文件路径
    mappings_file = Path(__file__).parent.parent.parent.parent / "mappings" / "swiftui-to-arkui.json"

    if not mappings_file.exists():
        print(f"❌ Mappings file not found: {mappings_file}")
        sys.exit(1)

    # 创建转换器
    converter = SwiftUIToArkTSConverter(mappings_file)

    # 批量转换
    report = converter.convert_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        recursive=True,
        parallel=parallel,
        max_workers=8
    )

    # 打印报告
    converter.print_report(report)

    # 保存报告到 JSON
    report_file = output_dir / "conversion_report.json"
    report_data = {
        "total_files": report.total_files,
        "success_count": report.success_count,
        "failed_count": report.failed_count,
        "skipped_count": report.skipped_count,
        "total_time": report.total_time,
        "avg_auto_percent": report.avg_auto_percent,
        "results": [
            {
                "input": str(r.input_file),
                "output": str(r.output_file),
                "success": r.success,
                "view_name": r.view_name,
                "auto_percent": r.auto_converted_percent,
                "error": r.error
            }
            for r in report.results
        ]
    }

    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Report saved to: {report_file}")


if __name__ == "__main__":
    main()
