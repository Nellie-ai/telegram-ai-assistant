from collections.abc import Mapping

from telegram_llm_bot.domain import ProfileName


class ProfileRouter:
    def __init__(self, profiles: Mapping[int, ProfileName]) -> None:
        self._profiles = dict(profiles)

    def resolve(self, user_id: int) -> ProfileName:
        return self._profiles.get(user_id, ProfileName.DEFAULT)

