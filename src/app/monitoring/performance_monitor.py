"""
Performance monitoring and optimization system for the audit workflow
Tracks processing times, resource usage, and system health metrics
"""
import time
import asyncio
import psutil
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
from functools import wraps
import logging

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""
    operation: str
    start_time: float
    end_time: float
    duration: float
    memory_usage_mb: float
    cpu_percent: float
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

class PerformanceMonitor:
    """Comprehensive performance monitoring system"""

    def __init__(self):
        self.metrics_history: List[PerformanceMetrics] = []
        self.active_operations: Dict[str, float] = {}
        self.system_alerts: List[Dict[str, Any]] = []
        self.monitoring_enabled = True

    @asynccontextmanager
    async def monitor_operation(self, operation_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Context manager for monitoring operation performance"""
        if not self.monitoring_enabled:
            yield
            return

        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        start_cpu = psutil.cpu_percent()

        operation_id = f"{operation_name}_{int(start_time)}"
        self.active_operations[operation_id] = start_time

        try:
            yield
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            end_cpu = psutil.cpu_percent()

            metrics = PerformanceMetrics(
                operation=operation_name,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                memory_usage_mb=end_memory - start_memory,
                cpu_percent=(start_cpu + end_cpu) / 2,
                success=success,
                error=error,
                metadata=metadata or {}
            )

            self.metrics_history.append(metrics)
            self.active_operations.pop(operation_id, None)

            # Check for performance alerts
            await self._check_performance_alerts(metrics)

    def performance_decorator(self, operation_name: str = None):
        """Decorator for monitoring function performance"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                op_name = operation_name or f"{func.__module__}.{func.__name__}"
                async with self.monitor_operation(op_name):
                    return await func(*args, **kwargs)

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                op_name = operation_name or f"{func.__module__}.{func.__name__}"
                # For sync functions, we'll create a simple synchronous context
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    success = True
                    error = None
                    return result
                except Exception as e:
                    success = False
                    error = str(e)
                    raise
                finally:
                    end_time = time.time()
                    metrics = PerformanceMetrics(
                        operation=op_name,
                        start_time=start_time,
                        end_time=end_time,
                        duration=end_time - start_time,
                        memory_usage_mb=psutil.Process().memory_info().rss / 1024 / 1024,
                        cpu_percent=psutil.cpu_percent(),
                        success=success,
                        error=error
                    )
                    self.metrics_history.append(metrics)

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator

    async def _check_performance_alerts(self, metrics: PerformanceMetrics):
        """Check for performance issues and generate alerts"""
        alerts = []

        # Duration alerts
        if metrics.duration > 30.0:  # 30 seconds
            alerts.append({
                'type': 'SLOW_OPERATION',
                'message': f'{metrics.operation} took {metrics.duration:.2f}s',
                'severity': 'HIGH' if metrics.duration > 60 else 'MEDIUM'
            })

        # Memory alerts
        if metrics.memory_usage_mb > 500:  # 500MB increase
            alerts.append({
                'type': 'HIGH_MEMORY_USAGE',
                'message': f'{metrics.operation} used {metrics.memory_usage_mb:.2f}MB',
                'severity': 'HIGH' if metrics.memory_usage_mb > 1000 else 'MEDIUM'
            })

        # CPU alerts
        if metrics.cpu_percent > 80:
            alerts.append({
                'type': 'HIGH_CPU_USAGE',
                'message': f'{metrics.operation} used {metrics.cpu_percent:.1f}% CPU',
                'severity': 'MEDIUM'
            })

        # Error alerts
        if not metrics.success:
            alerts.append({
                'type': 'OPERATION_FAILURE',
                'message': f'{metrics.operation} failed: {metrics.error}',
                'severity': 'HIGH'
            })

        # Add alerts to system alerts
        for alert in alerts:
            alert['timestamp'] = datetime.now().isoformat()
            alert['operation'] = metrics.operation
            self.system_alerts.append(alert)
            logger.warning(f"Performance Alert: {alert['message']}")

    def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance summary for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        recent_metrics = [m for m in self.metrics_history if m.start_time >= cutoff_time]

        if not recent_metrics:
            return {
                'status': 'no_data',
                'message': f'No performance data in the last {hours} hours'
            }

        # Calculate statistics
        total_operations = len(recent_metrics)
        successful_operations = sum(1 for m in recent_metrics if m.success)
        failed_operations = total_operations - successful_operations

        durations = [m.duration for m in recent_metrics]
        memory_usage = [m.memory_usage_mb for m in recent_metrics]

        # Operations by type
        operation_counts = {}
        operation_avg_duration = {}
        for metric in recent_metrics:
            op = metric.operation
            operation_counts[op] = operation_counts.get(op, 0) + 1
            if op not in operation_avg_duration:
                operation_avg_duration[op] = []
            operation_avg_duration[op].append(metric.duration)

        # Calculate averages
        for op in operation_avg_duration:
            operation_avg_duration[op] = sum(operation_avg_duration[op]) / len(operation_avg_duration[op])

        # Recent alerts
        alert_cutoff = datetime.now() - timedelta(hours=hours)
        recent_alerts = [
            alert for alert in self.system_alerts
            if datetime.fromisoformat(alert['timestamp']) >= alert_cutoff
        ]

        return {
            'time_period': f'last_{hours}_hours',
            'total_operations': total_operations,
            'success_rate': f'{(successful_operations / total_operations * 100):.1f}%',
            'failed_operations': failed_operations,
            'performance_stats': {
                'avg_duration': f'{sum(durations) / len(durations):.3f}s',
                'max_duration': f'{max(durations):.3f}s',
                'min_duration': f'{min(durations):.3f}s',
                'avg_memory_usage': f'{sum(memory_usage) / len(memory_usage):.1f}MB',
                'max_memory_usage': f'{max(memory_usage):.1f}MB'
            },
            'operations_breakdown': operation_counts,
            'operation_avg_durations': {op: f'{duration:.3f}s' for op, duration in operation_avg_duration.items()},
            'recent_alerts': len(recent_alerts),
            'alert_breakdown': self._categorize_alerts(recent_alerts),
            'system_health': self._assess_system_health(recent_metrics, recent_alerts)
        }

    def _categorize_alerts(self, alerts: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize alerts by type and severity"""
        categories = {}
        for alert in alerts:
            alert_type = alert.get('type', 'UNKNOWN')
            categories[alert_type] = categories.get(alert_type, 0) + 1
        return categories

    def _assess_system_health(self, metrics: List[PerformanceMetrics], alerts: List[Dict[str, Any]]) -> str:
        """Assess overall system health"""
        if not metrics:
            return 'UNKNOWN'

        success_rate = sum(1 for m in metrics if m.success) / len(metrics)
        avg_duration = sum(m.duration for m in metrics) / len(metrics)
        high_severity_alerts = sum(1 for a in alerts if a.get('severity') == 'HIGH')

        if success_rate >= 0.95 and avg_duration < 5.0 and high_severity_alerts == 0:
            return 'EXCELLENT'
        elif success_rate >= 0.90 and avg_duration < 10.0 and high_severity_alerts < 3:
            return 'GOOD'
        elif success_rate >= 0.80 and avg_duration < 20.0 and high_severity_alerts < 5:
            return 'FAIR'
        else:
            return 'POOR'

    def get_system_health_report(self) -> Dict[str, Any]:
        """Get comprehensive system health report"""
        current_time = datetime.now()

        # System resource info
        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage('/')
        cpu_info = psutil.cpu_percent(interval=1)

        # Active operations
        active_ops_info = []
        current_timestamp = time.time()
        for op_id, start_time in self.active_operations.items():
            duration = current_timestamp - start_time
            active_ops_info.append({
                'operation_id': op_id,
                'duration': f'{duration:.2f}s',
                'status': 'LONG_RUNNING' if duration > 30 else 'NORMAL'
            })

        return {
            'timestamp': current_time.isoformat(),
            'system_resources': {
                'memory_total_gb': f'{memory_info.total / (1024**3):.2f}GB',
                'memory_used_percent': f'{memory_info.percent}%',
                'memory_available_gb': f'{memory_info.available / (1024**3):.2f}GB',
                'disk_usage_percent': f'{disk_info.percent}%',
                'cpu_usage_percent': f'{cpu_info}%'
            },
            'active_operations': {
                'count': len(active_ops_info),
                'operations': active_ops_info
            },
            'metrics_history_size': len(self.metrics_history),
            'total_alerts': len(self.system_alerts),
            'performance_summary_24h': self.get_performance_summary(24),
            'recommendations': self._generate_optimization_recommendations()
        }

    def _generate_optimization_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on performance data"""
        recommendations = []

        if not self.metrics_history:
            return ['Insufficient performance data for recommendations']

        recent_metrics = self.metrics_history[-100:]  # Last 100 operations

        # Analyze duration patterns
        slow_operations = [m for m in recent_metrics if m.duration > 10.0]
        if slow_operations:
            slow_ops_by_type = {}
            for metric in slow_operations:
                op_type = metric.operation
                slow_ops_by_type[op_type] = slow_ops_by_type.get(op_type, 0) + 1

            for op_type, count in slow_ops_by_type.items():
                recommendations.append(f'Optimize {op_type} - {count} slow executions detected')

        # Analyze memory usage
        high_memory_ops = [m for m in recent_metrics if m.memory_usage_mb > 200]
        if high_memory_ops:
            recommendations.append('Consider memory optimization for high-usage operations')

        # Analyze error rates
        failed_ops = [m for m in recent_metrics if not m.success]
        if len(failed_ops) > len(recent_metrics) * 0.05:  # More than 5% failure rate
            recommendations.append('Investigate and fix recurring operation failures')

        # Active operations check
        if len(self.active_operations) > 10:
            recommendations.append('High number of concurrent operations - consider queue management')

        # Default recommendations
        if not recommendations:
            recommendations = [
                'System performance is healthy',
                'Continue regular monitoring',
                'Consider implementing caching for frequently accessed data'
            ]

        return recommendations

    def clear_old_metrics(self, hours: int = 168):  # Default 7 days
        """Clear metrics older than specified hours"""
        cutoff_time = time.time() - (hours * 3600)
        initial_count = len(self.metrics_history)

        self.metrics_history = [m for m in self.metrics_history if m.start_time >= cutoff_time]

        # Also clear old alerts
        alert_cutoff = datetime.now() - timedelta(hours=hours)
        initial_alert_count = len(self.system_alerts)

        self.system_alerts = [
            alert for alert in self.system_alerts
            if datetime.fromisoformat(alert['timestamp']) >= alert_cutoff
        ]

        cleared_metrics = initial_count - len(self.metrics_history)
        cleared_alerts = initial_alert_count - len(self.system_alerts)

        logger.info(f'Cleared {cleared_metrics} old metrics and {cleared_alerts} old alerts')

        return {
            'metrics_cleared': cleared_metrics,
            'alerts_cleared': cleared_alerts,
            'remaining_metrics': len(self.metrics_history),
            'remaining_alerts': len(self.system_alerts)
        }

    def export_metrics(self, filename: str = None) -> str:
        """Export performance metrics to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'performance_metrics_{timestamp}.json'

        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_metrics': len(self.metrics_history),
            'total_alerts': len(self.system_alerts),
            'metrics': [metric.to_dict() for metric in self.metrics_history],
            'alerts': self.system_alerts,
            'system_health': self.get_system_health_report()
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f'Performance metrics exported to {filename}')
            return filename

        except Exception as e:
            logger.error(f'Failed to export metrics: {e}')
            raise


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Optimization utilities
class WorkflowOptimizer:
    """Optimization utilities for audit workflows"""

    @staticmethod
    async def optimize_concurrent_processing(tasks: List, max_concurrent: int = 5):
        """Optimize concurrent task processing with semaphore"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(task):
            async with semaphore:
                return await task

        if asyncio.iscoroutinefunction(tasks[0]):
            # Tasks are coroutines
            return await asyncio.gather(*[process_with_limit(task) for task in tasks])
        else:
            # Tasks are functions that return coroutines
            return await asyncio.gather(*[process_with_limit(task()) for task in tasks])

    @staticmethod
    def cache_decorator(ttl_seconds: int = 300):
        """Simple in-memory cache decorator"""
        cache = {}
        cache_timestamps = {}

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Create cache key
                cache_key = f"{func.__name__}_{hash((args, tuple(sorted(kwargs.items()))))}"

                # Check cache validity
                current_time = time.time()
                if cache_key in cache and cache_key in cache_timestamps:
                    if current_time - cache_timestamps[cache_key] < ttl_seconds:
                        return cache[cache_key]

                # Execute function and cache result
                result = await func(*args, **kwargs)
                cache[cache_key] = result
                cache_timestamps[cache_key] = current_time

                return result

            return wrapper
        return decorator

    @staticmethod
    async def batch_process_with_backpressure(items: List, processor_func, batch_size: int = 10, delay_between_batches: float = 0.1):
        """Process items in batches with backpressure control"""
        results = []

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]

            # Process batch
            batch_tasks = [processor_func(item) for item in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            results.extend(batch_results)

            # Add delay between batches to prevent overwhelming the system
            if i + batch_size < len(items) and delay_between_batches > 0:
                await asyncio.sleep(delay_between_batches)

        return results


# Global optimizer instance
workflow_optimizer = WorkflowOptimizer()