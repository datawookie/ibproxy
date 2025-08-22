import logging


def logging_level(logger: logging.Logger | None = None) -> int:
    """
    Print the current logging level and whether DEBUG is enabled.
    """
    logger = logger or logging.getLogger()

    return logger.getEffectiveLevel()
