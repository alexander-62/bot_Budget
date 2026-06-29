import importlib.util
import sys
import unittest


class SmokeTests(unittest.TestCase):
    def test_runtime_smoke_requires_installed_dependencies(self) -> None:
        required = ("aiogram", "aiohttp", "gspread")
        missing: list[str] = []
        for name in required:
            module = sys.modules.get(name)
            if module is not None and getattr(module, "__spec__", None) is None:
                missing.append(name)
                continue
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        if missing:
            self.skipTest(f"Install requirements.txt to run runtime smoke check. Missing: {', '.join(missing)}")

        import app
        from keyboards.expenses import build_cancel_keyboard, build_saved_expense_actions_keyboard
        from keyboards.main import build_main_menu

        self.assertIsNotNone(app.create_dispatcher())
        self.assertIsNotNone(build_main_menu())
        self.assertIsNotNone(build_cancel_keyboard("1"))
        self.assertIsNotNone(build_saved_expense_actions_keyboard("1"))


if __name__ == "__main__":
    unittest.main()
