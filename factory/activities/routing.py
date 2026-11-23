from temporalio import activity

from factory.config import load_config
from factory.models import IntakeResult
from factory.routing import route


@activity.defn
def route_job(intake: IntakeResult) -> dict[str, str]:
    return route(load_config(), intake.risk, intake.surfaces)
