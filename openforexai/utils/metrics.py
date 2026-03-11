from __future__ import annotations

# Optional Prometheus metrics exporter.
# Set OPENFOREXAI_METRICS_ENABLED=true and install `prometheus_client` to activate.

_enabled = False
_registry: object | None = None


def setup_metrics(port: int = 9090) -> None:
    """Start the Prometheus HTTP metrics server on *port*."""
    global _enabled, _registry
    try:
        from prometheus_client import Counter, Gauge, Histogram, start_http_server  # type: ignore[import]

        start_http_server(port)
        _enabled = True
    except ImportError:
        import logging

        logging.getLogger(__name__).warning(
            "prometheus_client not installed; metrics disabled."
        )


def increment_counter(name: str, labels: dict[str, str] | None = None) -> None:
    if not _enabled:
        return
    # Stub — extend with actual Counter registry as needed


def record_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    if not _enabled:
        return


def observe_histogram(
    name: str, value: float, labels: dict[str, str] | None = None
) -> None:
    if not _enabled:
        return

