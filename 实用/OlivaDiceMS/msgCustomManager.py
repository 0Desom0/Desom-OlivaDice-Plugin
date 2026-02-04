# -*- encoding: utf-8 -*-
import OlivOS
import OlivaDiceCore
import OlivaDiceMS

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
        for dictStrCustom_this in OlivaDiceMS.msgCustom.dictStrCustom:
            if dictStrCustom_this not in OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this]:
                OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this][dictStrCustom_this] = OlivaDiceMS.msgCustom.dictStrCustom[dictStrCustom_this]
        if has_NativeGUI:
            for dictStrCustomNote_this in OlivaDiceMS.msgCustom.dictStrCustomNote:
                if dictStrCustomNote_this not in OlivaDiceNativeGUI.msgCustom.dictStrCustomNote:
                    OlivaDiceNativeGUI.msgCustom.dictStrCustomNote[dictStrCustomNote_this] = OlivaDiceMS.msgCustom.dictStrCustomNote[dictStrCustomNote_this]
        for dictHelpDoc_this in OlivaDiceMS.msgCustom.dictHelpDocTemp:
            if dictHelpDoc_this not in OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this]:
                OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this][dictHelpDoc_this] = OlivaDiceMS.msgCustom.dictHelpDocTemp[dictHelpDoc_this]
    OlivaDiceCore.msgCustom.dictStrConst.update(OlivaDiceMS.msgCustom.dictStrConst)
    OlivaDiceCore.msgCustom.dictGValue.update(OlivaDiceMS.msgCustom.dictGValue)
    OlivaDiceCore.msgCustom.dictTValue.update(OlivaDiceMS.msgCustom.dictTValue)
    if has_NativeGUI:
        OlivaDiceNativeGUI.msgCustom.dictStrCustomNote.update(OlivaDiceMS.msgCustom.dictStrCustomNote)
