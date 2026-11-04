"""Execution observation above the independent input/configuration layer."""
from contextlib import nullcontext
from functools import wraps

from .generation_run import observe, observed
from .validation_stage import staged as input_stage


def staged(function):
    @wraps(function)
    def verify_operation(*args, **kwargs):
        result = function(*args, **kwargs)
        execution = observed()
        if execution is not None and execution.publication_contract is not None:
            from .validation_stage import current
            # Keep existing transactional site rollback available until the
            # outer operation accepts its own input/head boundary as well.
            for undo in current().rollbacks:
                if undo not in execution.publication_contract.rollbacks:
                    execution.publication_contract.rollbacks.append(undo)
            execution.publication_contract.verify()
        return result
    checked = input_stage(verify_operation)
    @wraps(function)
    def wrapped(cfg, *args, **kwargs):
        # Audit owns an Execution with its explicitly independent review agent.
        model = args[0] if args and hasattr(args[0], 'evidence') else None
        observation = observe(cfg, function.__name__, model) if function.__name__ != 'audit' else nullcontext()
        with observation:
            return checked(cfg, *args, **kwargs)
    return wrapped
