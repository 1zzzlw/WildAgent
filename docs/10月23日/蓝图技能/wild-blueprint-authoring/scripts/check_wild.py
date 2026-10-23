"""从技能任意安装位置运行随包只读WILD检查器，参数原样透传。"""
import runpy
from pathlib import Path

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'references/blueprint-kit/工具/检查WILD.py'
    runpy.run_path(str(target), run_name='__main__')
