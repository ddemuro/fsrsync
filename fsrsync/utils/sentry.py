import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

DEFAULT_SENTRY_DSN = "https://18899450e45e41d5d685301c5159d434@sentry.takelan.com/33"


def setup_sentry(logging, sentry_dsn, max_breadcrumbs=100, max_value_length=1000):
    """Set up Sentry for error logging"""
    # If SENTRY_DSN is not set, use the default DSN
    if not sentry_dsn or sentry_dsn == "":
        sentry_dsn = DEFAULT_SENTRY_DSN

    sentry_logging = LoggingIntegration(
        level=logging.CRITICAL,  # Only capture critical errors
        event_level=logging.CRITICAL  # Send events to Sentry for critical errors only
    )

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[sentry_logging],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        # Increase breadcrumb limit
        max_breadcrumbs=int(max_breadcrumbs),
        max_value_length=int(max_value_length),
    )
