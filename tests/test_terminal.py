import subprocess
import unittest

from chip import terminal


class TerminalTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def test_terminal_app(self):
        ok, _ = terminal.open_command("claude attach ab12", "Terminal", runner=self.runner)
        self.assertTrue(ok)
        script = self.calls[0][2]
        self.assertEqual(self.calls[0][:2], ["osascript", "-e"])
        self.assertIn('tell application "Terminal"', script)
        self.assertIn('do script "claude attach ab12"', script)

    def test_iterm_wraps_in_login_shell_and_escapes(self):
        terminal.open_command('echo "hi"', "iTerm", runner=self.runner)
        self.assertIn("/bin/zsh -lc", self.calls[0][2])
        self.assertIn('\\"hi\\"', self.calls[0][2])

    def test_unknown_app(self):
        ok, message = terminal.open_command("x", "Warp", runner=self.runner)
        self.assertFalse(ok)
        self.assertIn("Warp", message)
        self.assertEqual(self.calls, [])

    def test_pick_app_prefers_the_running_terminal(self):
        self.assertEqual(terminal.pick_app("Terminal", {"TERM_PROGRAM": "iTerm.app"}), "iTerm")
        self.assertEqual(terminal.pick_app("iTerm", {}), "iTerm")
        self.assertEqual(terminal.pick_app("Terminal", {"TERM_PROGRAM": "vscode"}), "Terminal")
