# -*- encoding: utf-8 -*-
# 八卦基本信息 - 用于显示上卦下卦
bagua_info = {
    "000": {"name": "坤", "symbol": "☷", "element": "土"},
    "001": {"name": "艮", "symbol": "☶", "element": "土"},
    "010": {"name": "坎", "symbol": "☵", "element": "水"},
    "011": {"name": "巽", "symbol": "☴", "element": "木"},
    "100": {"name": "震", "symbol": "☳", "element": "木"},
    "101": {"name": "离", "symbol": "☲", "element": "火"},
    "110": {"name": "兑", "symbol": "☱", "element": "金"},
    "111": {"name": "乾", "symbol": "☰", "element": "金"}
}

# 投签用：根据三枚铜钱的正反顺序（正=阳爻=1，反=阴爻=0）选择对应的描述
mortal_identity_dict = {
    1: "[知识阶层]\n身份子项：\n1. 纸质媒体相关（编辑或记者）\n2. 教育从业（自定细节）\n3. 研究人员（自选方向）\n4. 专项官员（如水利、交通、文宣、考古等）",
    2: "[土地依存]\n身份子项：\n1. 种植业（农户、药农）\n2. 林业从业（猎户、守林人等）\n3. 养殖畜牧业（牧民、养殖户等）\n4. 渔业从业者（渔民、水产养殖等）",
    3: "[技术人员]\n身份子项：\n1. 机械工人\n2. 信息技术人员（电脑领域）\n3. 传统手工业者（木工、石匠、金匠、民俗手艺传承人）\n4. 运输行业（邮差、快递员、司机等）",
    4: "[商业贸易]\n身份子项：\n1. 企业白领（管理人员、职业经理人）\n2. 金融业者、银行业者\n3. 小商贩（玉石商人、书店店主等）\n4. 大宗贸易（外贸商人、某方向的工厂主）",
    5: "[医药相关]\n身份子项：\n1. 传统医学传承者（中医、萨满巫医等）\n2. 现代医生\n3. 药物相关（炼药者、药物检测员）\n4. 兽医、宠物医生",
    6: "[法律相关]\n身份子项：\n1. 军伍相关\n2. 警察\n3. 律政相关（律师、法务顾问、普法人员）\n4. 司法相关（法官、检察官、监狱相关）",
    7: "[艺术相关]\n身份子项：\n1. 书画家（西洋画、国画、书法、篆刻等）\n2. 音乐相关（音乐家、演奏家等）\n3. 传统艺人（江湖杂耍、戏法师等）\n4. 表演类（舞蹈演员、影视演员、话剧演员）",
    8: "[旁门九流]\n身份子项：\n1. 殡葬行业者（殡仪师、殓妆师、丧乐演奏）\n2. 贼人（扒手、小偷、盗墓者）\n3. 无业者（乞丐、流浪汉等）\n4. 宗教相关（风水师、算命者、僧道等）\n* 特指在传统观念中“非正统”的职业。",
}

motivation_dict = {
    1: "这是我的责任。",
    2: "偿还我的因果。",
    3: "我受够了被动的恐惧。",
    4: "这是我毕生追求的“真相”。",
    5: "为了自保。",
    6: "拯救所爱之人。",
    7: "这将赋予我生命新的意义与方向。",
    8: "我的才能能更广阔的舞台上发挥作用。",
}

obsession_dict = {
    1: "挥之不去的恐惧。",
    2: "对力量的贪恋。",
    3: "拯救的妄欲。",
    4: "过度的共情。",
    5: "无法忘怀的仇恨。",
    6: "职业惯性。",
    7: "（肉体或心灵上）的成瘾性慰藉。",
    8: "未竟的诺言。",
}

# 六十四卦完整数据
hexagram_data = {
    1: {
        "name": "乾为天",
        "description": "刚金折刃，刚亢独断必崩；化刚为柔，顺势分权则通。",
        "attributes": {
            "金": 3, "水": 3, "木": 3, "火": 3, "土": 3
        },
        "lifespan": 3,
        "special": "【天妒】：当你在投掷吉凶点数时，SG将获得结果中阴爻数量的凶点，最少为1。",
        "name_examples": ["凌锋", "昊阳"],
        "traits": "刚毅果断但易独断专行",
        "upper": "111", "lower": "111"
    },
    2: {
        "name": "坤为地",
        "description": "尘埋窒息，盲从无主必殆；破土见天，跟贤守正则安。",
        "attributes": {
            "金": 1, "水": 1, "木": 1, "火": 1, "土": 1
        },
        "lifespan": 1,
        "special": "【天怜】：一场游戏中有三次机会，当你在检定并得出结果后，你可以调换结果中阴爻与阳爻的数量。",
        "name_examples": ["承壤", "顺慈"],
        "traits": "谦逊包容但易失主见",
        "upper": "000", "lower": "000"
    },
    3: {
        "name": "水雷屯",
        "description": "雷雨没顶，妄动冒进必败；破芽穿石，固本待时则成。",
        "attributes": {
            "金": 2, "水": 3, "木": "2-3", "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["待时", "浚雷"],
        "traits": "逆境中坚韧不拔但冲动冒失",
        "upper": "010", "lower": "100"
    },
    4: {
        "name": "山水蒙",
        "description": "雾锁穷山，愚昧自封必困；凿石引光，虚心求教则明。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["启愚", "师砚"],
        "traits": "懵懂天真或固执己见",
        "upper": "001", "lower": "010"
    },
    5: {
        "name": "水天需",
        "description": "云涌金蚀，急躁涉险必祸；虹桥渡险，耐心守正则达。",
        "attributes": {
            "金": "2-3", "水": 3, "木": 2, "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["云衢", "涉川"],
        "traits": "有远大目标，但易产生急躁、冒险的心态",
        "upper": "010", "lower": "111"
    },
    6: {
        "name": "天水讼",
        "description": "金寒剑冷，争斗不休必伤；炉火煅情，退让自省则吉。",
        "attributes": {
            "金": "1-2", "水": 3, "木": "2-3", "火": 1, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["戒之", "自省"],
        "traits": "争强好胜，言辞犀利，热衷于竞争与辩论，易与人冲突",
        "upper": "111", "lower": "010"
    },
    7: {
        "name": "地水师",
        "description": "泥沼沉沦，将庸兵骄必溃；聚土为垒，任贤持正则胜。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["持正", "垒岳"],
        "traits": "纪律性强，但常常轻信他人",
        "upper": "000", "lower": "010"
    },
    8: {
        "name": "水地比",
        "description": "浊浪吞陆，结党营私必孤；种苇固滩，亲贤诚信则聚。",
        "attributes": {
            "金": "1-2", "水": 3, "木": 2, "火": 1, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["种苇", "信睦"],
        "traits": "亲和友善，善于团结他人，但动机不纯则易陷入小团体斗争",
        "upper": "010", "lower": "000"
    },
    9: {
        "name": "风天小畜",
        "description": "金削薄木，内耗德薄必散；雨润鞘藏，同心积微则丰。",
        "attributes": {
            "金": 2, "水": "1-2", "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["雨裳", "同薪"],
        "traits": "志大才疏，力量有限，易生嫌隙，因小失大",
        "upper": "011", "lower": "111"
    },
    10: {
        "name": "天泽履",
        "description": "金镞穿心，刚愎践危必亡；柔革裹锋，柔顺慎行则全。",
        "attributes": {
            "金": 3, "水": "2-3", "木": 1, "火": "1-2", "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["柔革", "知险"],
        "traits": "勇于实践，却行于险境，刚愎冒进易招致危险",
        "upper": "111", "lower": "110"
    },
    11: {
        "name": "地天泰",
        "description": "天地倾覆，安泰忘危必衰；柱立中宫，居安思危则久。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": "2-3", "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["安澜", "中流"],
        "traits": "通达安稳，万事和谐，但安于享乐，缺乏危机意识",
        "upper": "000", "lower": "111"
    },
    12: {
        "name": "天地否",
        "description": "天地不通，闭塞坐等必绝；凿土通阳，俭德待时则转。",
        "attributes": {
            "金": 3, "水": "2-3", "木": "1-2", "火": 2, "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["通阳", "俭德"],
        "traits": "内向闭塞，消极被动，易与外界隔绝",
        "upper": "111", "lower": "000"
    },
    13: {
        "name": "天火同人",
        "description": "孤阳自焚，党同伐异必失；薪传众焰，至公中正则和。",
        "attributes": {
            "金": 2, "水": 1, "木": "1-2", "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["至公", "中正"],
        "traits": "乐于合作，但心地偏私",
        "upper": "111", "lower": "101"
    },
    14: {
        "name": "火天大有",
        "description": "金玉焚炉，骄奢招恨必覆；土纳火气，富而有德则昌。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["纳丰", "昭明"],
        "traits": "光芒四射，但易骄奢淫逸",
        "upper": "101", "lower": "111"
    },
    15: {
        "name": "地山谦",
        "description": "山崩填谷，卑亢失度必蹇；空穴藏身，劳谦有实则亨。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["有实", "藏锋"],
        "traits": "谦逊有礼，但谦卑过度",
        "upper": "000", "lower": "001"
    },
    16: {
        "name": "雷地豫",
        "description": "地动雷裂，纵乐无度必殃；草茵覆土，乐不忘忧则宁。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["愉慎", "茵宁"],
        "traits": "乐观开朗，但沉溺享乐",
        "upper": "100", "lower": "000"
    },
    17: {
        "name": "泽雷随",
        "description": "雷泽吞舟，盲从失主必乱；顺流弃锚，择善守贞则利。",
        "attributes": {
            "金": 3, "水": "2-3", "木": 1, "火": "1-2", "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["择善", "顺贞"],
        "traits": "随和变通，善于跟随，但盲目跟从，易于迷失自我",
        "upper": "110", "lower": "100"
    },
    18: {
        "name": "山风蛊",
        "description": "虫蚀山崩，讳疾忌医必溃；焚瘴清源，革弊循序则治。",
        "attributes": {
            "金": 2, "水": 1, "木": "2-3", "火": "1-2", "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["清源", "革序"],
        "traits": "容易讳疾忌医，粉饰太平",
        "upper": "001", "lower": "011"
    },
    19: {
        "name": "地泽临",
        "description": "沼泽沉陷，威弛恩滥必垮；垒土成洲，恩威并济则服。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["成洲", "抚众"],
        "traits": "容易过度宽容或过分严厉",
        "upper": "000", "lower": "110"
    },
    20: {
        "name": "风地观",
        "description": "风沙蔽目，浮表闭目必误；立木定风，深察正己则明。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["定风", "观微"],
        "traits": "善于观察，但易流于表面",
        "upper": "011", "lower": "000"
    },
    21: {
        "name": "火雷噬嗑",
        "description": "电火焚身，蛮干硬啃必折；土掩雷息，依法攻键则解。",
        "attributes": {
            "金": 1, "水": "1-2", "木": "2-3", "火": 3, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["依法", "折狱"],
        "traits": "果断坚决，但容易滥用武力",
        "upper": "101", "lower": "100"
    },
    22: {
        "name": "山火贲",
        "description": "彩焰焚身，文过饰非必虚；返素守拙，返朴归真则美。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["守拙", "素心"],
        "traits": "注重自身光彩，但容易显得虚伪",
        "upper": "001", "lower": "101"
    },
    23: {
        "name": "山地剥",
        "description": "根基溃土，根基尽腐必塌；固石承阳，护本蛰伏则存。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["承阳", "固石"],
        "traits": "遇事容易消极应对",
        "upper": "001", "lower": "000"
    },
    24: {
        "name": "地雷复",
        "description": "冻土封根，初愈妄动必挫；一阳破冰，慎微积善则兴。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 3, "火": 2, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["一阳", "慎微"],
        "traits": "面对失败能够重振旗鼓，但容易轻举妄动再遭失败",
        "upper": "000", "lower": "100"
    },
    25: {
        "name": "天雷无妄",
        "description": "金斧伐生，非分妄求必灾；石种深埋，顺道务实则福。",
        "attributes": {
            "金": 3, "水": "2-3", "木": 1, "火": "1-2", "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["顺道", "非妄"],
        "traits": "诚实不虚，但容易心生妄念、非分贪求",
        "upper": "111", "lower": "100"
    },
    26: {
        "name": "山天大畜",
        "description": "金埋矿洞，囤而不用必窒；采炼成器，养贤济世则达。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["养贤", "济世"],
        "traits": "善于积累知识与德行，但囤积吝啬，只蓄不用",
        "upper": "001", "lower": "111"
    },
    27: {
        "name": "山雷颐",
        "description": "石封雷动，贪逸依人必堕；草隙破岩，自力养正则吉。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["养正", "破岩"],
        "traits": "注重养生与补给，但贪图口腹之欲",
        "upper": "001", "lower": "100"
    },
    28: {
        "name": "泽风大过",
        "description": "栋折金朽，极端避责必毁；新苗破梁，非常担纲则济。",
        "attributes": {
            "金": 3, "水": "2-3", "木": 1, "火": "1-2", "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["破梁", "非常"],
        "traits": "面对巨大危机时容易逃避责任，需要勇于担当",
        "upper": "110", "lower": "011"
    },
    29: {
        "name": "坎为水",
        "description": "寒渊溺陷，陷而丧志必溺；心火不灭，心亨慎行则脱。",
        "attributes": {
            "金": 3, "水": 3, "木": 2, "火": 1, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["心火", "慎行"],
        "traits": "外柔内刚，但内心容易产生恐惧",
        "upper": "010", "lower": "010"
    },
    30: {
        "name": "离为火",
        "description": "烛烬成灰，暗附失光必灭；添膏续明，自明依正则耀。",
        "attributes": {
            "金": 1, "水": 2, "木": 3, "火": 3, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["续明", "依正"],
        "traits": "光明磊落，富有智慧与热情，但容易依附错误的对象",
        "upper": "101", "lower": "101"
    },
    31: {
        "name": "泽山咸",
        "description": "石髓凝心，情欲蔽智必昏；以泪融盐，感而守贞则合。",
        "attributes": {
            "金": 3, "水": 2, "木": 1, "火": "1-2", "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["守贞", "感心"],
        "traits": "感性敏锐，易受情感触动",
        "upper": "110", "lower": "001"
    },
    32: {
        "name": "雷风恒",
        "description": "风雷摧柱，守常不变必僵；石础深埋，持中有度则久。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["持中", "度久"],
        "traits": "追求稳定，但不知变通",
        "upper": "100", "lower": "011"
    },
    33: {
        "name": "天山遁",
        "description": "山石埋金，当退不退必擒；退藏于林，明退待机则全。",
        "attributes": {
            "金": 3, "水": 2, "木": 1, "火": "1-2", "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["明退", "藏林"],
        "traits": "能够审时度势，但容易不知进退",
        "upper": "111", "lower": "001"
    },
    34: {
        "name": "雷天大壮",
        "description": "金梁折栋，恃强凌弱必折；藤缠固基，用壮守礼则盛。",
        "attributes": {
            "金": 1, "水": 2, "木": 3, "火": "2-3", "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["守礼", "固基"],
        "traits": "充满力量感，但容易滥用力量，恃强凌弱",
        "upper": "100", "lower": "111"
    },
    35: {
        "name": "火地晋",
        "description": "烈日焦土，躁进贪功必滞；借水润离，柔顺自昭则进。",
        "attributes": {
            "金": 1, "水": "1-2", "木": "2-3", "火": 3, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["柔进", "润离"],
        "traits": "追求上进，但容易贪功求快",
        "upper": "101", "lower": "000"
    },
    36: {
        "name": "地火明夷",
        "description": "地裂熔岩，露明招损必伤；掘井汲泉，晦明守正则存。",
        "attributes": {
            "金": 1, "水": 2, "木": "2-3", "火": 3, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["晦明", "存正"],
        "traits": "内心明察却身处黑暗，逆境中锋芒毕露，从而遭受更大伤害",
        "upper": "000", "lower": "101"
    },
    37: {
        "name": "风火家人",
        "description": "薪尽灶冷，家规失序必乱；添炭续炎，严慈有爱则睦。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["严慈", "睦序"],
        "traits": "重视内在秩序，但容易失之偏颇",
        "upper": "011", "lower": "101"
    },
    38: {
        "name": "火泽睽",
        "description": "焰灼湖涸，猜疑背道必孤；雨降天恩，求同存异则通。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["求同", "存异"],
        "traits": "与人乖离，容易相互猜疑",
        "upper": "101", "lower": "110"
    },
    39: {
        "name": "水山蹇",
        "description": "冰封悬瀑，遇险盲冲必困；凿火暖壑，止而反身则解。",
        "attributes": {
            "金": 2, "水": 3, "木": "2-3", "火": "1-2", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["止困", "暖壑"],
        "traits": "为人直率，但容易盲目向前，愈陷愈深",
        "upper": "010", "lower": "001"
    },
    40: {
        "name": "雷水解",
        "description": "雷雨溃堤，积患不除必复；疏渠导流，赦过宥罪则释。",
        "attributes": {
            "金": "1-2", "水": "2-3", "木": 3, "火": 2, "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["宥罪", "释患"],
        "traits": "善于解困，但易积患未除",
        "upper": "100", "lower": "010"
    },
    41: {
        "name": "山泽损",
        "description": "泽涸石裂，损下益上必叛；引泉润壑，损己悦人则得。",
        "attributes": {
            "金": "2-3", "水": 1, "木": "1-2", "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["悦人", "引泉"],
        "traits": "愿意减损自己以成就他人，但容易使自己根基受损",
        "upper": "001", "lower": "110"
    },
    42: {
        "name": "风雷益",
        "description": "雷劈空谷，施惠无节必耗；植林引电，利众顺势则长。",
        "attributes": {
            "金": 1, "水": 2, "木": 3, "火": "2-3", "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["利众", "植林"],
        "traits": "懂得施与，但施惠无度、没有节制",
        "upper": "011", "lower": "100"
    },
    43: {
        "name": "泽天夬",
        "description": "金锋决堤，除恶不决必反；柔网兜流，刚决柔化则胜。",
        "attributes": {
            "金": 3, "水": "2-3", "木": 1, "火": "1-2", "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["刚决", "化流"],
        "traits": "刚毅，善决断，但方式过于强硬会处处树敌",
        "upper": "110", "lower": "111"
    },
    44: {
        "name": "天风姤",
        "description": "滥交蚀骨，阴长失制必危；择木栖身，防微守正则遇。",
        "attributes": {
            "金": 3, "水": "2-3", "木": "1-2", "火": 1, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["防微", "守正"],
        "traits": "人缘好，但常常会滥交朋友从而导致危险",
        "upper": "111", "lower": "011"
    },
    45: {
        "name": "泽地萃",
        "description": "腐草生瘴，聚邪无主必散；焚原启新，诚敬感神则聚。",
        "attributes": {
            "金": 3, "水": 2, "木": 1, "火": "1-2", "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["诚敬", "荟新"],
        "traits": "善于凝聚众人，但易于鱼龙混杂",
        "upper": "110", "lower": "000"
    },
    46: {
        "name": "地风升",
        "description": "腐木蚀基，攀附无实必坠；火煅新生，积小用柔则达。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["积柔", "煅新"],
        "traits": "追求进步，但基础不固",
        "upper": "000", "lower": "011"
    },
    47: {
        "name": "泽水困",
        "description": "涸泽囚龙，言失志穷必绝；掘地通源，守道致命则亨。",
        "attributes": {
            "金": 3, "水": "2-3", "木": "1-2", "火": 1, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["守道", "通源"],
        "traits": "能力突出，但困于逆境时常常会怨天尤人，难以保守本心",
        "upper": "110", "lower": "010"
    },
    48: {
        "name": "水风井",
        "description": "枯井窒息，固敝不修必废；淘泉引活，养人润物则用。",
        "attributes": {
            "金": 2, "水": 3, "木": "2-3", "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["引泉", "养人"],
        "traits": "善于滋养他人，但易于故步自封，难以自省",
        "upper": "010", "lower": "011"
    },
    49: {
        "name": "泽火革",
        "description": "熔金蚀骨，革而不当必乱；引水淬锋，顺天应人则新。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["淬锋", "应人"],
        "traits": "勇于变革，破旧立新，但常常会时机不当或行为过激",
        "upper": "110", "lower": "101"
    },
    50: {
        "name": "火风鼎",
        "description": "金镬烹身，任非其位必覆；投木熄沸，正位凝命则定。",
        "attributes": {
            "金": 1, "水": "1-2", "木": "2-3", "火": 3, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["凝命", "正位"],
        "traits": "稳重可靠，但遇到不擅长的领域时，容易手足无措",
        "upper": "101", "lower": "011"
    },
    51: {
        "name": "震为雷",
        "description": "霹雳碎形，惊惶失据必溃；地导雷息，内省修身则安。",
        "attributes": {
            "金": 2, "水": 3, "木": 3, "火": 2, "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["省身", "地宁"],
        "traits": "遭遇突发情况时容易惊慌失措，难以从容面对",
        "upper": "100", "lower": "100"
    },
    52: {
        "name": "艮为山",
        "description": "石崩压顶，止而不动必滞；植木固岩，当止则止则明。",
        "attributes": {
            "金": 2, "水": 1, "木": 2, "火": 3, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["知止", "静岳"],
        "traits": "稳重安静，能适可而止，但过于笨拙、不知变通",
        "upper": "001", "lower": "001"
    },
    53: {
        "name": "风山渐",
        "description": "风蚀岩碎，欲速不达必弃；种籽成林，循序守正则归。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["成林", "归序"],
        "traits": "行动力强，但急于求成、妄想一步登天",
        "upper": "011", "lower": "001"
    },
    54: {
        "name": "雷泽归妹",
        "description": "雷激泽沸，强合失礼必咎；荷盖平波，宁缺守节则宜。",
        "attributes": {
            "金": "2-3", "水": "1-2", "木": 3, "火": 2, "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["平波", "宜贞"],
        "traits": "喜于追求自身欲望，但常常会动机不纯",
        "upper": "100", "lower": "110"
    },
    55: {
        "name": "雷火丰",
        "description": "霹雳焚林，盈满蔽明必暗；雨润雷息，戒骄持中则保。",
        "attributes": {
            "金": 1, "水": "1-2", "木": "2-3", "火": 3, "土": 2
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["持中", "保丰"],
        "traits": "当拥有较大成果时，容易骄傲自满",
        "upper": "100", "lower": "101"
    },
    56: {
        "name": "火山旅",
        "description": "焚途焦骨，漂泊失所必哀；汲泉沃足，柔顺守小则安。",
        "attributes": {
            "金": 1, "水": "1-2", "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["沃足", "慎行"],
        "traits": "行事漂泊不定，在外人眼里感觉十分招摇，行为不拘小节",
        "upper": "101", "lower": "001"
    },
    57: {
        "name": "巽为风",
        "description": "无骨随风，过顺无骨必靡；立竿定飓，因势利导则入。",
        "attributes": {
            "金": 2, "水": 2, "木": 3, "火": 3, "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["因势", "入神"],
        "traits": "善于顺从，但缺乏主见",
        "upper": "011", "lower": "011"
    },
    58: {
        "name": "兑为泽",
        "description": "甜泉腐骨，谄媚失真必疑；投盐调性，和悦中正则喜。",
        "attributes": {
            "金": 3, "水": 2, "木": 1, "火": 2, "土": 3
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["中和", "和悦"],
        "traits": "喜悦外向，善于言辞，但常会谄媚奉承、巧言令色",
        "upper": "110", "lower": "110"
    },
    59: {
        "name": "风水涣",
        "description": "风流云散，散而不聚必消；凝冰聚形，凝心济险则救。",
        "attributes": {
            "金": 2, "水": 3, "木": "2-3", "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["凝心", "济险"],
        "traits": "思维灵活，方法极多，但难以抉择，飘忽不定",
        "upper": "011", "lower": "010"
    },
    60: {
        "name": "水泽节",
        "description": "洪流决堤，苦节吝啬必穷；筑土为坝，适度通达则畅。",
        "attributes": {
            "金": "2-3", "水": 3, "木": 2, "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["适度", "通达"],
        "traits": "懂得节制与自律，但容易过分节制、最终变成苦节或者苦修",
        "upper": "010", "lower": "110"
    },
    61: {
        "name": "风泽中孚",
        "description": "信风卷浪，信虚诈伪必败；鹤鸣定波，至诚感物则化。",
        "attributes": {
            "金": 1, "水": 2, "木": 3, "火": "2-3", "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["至诚", "鹤鸣"],
        "traits": "善解人意，但有时会为达目的心口不一",
        "upper": "011", "lower": "110"
    },
    62: {
        "name": "雷山小过",
        "description": "雷劈危崖，过慎失机必蹉；避入深涧，小事恭谨则成。",
        "attributes": {
            "金": "1-2", "水": 2, "木": 3, "火": "2-3", "土": 1
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["恭谨", "避涧"],
        "traits": "难以注意细节，常常会好高骛远，看三步走五步。",
        "upper": "100", "lower": "001"
    },
    63: {
        "name": "水火既济",
        "description": "沸鼎烹身，守成懈怠必衰；金冷调离，思患预防则定。",
        "attributes": {
            "金": 2, "水": 3, "木": "2-3", "火": 1, "土": "1-2"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["思患", "金冷"],
        "traits": "容易在成事的最后一步放松警惕",
        "upper": "010", "lower": "101"
    },
    64: {
        "name": "火水未济",
        "description": "烈火焚舟，无序冒进必溺；引川覆焰，慎辨居方则济。",
        "attributes": {
            "金": "1-2", "水": 1, "木": 2, "火": 3, "土": "2-3"
        },
        "lifespan": None,
        "special": None,
        "name_examples": ["居方", "引川"],
        "traits": "往往事成一半便以为大功告成，从而迷失方向。",
        "upper": "101", "lower": "010"
    }
}

def get_hexagram_by_coins(coins):
    """
    根据六枚铜钱的结果获取卦象
    coins: 长度为6的列表，包含0(阴爻)和1(阳爻)
    返回对应的卦象编号
    """
    # 构建上卦下卦的二进制字符串
    lower = "".join(str(coin) for coin in coins[:3])  # 下卦：第1-3枚
    upper = "".join(str(coin) for coin in coins[3:])  # 上卦：第4-6枚
    
    # 通过上下卦组合查找对应的卦象
    for hex_num, hex_data in hexagram_data.items():
        if hex_data["upper"] == upper and hex_data["lower"] == lower:
            return hex_num
    
    return None

def get_bagua_info(bagua_code):
    """获取八卦信息"""
    return bagua_info.get(bagua_code, {"name": "未知", "symbol": "?", "element": "未知"})

def get_divination_index_by_coins(coins):
    """
    根据三枚铜钱结果获取投签序号
    coins: 长度为3的列表，包含0(反/阴)和1(正/阳)
    返回1-8的序号，对应规则书中的正反组合和D8结果
    """
    if len(coins) != 3 or any(coin not in [0, 1] for coin in coins):
        return None

    return 8 - int("".join(str(coin) for coin in coins), 2)

def resolve_attribute_fluctuation(attribute_value):
    """
    解析五行属性的波动值
    如果是"2-3"格式，返回需要投掷铜钱的标记和取值范围
    如果是固定值，直接返回
    """
    if isinstance(attribute_value, str) and "-" in attribute_value:
        # 波动属性，需要投掷铜钱
        low, high = map(int, attribute_value.split("-"))
        return {"type": "fluctuation", "low": low, "high": high}
    else:
        # 固定属性
        return {"type": "fixed", "value": attribute_value}
