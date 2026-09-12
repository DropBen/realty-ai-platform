import json
import logging

from realty.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "event": record.getMessage(),
                **{
                    k: getattr(record, k)
                    for k in ["request_id", "status", "duration_ms", "job_id", "org_id", "code"]
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
