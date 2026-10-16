import unittest

from glue_apps.shell import title_buttons


class TitleButtonsTest(unittest.TestCase):
    def test_gluemac_draws_its_own_title_bar(self):
        self.assertEqual(title_buttons({"GLUE_SESSION": "gluemac"}), ":")

    def test_bare_window_managers_get_a_close_button(self):
        for session in ("gluewc", "gluewc-noctalia", "gluewc-caelestia",
                        "hyprland-ii", "nvwm"):
            self.assertEqual(title_buttons({"GLUE_SESSION": session}), ":close", session)
        self.assertEqual(title_buttons({"XDG_CURRENT_DESKTOP": "Hyprland"}), ":close")

    def test_full_desktops_keep_their_own_layout(self):
        for desktop in ("KDE", "GNOME", "X-Cinnamon", "XFCE"):
            self.assertIsNone(title_buttons({"XDG_CURRENT_DESKTOP": desktop}), desktop)
        self.assertIsNone(title_buttons({"GLUE_SESSION": "kde-plasma"}))


if __name__ == "__main__":
    unittest.main()
