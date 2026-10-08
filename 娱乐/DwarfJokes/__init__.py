# -*- encoding: utf-8 -*-
"""
暴露给 OlivOS 的入口模块。

这里故意只导入 main，保持和 OlivOS 插件加载约定一致。
OlivOS 加载插件时只需要这个包入口。
"""

from . import main
