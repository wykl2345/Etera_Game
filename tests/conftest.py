"""
pytest 配置 — Etera_Game 测试套件

将项目根目录加入 sys.path，确保 Core.* 导入可用。
"""

import sys
from pathlib import Path

import pytest

# 项目根目录 (EE1/)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture(scope="session")
def qapp():
    """提供一个 QApplication 实例，供需要 Qt 事件循环的测试使用"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # session 级别，不退出 app
