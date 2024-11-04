from functools import wraps


def singleton(cls):
    """Singleton decorator to create a single instance of a class."""
    instances = dict()

    def wrapper(*args, **kwargs):
        if cls not in instances:
            instances[cls] = {}
        if args not in instances[cls]:
            instances[cls][args] = cls(*args, **kwargs)
        return instances[cls][args]

    return wraps(cls)(wrapper)
