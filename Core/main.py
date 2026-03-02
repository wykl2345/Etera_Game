import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")

import PySide6
import lupa
import yaml
import pygame

from lupa import LuaRuntime
lua = LuaRuntime()
print(lua.eval("1 + 1"))