# -*- encoding: utf-8 -*-
'''
这里不要动，这是msgCustom.py的自定义回复管理器，是往GUI中注入自定义回复的地方。
'''

import OlivOS
import OlivaDiceCore
import Blackjack
import os
import json

has_NativeGUI = False
try:
    import OlivaDiceNativeGUI
    has_NativeGUI = True
except ImportError:
    has_NativeGUI = False

def initMsgCustom(bot_info_dict):
    for bot_info_dict_this in bot_info_dict:
        if bot_info_dict_this not in OlivaDiceCore.msgCustom.dictStrCustomDict:
            OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this] = {}
        for dictStrCustom_this in Blackjack.msgCustom.dictStrCustom:
            if dictStrCustom_this not in OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this]:
                OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this][dictStrCustom_this] = Blackjack.msgCustom.dictStrCustom[dictStrCustom_this]
        for dictHelpDoc_this in Blackjack.msgCustom.dictHelpDocTemp:
            if dictHelpDoc_this not in OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this]:
                OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this][dictHelpDoc_this] = Blackjack.msgCustom.dictHelpDocTemp[dictHelpDoc_this]
        if has_NativeGUI:
            for dictStrCustomNote_this in Blackjack.msgCustom.dictStrCustomNote:
                if dictStrCustomNote_this not in OlivaDiceNativeGUI.msgCustom.dictStrCustomNote:
                    OlivaDiceNativeGUI.msgCustom.dictStrCustomNote[dictStrCustomNote_this] = Blackjack.msgCustom.dictStrCustomNote[dictStrCustomNote_this]   
    OlivaDiceCore.msgCustom.dictStrConst.update(Blackjack.msgCustom.dictStrConst)
    OlivaDiceCore.msgCustom.dictGValue.update(Blackjack.msgCustom.dictGValue)
    OlivaDiceCore.msgCustom.dictTValue.update(Blackjack.msgCustom.dictTValue)
    if has_NativeGUI:
        OlivaDiceNativeGUI.msgCustom.dictStrCustomNote.update(Blackjack.msgCustom.dictStrCustomNote)
