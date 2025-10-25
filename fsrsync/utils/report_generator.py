"""
Comprehensive Report Generation System for FSRsync

Provides report generation with:
- Multiple report formats (PDF, HTML, JSON, CSV)
- Custom report templates
- Scheduling and automation
- Email delivery
- Trend analysis in reports
- Executive summaries

## Report Types

PERFORMANCE: Performance metrics report
AUDIT: Security audit report
HEALTH: System health report
USAGE: Usage analytics report
INCIDENT: Incident summary report
CUSTOM: Custom report
"""

import time
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ReportType(Enum):
    """Type of report"""
    PERFORMANCE = "performance"
    AUDIT = "audit"
    HEALTH = "health"
    USAGE = "usage"
    INCIDENT = "incident"
    CUSTOM = "custom"


class ReportFormat(Enum):
    """Report output format"""
    PDF = "pdf"
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportSchedule(Enum):
    """Report generation schedule"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


@dataclass
class ReportSection:
    """Section in a report"""
    title: str
    content: str
    section_type: str = "text"  # text, table, chart, metric
    data: Dict[str, Any] = field(default_factory=dict)
    order: int = 0


@dataclass
class Report:
    """Report definition and output"""
    report_id: str
    report_type: ReportType
    title: str
    description: str = ""
    sections: List[ReportSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)
    generated_by: str = ""
    period_start: Optional[float] = None
    period_end: Optional[float] = None
    format: ReportFormat = ReportFormat.HTML


class ReportGenerator:
    """
    Comprehensive report generation system.

    Generates formatted reports with analytics,
    trends, and executive summaries.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize report generator.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Report storage
        self.reports: Dict[str, Report] = {}
        self.report_templates: Dict[str, Dict[str, Any]] = self._init_templates()

        # Report scheduling
        self.scheduled_reports: Dict[str, Dict[str, Any]] = {}
        self.report_history: Dict[str, List[str]] = defaultdict(list)

        # Report deliveries
        self.email_recipients: Dict[str, List[str]] = {}

        self.logger.info("ReportGenerator initialized")

    def _init_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize standard report templates"""
        return {
            'performance_daily': {
                'report_type': ReportType.PERFORMANCE,
                'title': 'Daily Performance Report',
                'schedule': ReportSchedule.DAILY,
                'sections': [
                    'executive_summary',
                    'performance_metrics',
                    'trends',
                    'bottlenecks',
                    'recommendations'
                ]
            },
            'health_weekly': {
                'report_type': ReportType.HEALTH,
                'title': 'Weekly Health Report',
                'schedule': ReportSchedule.WEEKLY,
                'sections': [
                    'system_status',
                    'component_health',
                    'resource_usage',
                    'incidents',
                    'alerts'
                ]
            },
            'audit_monthly': {
                'report_type': ReportType.AUDIT,
                'title': 'Monthly Audit Report',
                'schedule': ReportSchedule.MONTHLY,
                'sections': [
                    'access_summary',
                    'changes_log',
                    'security_events',
                    'compliance',
                    'recommendations'
                ]
            }
        }

    def create_report(self, report_type: str, title: str,
                     description: str = "", format_type: str = "html",
                     period_start: Optional[float] = None,
                     period_end: Optional[float] = None) -> Optional[str]:
        """
        Create new report.

        Args:
            report_type: Type of report
            title: Report title
            description: Report description
            format_type: Output format
            period_start: Report period start
            period_end: Report period end

        Returns:
            Report ID if successful
        """
        try:
            import uuid

            report_id = str(uuid.uuid4())

            report = Report(
                report_id=report_id,
                report_type=ReportType(report_type.lower()),
                title=title,
                description=description,
                format=ReportFormat(format_type.lower()),
                period_start=period_start,
                period_end=period_end
            )

            self.reports[report_id] = report

            self.logger.info(f"Created report: {report_id} ({title})")
            return report_id

        except Exception as e:
            self.logger.error(f"Error creating report: {e}")
            return None

    def add_section(self, report_id: str, title: str, content: str,
                   section_type: str = "text",
                   data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add section to report.

        Args:
            report_id: Report ID
            title: Section title
            content: Section content
            section_type: Type of section
            data: Section data (for tables, charts)

        Returns:
            True if added successfully
        """
        try:
            if report_id not in self.reports:
                return False

            report = self.reports[report_id]

            section = ReportSection(
                title=title,
                content=content,
                section_type=section_type,
                data=data or {},
                order=len(report.sections)
            )

            report.sections.append(section)

            return True

        except Exception as e:
            self.logger.error(f"Error adding section: {e}")
            return False

    def generate_executive_summary(self, report_id: str,
                                  summary_data: Dict[str, Any]) -> bool:
        """
        Generate executive summary section.

        Args:
            report_id: Report ID
            summary_data: Summary data dictionary

        Returns:
            True if generated successfully
        """
        try:
            if report_id not in self.reports:
                return False

            # Format summary
            summary_text = "## Executive Summary\n\n"

            if 'key_metrics' in summary_data:
                summary_text += "### Key Metrics:\n"
                for metric, value in summary_data['key_metrics'].items():
                    summary_text += f"- **{metric}**: {value}\n"

            if 'findings' in summary_data:
                summary_text += "\n### Key Findings:\n"
                for finding in summary_data['findings']:
                    summary_text += f"- {finding}\n"

            if 'recommendations' in summary_data:
                summary_text += "\n### Recommendations:\n"
                for rec in summary_data['recommendations']:
                    summary_text += f"- {rec}\n"

            return self.add_section(
                report_id,
                "Executive Summary",
                summary_text,
                section_type="text",
                data=summary_data
            )

        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return False

    def generate_metrics_section(self, report_id: str,
                                metrics: Dict[str, Any]) -> bool:
        """
        Generate metrics section.

        Args:
            report_id: Report ID
            metrics: Metrics dictionary

        Returns:
            True if generated successfully
        """
        try:
            if report_id not in self.reports:
                return False

            # Format metrics table
            metrics_text = "## Performance Metrics\n\n"
            metrics_text += "| Metric | Value | Unit | Status |\n"
            metrics_text += "|--------|-------|------|--------|\n"

            for name, value in metrics.items():
                if isinstance(value, dict):
                    unit = value.get('unit', '')
                    status = value.get('status', 'ok')
                    val = value.get('value', 0)
                else:
                    unit = ''
                    status = 'ok'
                    val = value

                metrics_text += f"| {name} | {val} | {unit} | {status} |\n"

            return self.add_section(
                report_id,
                "Metrics",
                metrics_text,
                section_type="table",
                data=metrics
            )

        except Exception as e:
            self.logger.error(f"Error generating metrics section: {e}")
            return False

    def schedule_report(self, report_template: str, schedule: str,
                       recipients: Optional[List[str]] = None) -> Optional[str]:
        """
        Schedule recurring report generation.

        Args:
            report_template: Template name
            schedule: Schedule type
            recipients: Email recipients

        Returns:
            Schedule ID if successful
        """
        try:
            import uuid

            if report_template not in self.report_templates:
                return None

            schedule_id = str(uuid.uuid4())

            schedule_config = {
                'template': report_template,
                'schedule': schedule,
                'recipients': recipients or [],
                'last_generated': None,
                'next_run': self._calculate_next_run(schedule),
                'created_at': time.time()
            }

            self.scheduled_reports[schedule_id] = schedule_config

            if recipients:
                self.email_recipients[schedule_id] = recipients

            self.logger.info(
                f"Scheduled report {report_template} with schedule {schedule}"
            )

            return schedule_id

        except Exception as e:
            self.logger.error(f"Error scheduling report: {e}")
            return None

    def _calculate_next_run(self, schedule: str) -> float:
        """Calculate next run time based on schedule"""
        now = time.time()

        if schedule == "hourly":
            return now + 3600
        elif schedule == "daily":
            return now + 86400
        elif schedule == "weekly":
            return now + 604800
        elif schedule == "monthly":
            return now + 2592000
        else:
            return now

    def export_report(self, report_id: str) -> Optional[str]:
        """
        Export report to string.

        Args:
            report_id: Report ID

        Returns:
            Formatted report string
        """
        try:
            if report_id not in self.reports:
                return None

            report = self.reports[report_id]

            if report.format == ReportFormat.JSON:
                return self._export_json(report)
            elif report.format == ReportFormat.MARKDOWN:
                return self._export_markdown(report)
            elif report.format == ReportFormat.HTML:
                return self._export_html(report)
            elif report.format == ReportFormat.CSV:
                return self._export_csv(report)
            else:
                return None

        except Exception as e:
            self.logger.error(f"Error exporting report: {e}")
            return None

    def _export_json(self, report: Report) -> str:
        """Export report as JSON"""
        try:
            data = {
                'report_id': report.report_id,
                'report_type': report.report_type.value,
                'title': report.title,
                'description': report.description,
                'generated_at': report.generated_at,
                'generated_by': report.generated_by,
                'period': {
                    'start': report.period_start,
                    'end': report.period_end
                },
                'sections': [
                    {
                        'title': s.title,
                        'type': s.section_type,
                        'content': s.content,
                        'data': s.data
                    }
                    for s in report.sections
                ]
            }

            return json.dumps(data, indent=2, default=str)

        except Exception as e:
            self.logger.error(f"Error exporting to JSON: {e}")
            return ""

    def _export_markdown(self, report: Report) -> str:
        """Export report as Markdown"""
        try:
            output = f"# {report.title}\n\n"

            if report.description:
                output += f"_{report.description}_\n\n"

            output += f"**Generated**: {time.ctime(report.generated_at)}\n\n"

            for section in report.sections:
                output += f"## {section.title}\n\n"
                output += section.content + "\n\n"

            return output

        except Exception as e:
            self.logger.error(f"Error exporting to Markdown: {e}")
            return ""

    def _export_html(self, report: Report) -> str:
        """Export report as HTML"""
        try:
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{report.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>{report.title}</h1>
    <p><em>{report.description}</em></p>
    <p><strong>Generated:</strong> {time.ctime(report.generated_at)}</p>
"""

            for section in report.sections:
                html += f"    <h2>{section.title}</h2>\n"
                html += f"    <p>{section.content}</p>\n"

            html += """</body>
</html>"""

            return html

        except Exception as e:
            self.logger.error(f"Error exporting to HTML: {e}")
            return ""

    def _export_csv(self, report: Report) -> str:
        """Export report as CSV"""
        try:
            lines = []
            lines.append(f"Report,{report.title}")
            lines.append(f"Type,{report.report_type.value}")
            lines.append(f"Generated,{time.ctime(report.generated_at)}")
            lines.append("")

            for section in report.sections:
                lines.append(f"Section,{section.title}")

                if section.section_type == "table" and section.data:
                    for key, value in section.data.items():
                        lines.append(f"{key},{value}")

                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            return ""

    def get_report_summary(self) -> Dict[str, Any]:
        """Get report system summary"""
        try:
            return {
                'timestamp': time.time(),
                'total_reports': len(self.reports),
                'scheduled_reports': len(self.scheduled_reports),
                'report_templates': len(self.report_templates),
                'reports': [
                    {
                        'report_id': r.report_id,
                        'title': r.title,
                        'type': r.report_type.value,
                        'generated_at': r.generated_at,
                        'sections': len(r.sections)
                    }
                    for r in list(self.reports.values())[-10:]
                ]
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
