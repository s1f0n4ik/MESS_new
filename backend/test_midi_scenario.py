import asyncio
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import main
from midi_config import LEGACY_MAPPING, LEGACY_OUTPUT_NOTE, match_action, migrate_obsolete_mapping

# Реальный поток Reaper (журнал координатора 2026-09-20). После закрывающей волны
# Reaper сам переоткрывает осевшие машины; перед новым кругом делает close→open pc1.
R1 = [61, 63, 65, 67, 68, 66, 64, 62, 61]
R2 = [62, 61, 63, 65, 67, 68, 66, 64, 62, 61, 63]
# Круги 3–4 в журнал не попали — предполагаем ту же схему.
R3 = [62, 61, 64, 63, 65, 67, 68, 66, 64, 62, 61, 63, 65]
R4 = [62, 61, 64, 63, 66, 65, 67, 68, 66, 64, 62, 61, 63, 65, 67]
# Альтернатива: осевшие не трогаются, круг начинается с первой неосевшей машины.
R3_ALT = [65, 67, 68, 66, 64, 62, 61, 63, 65]


def play(notes):
    for n in notes:
        action = match_action(LEGACY_MAPPING, 2, n)["action"]
        main.midi_window_step(action[-3:], action.startswith("open_"))


def win(role):
    return main.STATE["pdfWindowsByRole"][role]


class MidiScenarioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.GLOBAL_SETTINGS["installationMode"] = "exhibition"
        main.hard_reset({"type": "test_setup"})
        main.start_scenario({"type": "click_threshold", "role": "pc1", "clicks": 17})

    def assert_settled(self, count):
        s = main.STATE["scenario"]
        self.assertEqual(s["midiSettled"], count)
        self.assertFalse(s["midiRoundStarted"])
        for index, role in enumerate(main.ROLES, start=1):
            w = win(role)
            self.assertEqual(w["visible"], index <= count, role)
            if index <= count:
                self.assertEqual(w["tabs"], [f"pdf{i}.pdf" for i in range(1, count + 1)])
                self.assertEqual(w["activeTab"], f"pdf{index}.pdf")

    async def test_real_reaper_stream_four_rounds_then_blackout_reset(self):
        for n, rnd in enumerate((R1, R2, R3, R4), start=1):
            play(rnd)
            self.assert_settled(n)
        self.assertEqual(main.STATE["scenario"]["phase"], main.PHASE_CYCLE_SETTLE)

        await main.apply_action("final_black", {"via": "midi"})
        self.assertTrue(main.STATE["scenario"]["blackout"])
        self.assertFalse(any(w["visible"] for w in main.STATE["pdfWindowsByRole"].values()))

        await main.apply_action("launch", {"via": "midi"})
        self.assertEqual(main.STATE["scenario"]["phase"], main.PHASE_IDLE)
        self.assertFalse(main.STATE["scenario"]["blackout"])
        self.assertEqual(main.STATE["clicksByRole"]["pc1"], 0)
        self.assertFalse(main.STATE["clickScenarioLockedByRole"]["pc1"])

    def test_alternative_round_form_gives_same_result(self):
        play(R1); play(R2); play(R3_ALT)
        self.assert_settled(3)

    def test_content_inside_round_two(self):
        play(R1)
        play([62, 61])                       # Reaper «моргает» pc1 перед кругом 2
        self.assertEqual(main.STATE["scenario"]["waveIndex"], 2)
        self.assertEqual(win("pc1")["tabs"], ["pdf1.pdf", "pdf2.pdf"])
        self.assertEqual(win("pc1")["activeTab"], "pdf2.pdf")
        pc1_before = deepcopy(win("pc1"))
        play([63])
        self.assertEqual(win("pc2")["tabs"], ["pdf2.pdf"])
        self.assertEqual(win("pc1"), pc1_before)          # чужая нота pc1 не трогает
        play([65, 67, 68, 66, 64])
        self.assertTrue(win("pc1")["visible"])
        self.assertFalse(win("pc2")["visible"])
        self.assertEqual(main.STATE["scenario"]["midiSettled"], 1)  # круг ещё идёт
        play([62])
        self.assertEqual(main.STATE["scenario"]["midiSettled"], 2)
        self.assertFalse(any(w["visible"] for w in main.STATE["pdfWindowsByRole"].values()))
        play([61])
        self.assertEqual(win("pc1")["tabs"], ["pdf1.pdf", "pdf2.pdf"])
        self.assertEqual(win("pc1")["activeTab"], "pdf1.pdf")
        play([63])
        self.assertEqual(win("pc2")["activeTab"], "pdf2.pdf")
        self.assert_settled(2)

    def test_duplicates_and_strays_do_not_shift_round(self):
        play([62])                                        # close до любого open
        self.assertEqual(main.STATE["scenario"]["waveIndex"], 0)
        self.assertFalse(main.STATE["scenario"]["midiRoundStarted"])

        play([61])
        snapshot = deepcopy(main.STATE["pdfWindowsByRole"])
        play([61])                                        # дубль open
        self.assertEqual(main.STATE["scenario"]["waveIndex"], 1)
        self.assertEqual(main.STATE["pdfWindowsByRole"], snapshot)

        play([63, 65, 67, 68, 66, 64, 62])
        self.assertEqual(main.STATE["scenario"]["midiSettled"], 1)
        play([62])                                        # дубль close по скрытому pc1
        self.assertEqual(main.STATE["scenario"]["midiSettled"], 1)
        self.assertFalse(main.STATE["scenario"]["midiRoundStarted"])
        play([61])                                        # переоткрытие = оседание, не круг 2
        self.assertFalse(main.STATE["scenario"]["midiRoundStarted"])
        self.assert_settled(1)

    def test_exhibition_timer_is_inert(self):
        play([61])
        before = deepcopy(main.STATE)
        main.STATE["scenario"]["dwellStartedAt"] = 1
        main.STATE["scenario"]["dwellNextAt"] = 1
        self.assertFalse(main.cycle_tick_advance())
        self.assertIsNone(main.STATE["scenario"]["dwellNextAt"])
        before["scenario"]["dwellStartedAt"] = None
        before["scenario"]["dwellNextAt"] = None
        self.assertEqual(main.STATE, before)

    def test_laptop_vibro_turns_on_blackout(self):
        main.GLOBAL_SETTINGS["installationMode"] = "laptop"
        main.hard_reset({"type": "laptop_test"})
        main.STATE["scenario"]["active"] = True
        main.STATE["scenario"]["cyclePhaseRoles"] = list(main.ROLES)
        main.STATE["scenario"]["waveIndex"] = 4
        main.enter_final_hold()
        self.assertTrue(main.cycle_tick_advance())
        self.assertTrue(main.STATE["scenario"]["vibroFired"])
        self.assertTrue(main.STATE["scenario"]["blackout"])
        self.assertFalse(any(w["visible"] for w in main.STATE["pdfWindowsByRole"].values()))

    def test_obsolete_saved_mapping_is_migrated(self):
        obsolete = [dict(x) for x in LEGACY_MAPPING]
        obsolete[-1] = {"channel": 2, "note": 69, "action": "minimize_all_windows"}
        migrated, changed = migrate_obsolete_mapping(obsolete)
        self.assertTrue(changed)
        self.assertEqual(migrated, LEGACY_MAPPING)

    def test_open_pc1_can_safely_autostart_midi_run(self):
        main.hard_reset({"type": "autostart_test"})
        self.assertFalse(main.STATE["scenario"]["active"])
        main.midi_window_step("pc2", True)
        self.assertFalse(main.STATE["scenario"]["active"])
        main.midi_window_step("pc1", True)
        self.assertTrue(main.STATE["scenario"]["active"])
        self.assertEqual(main.STATE["scenario"]["waveIndex"], 1)
        self.assertEqual(win("pc1")["activeTab"], "pdf1.pdf")

    async def test_flip_all_cards_does_not_count_clicks(self):
        before_clicks = deepcopy(main.STATE["clicksByRole"])
        before_scenario = deepcopy(main.STATE["scenario"])
        await main.apply_action("flip_all_cards", {"role": "pc1"})
        self.assertEqual(main.STATE["clicksByRole"], before_clicks)
        self.assertEqual(main.STATE["scenario"], before_scenario)
        self.assertEqual(main.STATE["flipAllSeq"], 1)
        for role in main.ROLES:
            self.assertTrue(all(main.STATE["flippedCardsByRole"][role][str(i)] for i in range(8)))

        await main.apply_action("flip_all_cards", {"role": "pc1"})
        self.assertEqual(main.STATE["clicksByRole"], before_clicks)
        for role in main.ROLES:
            self.assertFalse(any(main.STATE["flippedCardsByRole"][role][str(i)] for i in range(8)))


class ClickCounterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.GLOBAL_SETTINGS["installationMode"] = "exhibition"
        main.hard_reset({"type": "click_counter_test"})

    async def click(self, role, count):
        for card_index in range(count):
            await main.apply_action(
                "click_card",
                {"role": role, "cardIndex": card_index % 8, "listened": True},
            )

    async def test_each_role_has_its_own_counter_and_can_trigger_note_72(self):
        self.assertEqual(LEGACY_OUTPUT_NOTE, 72)
        for trigger_role in main.ROLES:
            with self.subTest(role=trigger_role):
                main.hard_reset({"type": "click_counter_subtest"})
                with patch.object(
                    main.midi_service,
                    "send_scenario_started",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as send_note_72:
                    await self.click(trigger_role, main.CLICK_THRESHOLD - 1)
                    self.assertEqual(main.STATE["clicksByRole"][trigger_role], 16)
                    self.assertFalse(main.STATE["scenario"]["active"])
                    send_note_72.assert_not_awaited()

                    await self.click(trigger_role, 1)
                    await asyncio.sleep(0)

                    self.assertEqual(main.STATE["clicksByRole"][trigger_role], 17)
                    for other_role in set(main.ROLES) - {trigger_role}:
                        self.assertEqual(main.STATE["clicksByRole"][other_role], 0)
                    self.assertTrue(main.STATE["scenario"]["active"])
                    self.assertEqual(main.STATE["scenario"]["trigger"]["role"], trigger_role)
                    send_note_72.assert_awaited_once_with()

    async def test_interleaved_clicks_do_not_merge_between_computers(self):
        with patch.object(
            main.midi_service,
            "send_scenario_started",
            new_callable=AsyncMock,
            return_value=True,
        ) as send_note_72:
            await self.click("pc1", 4)
            await self.click("pc2", 8)
            await self.click("pc3", 12)
            await self.click("pc4", 16)
            self.assertEqual(
                main.STATE["clicksByRole"],
                {"pc1": 4, "pc2": 8, "pc3": 12, "pc4": 16},
            )
            send_note_72.assert_not_awaited()

            await self.click("pc4", 1)
            await asyncio.sleep(0)

            self.assertEqual(
                main.STATE["clicksByRole"],
                {"pc1": 4, "pc2": 8, "pc3": 12, "pc4": 17},
            )
            self.assertEqual(main.STATE["scenario"]["trigger"]["role"], "pc4")
            send_note_72.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
