from enum import Enum
import os
from typing import List, Optional
from getpass import getuser

import aws_cdk
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GrafanaRoles(str, Enum):
    viewer = "Viewer"
    editor = "Editor"
    admin = "Admin"
    grafana_admin = "GrafanaAdmin"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("DOTENV", ".env"),
        extra="ignore",
    )

    stage: str = Field(
        description="Unique identifier for this deployment, e.g. 'dev', 'prod'",
        default_factory=getuser,
    )

    vpc_id: str

    project: Optional[str] = "GRSS-VEDA"
    grafana_domain_name: Optional[str] = None

    grafana_certificate_arn: Optional[str] = None

    cloudfront_certificate_arn: Optional[str] = None


    permissions_boundary_arn: str

    # Keycloak auth provider configuration
    keycloak_config_secret_arn: Optional[str] = Field(
        None,
        description=(
            "ARN of AWS Secrets Manager Secret containing all Keycloak configuration. "
            "The secret should be a JSON object with keys: client_id, client_secret, "
            "auth_url, token_url, api_url, allowed_groups (optional), admin_group (optional), "
            "editor_group (optional)."
        ),
        alias="kc_config_secret_arn",
    )
    default_user_role: Optional[GrafanaRoles] = Field(
        GrafanaRoles.viewer,
        description=(
            "Role assigned to users who are not members of the specified Keycloak admin "
            "or editor groups. Used when using Keycloak auth provider."
        ),
    )

    grafana_alb_subnet_mask: int = Field(
        description="Subnet mask for the Grafana load balancer. Required to"
        "filter down the number of subnets to one per availability zone",
        default=24,
    )

    namespace_arn: Optional[str] = Field(
        description="ARN of the private namespace to use for service discovery",
        default=None,
    )

    namespace_id: Optional[str] = Field(
        description="ID of the private namespace to use for service discovery",
        default=None,
    )
    namespace_name: str = Field(
        description="Name of the private namespace to use for service discovery",
        default="GRSS-VEDA.internal",
    )

    # honeycomb_api_key: str

    trace_exporters: str = Field(
        description="Where to export trace data in opentelemetry collector",
        default="awsxray",
    )

    # Provided automatically when called with AWS_PROFILE=...
    cdk_deploy_account: Optional[str] = Field(
        ..., default_factory=lambda: os.environ["CDK_DEFAULT_ACCOUNT"]
    )
    cdk_deploy_region: Optional[str] = Field(
        ..., default_factory=lambda: os.environ["CDK_DEFAULT_REGION"]
    )

    def stack_name(self,service: str) -> str:
        return f"{self.project}-{service}-{self.stage}"

    @property
    def grafana_stack_name(self) -> str:
        return self.stack_name("grafana")

    @property
    def otel_stack_name(self) -> str:
        return self.stack_name("otel")

    @property
    def env(self) -> aws_cdk.Environment:
        return aws_cdk.Environment(
            account=self.cdk_deploy_account,
            region=self.cdk_deploy_region,
        )

