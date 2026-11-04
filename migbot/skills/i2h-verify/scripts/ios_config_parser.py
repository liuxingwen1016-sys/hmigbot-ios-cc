#!/usr/bin/env python3
"""
iOS 配置解析工具

解析 iOS Info.plist 和 Assets.xcassets 配置
"""
import plistlib
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


class IOSConfigParser:
    """iOS 配置解析器"""

    def __init__(self, ios_project_root: str):
        self.ios_root = Path(ios_project_root)
        self.info_plist_path = None
        self.assets_path = None

    def find_info_plist(self) -> Optional[Path]:
        """查找 Info.plist 文件"""
        # 常见位置
        candidates = [
            self.ios_root / "Info.plist",
            self.ios_root / "Supporting Files" / "Info.plist",
        ]

        # 查找项目名称对应的目录
        for subdir in self.ios_root.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                candidates.append(subdir / "Info.plist")

        # 递归搜索（限制深度为 3）
        for plist_file in self.ios_root.rglob("Info.plist"):
            if plist_file.is_file() and '.build' not in str(plist_file):
                candidates.append(plist_file)

        # 返回第一个存在的文件
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                self.info_plist_path = candidate
                return candidate

        return None

    def parse_info_plist(self) -> Tuple[Optional[Dict], Optional[str]]:
        """解析 Info.plist"""
        if not self.info_plist_path:
            plist_path = self.find_info_plist()
            if not plist_path:
                return None, "Info.plist not found"

        try:
            with open(self.info_plist_path, 'rb') as f:
                plist_data = plistlib.load(f)

            return {
                'bundle_id': plist_data.get('CFBundleIdentifier', ''),
                'display_name': plist_data.get('CFBundleDisplayName',
                                               plist_data.get('CFBundleName', '')),
                'version': plist_data.get('CFBundleShortVersionString', ''),
                'build': plist_data.get('CFBundleVersion', ''),
                'executable': plist_data.get('CFBundleExecutable', ''),
                'bundle_name': plist_data.get('CFBundleName', ''),
                'raw': plist_data
            }, None

        except Exception as e:
            return None, f"Failed to parse Info.plist: {e}"

    def find_assets_xcassets(self) -> Optional[Path]:
        """查找 Assets.xcassets 目录"""
        for assets_dir in self.ios_root.rglob("Assets.xcassets"):
            if assets_dir.is_dir() and '.build' not in str(assets_dir):
                self.assets_path = assets_dir
                return assets_dir
        return None

    def parse_app_icon(self) -> Tuple[Optional[Dict], Optional[str]]:
        """解析应用图标信息"""
        if not self.assets_path:
            assets_path = self.find_assets_xcassets()
            if not assets_path:
                return None, "Assets.xcassets not found"

        # 查找 AppIcon.appiconset
        appicon_path = self.assets_path / "AppIcon.appiconset"
        if not appicon_path.exists():
            return None, "AppIcon.appiconset not found"

        # 读取 Contents.json
        contents_json = appicon_path / "Contents.json"
        if not contents_json.exists():
            return None, "AppIcon Contents.json not found"

        try:
            with open(contents_json) as f:
                contents = json.load(f)

            images = contents.get('images', [])
            icon_files = []

            for img in images:
                filename = img.get('filename')
                if filename:
                    icon_path = appicon_path / filename
                    size = icon_path.stat().st_size if icon_path.exists() else 0

                    icon_files.append({
                        'filename': filename,
                        'size': img.get('size', ''),
                        'scale': img.get('scale', ''),
                        'idiom': img.get('idiom', ''),
                        'exists': icon_path.exists(),
                        'file_size': size,
                        'path': str(icon_path)
                    })

            return {
                'appiconset_path': str(appicon_path),
                'icons': icon_files,
                'total': len(icon_files),
                'missing': len([f for f in icon_files if not f['exists']])
            }, None

        except Exception as e:
            return None, f"Failed to parse AppIcon: {e}"

    def get_all_config(self) -> Dict:
        """获取所有配置信息"""
        result = {
            'ios_root': str(self.ios_root),
            'info_plist': None,
            'app_icon': None,
            'errors': []
        }

        # 解析 Info.plist
        plist_data, error = self.parse_info_plist()
        if error:
            result['errors'].append(f"Info.plist: {error}")
        else:
            result['info_plist'] = plist_data

        # 解析 AppIcon
        icon_data, error = self.parse_app_icon()
        if error:
            result['errors'].append(f"AppIcon: {error}")
        else:
            result['app_icon'] = icon_data

        return result

    def print_summary(self, config: Dict):
        """打印配置摘要"""
        print("=" * 60)
        print("iOS 配置解析结果")
        print("=" * 60)

        # Info.plist
        print("\n📄 Info.plist:")
        if config['info_plist']:
            info = config['info_plist']
            print(f"  Bundle Identifier:  {info['bundle_id']}")
            print(f"  Display Name:       {info['display_name']}")
            print(f"  Version:            {info['version']}")
            print(f"  Build:              {info['build']}")
            print(f"  Executable:         {info['executable']}")
            print(f"  路径: {self.info_plist_path}")
        else:
            print("  ❌ 解析失败")

        # AppIcon
        print(f"\n🎨 应用图标:")
        if config['app_icon']:
            icon = config['app_icon']
            print(f"  图标集路径: {icon['appiconset_path']}")
            print(f"  图标总数:   {icon['total']}")
            print(f"  缺失图标:   {icon['missing']}")

            if icon['icons']:
                print(f"\n  图标详情:")
                for img in icon['icons'][:5]:  # 只显示前 5 个
                    status = "✅" if img['exists'] else "❌"
                    size_kb = img['file_size'] / 1024 if img['file_size'] > 0 else 0
                    print(f"    {status} {img['filename']} "
                          f"({img['size']} @{img['scale']}) - {size_kb:.1f} KB")

                if len(icon['icons']) > 5:
                    print(f"    ... 还有 {len(icon['icons']) - 5} 个图标")
        else:
            print("  ❌ 解析失败")

        # 错误
        if config['errors']:
            print(f"\n⚠️  错误:")
            for error in config['errors']:
                print(f"  - {error}")

        print("\n" + "=" * 60)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='iOS 配置解析工具')
    parser.add_argument('ios_root', help='iOS 项目根目录')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--plist-only', action='store_true', help='只解析 Info.plist')
    parser.add_argument('--icon-only', action='store_true', help='只解析 AppIcon')

    args = parser.parse_args()

    parser_obj = IOSConfigParser(args.ios_root)

    if args.plist_only:
        plist_data, error = parser_obj.parse_info_plist()
        if args.json:
            print(json.dumps({'info_plist': plist_data, 'error': error},
                           indent=2, ensure_ascii=False))
        else:
            if error:
                print(f"错误: {error}", file=sys.stderr)
                sys.exit(1)
            else:
                for key, value in plist_data.items():
                    if key != 'raw':
                        print(f"{key}: {value}")
    elif args.icon_only:
        icon_data, error = parser_obj.parse_app_icon()
        if args.json:
            print(json.dumps({'app_icon': icon_data, 'error': error},
                           indent=2, ensure_ascii=False))
        else:
            if error:
                print(f"错误: {error}", file=sys.stderr)
                sys.exit(1)
            else:
                print(f"图标集: {icon_data['appiconset_path']}")
                print(f"总数: {icon_data['total']}, 缺失: {icon_data['missing']}")
    else:
        config = parser_obj.get_all_config()
        if args.json:
            # 移除 raw 数据以减少输出
            if config.get('info_plist'):
                config['info_plist'].pop('raw', None)
            print(json.dumps(config, indent=2, ensure_ascii=False))
        else:
            parser_obj.print_summary(config)

        sys.exit(0 if not config['errors'] else 1)


if __name__ == '__main__':
    main()
