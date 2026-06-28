"""
PyInstaller 包装脚本 - 修复 Python 3.12.10 的 dis 模块回归 bug

Python 3.12.10 的 dis._get_instructions_bytes 中存在回归 bug，
在调用 next(co_positions, ()) 时会抛出 SystemError: Unmatched paren in format。
此 bug 在 Python 3.12.11 中已修复。

本脚本在运行 PyInstaller 之前修补 dis.get_instructions，
使其在遇到 SystemError 时优雅地跳过有问题的字节码，
而不是让整个构建过程崩溃。

用法: python pyinstaller_wrapper.py [PyInstaller 参数...]
  等同于直接调用 pyinstaller，但会在启动前修补 dis 模块 bug。

参考: https://github.com/python/cpython/issues/123584
"""

import dis
import sys


def _patch_dis_module():
    """修补 dis.get_instructions 以处理 Python 3.12.10 的 SystemError 回归"""

    _original_get_instructions = dis.get_instructions

    def _safe_get_instructions(code_object):
        """安全版本的 get_instructions，捕获 SystemError 并返回空迭代器"""
        try:
            iterator = _original_get_instructions(code_object)
        except SystemError:
            # Python 3.12.10 回归: Unmatched paren in format
            # 无法创建迭代器，返回空迭代器
            return
        while True:
            try:
                yield next(iterator)
            except StopIteration:
                return
            except SystemError:
                # Python 3.12.10 回归: Unmatched paren in format
                # 迭代过程中遇到错误，停止迭代此模块的字节码
                # PyInstaller 将跳过此模块的依赖分析
                return

    dis.get_instructions = _safe_get_instructions
    print("[pyinstaller_wrapper] Patched dis.get_instructions for Python 3.12.10 compatibility")


def main():
    """运行 PyInstaller，传入所有命令行参数"""
    # 对 Python 3.12.x 系列都修补（3.12.10 已确认有 bug，其他小版本安全起见也修补）
    python_version = sys.version_info
    if python_version.major == 3 and python_version.minor >= 12:
        _patch_dis_module()
    elif python_version.major == 3 and python_version.minor == 10 and python_version.micro == 0:
        # Python 3.10.0 也可能有类似问题
        _patch_dis_module()

    # sys.argv[0] 是本包装脚本路径，需要替换为 pyinstaller 命令名
    # PyInstaller.__main__.run() 会解析 sys.argv
    # 将 sys.argv[0] 替换为 'pyinstaller'，保留其余参数
    sys.argv[0] = 'pyinstaller'

    # 导入并运行 PyInstaller
    from PyInstaller.__main__ import run as pyinstaller_run
    pyinstaller_run()


if __name__ == '__main__':
    main()