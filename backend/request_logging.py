"""Keep OAuth credentials out of Uvicorn request logs."""
import logging


class RedactOAuthQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            address, method, path, version, status = record.args
            if isinstance(path, str) and path.startswith('/auth/google/callback?'):
                record.args = (address, method, '/auth/google/callback?[redacted]', version, status)
        return True


def configure_request_logging():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, RedactOAuthQuery) for item in logger.filters):
        logger.addFilter(RedactOAuthQuery())
