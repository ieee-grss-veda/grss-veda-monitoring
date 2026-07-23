from constructs import Construct
from aws_cdk import (
    CfnOutput,
    Stack,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_rum as rum,
)

from .settings import Settings


class RumStack(Stack):
    """
    CloudWatch RUM app monitor for the GRSS-VEDA website, along with the Cognito
    identity pool that allows anonymous browsers to submit RUM events.

    The stack outputs contain the values needed to render the JS snippet that
    must be added to the website's <head>:
    https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-RUM-modify-app.html
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        settings: Settings,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Apply global permissions boundary
        boundary = iam.ManagedPolicy.from_managed_policy_arn(
            self, "Boundary", settings.permissions_boundary_arn
        )
        iam.PermissionsBoundary.of(self).apply(boundary)

        # The monitor name is used as the `application_name` dimension on
        # AWS/RUM metrics and as the prefix of the vended log group, both of
        # which the provisioned Grafana dashboards discover dynamically.
        monitor_name = construct_id

        identity_pool = cognito.CfnIdentityPool(
            self,
            "IdentityPool",
            allow_unauthenticated_identities=True,
        )

        guest_role = iam.Role(
            self,
            "GuestRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": identity_pool.ref,
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "unauthenticated",
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )
        guest_role.add_to_policy(
            iam.PolicyStatement(
                actions=["rum:PutRumEvents"],
                resources=[
                    self.format_arn(
                        service="rum",
                        resource="appmonitor",
                        resource_name=monitor_name,
                    )
                ],
            )
        )

        cognito.CfnIdentityPoolRoleAttachment(
            self,
            "RoleAttachment",
            identity_pool_id=identity_pool.ref,
            roles={"unauthenticated": guest_role.role_arn},
        )

        app_monitor = rum.CfnAppMonitor(
            self,
            "AppMonitor",
            name=monitor_name,
            domain=settings.monitoring_website_domain,
            # Export events to CloudWatch Logs so Grafana can query visitor
            # geography, top pages, etc. via Logs Insights
            cw_log_enabled=True,
            app_monitor_configuration=rum.CfnAppMonitor.AppMonitorConfigurationProperty(
                # Cookies enable session and (approximate) unique-user tracking
                allow_cookies=True,
                enable_x_ray=False,
                session_sample_rate=1,
                telemetries=["performance", "errors", "http"],
                identity_pool_id=identity_pool.ref,
                guest_role_arn=guest_role.role_arn,
            ),
        )

        CfnOutput(
            self,
            "AppMonitorName",
            value=monitor_name,
            description="CloudWatch RUM app monitor name",
        )
        CfnOutput(
            self,
            "AppMonitorId",
            value=app_monitor.attr_id,
            description="CloudWatch RUM app monitor ID (used in the JS snippet)",
        )
        CfnOutput(
            self,
            "IdentityPoolId",
            value=identity_pool.ref,
            description="Cognito identity pool ID (used in the JS snippet)",
        )
        CfnOutput(
            self,
            "GuestRoleArn",
            value=guest_role.role_arn,
            description="IAM role assumed by anonymous website visitors",
        )
