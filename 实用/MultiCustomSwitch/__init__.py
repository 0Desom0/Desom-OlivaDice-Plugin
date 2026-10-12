"""强依赖 Core；运行期使用的子模块在 OPK 清理前全部导入。"""

import OlivaDiceCore

from . import api, commands, files, gui, main, msgCustom, resources, runtime, store
