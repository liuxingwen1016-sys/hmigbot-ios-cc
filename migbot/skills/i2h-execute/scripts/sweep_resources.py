#!/usr/bin/env python3
"""
Sweep Resources

用途: 扫描代码中的资源引用，转换缺失的 iOS 资源到 HarmonyOS 格式
"""

import argparse
import json
import sys
import re
from pathlib import Path
from typing import Set, Dict, List, Any

class ResourceSweeper:
    """资源扫描和转换器"""

    def __init__(self, project_root: str, ios_root: str):
        self.project_root = Path(project_root)
        self.ios_root = Path(ios_root)
        self.hmos_resources = self.project_root / 'entry/src/main/resources'

        self.stats = {
            'total_refs': 0,
            'images': {'found': 0, 'converted': 0, 'missing': 0},
            'colors': {'found': 0, 'converted': 0, 'missing': 0},
            'strings': {'found': 0, 'converted': 0, 'missing': 0}
        }

    def sweep(self, target_dir: str = None) -> Dict[str, Any]:
        """扫描资源引用并转换"""
        print("🔍 开始资源扫描...")

        # 1. 扫描所有 .ets 文件，收集资源引用
        refs = self._collect_resource_refs(target_dir)

        # 2. 检查哪些资源已存在
        existing = self._check_existing_resources(refs)

        # 3. 转换缺失的资源
        missing = self._get_missing_resources(refs, existing)
        converted = self._convert_missing_resources(missing)

        # 4. 生成报告
        report = self._generate_report(refs, existing, converted)

        return report

    def _collect_resource_refs(self, target_dir: str = None) -> Dict[str, Set[str]]:
        """收集所有资源引用"""
        print("\n📂 收集资源引用...")

        search_dir = self.project_root / (target_dir or 'entry/src/main/ets')
        refs = {
            'images': set(),
            'colors': set(),
            'strings': set()
        }

        # 正则表达式匹配 $r('app.type.name')
        pattern = re.compile(r"\$r\('app\.(media|color|string)\.(\w+)'\)")

        for ets_file in search_dir.rglob('*.ets'):
            try:
                content = ets_file.read_text(encoding='utf-8')

                for match in pattern.finditer(content):
                    res_type = match.group(1)
                    res_name = match.group(2)

                    if res_type == 'media':
                        refs['images'].add(res_name)
                    elif res_type == 'color':
                        refs['colors'].add(res_name)
                    elif res_type == 'string':
                        refs['strings'].add(res_name)

            except Exception as e:
                print(f"⚠️  读取文件失败: {ets_file}: {e}")

        self.stats['total_refs'] = sum(len(v) for v in refs.values())

        print(f"  - 图片引用: {len(refs['images'])} 个")
        print(f"  - 颜色引用: {len(refs['colors'])} 个")
        print(f"  - 字符串引用: {len(refs['strings'])} 个")
        print(f"  总计: {self.stats['total_refs']} 个")

        return refs

    def _check_existing_resources(self, refs: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
        """检查哪些资源已存在"""
        print("\n✅ 检查已有资源...")

        existing = {
            'images': set(),
            'colors': set(),
            'strings': set()
        }

        # 检查图片
        media_dir = self.hmos_resources / 'base/media'
        if media_dir.exists():
            for img_name in refs['images']:
                # 检查常见图片格式
                for ext in ['.png', '.jpg', '.jpeg', '.svg']:
                    if (media_dir / f"{img_name}{ext}").exists():
                        existing['images'].add(img_name)
                        break

        # 检查颜色
        color_file = self.hmos_resources / 'base/element/color.json'
        if color_file.exists():
            colors = json.loads(color_file.read_text())
            for color_def in colors.get('color', []):
                color_name = color_def.get('name')
                if color_name in refs['colors']:
                    existing['colors'].add(color_name)

        # 检查字符串
        string_file = self.hmos_resources / 'zh_CN/element/string.json'
        if string_file.exists():
            strings = json.loads(string_file.read_text())
            for str_def in strings.get('string', []):
                str_name = str_def.get('name')
                if str_name in refs['strings']:
                    existing['strings'].add(str_name)

        print(f"  - 已有图片: {len(existing['images'])} 个")
        print(f"  - 已有颜色: {len(existing['colors'])} 个")
        print(f"  - 已有字符串: {len(existing['strings'])} 个")

        return existing

    def _get_missing_resources(self, refs: Dict[str, Set[str]],
                               existing: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
        """获取缺失的资源"""
        missing = {
            'images': refs['images'] - existing['images'],
            'colors': refs['colors'] - existing['colors'],
            'strings': refs['strings'] - existing['strings']
        }

        print(f"\n🔍 缺失资源统计:")
        print(f"  - 缺失图片: {len(missing['images'])} 个")
        print(f"  - 缺失颜色: {len(missing['colors'])} 个")
        print(f"  - 缺失字符串: {len(missing['strings'])} 个")

        return missing

    def _convert_missing_resources(self, missing: Dict[str, Set[str]]) -> Dict[str, Any]:
        """转换缺失的资源"""
        print(f"\n🔄 开始转换缺失资源...")

        converted = {
            'images': [],
            'colors': [],
            'strings': [],
            'failed': []
        }

        # 转换图片
        for img_name in missing['images']:
            result = self._convert_image(img_name)
            if result['success']:
                converted['images'].append(result)
                self.stats['images']['converted'] += 1
            else:
                converted['failed'].append(result)
                self.stats['images']['missing'] += 1

        # 转换颜色
        for color_name in missing['colors']:
            result = self._convert_color(color_name)
            if result['success']:
                converted['colors'].append(result)
                self.stats['colors']['converted'] += 1
            else:
                converted['failed'].append(result)
                self.stats['colors']['missing'] += 1

        # 转换字符串
        for str_name in missing['strings']:
            result = self._convert_string(str_name)
            if result['success']:
                converted['strings'].append(result)
                self.stats['strings']['converted'] += 1
            else:
                converted['failed'].append(result)
                self.stats['strings']['missing'] += 1

        print(f"  ✅ 转换成功: {len(converted['images']) + len(converted['colors']) + len(converted['strings'])} 个")
        print(f"  ❌ 转换失败: {len(converted['failed'])} 个")

        return converted

    def _convert_image(self, img_name: str) -> Dict[str, Any]:
        """转换单个图片"""
        # 在 iOS Assets.xcassets 中查找
        assets_dir = self.ios_root / 'Assets.xcassets'

        if not assets_dir.exists():
            return {
                'success': False,
                'type': 'image',
                'name': img_name,
                'reason': 'iOS Assets.xcassets 不存在'
            }

        # 查找图片资源
        image_set = None
        for imageset in assets_dir.rglob(f"{img_name}.imageset"):
            image_set = imageset
            break

        if not image_set:
            # 尝试其他命名方式
            for imageset in assets_dir.rglob("*.imageset"):
                if img_name.lower() in imageset.name.lower():
                    image_set = imageset
                    break

        if not image_set:
            return {
                'success': False,
                'type': 'image',
                'name': img_name,
                'reason': f'在 iOS 项目中未找到'
            }

        # 复制图片到 HarmonyOS
        source_images = list(image_set.glob('*.png')) + list(image_set.glob('*.jpg'))

        if not source_images:
            return {
                'success': False,
                'type': 'image',
                'name': img_name,
                'reason': '未找到实际图片文件'
            }

        # 使用第一个找到的图片（通常是 @1x）
        source_img = source_images[0]
        target_dir = self.hmos_resources / 'base/media'
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / f"{img_name}{source_img.suffix}"

        # 复制文件
        import shutil
        shutil.copy2(source_img, target_path)

        return {
            'success': True,
            'type': 'image',
            'name': img_name,
            'source': str(source_img),
            'target': str(target_path.relative_to(self.project_root))
        }

    def _convert_color(self, color_name: str) -> Dict[str, Any]:
        """转换单个颜色"""
        # 在 iOS Colors.xcassets 中查找
        colors_dir = self.ios_root / 'Colors.xcassets'

        if not colors_dir.exists():
            # 尝试在 Assets.xcassets 中查找
            colors_dir = self.ios_root / 'Assets.xcassets'

        if not colors_dir.exists():
            return {
                'success': False,
                'type': 'color',
                'name': color_name,
                'reason': 'iOS 颜色资源目录不存在'
            }

        # 查找颜色定义
        color_set = None
        for colorset in colors_dir.rglob(f"{color_name}.colorset"):
            color_set = colorset
            break

        if not color_set:
            # 使用默认颜色
            default_color = "#333333"
            return self._add_color_to_json(color_name, default_color,
                                          reason='iOS 中未找到，使用默认值')

        # 读取 Contents.json
        contents_file = color_set / 'Contents.json'
        if not contents_file.exists():
            return {
                'success': False,
                'type': 'color',
                'name': color_name,
                'reason': 'Contents.json 不存在'
            }

        try:
            contents = json.loads(contents_file.read_text())
            colors = contents.get('colors', [])

            if not colors:
                return {
                    'success': False,
                    'type': 'color',
                    'name': color_name,
                    'reason': '颜色定义为空'
                }

            # 获取第一个颜色（light mode）
            color_def = colors[0]
            color_value = color_def.get('color', {})

            # 转换为 HEX
            hex_color = self._rgb_to_hex(color_value)

            return self._add_color_to_json(color_name, hex_color)

        except Exception as e:
            return {
                'success': False,
                'type': 'color',
                'name': color_name,
                'reason': f'解析失败: {e}'
            }

    def _add_color_to_json(self, name: str, value: str, reason: str = None) -> Dict[str, Any]:
        """添加颜色到 color.json"""
        color_file = self.hmos_resources / 'base/element/color.json'
        color_file.parent.mkdir(parents=True, exist_ok=True)

        # 读取或创建 color.json
        if color_file.exists():
            colors = json.loads(color_file.read_text())
        else:
            colors = {'color': []}

        # 添加新颜色
        colors['color'].append({
            'name': name,
            'value': value
        })

        # 写回文件
        color_file.write_text(json.dumps(colors, indent=2, ensure_ascii=False))

        return {
            'success': True,
            'type': 'color',
            'name': name,
            'value': value,
            'reason': reason
        }

    def _rgb_to_hex(self, color_def: Dict[str, Any]) -> str:
        """RGB 转 HEX"""
        try:
            r = int(float(color_def.get('red', '0')) * 255)
            g = int(float(color_def.get('green', '0')) * 255)
            b = int(float(color_def.get('blue', '0')) * 255)
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return "#333333"  # 默认颜色

    def _convert_string(self, str_name: str) -> Dict[str, Any]:
        """转换单个字符串"""
        # 在 iOS Localizable.strings 中查找
        strings_file = self.ios_root / 'zh-Hans.lproj/Localizable.strings'

        if not strings_file.exists():
            strings_file = self.ios_root / 'Base.lproj/Localizable.strings'

        if not strings_file.exists():
            # 使用占位符
            return self._add_string_to_json(str_name, f"TODO: {str_name}",
                                           reason='iOS 中未找到，使用占位符')

        # 读取 .strings 文件
        try:
            content = strings_file.read_text(encoding='utf-8')

            # 查找字符串定义 "key" = "value";
            pattern = rf'"{str_name}"\s*=\s*"([^"]+)";'
            match = re.search(pattern, content)

            if match:
                value = match.group(1)
                return self._add_string_to_json(str_name, value)
            else:
                return self._add_string_to_json(str_name, f"TODO: {str_name}",
                                               reason='在 Localizable.strings 中未找到')

        except Exception as e:
            return {
                'success': False,
                'type': 'string',
                'name': str_name,
                'reason': f'读取失败: {e}'
            }

    def _add_string_to_json(self, name: str, value: str, reason: str = None) -> Dict[str, Any]:
        """添加字符串到 string.json"""
        string_file = self.hmos_resources / 'zh_CN/element/string.json'
        string_file.parent.mkdir(parents=True, exist_ok=True)

        # 读取或创建 string.json
        if string_file.exists():
            strings = json.loads(string_file.read_text())
        else:
            strings = {'string': []}

        # 添加新字符串
        strings['string'].append({
            'name': name,
            'value': value
        })

        # 写回文件
        string_file.write_text(json.dumps(strings, indent=2, ensure_ascii=False))

        return {
            'success': True,
            'type': 'string',
            'name': name,
            'value': value,
            'reason': reason
        }

    def _generate_report(self, refs: Dict[str, Set[str]],
                        existing: Dict[str, Set[str]],
                        converted: Dict[str, Any]) -> Dict[str, Any]:
        """生成报告"""
        report = {
            'summary': {
                'total_refs': self.stats['total_refs'],
                'images': self.stats['images'],
                'colors': self.stats['colors'],
                'strings': self.stats['strings']
            },
            'converted': converted,
            'status': 'SUCCESS' if not converted['failed'] else 'PARTIAL'
        }

        return report

def main():
    parser = argparse.ArgumentParser(description='扫描并转换缺失的资源')
    parser.add_argument('--project-root', required=True, help='HarmonyOS 项目根目录')
    parser.add_argument('--ios-root', required=True, help='iOS 项目根目录')
    parser.add_argument('--target-dir', help='指定扫描目录（相对于 project-root）')
    parser.add_argument('--output', help='输出报告文件路径')

    args = parser.parse_args()

    print("=" * 60)
    print("🔍 Resource Sweeper")
    print("=" * 60)
    print(f"HarmonyOS Project: {args.project_root}")
    print(f"iOS Project: {args.ios_root}")
    print("=" * 60)

    # 创建 sweeper
    sweeper = ResourceSweeper(args.project_root, args.ios_root)

    # 执行 sweep
    report = sweeper.sweep(args.target_dir)

    # 输出报告
    if args.output:
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\n📄 报告已保存: {args.output}")

    # 打印统计
    print("\n" + "=" * 60)
    print("📊 最终统计:")
    print("=" * 60)
    print(f"  图片 - 转换: {report['summary']['images']['converted']}, "
          f"缺失: {report['summary']['images']['missing']}")
    print(f"  颜色 - 转换: {report['summary']['colors']['converted']}, "
          f"缺失: {report['summary']['colors']['missing']}")
    print(f"  字符串 - 转换: {report['summary']['strings']['converted']}, "
          f"缺失: {report['summary']['strings']['missing']}")
    print("=" * 60)

    if report['status'] == 'SUCCESS':
        print("✅ 所有资源已处理")
        return 0
    else:
        print("⚠️  部分资源转换失败")
        return 0  # 不阻断执行

if __name__ == '__main__':
    sys.exit(main())
