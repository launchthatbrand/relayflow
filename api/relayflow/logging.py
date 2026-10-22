import logging


class CorrelationFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "-"
        return super().format(record)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        CorrelationFormatter("%(asctime)s %(levelname)s %(correlation_id)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
