WEBHOOK_ENV = "WEBHOOK_BILIBILI"
FORUM_THREAD_PREFIX = "Bilibili 更新"

WATCH_VIDEOS = [
    "BV11kMh6WEe5",
    "BV1FxT966Emy",
    "BV1dEMb6wE2y",
    "BV15yM86PEna",
    "BV16xT966EyV",
    "BV1XQTZ6MEcS",
    "BV1EFMF6QE41",
    "BV18yMA6EE9g",
    "BV1Xi7s6iE3e",
    "BV17gMP6hETy",
    "BV1cUMK6VEzR",
    "BV16DMb6gEt6",
    "BV14qTo6fExY",
]

# Same show can sometimes be uploaded as separate BVIDs. Videos with the same
# key post updates to the same Discord forum thread.
THREAD_KEY_OVERRIDES = {
    "BV1FxT966Emy": "world_is_dancing",
    "BV16xT966EyV": "world_is_dancing",
    "BV1XQTZ6MEcS": "mushoku_tensei",
    "BV1Xi7s6iE3e": "cat_and_dragon",
    "BV16DMb6gEt6": "rick_and_morty_s9",
    "BV14qTo6fExY": "a_record_of_a_mortal_journey",
}

THREAD_TITLES = {
    "BV11kMh6WEe5": "攻壳机动队 THE GHOST IN THE SHELL",
    "world_is_dancing": "擅长跳舞的殿下 世界在起舞",
    "BV1dEMb6wE2y": "与你相恋到生命尽头",
    "BV15yM86PEna": "尼古喵喵",
    "mushoku_tensei": "无职转生 第三季",
    "BV1EFMF6QE41": "描绘直至生命尽头",
    "BV18yMA6EE9g": "穹庐下的魔女",
    "cat_and_dragon": "猫与龙",
    "BV17gMP6hETy": "黄泉的使者",
    "BV1cUMK6VEzR": "魔法光源股份有限公司 第二季",
    "rick_and_morty_s9": "瑞克和莫蒂 第九季",
    "a_record_of_a_mortal_journey": "凡人修仙传",
}
