"""Nothing noticed a broker going away.

BROKER_CONNECTED was emitted once at startup and BROKER_DISCONNECTED was
declared in the auto-pin set but never raised by anything. A dead MT5 terminal
produced a stream of individual errors and no statement that the connection
was gone — on a live trading system, the one thing you want said out loud.
"""
from __future__ import annotations

from openforexai.adapters.brokers.base import BrokerBase
from openforexai.models.monitoring import MonitoringEventType


class _Broker:
    """Binds the real methods under test; BrokerBase itself is abstract and
    would need nine unrelated stubs to instantiate."""

    short_name = "TEST1"
    ACCOUNT_POLL_FAILURES_UNTIL_DISCONNECTED = BrokerBase.ACCOUNT_POLL_FAILURES_UNTIL_DISCONNECTED
    _note_account_poll_failure = BrokerBase._note_account_poll_failure
    _note_account_poll_success = BrokerBase._note_account_poll_success

    def __init__(self):
        self._account_poll_failures = 0
        self._connection_lost = False
        self.emitted: list[tuple[str, dict]] = []

    def _emit(self, source, event_type, **payload):
        self.emitted.append((str(event_type), payload))

    def kinds(self):
        return [k for k, _ in self.emitted]


def _fail(b, times):
    for _ in range(times):
        b._note_account_poll_failure("broker.TEST1", "terminal not reachable")


def test_one_failed_poll_is_a_hiccup_not_an_outage():
    b = _Broker()
    _fail(b, 1)
    assert b.kinds() == []
    assert b._connection_lost is False


def test_repeated_failures_declare_the_connection_lost():
    b = _Broker()
    _fail(b, 2)
    assert b.kinds() == [MonitoringEventType.BROKER_DISCONNECTED]
    payload = b.emitted[0][1]
    assert payload["broker_name"] == "TEST1"
    assert payload["failed_polls"] == 2
    assert "terminal not reachable" in payload["error"]


def test_an_ongoing_outage_is_reported_once_not_every_minute():
    """A channel that repeats itself is one people stop reading."""
    b = _Broker()
    _fail(b, 10)
    assert b.kinds().count(MonitoringEventType.BROKER_DISCONNECTED) == 1


def test_recovery_is_reported_once():
    b = _Broker()
    _fail(b, 3)
    b._note_account_poll_success("broker.TEST1")
    b._note_account_poll_success("broker.TEST1")
    assert b.kinds() == [
        MonitoringEventType.BROKER_DISCONNECTED,
        MonitoringEventType.BROKER_CONNECTED,
    ]
    assert b.emitted[1][1]["recovered"] is True


def test_a_healthy_broker_stays_silent():
    b = _Broker()
    for _ in range(5):
        b._note_account_poll_success("broker.TEST1")
    assert b.kinds() == []


def test_the_counter_resets_so_scattered_failures_never_add_up():
    """Two failures a day apart are not an outage."""
    b = _Broker()
    _fail(b, 1)
    b._note_account_poll_success("broker.TEST1")
    _fail(b, 1)
    assert b.kinds() == []


def test_a_second_outage_is_reported_again():
    b = _Broker()
    _fail(b, 2)
    b._note_account_poll_success("broker.TEST1")
    _fail(b, 2)
    assert b.kinds().count(MonitoringEventType.BROKER_DISCONNECTED) == 2
