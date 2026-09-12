import json
import logging
from datetime import UTC, datetime
from threading import Lock

from realty.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                **{
                    k: getattr(record, k)
                    for k in [
                        "request_id",
                        "status",
                        "duration_ms",
                        "job_id",
                        "org_id",
                        "code",
                        "attempt",
                    ]
                    if hasattr(record, k)
                },
            }
        )


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("realty")
    logger.handlers = [handler]
    logger.setLevel(settings.log_level)
    logger.propagate = False
    return logger


_metric_lock = Lock()
_http_metrics: dict[tuple[str, int], tuple[int, float]] = {}


def record_request(method: str, status: int, duration: float) -> None:
    method = (
        method
        if method in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        else "OTHER"
    )
    with _metric_lock:
        count, total = _http_metrics.get((method, status), (0, 0.0))
        _http_metrics[method, status] = count + 1, total + duration


def render_metrics() -> str:
    rows = [
        "# TYPE realty_http_requests_total counter",
        "# TYPE realty_http_duration_seconds_total counter",
    ]
    with _metric_lock:
        for (method, status), (count, total) in sorted(_http_metrics.items()):
            labels = f'method="{method}",status="{status}"'
            rows.extend(
                [
                    f"realty_http_requests_total{{{labels}}} {count}",
                    f"realty_http_duration_seconds_total{{{labels}}} {total:.6f}",
                ]
            )
    return "\n".join(rows)
