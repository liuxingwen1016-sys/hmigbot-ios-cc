#!/usr/bin/env python3
"""
截图相似度对比工具

使用感知哈希算法对比 iOS 和 HarmonyOS 截图
"""
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

try:
    from PIL import Image, ImageChops, ImageStat
    import imagehash
except ImportError:
    print("错误: 需要安装 PIL 和 imagehash", file=sys.stderr)
    print("运行: pip3 install Pillow imagehash", file=sys.stderr)
    sys.exit(1)


class ScreenshotComparator:
    """截图对比器"""

    def __init__(
        self,
        ios_dir: str,
        harmonyos_dir: str,
        hash_size: int = 16,
        content_region: bool = False,
        crop_top: float = 0.05,
        crop_bottom: float = 0.05,
        pixel_metrics: bool = False,
        pixel_threshold: int = 30,
        regions_manifest: Optional[str] = None,
    ):
        self.ios_dir = Path(ios_dir)
        self.harmonyos_dir = Path(harmonyos_dir)
        self.hash_size = hash_size
        self.max_distance = hash_size * hash_size  # 最大汉明距离
        self.content_region = content_region
        self.crop_top = crop_top
        self.crop_bottom = crop_bottom
        self.pixel_metrics = pixel_metrics
        self.pixel_threshold = pixel_threshold
        self.regions_manifest = Path(regions_manifest) if regions_manifest else None
        self._regions_manifest_enabled = self.regions_manifest is not None
        self._region_entries = self._load_regions_manifest()

    def _load_regions_manifest(self) -> Dict[str, Dict]:
        """Load an evidence-bound content-region manifest.

        The legacy ``--content-region`` mode intentionally remains available,
        but it uses fixed percentages and cannot prove that the crop matches
        the app content.  The manifest mode binds a source and target crop to
        the exact screenshot bytes and keeps the full-screen result alongside
        the content result.
        """
        if self.regions_manifest is None:
            return {}
        try:
            payload = json.loads(self.regions_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid regions manifest: {exc}") from exc
        if payload.get("schema") != "i2h-visual-regions/1":
            raise ValueError("regions manifest schema must be i2h-visual-regions/1")
        pages = payload.get("pages")
        if not isinstance(pages, dict):
            raise ValueError("regions manifest pages must be an object")
        return pages

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_rect(value: object, size: tuple[int, int], label: str) -> tuple[int, int, int, int]:
        if not isinstance(value, list) or len(value) != 4 or not all(isinstance(item, int) for item in value):
            raise ValueError(f"{label} must be [x, y, width, height]")
        x, y, width, height = value
        image_width, image_height = size
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > image_width or y + height > image_height:
            raise ValueError(f"{label} is outside image bounds {size}")
        return x, y, width, height

    def _manifest_content_metrics(self, ios_img: Path, harmony_img: Path, entry: Dict) -> Dict:
        """Compare only app content using exact, per-side evidence rectangles."""
        if not isinstance(entry, dict):
            raise ValueError("page entry must be an object")
        evidence = entry.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("page entry is missing evidence binding")
        required = ("source_screenshot_sha256", "target_screenshot_sha256")
        if any(not isinstance(evidence.get(key), str) or not evidence[key] for key in required):
            raise ValueError("page entry is missing screenshot hash binding")
        source_hash = self._sha256(ios_img)
        target_hash = self._sha256(harmony_img)
        if source_hash != evidence["source_screenshot_sha256"]:
            raise ValueError("source screenshot hash does not match manifest")
        if target_hash != evidence["target_screenshot_sha256"]:
            raise ValueError("target screenshot hash does not match manifest")
        source = Image.open(ios_img)
        target = Image.open(harmony_img)
        source_rect = self._validate_rect(entry.get("source_content_rect"), source.size, "source_content_rect")
        target_rect = self._validate_rect(entry.get("target_content_rect"), target.size, "target_content_rect")
        source_crop = source.crop((source_rect[0], source_rect[1], source_rect[0] + source_rect[2], source_rect[1] + source_rect[3]))
        target_crop = target.crop((target_rect[0], target_rect[1], target_rect[0] + target_rect[2], target_rect[1] + target_rect[3]))
        result = self._calculate_pair(source_crop, target_crop)
        result["source_content_rect"] = list(source_rect)
        result["target_content_rect"] = list(target_rect)
        result["system_chrome"] = {
            "excluded_from_content_metric": True,
            "source_rects": entry.get("source_system_chrome_rects", []),
            "target_rects": entry.get("target_system_chrome_rects", []),
        }
        result["evidence_bound"] = True
        return result

    def _calculate_pair(self, img1: Image.Image, img2: Image.Image) -> Dict:
        """Calculate pHash and optional pixel metrics for a prepared pair."""
        prepared1 = img1.convert("RGB")
        prepared2 = img2.convert("RGB")
        hash1 = imagehash.phash(prepared1, hash_size=self.hash_size)
        hash2 = imagehash.phash(prepared2, hash_size=self.hash_size)
        distance = hash1 - hash2
        similarity = (self.max_distance - distance) / self.max_distance * 100
        result = {
            "similarity": round(similarity, 2),
            "distance": int(distance),
            "status": "match" if similarity >= 95 else "similar" if similarity >= 85 else "different",
            "hash1": str(hash1),
            "hash2": str(hash2),
        }
        if self.pixel_metrics:
            first = prepared1.resize((1000, 2000))
            second = prepared2.resize((1000, 2000))
            difference = ImageChops.difference(first, second)
            channel_means = ImageStat.Stat(difference).mean
            mae = sum(channel_means) / len(channel_means)
            changed = difference.convert("L")
            values = list(changed.getdata())
            over_threshold = sum(value > self.pixel_threshold for value in values)
            result.update({
                "pixel_normalized_size": [1000, 2000],
                "pixel_mae": round(mae, 4),
                "pixel_threshold": self.pixel_threshold,
                "pixel_over_threshold_pct": round(over_threshold / len(values) * 100, 4),
            })
        return result

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        if not self.content_region:
            return image

        width, height = image.size
        top = int(height * self.crop_top)
        bottom = int(height * (1.0 - self.crop_bottom))
        if top >= bottom:
            raise ValueError("content crop removes the entire image")
        return image.crop((0, top, width, bottom)).resize((1000, 2000))

    def _prepare_pixel_image(self, image: Image.Image) -> Image.Image:
        prepared = self._prepare_image(image).convert("RGB")
        if prepared.size != (1000, 2000):
            prepared = prepared.resize((1000, 2000))
        return prepared

    def _pixel_metrics(self, img1: Image.Image, img2: Image.Image) -> Dict:
        first = self._prepare_pixel_image(img1)
        second = self._prepare_pixel_image(img2)
        difference = ImageChops.difference(first, second)
        channel_means = ImageStat.Stat(difference).mean
        mae = sum(channel_means) / len(channel_means)
        changed = difference.convert("L")
        values = list(changed.getdata())
        over_threshold = sum(value > self.pixel_threshold for value in values)
        return {
            "pixel_normalized_size": [1000, 2000],
            "pixel_mae": round(mae, 4),
            "pixel_threshold": self.pixel_threshold,
            "pixel_over_threshold_pct": round(over_threshold / len(values) * 100, 4),
        }

    def calculate_similarity(self, img1_path: Path, img2_path: Path) -> Dict:
        """计算两张图片的相似度"""
        try:
            # 打开图片
            img1 = self._prepare_image(Image.open(img1_path))
            img2 = self._prepare_image(Image.open(img2_path))

            return self._calculate_pair(img1, img2)

        except Exception as e:
            return {
                "similarity": 0,
                "distance": self.max_distance,
                "status": "error",
                "error": str(e)
            }

    def compare_all(self) -> Dict:
        """对比所有截图"""
        results = {
            "ios_dir": str(self.ios_dir),
            "harmonyos_dir": str(self.harmonyos_dir),
            "comparison_mode": (
                "evidence_bound_content_and_full_screen" if self._regions_manifest_enabled
                else "content_region" if self.content_region else "full_screen"
            ),
            "regions_manifest": str(self.regions_manifest) if self.regions_manifest else None,
            "comparisons": [],
            "summary": {
                "total": 0,
                "matched": 0,
                "similar": 0,
                "different": 0,
                "missing_harmonyos": 0,
                "error": 0,
                "avg_similarity": 0.0,
                "content_avg_similarity": None,
                "content_gate": "not_configured",
            }
        }

        # 检查目录是否存在
        if not self.ios_dir.exists():
            results["error"] = f"iOS 截图目录不存在: {self.ios_dir}"
            return results

        if not self.harmonyos_dir.exists():
            results["error"] = f"HarmonyOS 截图目录不存在: {self.harmonyos_dir}"
            return results

        # 遍历所有 iOS 截图
        ios_images = sorted(self.ios_dir.glob("*.png"))

        if not ios_images:
            results["error"] = f"iOS 目录中没有 PNG 文件: {self.ios_dir}"
            return results

        print(f"🔍 开始对比截图...")
        print(f"   iOS 目录: {self.ios_dir}")
        print(f"   HarmonyOS 目录: {self.harmonyos_dir}")
        print(f"   截图数量: {len(ios_images)}")
        print()

        total_similarity = 0
        content_total_similarity = 0
        content_valid_count = 0
        valid_count = 0

        for ios_img in ios_images:
            page_name = ios_img.stem
            harmonyos_img = self.harmonyos_dir / ios_img.name

            print(f"   对比: {page_name}...", end=" ")

            comparison = {
                "page": page_name,
                "ios_path": str(ios_img),
                "harmonyos_path": str(harmonyos_img)
            }

            # 检查 HarmonyOS 截图是否存在
            if not harmonyos_img.exists():
                comparison.update({
                    "status": "missing_harmonyos",
                    "similarity": 0,
                    "message": "HarmonyOS 截图缺失"
                })
                results["summary"]["missing_harmonyos"] += 1
                print("❌ HarmonyOS 截图缺失")
            else:
                # 计算相似度
                result = self.calculate_similarity(ios_img, harmonyos_img)
                comparison.update(result)

                if result["status"] == "error":
                    results["summary"]["error"] += 1
                    print(f"❌ 错误: {result.get('error', '未知')}")
                else:
                    similarity = result["similarity"]
                    total_similarity += similarity
                    valid_count += 1

                    if result["status"] == "match":
                        results["summary"]["matched"] += 1
                        print(f"✅ {similarity}% (高度匹配)")
                    elif result["status"] == "similar":
                        results["summary"]["similar"] += 1
                        print(f"⚠️  {similarity}% (轻微差异)")
                    else:
                        results["summary"]["different"] += 1
                        print(f"❌ {similarity}% (差异较大)")

                if self._regions_manifest_enabled and result.get("status") != "error":
                    try:
                        content_result = self._manifest_content_metrics(
                            ios_img, harmonyos_img, self._region_entries.get(page_name)
                        )
                    except (OSError, ValueError) as exc:
                        content_result = {
                            "status": "error",
                            "error": str(exc),
                            "evidence_bound": False,
                        }
                    comparison["application_content"] = content_result
                    if content_result.get("status") != "error":
                        content_total_similarity += content_result["similarity"]
                        content_valid_count += 1

            results["comparisons"].append(comparison)

        results["summary"]["total"] = len(ios_images)

        # 计算平均相似度
        if valid_count > 0:
            results["summary"]["avg_similarity"] = round(total_similarity / valid_count, 2)
        if self._regions_manifest_enabled:
            if content_valid_count:
                results["summary"]["content_avg_similarity"] = round(content_total_similarity / content_valid_count, 2)
                results["summary"]["content_gate"] = (
                    "pass" if content_valid_count == len(ios_images) and results["summary"]["content_avg_similarity"] >= 95 else "fail"
                )
            else:
                results["summary"]["content_gate"] = "fail"

        return results

    def print_summary(self, results: Dict):
        """打印对比摘要"""
        print("\n" + "=" * 60)
        print("截图对比结果")
        print("=" * 60)

        if "error" in results:
            print(f"\n❌ 错误: {results['error']}")
            return

        summary = results["summary"]

        print(f"\n📊 总体统计:")
        print(f"  对比页面数:      {summary['total']}")
        print(f"  高度匹配 (≥95%): {summary['matched']} 页")
        print(f"  良好 (85-95%):   {summary['similar']} 页")
        print(f"  差异较大 (<85%): {summary['different']} 页")
        print(f"  HarmonyOS 缺失:  {summary['missing_harmonyos']} 页")
        print(f"  对比错误:        {summary['error']} 页")
        print(f"  平均相似度:      {summary['avg_similarity']:.1f}%")
        if summary.get("content_avg_similarity") is not None:
            print(f"  应用内容平均相似度: {summary['content_avg_similarity']:.1f}% ({summary['content_gate']})")

        # 匹配率
        if summary['total'] > 0:
            match_rate = summary['matched'] / summary['total'] * 100
            print(f"  匹配率:          {match_rate:.1f}%")

        # 详细列表
        print(f"\n📋 详细结果:")
        for comp in results["comparisons"]:
            page = comp["page"]
            status = comp.get("status", "unknown")
            similarity = comp.get("similarity", 0)

            if status == "match":
                icon = "✅"
            elif status == "similar":
                icon = "⚠️ "
            elif status == "different":
                icon = "❌"
            elif status == "missing_harmonyos":
                icon = "❓"
            else:
                icon = "❌"

            print(f"  {icon} {page}: {similarity:.1f}%")

        # 判定
        print("\n" + "=" * 60)
        avg = summary['avg_similarity']
        if avg >= 95:
            print(f"✅ CHECK-3 判定: PASS (平均相似度 {avg:.1f}%)")
        elif avg >= 85:
            print(f"⚠️  CHECK-3 判定: FAIL-visual (平均相似度 {avg:.1f}%，轻微差异)")
        else:
            print(f"❌ CHECK-3 判定: FAIL-functional (平均相似度 {avg:.1f}%，差异较大)")

        if summary['missing_harmonyos'] > 0:
            print(f"⚠️  警告: 有 {summary['missing_harmonyos']} 个页面缺少 HarmonyOS 截图")

        print("=" * 60)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='截图相似度对比工具')
    parser.add_argument('ios_dir', help='iOS 截图目录')
    parser.add_argument('harmonyos_dir', help='HarmonyOS 截图目录')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--output', '-o', help='输出文件路径')
    parser.add_argument('--hash-size', type=int, default=16,
                       help='感知哈希大小 (默认: 16)')
    parser.add_argument('--content-region', action='store_true',
                       help='裁剪两端顶部和底部系统区域并统一为 1000x2000 后比较')
    parser.add_argument('--crop-top', type=float, default=0.05,
                       help='content-region 顶部裁剪比例 (默认: 0.05)')
    parser.add_argument('--crop-bottom', type=float, default=0.05,
                       help='content-region 底部裁剪比例 (默认: 0.05)')
    parser.add_argument('--pixel-metrics', action='store_true',
                       help='输出归一化像素 MAE 和超过阈值的像素比例，不改变 pHash 门禁')
    parser.add_argument('--pixel-threshold', type=int, default=30,
                       help='像素差阈值 (默认: 30)')
    parser.add_argument('--regions-manifest',
                       help='证据绑定的 iOS/Harmony 应用内容区域清单，输出原始全屏与 content 双指标')

    args = parser.parse_args()

    # 执行对比
    try:
        comparator = ScreenshotComparator(
            args.ios_dir,
            args.harmonyos_dir,
            args.hash_size,
            args.content_region,
            args.crop_top,
            args.crop_bottom,
            args.pixel_metrics,
            args.pixel_threshold,
            args.regions_manifest,
        )
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        sys.exit(2)
    results = comparator.compare_all()

    # 输出结果
    if args.json:
        output = json.dumps(results, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n✅ 结果已保存到: {args.output}")
        else:
            print(output)
    else:
        comparator.print_summary(results)

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n✅ 结果已保存到: {args.output}")

    # 返回状态码
    if "error" in results:
        sys.exit(1)

    summary = results.get("summary", {})
    if args.regions_manifest and summary.get("content_gate") != "pass":
        sys.exit(1)
    avg = summary.get("avg_similarity", 0)

    if avg >= 85:
        sys.exit(0)  # PASS 或 FAIL-visual
    else:
        sys.exit(1)  # FAIL-functional


if __name__ == '__main__':
    main()
