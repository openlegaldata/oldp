from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = 'oldp.apps.cases'

    def ready(self):
        from oldp.apps.cases import signals

        if signals.pre_save_case:
            pass
