import aws_cdk as cdk

from .grafana import GrafanaStack
from .otel import OtelStack
from .rum import RumStack
from .settings import Settings

settings = Settings()

app = cdk.App()

GrafanaStack(
    app,
    construct_id=settings.grafana_stack_name,
    settings=settings,
    env=settings.env,
)

OtelStack(
    app,
    construct_id=settings.otel_stack_name,
    settings=settings,
    env=settings.env,
)

if settings.monitoring_website_domain:
    RumStack(
        app,
        construct_id=settings.rum_stack_name,
        settings=settings,
        env=settings.env,
    )

app.synth()
