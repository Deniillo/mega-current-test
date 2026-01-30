import logging
import sys

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "%(message)s"
)

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout)  # важно для Docker
        ],
    )
