"""A deliberately non-filesystem backend for the publication contract tests."""

from django.core.files.base import ContentFile
from django.core.files.storage import Storage


class RemoteStorage(Storage):
    def __init__(self, **kwargs):
        self.files = {}
        self.fail_save = False
        self.fail_delete = False
        self.after_save = None
        self.return_key = None

    def _save(self, name, content):
        if self.fail_save:
            raise OSError("upload failed")
        key = self.return_key or name + ".renamed"
        self.files[key] = content.read()
        if self.after_save:
            self.after_save()
        return key

    def _open(self, name, mode="rb"):
        try:
            return ContentFile(self.files[name], name=name)
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def exists(self, name):
        return name in self.files

    def delete(self, name):
        if self.fail_delete:
            raise OSError("delete failed")
        self.files.pop(name, None)
