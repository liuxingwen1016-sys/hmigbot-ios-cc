#!/usr/bin/env python3
"""
截图相似度对比工具

使用感知哈希算法对比 iOS 和 HarmonyOS 截图
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    from PIL import Image
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
    ):
        self.ios_dir = Path(ios_dir)
        self.harmonyos_dir = Path(harmonyos_dir)
        self.hash_size = hash_size
        self.max_distance = hash_size * hash_size  # 最大汉明距离
        self.content_region = content_region
        self.crop_top = crop_top
        self.crop_bottom = crop_bottom

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        if not self.content_region:
            return image

        width, height = image.size
        top = int(height * self.crop_top)
        bottom = int(height * (1.0 - self.crop_bottom))
        if top >= bottom:
            raise ValueError("content crop removes the entire image")
        return image.crop((0, top, width, bottom)).resize((1000, 2000))

    def calculate_similarity(self, img1_path: Path, img2_path: Path) -> Dict:
        """计算两张图片的相似度"""
        try:
            # 打开图片
            img1 = self._prepare_image(Image.open(img1_path))
            img2 = self._prepare_image(Image.open(img2_path))

            # 计算感知哈希
            hash1 = imagehash.phash(img1, hash_size=self.hash_size)
            hash2 = imagehash.phash(img2, hash_size=self.hash_size)

            # 计算汉明距离
            distance = hash1 - hash2

            # 转换为相似度百分比
            similarity = (self.max_distance - distance) / self.max_distance * 100

            # 判定状态
            if similarity >= 95:
                status = "match"
            elif similarity >= 85:
                status = "similar"
            else:
                status = "different"

            return {
                "similarity": round(similarity, 2),
                "distance": int(distance),
                "status": status,
                "hash1": str(hash1),
                "hash2": str(hash2)
            }

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
            "comparison_mode": "content_region" if self.content_region else "full_screen",
            "comparisons": [],
            "summary": {
                "total": 0,
                "matched": 0,
                "similar": 0,
                "different": 0,
                "missing_harmonyos": 0,
                "error": 0,
                "avg_similarity": 0.0
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

            results["comparisons"].append(comparison)

        results["summary"]["total"] = len(ios_images)

        # 计算平均相似度
        if valid_count > 0:
            results["summary"]["avg_similarity"] = round(total_similarity / valid_count, 2)

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

    args = parser.parse_args()

    # 执行对比
    comparator = ScreenshotComparator(
        args.ios_dir,
        args.harmonyos_dir,
        args.hash_size,
        args.content_region,
        args.crop_top,
        args.crop_bottom,
    )
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
    avg = summary.get("avg_similarity", 0)

    if avg >= 85:
        sys.exit(0)  # PASS 或 FAIL-visual
    else:
        sys.exit(1)  # FAIL-functional


if __name__ == '__main__':
    main()
