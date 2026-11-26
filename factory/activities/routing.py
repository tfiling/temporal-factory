from temporalio import activity

from factory.core.config import load_config
from factory.core.models import IntakeResult
from factory.core.routing import route


@activity.defn
def route_job(intake: IntakeResult) -> dict[str, str]:
    return route(load_config(), intake.risk, intake.surfaces)
