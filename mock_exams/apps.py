from django.apps import AppConfig


class MockExamsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mock_exams'
    verbose_name = 'Mock Exams Management'
    
    def ready(self):
        # Import signals to register them
        from . import models  # This will trigger signal registration
