#!/usr/bin/env python3
"""
Novel Content Audit System - Health Check Script
Comprehensive health monitoring and system validation
"""

import asyncio
import aiohttp
import json
import time
import sys
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ServiceCheck:
    """Service health check result"""
    name: str
    url: str
    status: str
    response_time: float
    details: Dict[str, Any]
    error: Optional[str] = None

class HealthChecker:
    """Comprehensive system health checker"""

    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url.rstrip('/')
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_service(self, name: str, url: str, expected_status: int = 200) -> ServiceCheck:
        """Check individual service health"""
        start_time = time.time()

        try:
            async with self.session.get(url) as response:
                response_time = (time.time() - start_time) * 1000  # ms

                if response.status == expected_status:
                    try:
                        data = await response.json()
                        return ServiceCheck(
                            name=name,
                            url=url,
                            status="healthy",
                            response_time=response_time,
                            details=data
                        )
                    except json.JSONDecodeError:
                        text = await response.text()
                        return ServiceCheck(
                            name=name,
                            url=url,
                            status="healthy",
                            response_time=response_time,
                            details={"response": text[:200] + "..." if len(text) > 200 else text}
                        )
                else:
                    return ServiceCheck(
                        name=name,
                        url=url,
                        status="unhealthy",
                        response_time=response_time,
                        details={"http_status": response.status},
                        error=f"HTTP {response.status}"
                    )

        except aiohttp.ClientError as e:
            response_time = (time.time() - start_time) * 1000
            return ServiceCheck(
                name=name,
                url=url,
                status="unreachable",
                response_time=response_time,
                details={},
                error=str(e)
            )
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return ServiceCheck(
                name=name,
                url=url,
                status="timeout",
                response_time=response_time,
                details={},
                error="Request timeout"
            )

    async def check_api_functionality(self) -> Dict[str, Any]:
        """Test core API functionality"""
        functionality_tests = {}

        # Test health endpoint
        health_check = await self.check_service(
            "API Health",
            f"{self.base_url}:8000/health"
        )
        functionality_tests["health_endpoint"] = health_check.status == "healthy"

        # Test audit endpoint with sample content
        try:
            test_content = {
                "content": "这是一个用于健康检查的测试内容，应该被正常处理。",
                "metadata": {"test": True}
            }

            start_time = time.time()
            async with self.session.post(
                f"{self.base_url}:8000/api/v1/audit",
                json=test_content
            ) as response:
                audit_time = (time.time() - start_time) * 1000

                if response.status == 200:
                    audit_result = await response.json()
                    functionality_tests["audit_endpoint"] = {
                        "status": "healthy",
                        "response_time_ms": audit_time,
                        "decision": audit_result.get("final_decision"),
                        "confidence": audit_result.get("confidence_score")
                    }
                else:
                    functionality_tests["audit_endpoint"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status}"
                    }

        except Exception as e:
            functionality_tests["audit_endpoint"] = {
                "status": "error",
                "error": str(e)
            }

        # Test monitoring endpoint
        try:
            async with self.session.get(f"{self.base_url}:8000/api/v1/monitoring/performance") as response:
                if response.status == 200:
                    perf_data = await response.json()
                    functionality_tests["monitoring_endpoint"] = {
                        "status": "healthy",
                        "metrics_available": bool(perf_data.get("performance_summary"))
                    }
                else:
                    functionality_tests["monitoring_endpoint"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status}"
                    }
        except Exception as e:
            functionality_tests["monitoring_endpoint"] = {
                "status": "error",
                "error": str(e)
            }

        return functionality_tests

    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check"""
        logger.info("Starting comprehensive health check...")

        # Define services to check
        services = [
            ("Novel Audit API", f"{self.base_url}:8000/health"),
            ("ChromaDB", f"{self.base_url}:8001/api/v1/heartbeat"),
            ("Redis", f"{self.base_url}:6379"),  # Would need Redis HTTP interface
            ("Nginx", f"{self.base_url}/health"),
            ("Prometheus", f"{self.base_url}:9090/-/healthy"),
            ("Grafana", f"{self.base_url}:3000/api/health"),
            ("Elasticsearch", f"{self.base_url}:9200/_cluster/health"),
            ("Kibana", f"{self.base_url}:5601/api/status")
        ]

        # Check all services concurrently
        service_checks = await asyncio.gather(
            *[self.check_service(name, url) for name, url in services],
            return_exceptions=True
        )

        # Process results
        service_results = {}
        overall_health = "healthy"

        for check in service_checks:
            if isinstance(check, Exception):
                continue

            service_results[check.name] = {
                "status": check.status,
                "response_time_ms": round(check.response_time, 2),
                "url": check.url,
                "error": check.error,
                "details": check.details
            }

            # Update overall health
            if check.status in ["unhealthy", "unreachable"]:
                overall_health = "critical"
            elif check.status == "timeout" and overall_health == "healthy":
                overall_health = "degraded"

        # Check API functionality
        api_functionality = await self.check_api_functionality()

        # Check if core functionality is working
        core_services_healthy = all(
            service_results.get(service, {}).get("status") == "healthy"
            for service in ["Novel Audit API", "ChromaDB"]
        )

        if not core_services_healthy:
            overall_health = "critical"

        # Compile comprehensive report
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_health": overall_health,
            "summary": {
                "total_services": len(service_results),
                "healthy_services": sum(1 for s in service_results.values() if s["status"] == "healthy"),
                "unhealthy_services": sum(1 for s in service_results.values() if s["status"] != "healthy"),
                "core_functionality": "working" if core_services_healthy else "impaired"
            },
            "services": service_results,
            "api_functionality": api_functionality,
            "recommendations": self._generate_recommendations(service_results, api_functionality)
        }

        return report

    def _generate_recommendations(self, service_results: Dict, api_functionality: Dict) -> List[str]:
        """Generate health recommendations"""
        recommendations = []

        # Check for critical services
        critical_services = ["Novel Audit API", "ChromaDB"]
        for service in critical_services:
            if service in service_results and service_results[service]["status"] != "healthy":
                recommendations.append(f"CRITICAL: {service} is not healthy - immediate attention required")

        # Check response times
        slow_services = [
            name for name, data in service_results.items()
            if data["response_time_ms"] > 1000
        ]
        if slow_services:
            recommendations.append(f"Performance: Slow response times detected for {', '.join(slow_services)}")

        # Check API functionality
        if not api_functionality.get("audit_endpoint", {}).get("status") == "healthy":
            recommendations.append("CRITICAL: Core audit functionality is not working")

        # Check monitoring
        if not api_functionality.get("monitoring_endpoint", {}).get("status") == "healthy":
            recommendations.append("WARNING: Monitoring endpoint is not accessible")

        # General recommendations
        if not recommendations:
            recommendations.append("All systems are operating normally")

        return recommendations

def print_health_report(report: Dict[str, Any], format_type: str = "text"):
    """Print health report in specified format"""

    if format_type == "json":
        print(json.dumps(report, indent=2))
        return

    # Text format
    print("=" * 70)
    print("NOVEL CONTENT AUDIT SYSTEM - HEALTH CHECK REPORT")
    print("=" * 70)
    print(f"Timestamp: {report['timestamp']}")
    print(f"Overall Health: {report['overall_health'].upper()}")

    # Summary
    summary = report['summary']
    print(f"\nSummary:")
    print(f"  Total Services: {summary['total_services']}")
    print(f"  Healthy: {summary['healthy_services']}")
    print(f"  Unhealthy: {summary['unhealthy_services']}")
    print(f"  Core Functionality: {summary['core_functionality']}")

    # Service status
    print(f"\nService Status:")
    for service, data in report['services'].items():
        status = data['status'].upper()
        response_time = data['response_time_ms']

        status_icon = "✓" if status == "HEALTHY" else "✗"
        print(f"  {status_icon} {service:<20} {status:<12} ({response_time}ms)")

        if data['error']:
            print(f"    Error: {data['error']}")

    # API Functionality
    print(f"\nAPI Functionality:")
    for test, result in report['api_functionality'].items():
        if isinstance(result, dict):
            status = result.get('status', 'unknown').upper()
            status_icon = "✓" if status == "HEALTHY" else "✗"
            print(f"  {status_icon} {test.replace('_', ' ').title():<20} {status}")
        else:
            status_icon = "✓" if result else "✗"
            print(f"  {status_icon} {test.replace('_', ' ').title():<20} {'PASS' if result else 'FAIL'}")

    # Recommendations
    print(f"\nRecommendations:")
    for i, rec in enumerate(report['recommendations'], 1):
        print(f"  {i}. {rec}")

    print("=" * 70)

async def main():
    """Main health check function"""
    parser = argparse.ArgumentParser(description='Novel Content Audit System Health Check')
    parser.add_argument('--url', default='http://localhost', help='Base URL for services')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--timeout', type=int, default=30, help='Request timeout in seconds')
    parser.add_argument('--continuous', action='store_true', help='Run continuous health checks')
    parser.add_argument('--interval', type=int, default=60, help='Interval for continuous checks (seconds)')

    args = parser.parse_args()

    try:
        async with HealthChecker(args.url) as checker:
            if args.continuous:
                logger.info(f"Starting continuous health checks every {args.interval} seconds...")
                while True:
                    try:
                        report = await checker.comprehensive_health_check()
                        print_health_report(report, args.format)

                        # Exit with appropriate code for monitoring systems
                        if report['overall_health'] == 'critical':
                            logger.error("Critical health issues detected!")

                        await asyncio.sleep(args.interval)
                    except KeyboardInterrupt:
                        logger.info("Health check interrupted by user")
                        break
            else:
                report = await checker.comprehensive_health_check()
                print_health_report(report, args.format)

                # Exit with appropriate code for monitoring systems
                if report['overall_health'] == 'critical':
                    sys.exit(1)
                elif report['overall_health'] == 'degraded':
                    sys.exit(2)
                else:
                    sys.exit(0)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        if args.format == 'json':
            error_report = {
                "timestamp": datetime.now().isoformat(),
                "overall_health": "critical",
                "error": str(e)
            }
            print(json.dumps(error_report, indent=2))
        else:
            print(f"Health check failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())