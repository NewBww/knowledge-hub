"""Updater coverage uses no owner feed, keys, app installation or knowledge."""
import socket


def test_unconfigured_reports_installed_version_and_never_opens_network(monkeypatch):
    from knowledge_hub.updater import Updater

    def forbidden(*args, **kwargs):
        raise AssertionError('Unconfigured updater must not use the network')

    monkeypatch.setattr(socket, 'socket', forbidden)
    updater = Updater('1.2.3')
    expected = {'current_version': '1.2.3', 'status': 'unconfigured', 'configured': False,
                'reason': 'Update source not configured'}
    assert updater.state() == expected
    assert updater.check() == expected
    assert updater.install() == expected


def test_native_startup_failure_is_visible_without_claiming_service_ready():
    from knowledge_hub.updater import Updater

    updater = Updater('0.3.0')
    updater.unavailable_reason = 'Move the application out of the disk image to enable updates'
    assert updater.state()['reason'] == updater.unavailable_reason
    assert updater.state()['configured'] is False
    assert updater.check() == updater.state()

