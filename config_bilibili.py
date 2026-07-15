WEBHOOK_ENV = "WEBHOOK_BILIBILI"
FORUM_THREAD_PREFIX = "Bilibili 更新"

WATCH_VIDEOS = [
    "BV11kMh6WEe5",
    "BV1smN26sEqQ",
    "BV1dEMb6wE2y",
    "BV1N3MW6aEoQ",
    "BV14JN36oEwX",
    "BV1EFMF6QE41",
    "BV1Xi7s6iE3e",
    "BV1QvNA6CESz",
    "BV15aNN6sECM",
    "BV19CNC68Eiq",
    "BV14qTo6fExY",
    "BV1jhM56oE3t",
]

# Same show can sometimes be uploaded as separate BVIDs. Videos with the same
# key post updates to the same Discord forum thread.
THREAD_KEY_OVERRIDES = {
    "BV1smN26sEqQ": "world_is_dancing",
    "BV1N3MW6aEoQ": "BV15yM86PEna",
    "BV14JN36oEwX": "mushoku_tensei",
    "BV1Xi7s6iE3e": "cat_and_dragon",
    "BV1QvNA6CESz": "BV17gMP6hETy",
    "BV15aNN6sECM": "BV1cUMK6VEzR",
    "BV19CNC68Eiq": "rick_and_morty_s9",
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
    "BV1jhM56oE3t": "雷霆三人行",
}

# Some uploaders publish every episode as a new BVID instead of updating one
# multi-part collection. These rules scan the uploader's archive search and
# route matching new uploads back to the existing forum thread.
UPLOAD_MONITORS = [
    {
        "name": "KAYGEZ",
        "mid": "690151424",
        "thread_key": "BV11kMh6WEe5",
        "keywords": ["攻壳机动队", "GHOST IN THE SHELL"],
    },
    {
        "name": "KAYGEZ",
        "mid": "690151424",
        "thread_key": "BV1EFMF6QE41",
        "keywords": ["描绘直至生命尽头"],
    },
    {
        "name": "KAYGEZ",
        "mid": "690151424",
        "thread_key": "BV1jhM56oE3t",
        "keywords": ["雷霆三人行"],
    },
    {
        "name": "后宫补番",
        "mid": "4262884",
        "thread_key": "BV17gMP6hETy",
        "keywords": ["黄泉的使者"],
    },
    {
        "name": "后宫补番",
        "mid": "4262884",
        "thread_key": "BV1cUMK6VEzR",
        "keywords": ["魔法光源股份有限公司"],
    },
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "world_is_dancing",
        "keywords": ["世界在起舞"],
    },
]

# Anime1 category pages list each episode as a separate WordPress post.  These
# updates are sent to the matching Bilibili forum thread with their version label.
ANIME1_MONITORS = [
    {
        "name": "Anime1",
        "url": "https://anime1.me/category/2026%E5%B9%B4%E5%A4%8F%E5%AD%A3/%E5%B0%BC%E5%8F%A4%E5%96%B5%E5%96%B5",
        "thread_key": "BV15yM86PEna",
        "label": "無刪減版",
    },
]

# Official Bilibili Bangumi episodes are separate BVIDs, so a fixed video
# monitor cannot see the next episode.  These rules follow the season feed.
BANGUMI_MONITORS = [
    {
        "name": "凡人修仙传",
        "season_id": "28747",
        "thread_key": "a_record_of_a_mortal_journey",
    },
]

# YouTube's channel RSS feed is used for official uploads that are not kept in
# a Bilibili collection.
YOUTUBE_MONITORS = [
    {
        "name": "回歸線娛樂",
        "channel_id": "UCBxsPpM2YiwN6phyYgvc4Pw",
        "thread_key": "BV18yMA6EE9g",
        "keywords": ["穹廬下的魔女"],
    },
]
