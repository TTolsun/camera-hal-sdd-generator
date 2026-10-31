"""Execution observation above the independent input/configuration layer."""
from contextlib import nullcontext
from functools import wraps

from .generation_run import observe
from .validation_stage import staged as input_stage


def staged(function):
    checked = input_stage(function)
    @wraps(function)
    def wrapped(cfg, *args, **kwargs):
        # Audit owns an Execution with its explicitly independent review agent.
        observation = observe(cfg, function.__name__) if function.__name__ != 'audit' else nullcontext()
        with observation:
            return checked(cfg, *args, **kwargs)
    return wrapped
