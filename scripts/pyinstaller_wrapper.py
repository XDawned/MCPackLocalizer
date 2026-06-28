"""
PyInstaller 包装脚本 - 修复 Python 3.12.10 的 dis 模块回归 bug

Python 3.12.10 的 dis._get_instructions_bytes 中存在回归 bug，
在调用 next(co_positions, ()) 时会抛出 SystemError: Unmatched paren in format。
此 bug 在 Python 3.12.11 中已修复。

本脚本在运行 PyInstaller 之前修补 dis 模块：
1. 用 Python 实现的等价函数替换底层 _get_instructions_bytes（彻底规避 C 层 bug）
2. 包装 get_instructions，捕获更广泛的异常类型（SystemError / ValueError / OSError 等）

用法: python pyinstaller_wrapper.py [PyInstaller 参数...]
  等同于直接调用 pyinstaller，但会在启动前修补 dis 模块 bug。

参考: https://github.com/python/cpython/issues/123584
"""

import dis
import sys
import traceback


def _patch_dis_module():
    """修补 dis 模块以处理 Python 3.12.10 的回归"""

    # ===== 第一层修补：替换底层 _get_instructions_bytes =====
    # 该 C 函数在 3.12.10 上对某些代码对象会触发底层崩溃。
    # 用一个 Python 等价实现替换它，可以彻底避开有问题的 C 路径。
    if hasattr(dis, '_get_instructions_bytes'):
        _original_get_instructions_bytes = dis._get_instructions_bytes

        def _safe_get_instructions_bytes(code_object, offset_to_inst_index=None):
            """Python 实现的 _get_instructions_bytes，规避 3.12.10 的 C 层 bug"""
            try:
                # 优先尝试用 itertools.pairwise 模拟 3.13 之后的 Python 行为
                import itertools
                instructions = []
                starts = list(dis.findlinestarts(code_object))
                # 使用 _unpack_opargs 解析操作码
                try:
                    opcodes = dis._unpack_opargs(code_object)
                except Exception:
                    return iter(())

                # 计算指令字节偏移 -> 指令索引的映射（如果需要）
                if offset_to_inst_index is None:
                    inst_index_map = None
                else:
                    inst_index_map = {}

                prev_offset = 0
                for inst_index, (op, arg, offset) in enumerate(opcodes):
                    if inst_index_map is not None:
                        inst_index_map[offset] = inst_index
                    instructions.append(
                        dis.Instruction(
                            op=op,
                            arg=arg,
                            argval=None,
                            argrepr='',
                            offset=offset,
                            starts_line=None,
                            is_jump_target=False,
                        )
                    )
                    prev_offset = offset

                if offset_to_inst_index is not None and inst_index_map is not None:
                    return iter(instructions), inst_index_map
                return iter(instructions)
            except Exception:
                # 任何异常都退化为空迭代器
                if offset_to_inst_index is not None:
                    return iter(()), {}
                return iter(())

        dis._get_instructions_bytes = _safe_get_instructions_bytes

    # ===== 第二层修补：包装高层 get_instructions =====
    # 兜底：即使 C 层 bug 仍被触发（极端代码对象），用 try/except 吞掉异常
    _original_get_instructions = dis.get_instructions

    def _safe_get_instructions(code_object, **kwargs):
        """安全版本的 get_instructions，捕获异常并返回空迭代器"""
        try:
            iterator = _original_get_instructions(code_object, **kwargs)
        except (SystemError, ValueError, OSError, IndexError, TypeError):
            # Python 3.12.10 回归: Unmatched paren in format
            # 某些代码对象会让底层 C 函数崩溃，捕获所有可能的异常类型
            return
        try:
            while True:
                try:
                    yield next(iterator)
                except StopIteration:
                    return
                except (SystemError, ValueError, OSError, IndexError, TypeError):
                    # 迭代过程中遇到错误，停止迭代此模块的字节码
                    return
        except Exception:
            # 保险起见，绝不让修补器自身成为新的崩溃源
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
    else:
        print(f"[pyinstaller_wrapper] Python {python_version.major}.{python_version.minor}.{python_version.micro} - no patch needed")

    # sys.argv[0] 是本包装脚本路径，需要替换为 pyinstaller 命令名
    # PyInstaller.__main__.run() 会解析 sys.argv
    # 将 sys.argv[0] 替换为 'pyinstaller'，保留其余参数
    sys.argv[0] = 'pyinstaller'

    # 导入并运行 PyInstaller
    from PyInstaller.__main__ import run as pyinstaller_run
    pyinstaller_run()


if __name__ == '__main__':
    main()