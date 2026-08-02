from constructs import Construct
from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_athena as athena,
    aws_glue as glue,
    aws_iam as iam,
    aws_s3 as s3,
)

from .settings import Settings


# Column order matches the CSV header of Amplify's GenerateAccessLogs export
# (CloudFront standard log fields).
ACCESS_LOG_COLUMNS = [
    "date",
    "time",
    "edge_location",
    "sc_bytes",
    "c_ip",
    "method",
    "host",
    "uri_stem",
    "status",
    "referer",
    "useragent",
    "uri_query",
    "cookie",
    "edge_result_type",
    "request_id",
    "host_header",
    "protocol",
    "cs_bytes",
    "time_taken",
    "forwarded_for",
    "ssl_protocol",
    "ssl_cipher",
    "edge_response_result_type",
    "protocol_version",
    "fle_status",
    "fle_encrypted_fields",
    "c_port",
    "time_to_first_byte",
    "edge_detailed_result_type",
    "content_type",
    "content_len",
    "range_start",
    "range_end",
]


class AccessLogsStack(Stack):
    """
    Storage and query layer for Amplify access logs, so Grafana can chart
    website traffic via the Athena datasource.

    Data flow: the fetch-amplify-access-logs workflow pulls CSVs from the
    Amplify API on a schedule and drops them under s3://<bucket>/logs/;
    the Glue table makes them queryable; the Athena workgroup provides a
    query-result location for the Grafana Athena datasource.
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

        bucket = s3.Bucket(
            self,
            "Bucket",
            bucket_name=settings.access_logs_bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            lifecycle_rules=[
                # Athena query results are scratch data
                s3.LifecycleRule(
                    prefix="athena-results/",
                    expiration=Duration.days(30),
                )
            ],
        )

        database = glue.CfnDatabase(
            self,
            "Database",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=settings.glue_database_name,
            ),
        )

        table = glue.CfnTable(
            self,
            "Table",
            catalog_id=self.account,
            database_name=settings.glue_database_name,
            table_input=glue.CfnTable.TableInputProperty(
                name="access_logs",
                table_type="EXTERNAL_TABLE",
                parameters={
                    "classification": "csv",
                    "skip.header.line.count": "1",
                },
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    location=f"s3://{bucket.bucket_name}/logs/",
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format=(
                        "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
                    ),
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library=(
                            "org.apache.hadoop.hive.serde2.OpenCSVSerde"
                        ),
                        parameters={
                            "separatorChar": ",",
                            "quoteChar": '"',
                            "escapeChar": "\\",
                        },
                    ),
                    columns=[
                        glue.CfnTable.ColumnProperty(name=c, type="string")
                        for c in ACCESS_LOG_COLUMNS
                    ],
                ),
            ),
        )
        table.add_dependency(database)

        athena.CfnWorkGroup(
            self,
            "WorkGroup",
            name=settings.athena_workgroup_name,
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{bucket.bucket_name}/athena-results/",
                ),
                publish_cloud_watch_metrics_enabled=False,
            ),
        )

        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "GlueDatabase", value=settings.glue_database_name)
        CfnOutput(self, "AthenaWorkgroup", value=settings.athena_workgroup_name)
