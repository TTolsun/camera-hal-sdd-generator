"""Separate review execution identity from historical generation settings."""
from .config import load


def resolve(cfg, model, groups, identity, request):
    path = cfg.paths.get('consistency_review_config')
    if path is None:
        return cfg
    review = load(path)
    from .validation_stage import current
    if current() is not None:
        current().pin(review)
    if groups(review) != groups(cfg):
        raise ValueError('Consistency review profile changes the contract scope')
    if review.build_dir.resolve() != cfg.build_dir.resolve():
        raise ValueError('Consistency review profile changes the receipt directory')
    for group in groups(cfg):
        if identity(request(review, model, group)) != identity(request(cfg, model, group)):
            raise ValueError('Consistency review profile changes publication inputs')
    return review
