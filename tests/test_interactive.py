import unittest
from pathlib import Path
from unittest.mock import patch

from pydisktriage.catalog import Finding
from pydisktriage.interactive import (
    render_menu_table,
    render_findings_table,
    select_menu,
    select_finding,
)


class TestInteractive(unittest.TestCase):
    def test_render_menu_table(self):
        options = [("1", "Ação 1"), ("2", "Ação 2"), ("0", "Voltar")]
        table = render_menu_table(options, selected_idx=1)
        self.assertEqual(len(table.rows), 3)

    def test_render_findings_table(self):
        findings = [
            Finding("item1", Path("C:/test1"), "descartavel", 1024, 1, False),
            Finding("item2", Path("C:/test2"), "movivel", 2048, 2, False),
        ]
        table = render_findings_table(findings, selected_idx=0)
        self.assertEqual(len(table.rows), 2)

    @patch("pydisktriage.interactive.Prompt.ask", return_value="2")
    @patch("sys.stdin.isatty", return_value=False)
    def test_select_menu_non_tty_fallback(self, mock_isatty, mock_prompt):
        options = [("1", "Primeiro"), ("2", "Segundo"), ("0", "Sair")]
        choice = select_menu(options, title="Teste", default_key="1")
        self.assertEqual(choice, "2")

    @patch("pydisktriage.interactive._read_key", side_effect=["DOWN", "ENTER"])
    @patch("sys.stdin.isatty", return_value=True)
    def test_select_menu_interactive_keys(self, mock_isatty, mock_read_key):
        options = [("1", "Primeiro"), ("2", "Segundo"), ("0", "Sair")]
        choice = select_menu(options, title="Teste", default_key="1")
        self.assertEqual(choice, "2")

    @patch("pydisktriage.interactive._read_key", side_effect=["DOWN", "ENTER"])
    @patch("sys.stdin.isatty", return_value=True)
    def test_select_finding_interactive(self, mock_isatty, mock_read_key):
        findings = [
            Finding("item1", Path("C:/test1"), "descartavel", 1024, 1, False),
            Finding("item2", Path("C:/test2"), "movivel", 2048, 2, False),
        ]
        chosen = select_finding(findings, title="Escolha")
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen.ident, "item2")

    def test_render_findings_table_multilang(self):
        from pydisktriage.i18n import set_language
        findings = [
            Finding("npm-cache", Path("C:/test1"), "movivel", 1024, 1, False),
        ]
        set_language("en-US")
        t_en = render_findings_table(findings, selected_idx=0)
        self.assertEqual(len(t_en.rows), 1)

        set_language("pt-BR")
        t_pt = render_findings_table(findings, selected_idx=0)
        self.assertEqual(len(t_pt.rows), 1)


if __name__ == "__main__":
    unittest.main()
