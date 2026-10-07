from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDraftStorage(FileSystemStorage):
    @property
    def location(self):
        import os
        return os.path.abspath(settings.PRIVATE_UPLOAD_ROOT)

    @property
    def base_location(self):
        return settings.PRIVATE_UPLOAD_ROOT


draft_storage = PrivateDraftStorage()
