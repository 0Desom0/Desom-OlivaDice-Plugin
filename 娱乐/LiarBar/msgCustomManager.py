# -*- encoding: utf-8 -*-
import OlivaDiceCore
import LiarBar


def initMsgCustom(bot_info_dict):
    for bot_info_dict_this in bot_info_dict:
        if bot_info_dict_this not in OlivaDiceCore.msgCustom.dictStrCustomDict:
            OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this] = {}
        for dictStrCustom_this in LiarBar.msgCustom.dictStrCustom:
            if dictStrCustom_this not in OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this]:
                OlivaDiceCore.msgCustom.dictStrCustomDict[bot_info_dict_this][dictStrCustom_this] = LiarBar.msgCustom.dictStrCustom[dictStrCustom_this]

        for dictHelpDoc_this in LiarBar.msgCustom.dictHelpDocTemp:
            if bot_info_dict_this not in OlivaDiceCore.helpDocData.dictHelpDoc:
                OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this] = {}
            if dictHelpDoc_this not in OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this]:
                OlivaDiceCore.helpDocData.dictHelpDoc[bot_info_dict_this][dictHelpDoc_this] = LiarBar.msgCustom.dictHelpDocTemp[dictHelpDoc_this]

        try:
            import OlivaDiceNativeGUI
            for dictStrCustomNote_this in LiarBar.msgCustom.dictStrCustomNote:
                if dictStrCustomNote_this not in OlivaDiceNativeGUI.msgCustom.dictStrCustomNote:
                    OlivaDiceNativeGUI.msgCustom.dictStrCustomNote[dictStrCustomNote_this] = LiarBar.msgCustom.dictStrCustomNote[dictStrCustomNote_this]
        except Exception:
            pass

    OlivaDiceCore.msgCustom.dictStrConst.update(LiarBar.msgCustom.dictStrConst)
    OlivaDiceCore.msgCustom.dictGValue.update(LiarBar.msgCustom.dictGValue)
    OlivaDiceCore.msgCustom.dictTValue.update(LiarBar.msgCustom.dictTValue)

    try:
        import OlivaDiceNativeGUI
        OlivaDiceNativeGUI.msgCustom.dictStrCustomNote.update(LiarBar.msgCustom.dictStrCustomNote)
    except Exception:
        pass
