"""Map intake's risk and surfaces to the reviewer set (ported from factory/bin/route)."""

from factory.core.config import FactoryConfig


def route(cfg: FactoryConfig, risk: str, surfaces: list[str]) -> dict[str, str]:
    if risk not in cfg.routing:
        raise ValueError(f"risk {risk!r} isn't in routing ({', '.join(cfg.routing)})")
    reviewers = dict(cfg.routing[risk])
    for surface in surfaces:
        if surface not in cfg.surface_reviewers:
            raise ValueError(f"surface {surface!r} isn't in surface_reviewers ({', '.join(cfg.surface_reviewers)})")
        reviewers.update(cfg.surface_reviewers[surface])
    return reviewers
