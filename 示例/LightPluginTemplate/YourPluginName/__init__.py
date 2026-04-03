# -*- encoding: utf-8 -*-
"""
暴露给 OlivOS 的入口模块。

这里故意只导入 main，保持和 OlivOS 插件加载约定一致。
当用户将整个模板目录复制并重命名时，通常只需要把包名
YourPluginName 做一次全局替换即可。
"""

from . import main
