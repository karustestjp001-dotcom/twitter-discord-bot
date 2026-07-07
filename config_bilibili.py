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
    "BV1i9MP6wEtH",
    "BV17gMP6hETy",
    "BV1cUMK6VEzR",
    "BV16DMb6gEt6",
]

# Same show can sometimes be uploaded as separate BVIDs. Videos with the same
# key post updates to the same Discord forum thread.
THREAD_KEY_OVERRIDES = {
    "BV1FxT966Emy": "world_is_dancing",
    "BV16xT966EyV": "world_is_dancing",
    "BV1XQTZ6MEcS": "mushoku_tensei",
    "BV16DMb6gEt6": "rick_and_morty_s9",
}
