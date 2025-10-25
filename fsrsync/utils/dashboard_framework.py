"""
Interactive Dashboard Framework for FSRsync

Provides dashboard building and visualization with:
- Widget system for displaying metrics
- Layout management
- Real-time data binding
- Interactive controls
- Custom visualizations
- Report generation

## Widget Types

CHART: Time-series or categorical chart
GAUGE: Metric gauge/progress
STATUS: Status indicator
TABLE: Data table
ALERT: Alert display
MAP: Geographic or network map
METRIC: Single metric display
CUSTOM: Custom HTML widget
"""

import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class WidgetType(Enum):
    """Type of dashboard widget"""
    CHART = "chart"
    GAUGE = "gauge"
    STATUS = "status"
    TABLE = "table"
    ALERT = "alert"
    MAP = "map"
    METRIC = "metric"
    CUSTOM = "custom"


class ChartType(Enum):
    """Type of chart"""
    LINE = "line"
    BAR = "bar"
    AREA = "area"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"


class RefreshMode(Enum):
    """Data refresh mode"""
    MANUAL = "manual"
    AUTO = "auto"
    STREAM = "stream"


@dataclass
class Widget:
    """Dashboard widget definition"""
    widget_id: str
    widget_type: WidgetType
    title: str
    description: str = ""
    data_source: str = ""
    refresh_mode: RefreshMode = RefreshMode.AUTO
    refresh_interval: int = 5000  # milliseconds
    width: int = 6  # 1-12 grid units
    height: int = 4  # rows
    position: tuple = (0, 0)  # (row, col)
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)


@dataclass
class Dashboard:
    """Dashboard definition"""
    dashboard_id: str
    name: str
    description: str = ""
    widgets: Dict[str, Widget] = field(default_factory=dict)
    layout: str = "grid"  # grid, flex, absolute
    grid_columns: int = 12
    refresh_interval: int = 5000  # global refresh in ms
    auto_arrange: bool = True
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    owner: str = ""
    tags: List[str] = field(default_factory=list)
    is_public: bool = False


@dataclass
class DashboardData:
    """Data for dashboard rendering"""
    dashboard_id: str
    timestamp: float = field(default_factory=time.time)
    widgets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DashboardBuilder:
    """
    Interactive dashboard builder and framework.

    Allows creation and management of custom dashboards
    with various widgets and visualizations.
    """

    def __init__(self, logger_instance=None):
        """
        Initialize dashboard builder.

        Args:
            logger_instance: Logger instance
        """
        self.logger = logger_instance or logging.getLogger(__name__)

        # Dashboard storage
        self.dashboards: Dict[str, Dashboard] = {}
        self.widgets: Dict[str, Widget] = {}

        # Data providers (metric_name -> callable)
        self.data_providers: Dict[str, Callable] = {}

        # Widget templates
        self.widget_templates: Dict[str, Dict[str, Any]] = self._init_templates()

        self.logger.info("DashboardBuilder initialized")

    def _init_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize standard widget templates"""
        return {
            'cpu_gauge': {
                'widget_type': WidgetType.GAUGE,
                'title': 'CPU Usage',
                'config': {
                    'min': 0,
                    'max': 100,
                    'unit': '%',
                    'thresholds': [
                        {'value': 20, 'color': 'green'},
                        {'value': 50, 'color': 'yellow'},
                        {'value': 80, 'color': 'orange'},
                        {'value': 100, 'color': 'red'}
                    ]
                }
            },
            'memory_gauge': {
                'widget_type': WidgetType.GAUGE,
                'title': 'Memory Usage',
                'config': {
                    'min': 0,
                    'max': 100,
                    'unit': '%',
                    'thresholds': [
                        {'value': 25, 'color': 'green'},
                        {'value': 60, 'color': 'yellow'},
                        {'value': 85, 'color': 'orange'},
                        {'value': 100, 'color': 'red'}
                    ]
                }
            },
            'latency_chart': {
                'widget_type': WidgetType.CHART,
                'title': 'Latency Trend',
                'config': {
                    'chart_type': 'line',
                    'x_axis': 'time',
                    'y_axis': 'latency (ms)',
                    'show_legend': True,
                    'show_grid': True
                }
            },
            'throughput_chart': {
                'widget_type': WidgetType.CHART,
                'title': 'Throughput',
                'config': {
                    'chart_type': 'area',
                    'x_axis': 'time',
                    'y_axis': 'throughput (MB/s)',
                    'stacked': True
                }
            },
            'status_table': {
                'widget_type': WidgetType.TABLE,
                'title': 'Component Status',
                'config': {
                    'sortable': True,
                    'filterable': True,
                    'paginated': True,
                    'page_size': 10
                }
            },
            'alerts_widget': {
                'widget_type': WidgetType.ALERT,
                'title': 'Recent Alerts',
                'config': {
                    'max_alerts': 5,
                    'auto_dismiss': 0,  # Never auto-dismiss
                    'show_timestamp': True
                }
            }
        }

    def create_dashboard(self, name: str, description: str = "",
                        owner: str = "", is_public: bool = False) -> str:
        """
        Create new dashboard.

        Args:
            name: Dashboard name
            description: Dashboard description
            owner: Dashboard owner
            is_public: Whether dashboard is public

        Returns:
            Dashboard ID
        """
        try:
            import uuid

            dashboard_id = str(uuid.uuid4())

            dashboard = Dashboard(
                dashboard_id=dashboard_id,
                name=name,
                description=description,
                owner=owner,
                is_public=is_public
            )

            self.dashboards[dashboard_id] = dashboard

            self.logger.info(f"Created dashboard: {dashboard_id} ({name})")
            return dashboard_id

        except Exception as e:
            self.logger.error(f"Error creating dashboard: {e}")
            return ""

    def add_widget(self, dashboard_id: str, widget_type: str, title: str,
                  data_source: str = "", config: Optional[Dict[str, Any]] = None,
                  width: int = 6, height: int = 4) -> Optional[str]:
        """
        Add widget to dashboard.

        Args:
            dashboard_id: Dashboard ID
            widget_type: Type of widget
            title: Widget title
            data_source: Data source for widget
            config: Widget configuration
            width: Widget width (1-12)
            height: Widget height

        Returns:
            Widget ID if successful
        """
        try:
            if dashboard_id not in self.dashboards:
                return None

            import uuid

            widget_id = str(uuid.uuid4())
            dashboard = self.dashboards[dashboard_id]

            widget = Widget(
                widget_id=widget_id,
                widget_type=WidgetType(widget_type.lower()),
                title=title,
                data_source=data_source,
                width=width,
                height=height,
                config=config or {}
            )

            dashboard.widgets[widget_id] = widget
            self.widgets[widget_id] = widget

            # Auto-arrange if enabled
            if dashboard.auto_arrange:
                self._arrange_widgets(dashboard)

            dashboard.modified_at = time.time()

            self.logger.info(f"Added widget {widget_id} to dashboard {dashboard_id}")
            return widget_id

        except Exception as e:
            self.logger.error(f"Error adding widget: {e}")
            return None

    def remove_widget(self, dashboard_id: str, widget_id: str) -> bool:
        """
        Remove widget from dashboard.

        Args:
            dashboard_id: Dashboard ID
            widget_id: Widget ID

        Returns:
            True if removed successfully
        """
        try:
            if dashboard_id not in self.dashboards:
                return False

            dashboard = self.dashboards[dashboard_id]

            if widget_id not in dashboard.widgets:
                return False

            del dashboard.widgets[widget_id]
            del self.widgets[widget_id]

            dashboard.modified_at = time.time()

            self.logger.info(f"Removed widget {widget_id} from dashboard {dashboard_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error removing widget: {e}")
            return False

    def register_data_provider(self, metric_name: str, provider: Callable) -> None:
        """
        Register data provider for metric.

        Args:
            metric_name: Metric name
            provider: Callable that returns metric data
        """
        try:
            self.data_providers[metric_name] = provider
            self.logger.info(f"Registered data provider for {metric_name}")

        except Exception as e:
            self.logger.error(f"Error registering provider: {e}")

    def _arrange_widgets(self, dashboard: Dashboard) -> None:
        """Auto-arrange widgets in grid layout"""
        try:
            row, col = 0, 0

            for widget_id, widget in dashboard.widgets.items():
                widget.position = (row, col)

                col += widget.width

                if col >= dashboard.grid_columns:
                    col = 0
                    row += 1

        except Exception as e:
            self.logger.error(f"Error arranging widgets: {e}")

    def get_dashboard_data(self, dashboard_id: str) -> Optional[DashboardData]:
        """
        Get rendered dashboard data.

        Args:
            dashboard_id: Dashboard ID

        Returns:
            DashboardData if available
        """
        try:
            if dashboard_id not in self.dashboards:
                return None

            dashboard = self.dashboards[dashboard_id]
            dashboard_data = DashboardData(dashboard_id=dashboard_id)

            # Collect widget data
            for widget_id, widget in dashboard.widgets.items():
                if not widget.enabled:
                    continue

                widget_data = {
                    'widget_id': widget_id,
                    'widget_type': widget.widget_type.value,
                    'title': widget.title,
                    'data_source': widget.data_source,
                    'position': widget.position,
                    'size': {'width': widget.width, 'height': widget.height},
                    'config': widget.config
                }

                # Get data from provider if available
                if widget.data_source and widget.data_source in self.data_providers:
                    try:
                        widget_data['data'] = self.data_providers[widget.data_source]()
                    except Exception as e:
                        self.logger.warning(f"Error fetching data for {widget.data_source}: {e}")
                        widget_data['data'] = None

                dashboard_data.widgets[widget_id] = widget_data

            return dashboard_data

        except Exception as e:
            self.logger.error(f"Error getting dashboard data: {e}")
            return None

    def get_dashboard_list(self) -> List[Dict[str, Any]]:
        """Get list of all dashboards"""
        try:
            return [
                {
                    'dashboard_id': dashboard.dashboard_id,
                    'name': dashboard.name,
                    'description': dashboard.description,
                    'widget_count': len(dashboard.widgets),
                    'owner': dashboard.owner,
                    'is_public': dashboard.is_public,
                    'created_at': dashboard.created_at,
                    'modified_at': dashboard.modified_at
                }
                for dashboard in self.dashboards.values()
            ]

        except Exception as e:
            self.logger.error(f"Error getting dashboard list: {e}")
            return []

    def export_dashboard(self, dashboard_id: str) -> Optional[Dict[str, Any]]:
        """
        Export dashboard configuration.

        Args:
            dashboard_id: Dashboard ID

        Returns:
            Dashboard configuration
        """
        try:
            if dashboard_id not in self.dashboards:
                return None

            dashboard = self.dashboards[dashboard_id]

            return {
                'dashboard_id': dashboard.dashboard_id,
                'name': dashboard.name,
                'description': dashboard.description,
                'layout': dashboard.layout,
                'grid_columns': dashboard.grid_columns,
                'owner': dashboard.owner,
                'is_public': dashboard.is_public,
                'tags': dashboard.tags,
                'widgets': [
                    {
                        'widget_id': widget.widget_id,
                        'widget_type': widget.widget_type.value,
                        'title': widget.title,
                        'data_source': widget.data_source,
                        'position': widget.position,
                        'size': {'width': widget.width, 'height': widget.height},
                        'config': widget.config
                    }
                    for widget in dashboard.widgets.values()
                ]
            }

        except Exception as e:
            self.logger.error(f"Error exporting dashboard: {e}")
            return None

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get dashboard system summary"""
        try:
            return {
                'timestamp': time.time(),
                'total_dashboards': len(self.dashboards),
                'total_widgets': len(self.widgets),
                'data_providers': len(self.data_providers),
                'widget_templates': len(self.widget_templates),
                'dashboards': self.get_dashboard_list()
            }

        except Exception as e:
            self.logger.error(f"Error getting summary: {e}")
            return {}
