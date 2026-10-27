WEBHOOK_ENV = "WEBHOOK_BILIBILI"
FORUM_THREAD_PREFIX = "Bilibili 更新"

# Keep routing/history for a later season; completed shows have no next-week alarm.
COMPLETED_THREADS = {
    "rick_and_morty_s9": 10,
    "BV11kMh6WEe5": 10,
    "world_is_dancing": 13,
    "BV1dEMb6wE2y": 13,
    "president_curtis_s1": 10,
}

# Manually closed by the user; retain sources/history for possible reactivation.
CLOSED_THREADS = {
    "stuart_fails_to_save_the_universe",
    "BV18yMA6EE9g",
    "BV1EFMF6QE41",
    "mushoku_tensei",
}

WATCH_VIDEOS = [
    "BV1Xi7s6iE3e",
    "BV1QvNA6CESz",
    "BV15aNN6sECM",
    "BV14qTo6fExY",
    "BV1CPJY67E2o",
    "BV1akH96fEjw",
    "BV1yqp46GEdk",
    "BV1Pkph6sEee",
    "BV1nWJX6KEst",
    "BV1GTpn6BEsH",
    "BV1dNpe6jEj3",
    "BV1uWpB6DEXJ",
    "BV1KsHj62Esc",
]

# Same show can sometimes be uploaded as separate BVIDs. Videos with the same
# key post updates to the same Discord forum thread.
THREAD_KEY_OVERRIDES = {
    "BV1smN26sEqQ": "world_is_dancing",
    "BV1jnNY6iEsQ": "BV1dEMb6wE2y",
    "BV1N3MW6aEoQ": "BV15yM86PEna",
    "BV14JN36oEwX": "mushoku_tensei",
    "BV1g13d6gEWf": "mushoku_tensei",
    "BV1Xi7s6iE3e": "cat_and_dragon",
    "BV1QvNA6CESz": "BV17gMP6hETy",
    "BV15aNN6sECM": "BV1cUMK6VEzR",
    "BV14qTo6fExY": "a_record_of_a_mortal_journey",
    "BV1CPJY67E2o": "apothecary_diaries_s3",
    "BV1akH96fEjw": "fx_fighter_kurumi",
    "BV1yqp46GEdk": "student_council_holes",
    "BV1Pkph6sEee": "dark_side_item",
    "BV1nWJX6KEst": "firefly_wedding",
    "BV1GTpn6BEsH": "tank_chair",
    "BV1dNpe6jEj3": "keroro_2026",
    "BV1uWpB6DEXJ": "dark_machine",
    "BV1KsHj62Esc": "dating_dark_summoner",
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
    "stuart_fails_to_save_the_universe": "生活大爆炸衍生劇《斯圖爾特未能拯救宇宙》",
    "president_curtis_s1": "柯蒂斯總統 第一季",
    "apothecary_diaries_s3": "藥師少女的獨語 第三季 前半",
    "fx_fighter_kurumi": "FX 戰士久留美",
    "student_council_holes": "學生會也有洞！",
    "dark_side_item": "暗部共生少女",
    "firefly_wedding": "螢火蟲的出嫁",
    "tank_chair": "戰車椅子 TANK CHAIR",
    "keroro_2026": "Keroro 軍曹☆",
    "dark_machine": "闇機 DARK MACHINE",
    "dating_dark_summoner": "與暗黑召喚師秘密戀愛中",
}

# Some uploaders publish every episode as a new BVID instead of updating one
# multi-part collection. These rules scan the uploader's archive search and
# route matching new uploads back to the existing forum thread.
UPLOAD_MONITORS = [
    {
        "name": "后宫补番",
        "mid": "4262884",
        "thread_key": "apothecary_diaries_s3",
        "keywords": ["药屋少女的呢喃 第三季"],
        "search_keyword": "药屋少女的呢喃 第三季",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "夏日幻听MCE",
        "mid": "224267770",
        "thread_key": "fx_fighter_kurumi",
        "keywords": ["FX战士久留美", "拟股喵喵"],
        "search_keyword": "FX战士久留美",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "夏日幻听MCE",
        "mid": "224267770",
        "thread_key": "student_council_holes",
        "keywords": ["学生会也有洞", "脑洞学生会"],
        "search_keyword": "学生会",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "dark_side_item",
        "keywords": ["某暗部的少女共栖"],
        "search_keyword": "某暗部的少女共栖",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "后宫补番",
        "mid": "4262884",
        "thread_key": "firefly_wedding",
        "keywords": ["萤火虫的出嫁", "萤火虫之婚"],
        "search_keyword": "萤火虫",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "tank_chair",
        "keywords": ["战车椅子"],
        "search_keyword": "战车椅子",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "keroro_2026",
        "keywords": ["Keroro军曹☆ 2026新版"],
        "search_keyword": "Keroro",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "dark_machine",
        "keywords": ["黑暗机器"],
        "search_keyword": "黑暗机器",
        "min_episode_duration": 900,
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "红の甜豌豆",
        "mid": "3546768887253334",
        "thread_key": "dating_dark_summoner",
        "keywords": ["与暗黑召唤师秘密恋爱中", "黑暗召唤师在地下恋爱中"],
        "search_keyword": "召唤师",
        "min_episode_duration": 600,
        "first_page_only": True,
        "require_episode_number": True,
    },
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
        "keywords": ["描绘直至生命尽头", "画完这个再去死", "これ描いて死ね"],
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
    {
        "name": "晓月の诗",
        "mid": "3493112693394137",
        "thread_key": "BV1dEMb6wE2y",
        "keywords": ["与你相恋到生命尽头"],
    },
    {
        "name": "晓月の诗 無職轉生",
        "mid": "3493112693394137",
        "thread_key": "mushoku_tensei",
        "keywords": ["无职转生", "無職轉生", "传奇上锁王", "傳奇上鎖王"],
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "a-skethes",
        "mid": "314790542",
        "thread_key": "stuart_fails_to_save_the_universe",
        "keywords": [
            "斯图尔特未能拯救宇宙",
            "斯圖爾特未能拯救宇宙",
            "Stuart Fails to Save the Universe",
        ],
        "first_page_only": True,
        "require_episode_number": True,
    },
    {
        "name": "a-skethes",
        "mid": "314790542",
        "thread_key": "president_curtis_s1",
        "keywords": [
            "柯蒂斯总统",
            "柯蒂斯總統",
            "President Curtis",
        ],
        "first_page_only": True,
        "require_episode_number": True,
    },
]

# Anime1's official Telegram feed links each update back to its WordPress post.
# Updates are sent to the matching Bilibili forum thread with their version label.
ANIME1_MONITORS = [
    {
        "name": "Anime1 尼古喵喵",
        "url": "https://anime1.me/category/2026%E5%B9%B4%E5%A4%8F%E5%AD%A3/%E5%B0%BC%E5%8F%A4%E5%96%B5%E5%96%B5",
        "feed_url": "https://t.me/s/anime1notify",
        "title_keywords": ["尼古喵喵"],
        "thread_key": "BV15yM86PEna",
        "label": "無刪減版",
    },
    {
        "name": "Anime1 無職轉生 III",
        "url": "https://anime1.me/category/2026%E5%B9%B4%E6%98%A5%E5%AD%A3/%E7%84%A1%E8%81%B7%E8%BD%89%E7%94%9F-%E5%88%B0%E4%BA%86%E7%95%B0%E4%B8%96%E7%95%8C%E5%B0%B1%E6%8B%BF%E5%87%BA%E7%9C%9F%E6%9C%AC%E4%BA%8B-%E7%AC%AC%E4%B8%89%E5%AD%A3",
        "feed_url": "https://t.me/s/anime1notify",
        "title_keywords": ["無職轉生III", "無職轉生 III"],
        "thread_key": "mushoku_tensei",
        "label": "Anime1",
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
