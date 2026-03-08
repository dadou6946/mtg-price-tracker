from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.dispatch import receiver


class CardsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cards'

    def ready(self):
        """Configure SQLite pragmas on app startup."""
        @receiver(connection_created)
        def set_sqlite_pragma(sender, connection, **kwargs):
            """Enable WAL mode and optimize SQLite for concurrent access."""
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                cursor.execute('PRAGMA journal_mode = WAL')
                cursor.execute('PRAGMA timeout = 20000')  # 20 secondes
                cursor.execute('PRAGMA cache_size = -64000')  # 64 MB
                cursor.execute('PRAGMA synchronous = NORMAL')
                cursor.close()
