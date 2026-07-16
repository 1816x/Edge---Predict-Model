"""Pure unit tests for app.features.transactions (no network, no database).

Hand-computed classifier cases, including the pre-2019 "disabled list" wording
that the 2018 backfill must still classify (the DL was renamed the IL in 2019).
"""

from app.features.transactions import il_effect, mentions_il


class TestIlEffect:
    def test_placement_on_injured_list_is_out(self):
        assert (
            il_effect(
                "SC", "Status Change",
                "New York Yankees placed RF Aaron Judge on the 10-day injured list.",
            )
            == 1
        )

    def test_activation_from_injured_list_is_back(self):
        assert (
            il_effect(
                "SC", "Status Change",
                "Los Angeles Angels activated CF Mike Trout from the 10-day injured list.",
            )
            == -1
        )

    def test_transfer_between_il_tiers_keeps_player_out(self):
        # 10-day -> 60-day IL: the player is STILL out, so it is a +1.
        assert (
            il_effect(
                "SC", "Status Change",
                "Chicago Cubs transferred RHP X to the 60-day injured list.",
            )
            == 1
        )

    def test_pre_2019_disabled_list_placement_still_classifies(self):
        # 2018 backfill: MLB called it the DISABLED list before 2019. This is
        # the exact case a naive "injured list"-only matcher would silently
        # miss across a whole season of history.
        assert (
            il_effect(
                "SC", "Status Change",
                "Boston Red Sox placed LHP Y on the 10-day disabled list.",
            )
            == 1
        )

    def test_pre_2019_disabled_list_activation_still_classifies(self):
        assert (
            il_effect(
                "SC", "Status Change",
                "Boston Red Sox activated LHP Y from the 10-day disabled list.",
            )
            == -1
        )

    def test_trade_is_not_an_il_move(self):
        assert (
            il_effect(
                "TR", "Trade",
                "Los Angeles Dodgers traded RF Mookie Betts to the Boston Red Sox.",
            )
            is None
        )

    def test_recall_is_not_an_il_move(self):
        assert il_effect("SC", "Status Change", "Team recalled RHP Z from Triple-A.") is None

    def test_il_mention_without_a_verb_is_unclassified_not_guessed(self):
        # Names the IL but no recognized verb: return None (do not guess), and
        # the caller's drift canary (mentions_il) flags it.
        desc = "Roster note referencing the injured list with no move verb."
        assert il_effect("SC", "Status Change", desc) is None
        assert mentions_il("Status Change", desc) is True

    def test_mentions_il_covers_both_names(self):
        assert mentions_il(None, "placed on the injured list") is True
        assert mentions_il(None, "placed on the disabled list") is True
        assert mentions_il("Trade", "traded to the Red Sox") is False
