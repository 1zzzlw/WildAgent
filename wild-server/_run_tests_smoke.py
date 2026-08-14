"""临时冒烟测试 runner：用 stdlib unittest 跑测试套件，输出精简汇总。

仅用于本次会话内的回归对照，不属于项目交付物。
用法: .venv\\Scripts\\python.exe _run_tests_smoke.py
"""
import io
import sys
import unittest

sys.path.insert(0, ".")

# 压掉 loguru 噪音
try:
    from loguru import logger
    logger.remove()
except Exception:
    pass


def _names(entries):
    return [name for name, _ in entries]


def main():
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py", top_level_dir=".")
    runner = unittest.TextTestRunner(verbosity=0, stream=io.StringIO())
    result = runner.run(suite)
    failures = _names(result.failures)
    errors = _names(result.errors)
    print(f"SMOKE_RESULT ran={result.testsRun} failures={len(failures)} errors={len(errors)}")
    for name in failures:
        print(f"  FAIL {name}")
    for name in errors:
        print(f"  ERR  {name}")
    sys.exit(0 if (not failures and not errors) else 1)


if __name__ == "__main__":
    main()
