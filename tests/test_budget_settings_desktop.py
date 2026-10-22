"""Real widgets read/save Sheet currency for the captured profile, not selection."""
from types import SimpleNamespace
import tkinter
import unittest
from unittest.mock import Mock, patch

import desktop_app as ui
from services.bot_profiles import BotProfile
from services.budget_settings import BudgetSettings


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class BudgetCurrencyUITests(unittest.TestCase):
    def setUp(self):
        try:
            probe = tkinter.Tk()
            probe.destroy()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        self.profile=BotProfile('work','Work','sheet-work',currency='EUR')
        self.patches=[patch.object(ui,'list_profiles',return_value=[self.profile]),
                      patch.object(ui,'WindowsAutostart',return_value=Mock(supported=False)),
                      patch.object(ui.BudgetPanel,'_submit')]
        for guard in self.patches:
            guard.start()
            self.addCleanup(guard.stop)
        self.panel=ui.BudgetPanel()
        self.addCleanup(self.close)

    def close(self):
        for callback in self.panel.tk.call('after','info'):
            self.panel.after_cancel(callback)
        self.panel._quit()

    def test_existing_profile_form_has_sheet_currency_action_and_no_local_currency_dropdown(self):
        self.panel._show_profile_editor(self.profile)
        widgets=list(descendants(self.panel._editor))
        self.assertFalse(any(isinstance(w,ui.ctk.CTkOptionMenu) and w.cget('values')==['EUR','RUB'] for w in widgets))
        button=next(w for w in widgets if isinstance(w,ui.ctk.CTkButton) and w.cget('text')=='Валюта бюджета — Google Sheets')
        button.invoke()
        context=self.panel._currency_context
        self.assertEqual(context['profile'].id,'work')
        self.assertEqual(context['choice'].cget('state'),'disabled')
        self.panel._finish_budget_currency((context,BudgetSettings('RUB'),'loaded'),None)
        self.assertEqual(context['choice'].get(),'RUB')
        # Another card must not change the already-open editor's save destination.
        self.panel.selected_profile=BotProfile('other','Other','sheet-other')
        context['choice'].set('EUR')
        context['button'].invoke()
        args=self.panel._submit.call_args.args
        self.assertEqual(args[0],'budget-currency')
        self.assertIs(args[2],context)
        self.assertEqual(args[2]['profile'].id,'work')
        self.assertEqual(args[3],'EUR')

    def test_closed_or_replaced_dialog_ignores_delayed_load(self):
        self.panel._show_budget_currency(self.profile)
        context=self.panel._currency_context
        context['editor'].destroy()
        self.panel._show_budget_currency(self.profile)
        current=self.panel._currency_context
        self.panel._finish_budget_currency((context,BudgetSettings('RUB'),'old'),None)
        self.assertIsNone(current['settings'])
        self.assertEqual(current['choice'].cget('state'),'disabled')


if __name__=='__main__': unittest.main()
