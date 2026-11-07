"""Manual native updates. No feed, credentials or knowledge enter this boundary."""
from __future__ import annotations


class Updater:
    def __init__(self, current_version: str, native=None):
        self.current_version = current_version
        self.native = native
        self.unavailable_reason: str | None = None

    def state(self) -> dict:
        if self.native is not None:
            return {'current_version': self.current_version, 'status': 'ready',
                    'configured': True, 'reason': 'Native signed-update service ready'}
        return {'current_version': self.current_version, 'status': 'unconfigured',
                'configured': False, 'reason': self.unavailable_reason or 'Update source not configured'}

    def check(self) -> dict:
        if self.native is None:
            return self.state()
        self.native.check_for_updates()
        return {**self.state(), 'status': 'native_dialog',
                'reason': 'Continue in the native update window. Installation requires your confirmation.'}

    def install(self) -> dict:
        return self.state()
