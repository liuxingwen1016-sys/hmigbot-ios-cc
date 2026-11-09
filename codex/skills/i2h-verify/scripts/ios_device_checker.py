#!/usr/bin/env python3
"""
iOS 设备检测工具

检测 iOS 模拟器和真机设备的可用性
"""
import subprocess
import sys
import json
from typing import Dict, List, Optional, Tuple


class IOSDeviceChecker:
    """iOS 设备检测器"""

    def __init__(self):
        self.simulator_devices = []
        self.physical_devices = []

    def check_xcrun(self) -> bool:
        """检查 xcrun 是否可用（模拟器工具）"""
        try:
            result = subprocess.run(
                ['which', 'xcrun'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"检查 xcrun 失败: {e}", file=sys.stderr)
            return False

    def check_idevice_tools(self) -> bool:
        """检查 libimobiledevice 工具是否可用（真机工具）"""
        try:
            result = subprocess.run(
                ['which', 'idevice_id'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"检查 idevice_id 失败: {e}", file=sys.stderr)
            return False

    def list_simulators(self) -> List[Dict[str, str]]:
        """列出所有 iOS 模拟器"""
        if not self.check_xcrun():
            return []

        try:
            # 获取模拟器列表（JSON 格式）
            result = subprocess.run(
                ['xcrun', 'simctl', 'list', 'devices', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            devices = []

            # 解析设备列表
            for runtime, device_list in data.get('devices', {}).items():
                for device in device_list:
                    if device.get('isAvailable', False):
                        devices.append({
                            'udid': device['udid'],
                            'name': device['name'],
                            'state': device['state'],
                            'runtime': runtime,
                            'type': 'simulator',
                            'booted': device['state'] == 'Booted'
                        })

            self.simulator_devices = devices
            return devices

        except Exception as e:
            print(f"列出模拟器失败: {e}", file=sys.stderr)
            return []

    def list_physical_devices(self) -> List[Dict[str, str]]:
        """列出所有连接的 iOS 真机"""
        if not self.check_idevice_tools():
            return []

        try:
            # 获取设备列表
            result = subprocess.run(
                ['idevice_id', '-l'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return []

            devices = []
            for line in result.stdout.strip().split('\n'):
                udid = line.strip()
                if udid:
                    # 获取设备名称
                    name_result = subprocess.run(
                        ['ideviceinfo', '-u', udid, '-k', 'DeviceName'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    device_name = name_result.stdout.strip() if name_result.returncode == 0 else 'Unknown'

                    devices.append({
                        'udid': udid,
                        'name': device_name,
                        'state': 'Connected',
                        'type': 'physical',
                        'booted': True  # 真机连接即可用
                    })

            self.physical_devices = devices
            return devices

        except Exception as e:
            print(f"列出真机失败: {e}", file=sys.stderr)
            return []

    def get_booted_simulator(self) -> Optional[Dict[str, str]]:
        """获取正在运行的模拟器"""
        simulators = self.list_simulators()
        booted = [d for d in simulators if d['booted']]
        return booted[0] if booted else None

    def get_first_available_device(self) -> Optional[Dict[str, str]]:
        """获取第一个可用设备（优先模拟器）"""
        # 优先使用正在运行的模拟器
        booted_sim = self.get_booted_simulator()
        if booted_sim:
            return booted_sim

        # 其次使用其他可用模拟器
        if self.simulator_devices:
            return self.simulator_devices[0]

        # 最后使用真机
        if self.physical_devices:
            return self.physical_devices[0]

        return None

    def check_all(self) -> Dict[str, any]:
        """检查所有设备"""
        # 检查工具可用性
        xcrun_available = self.check_xcrun()
        idevice_available = self.check_idevice_tools()

        # 列出设备
        simulators = self.list_simulators() if xcrun_available else []
        physical_devices = self.list_physical_devices() if idevice_available else []

        # 统计
        booted_simulators = [d for d in simulators if d['booted']]

        return {
            'tools': {
                'xcrun': xcrun_available,
                'idevice': idevice_available
            },
            'simulators': {
                'total': len(simulators),
                'booted': len(booted_simulators),
                'devices': simulators
            },
            'physical': {
                'total': len(physical_devices),
                'devices': physical_devices
            },
            'available': len(simulators) + len(physical_devices) > 0,
            'recommended': self.get_first_available_device()
        }

    def print_summary(self, result: Dict[str, any]):
        """打印检测摘要"""
        print("=" * 60)
        print("iOS 设备检测结果")
        print("=" * 60)

        # 工具状态
        print("\n📦 工具可用性:")
        print(f"  xcrun (模拟器):     {'✅ 可用' if result['tools']['xcrun'] else '❌ 不可用'}")
        print(f"  idevice (真机):     {'✅ 可用' if result['tools']['idevice'] else '❌ 不可用'}")

        # 模拟器
        print(f"\n📱 iOS 模拟器: {result['simulators']['total']} 个")
        if result['simulators']['total'] > 0:
            print(f"  运行中: {result['simulators']['booted']} 个")
            for device in result['simulators']['devices']:
                status = "🟢 运行中" if device['booted'] else "⚪ 已关机"
                print(f"  - {device['name']} [{status}]")
                print(f"    UDID: {device['udid']}")
        else:
            print("  ⚠️  未找到可用模拟器")

        # 真机
        print(f"\n📲 iOS 真机: {result['physical']['total']} 个")
        if result['physical']['total'] > 0:
            for device in result['physical']['devices']:
                print(f"  - {device['name']} [🟢 已连接]")
                print(f"    UDID: {device['udid']}")
        else:
            print("  ⚠️  未找到连接的真机")

        # 推荐设备
        print("\n🎯 推荐使用:")
        if result['recommended']:
            device = result['recommended']
            device_type = "模拟器" if device['type'] == 'simulator' else "真机"
            print(f"  {device['name']} ({device_type})")
            print(f"  UDID: {device['udid']}")
        else:
            print("  ❌ 无可用设备")

        # 总体状态
        print("\n" + "=" * 60)
        if result['available']:
            print("✅ 状态: iOS 设备可用，可以继续 CHECK-3")
        else:
            print("❌ 状态: 无可用 iOS 设备，CHECK-3 将记为 DEFERRED")
            print("\n恢复条件:")
            if not result['tools']['xcrun']:
                print("  1. 安装 Xcode 和 Command Line Tools")
            else:
                print("  1. 启动 iOS 模拟器（Xcode > Open Developer Tool > Simulator）")
            if not result['tools']['idevice']:
                print("  2. 安装 libimobiledevice（可选，用于真机）")
                print("     brew install libimobiledevice")
        print("=" * 60)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='iOS 设备检测工具')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--quiet', action='store_true', help='静默模式，只输出 UDID')
    parser.add_argument('--type', choices=['simulator', 'physical', 'any'],
                       default='any', help='设备类型')

    args = parser.parse_args()

    checker = IOSDeviceChecker()
    result = checker.check_all()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.quiet:
        device = result['recommended']
        if device:
            print(device['udid'])
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        checker.print_summary(result)
        sys.exit(0 if result['available'] else 1)


if __name__ == '__main__':
    main()
