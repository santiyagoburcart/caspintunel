import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()

from apps.tenancy import context as _tenancy  # noqa: E402

_tenancy.IN_WEB_PROCESS = True        # a tenant-table query outside a request here is logged (Release B)
