import unittest
from pydisktriage.i18n import (
    get_available_languages,
    get_language,
    normalize_language,
    set_language,
    t,
)


class TestI18n(unittest.TestCase):
    def setUp(self):
        set_language("pt-BR")

    def test_normalize_language(self):
        self.assertEqual(normalize_language("pt"), "pt-BR")
        self.assertEqual(normalize_language("pt_BR"), "pt-BR")
        self.assertEqual(normalize_language("pt-br"), "pt-BR")
        self.assertEqual(normalize_language("en"), "en-US")
        self.assertEqual(normalize_language("en_US"), "en-US")
        self.assertEqual(normalize_language("en-us"), "en-US")
        self.assertEqual(normalize_language("unknown"), "pt-BR")

    def test_set_and_get_language(self):
        set_language("en-US")
        self.assertEqual(get_language(), "en-US")
        set_language("pt-BR")
        self.assertEqual(get_language(), "pt-BR")

    def test_translation_pt_and_en(self):
        set_language("pt-BR")
        pt_text = t("menu.exit")
        self.assertEqual(pt_text, "Sair")

        set_language("en-US")
        en_text = t("menu.exit")
        self.assertEqual(en_text, "Exit")

    def test_translation_fallback(self):
        set_language("en-US")
        # If key is completely missing, return key
        self.assertEqual(t("non.existent.key"), "non.existent.key")

    def test_translation_formatting(self):
        set_language("en-US")
        msg = t("actions.freed_space", size="10 GB", files=5)
        self.assertIn("10 GB", msg)
        self.assertIn("5", msg)

    def test_get_available_languages(self):
        langs = get_available_languages()
        self.assertEqual(len(langs), 2)
        codes = [code for code, _ in langs]
        self.assertIn("pt-BR", codes)
        self.assertIn("en-US", codes)


if __name__ == "__main__":
    unittest.main()
