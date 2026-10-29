from __future__ import annotations

from topgrade_update.core.engine import UpdateEngine
from topgrade_update.core.models import Config, Update
from topgrade_update.core.provider import UpdateChecker


class PacmanChecker(UpdateChecker):
    name = "pacman"
    label = "Pacman"
    checked = False

    def is_available(self) -> bool:
        return True

    def check(self) -> list[Update]:
        self.checked = True
        return [Update(self.name, "1", "2", self.name)]


class FlatpakChecker(UpdateChecker):
    name = "flatpak"
    label = "Flatpak"
    checked = False

    def is_available(self) -> bool:
        return True

    def check(self) -> list[Update]:
        self.checked = True
        return [Update(self.name, "1", "2", self.name)]


def test_check_all_skips_topgrade_disabled_checkers() -> None:
    pacman = PacmanChecker()
    flatpak = FlatpakChecker()
    engine = UpdateEngine()
    engine.register(pacman)
    engine.register(flatpak)

    results = engine.check_all(Config(), topgrade_disabled={"flatpak"})

    assert [result.source for result in results] == ["pacman"]
    assert pacman.checked is True
    assert flatpak.checked is False
