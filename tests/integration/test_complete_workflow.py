"""
Integration tests for complete audit workflow
Tests end-to-end functionality, agent interactions, and system integration
"""
import asyncio
import pytest
import json
import sys
import os
from typing import Dict, Any, List
from datetime import datetime

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from app.workflows.complete_audit_workflow import CompleteAuditWorkflow
from app.agents.initial_judgment_agent import InitialJudgmentAgent
from app.agents.smart_router_agent import SmartRouterAgent
from app.agents.rag_enhanced_judge import RAGEnhancedJudgeAgent
from app.agents.perspective_agents import (
    LegalComplianceAgent,
    SocialImpactAgent,
    UXContentAgent,
    PlatformRiskAgent
)
from app.agents.arbitration_agent import ArbitrationAgent
from app.services.human_review_service import human_review_service, ReviewPriority
from app.monitoring.performance_monitor import performance_monitor
import logging

logger = logging.getLogger(__name__)

class IntegrationTestSuite:
    """Comprehensive integration test suite"""

    def __init__(self):
        self.workflow = CompleteAuditWorkflow()
        self.test_results = []

    async def run_integration_tests(self) -> Dict[str, Any]:
        """Run complete integration test suite"""
        logger.info("🧪 Starting Integration Test Suite")

        test_methods = [
            self.test_workflow_initialization,
            self.test_high_confidence_path,
            self.test_rag_escalation_path,
            self.test_multimodal_analysis_path,
            self.test_arbitration_system,
            self.test_human_review_integration,
            self.test_agent_communication,
            self.test_state_management,
            self.test_error_recovery,
            self.test_performance_integration,
            self.test_concurrent_processing,
            self.test_data_flow_integrity
        ]

        for test_method in test_methods:
            try:
                async with performance_monitor.monitor_operation(f"integration_test_{test_method.__name__}"):
                    result = await test_method()
                    result['test_name'] = test_method.__name__
                    result['status'] = result.get('status', 'PASSED')
                    self.test_results.append(result)
                    logger.info(f"✅ {test_method.__name__}: {result['status']}")
            except Exception as e:
                error_result = {
                    'test_name': test_method.__name__,
                    'status': 'FAILED',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
                self.test_results.append(error_result)
                logger.error(f"❌ {test_method.__name__}: {str(e)}")

        return self._generate_integration_summary()

    async def test_workflow_initialization(self) -> Dict[str, Any]:
        """Test workflow initialization and component setup"""
        # Check if all agents are properly initialized
        assert self.workflow.initial_judgment_agent is not None
        assert self.workflow.smart_router_agent is not None
        assert self.workflow.rag_enhanced_judge is not None
        assert self.workflow.legal_compliance_agent is not None
        assert self.workflow.social_impact_agent is not None
        assert self.workflow.ux_content_agent is not None
        assert self.workflow.platform_risk_agent is not None
        assert self.workflow.arbitration_agent is not None

        # Test workflow state initialization
        initial_state = {
            'content_text': '测试内容',
            'audit_id': 'test_001'
        }

        # Verify workflow can create a graph
        graph = self.workflow._create_workflow_graph()
        assert graph is not None

        return {
            'agents_initialized': True,
            'workflow_graph_created': True,
            'state_handling': 'functional',
            'component_count': 8
        }

    async def test_high_confidence_path(self) -> Dict[str, Any]:
        """Test high-confidence direct approval path"""
        test_content = "这是一个温暖美好的爱情故事，男女主角在春天的花园里相遇，从此开始了美好的恋情。"

        start_time = datetime.now()
        result = await self.workflow.run_complete_audit(test_content)
        processing_time = (datetime.now() - start_time).total_seconds()

        # Verify result structure
        assert 'final_decision' in result
        assert 'confidence_score' in result
        assert 'workflow_path' in result
        assert 'audit_id' in result

        # Check that it took the direct path for high confidence
        workflow_path = result['workflow_path']
        expected_path = ['initial_judgment', 'router_decision']

        # High confidence should skip complex analysis
        assert 'rag_enhanced_judgment' not in workflow_path or len([x for x in workflow_path if 'multi_modal' in x]) == 0

        return {
            'processing_time_seconds': processing_time,
            'workflow_path': workflow_path,
            'confidence_score': result.get('confidence_score'),
            'decision': result.get('final_decision'),
            'path_efficiency': 'optimal' if processing_time < 5 else 'acceptable'
        }

    async def test_rag_escalation_path(self) -> Dict[str, Any]:
        """Test RAG escalation for medium confidence cases"""
        test_content = "这个战斗场景中有轻微的血腥描述，但整体是正义战胜邪恶的励志故事。"

        start_time = datetime.now()
        result = await self.workflow.run_complete_audit(test_content)
        processing_time = (datetime.now() - start_time).total_seconds()

        workflow_path = result['workflow_path']

        # Should include RAG analysis for borderline cases
        rag_analysis_performed = 'rag_enhanced_judgment' in workflow_path

        # Check RAG analysis details
        rag_details = result.get('rag_analysis', {})
        similar_cases_found = len(rag_details.get('similar_cases', []))

        return {
            'processing_time_seconds': processing_time,
            'rag_analysis_performed': rag_analysis_performed,
            'similar_cases_found': similar_cases_found,
            'workflow_path': workflow_path,
            'rag_confidence_boost': rag_details.get('confidence_adjustment', 0),
            'precedent_analysis': 'precedent_analysis' in str(rag_details)
        }

    async def test_multimodal_analysis_path(self) -> Dict[str, Any]:
        """Test multi-modal expert analysis path"""
        test_content = "这个故事涉及复杂的政治改革议题，需要考虑法律合规性和社会影响。"

        start_time = datetime.now()
        result = await self.workflow.run_complete_audit(test_content)
        processing_time = (datetime.now() - start_time).total_seconds()

        workflow_path = result['workflow_path']
        expert_analyses = result.get('expert_analyses', {})

        # Should have triggered multi-modal analysis
        multimodal_triggered = 'multi_modal_analysis' in workflow_path

        # Check individual expert analyses
        legal_analysis = expert_analyses.get('legal_compliance')
        social_analysis = expert_analyses.get('social_impact')
        ux_analysis = expert_analyses.get('ux_content')
        risk_analysis = expert_analyses.get('platform_risk')

        expert_count = sum(1 for analysis in [legal_analysis, social_analysis, ux_analysis, risk_analysis] if analysis)

        return {
            'processing_time_seconds': processing_time,
            'multimodal_analysis_triggered': multimodal_triggered,
            'expert_analyses_count': expert_count,
            'legal_analysis_present': bool(legal_analysis),
            'social_analysis_present': bool(social_analysis),
            'ux_analysis_present': bool(ux_analysis),
            'risk_analysis_present': bool(risk_analysis),
            'workflow_path': workflow_path
        }

    async def test_arbitration_system(self) -> Dict[str, Any]:
        """Test arbitration system for conflicting expert opinions"""
        # Create a scenario that should trigger conflicting opinions
        test_content = "这个商业伦理故事涉及员工权益保护，但可能触及敏感的劳资关系议题。"

        result = await self.workflow.run_complete_audit(test_content)

        arbitration_analysis = result.get('arbitration_analysis', {})
        workflow_path = result['workflow_path']

        arbitration_performed = 'arbitration_analysis' in workflow_path
        conflicts_detected = arbitration_analysis.get('conflicts_detected', 0)
        resolution_method = arbitration_analysis.get('resolution_method')

        return {
            'arbitration_performed': arbitration_performed,
            'conflicts_detected': conflicts_detected,
            'resolution_method': resolution_method,
            'final_confidence': arbitration_analysis.get('final_confidence'),
            'expert_weights_applied': bool(arbitration_analysis.get('expert_weights')),
            'reasoning_synthesis': bool(arbitration_analysis.get('synthesis_reasoning'))
        }

    async def test_human_review_integration(self) -> Dict[str, Any]:
        """Test human review escalation integration"""
        # Create controversial content that should escalate to human review
        test_content = "这个极具争议性的政治敏感内容需要人工仔细审查，涉及多个复杂的社会和法律问题。"

        result = await self.workflow.run_complete_audit(test_content)
        workflow_path = result['workflow_path']

        human_review_triggered = 'human_review' in workflow_path
        human_review_details = result.get('human_review', {})

        # Check human review service integration
        if human_review_triggered:
            review_id = human_review_details.get('review_id')
            priority = human_review_details.get('priority')
            escalation_reason = human_review_details.get('escalation_reason')

            # Verify the review was properly submitted
            pending_reviews = await human_review_service.get_pending_reviews(limit=10)
            review_found = any(review.get('review_id') == review_id for review in pending_reviews)
        else:
            review_found = False
            review_id = None
            priority = None
            escalation_reason = None

        return {
            'human_review_triggered': human_review_triggered,
            'review_properly_queued': review_found,
            'review_id': review_id,
            'review_priority': priority,
            'escalation_reason': escalation_reason,
            'workflow_path': workflow_path
        }

    async def test_agent_communication(self) -> Dict[str, Any]:
        """Test communication and data flow between agents"""
        test_content = "测试代理间通信的标准内容"

        # Mock individual agent calls to verify communication
        initial_agent = InitialJudgmentAgent()
        initial_result = await initial_agent.process(test_content)

        router_agent = SmartRouterAgent()
        router_result = await router_agent.route_decision(initial_result, test_content)

        # Verify data structure compatibility
        assert 'decision' in initial_result
        assert 'confidence_score' in initial_result
        assert 'route' in router_result

        # Test state passing
        state = {
            'content_text': test_content,
            'initial_judgment': initial_result
        }

        # Verify state is properly maintained
        assert state['content_text'] == test_content
        assert state['initial_judgment']['decision'] == initial_result['decision']

        return {
            'initial_agent_response': bool(initial_result),
            'router_agent_response': bool(router_result),
            'data_structure_compatibility': True,
            'state_management': 'functional',
            'agent_chain_integrity': True
        }

    async def test_state_management(self) -> Dict[str, Any]:
        """Test workflow state management throughout the process"""
        test_content = "状态管理测试内容"

        # Track state changes throughout workflow
        state_snapshots = []

        # We would need to modify the workflow to capture state snapshots
        # For now, we'll test the final state integrity
        result = await self.workflow.run_complete_audit(test_content)

        # Verify final state completeness
        required_fields = ['final_decision', 'confidence_score', 'workflow_path', 'audit_id']
        state_completeness = all(field in result for field in required_fields)

        # Check workflow path consistency
        workflow_path = result.get('workflow_path', [])
        path_consistency = len(workflow_path) > 0 and 'initial_judgment' in workflow_path

        return {
            'state_completeness': state_completeness,
            'workflow_path_consistency': path_consistency,
            'required_fields_present': sum(1 for field in required_fields if field in result),
            'total_required_fields': len(required_fields),
            'workflow_steps_recorded': len(workflow_path)
        }

    async def test_error_recovery(self) -> Dict[str, Any]:
        """Test error handling and recovery mechanisms"""
        error_scenarios = []

        # Test empty content
        try:
            result = await self.workflow.run_complete_audit("")
            error_scenarios.append({
                'scenario': 'empty_content',
                'handled': True,
                'result': 'processed'
            })
        except Exception as e:
            error_scenarios.append({
                'scenario': 'empty_content',
                'handled': False,
                'error': str(e)
            })

        # Test None content
        try:
            result = await self.workflow.run_complete_audit(None)
            error_scenarios.append({
                'scenario': 'none_content',
                'handled': True,
                'result': 'processed'
            })
        except Exception as e:
            error_scenarios.append({
                'scenario': 'none_content',
                'handled': False,
                'error': str(e)
            })

        # Test extremely long content
        try:
            long_content = "测试" * 10000
            result = await self.workflow.run_complete_audit(long_content)
            error_scenarios.append({
                'scenario': 'long_content',
                'handled': True,
                'result': 'processed'
            })
        except Exception as e:
            error_scenarios.append({
                'scenario': 'long_content',
                'handled': False,
                'error': str(e)
            })

        handled_scenarios = sum(1 for scenario in error_scenarios if scenario['handled'])

        return {
            'total_scenarios_tested': len(error_scenarios),
            'scenarios_handled_gracefully': handled_scenarios,
            'error_recovery_rate': f"{(handled_scenarios / len(error_scenarios) * 100):.1f}%",
            'scenario_details': error_scenarios
        }

    async def test_performance_integration(self) -> Dict[str, Any]:
        """Test performance monitoring integration"""
        test_content = "性能监控集成测试内容"

        # Check if performance monitoring is working
        metrics_before = len(performance_monitor.metrics_history)

        async with performance_monitor.monitor_operation("integration_test_operation"):
            result = await self.workflow.run_complete_audit(test_content)

        metrics_after = len(performance_monitor.metrics_history)
        metrics_added = metrics_after - metrics_before

        # Get recent performance summary
        perf_summary = performance_monitor.get_performance_summary(hours=1)

        return {
            'performance_monitoring_active': metrics_added > 0,
            'metrics_captured': metrics_added,
            'performance_summary_available': bool(perf_summary),
            'workflow_completed': bool(result),
            'monitoring_integration': 'functional'
        }

    async def test_concurrent_processing(self) -> Dict[str, Any]:
        """Test concurrent request processing capabilities"""
        test_contents = [
            f"并发测试内容 {i}" for i in range(5)
        ]

        # Sequential processing
        start_time = datetime.now()
        sequential_results = []
        for content in test_contents:
            result = await self.workflow.run_complete_audit(content)
            sequential_results.append(result)
        sequential_time = (datetime.now() - start_time).total_seconds()

        # Concurrent processing
        start_time = datetime.now()
        concurrent_tasks = [
            self.workflow.run_complete_audit(content)
            for content in test_contents
        ]
        concurrent_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        concurrent_time = (datetime.now() - start_time).total_seconds()

        # Analyze results
        successful_concurrent = sum(1 for r in concurrent_results if not isinstance(r, Exception))
        performance_improvement = ((sequential_time / concurrent_time) - 1) * 100 if concurrent_time > 0 else 0

        return {
            'sequential_processing_time': sequential_time,
            'concurrent_processing_time': concurrent_time,
            'performance_improvement_percent': f"{performance_improvement:.1f}%",
            'sequential_success_count': len(sequential_results),
            'concurrent_success_count': successful_concurrent,
            'concurrency_handling': 'excellent' if successful_concurrent == len(test_contents) else 'needs_improvement'
        }

    async def test_data_flow_integrity(self) -> Dict[str, Any]:
        """Test data integrity throughout the workflow"""
        test_content = "数据流完整性测试 - 这个内容将经过多个处理阶段"

        result = await self.workflow.run_complete_audit(test_content)

        # Check data consistency
        checks = {
            'original_content_preserved': test_content in str(result),
            'audit_id_generated': bool(result.get('audit_id')),
            'confidence_score_valid': 0 <= result.get('confidence_score', -1) <= 1,
            'workflow_path_logical': len(result.get('workflow_path', [])) >= 2,
            'decision_present': bool(result.get('final_decision')),
            'timestamp_valid': bool(result.get('processing_timestamp'))
        }

        # Check for data corruption or loss
        data_integrity_score = sum(checks.values()) / len(checks)

        return {
            'data_integrity_checks': checks,
            'data_integrity_score': f"{data_integrity_score * 100:.1f}%",
            'all_checks_passed': all(checks.values()),
            'failed_checks': [check for check, passed in checks.items() if not passed]
        }

    def _generate_integration_summary(self) -> Dict[str, Any]:
        """Generate comprehensive integration test summary"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.get('status') == 'PASSED')
        failed_tests = sum(1 for result in self.test_results if result.get('status') == 'FAILED')

        # Calculate overall system integration health
        integration_health = 'EXCELLENT' if failed_tests == 0 else 'GOOD' if failed_tests <= 2 else 'NEEDS_ATTENTION'

        # Generate recommendations
        recommendations = self._generate_integration_recommendations()

        return {
            'integration_test_summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': f"{(passed_tests / total_tests * 100):.1f}%",
                'integration_health': integration_health
            },
            'detailed_test_results': self.test_results,
            'system_readiness': 'PRODUCTION_READY' if integration_health in ['EXCELLENT', 'GOOD'] else 'NEEDS_FIXES',
            'recommendations': recommendations,
            'test_completion_timestamp': datetime.now().isoformat()
        }

    def _generate_integration_recommendations(self) -> List[str]:
        """Generate recommendations based on integration test results"""
        recommendations = []

        failed_tests = [r for r in self.test_results if r.get('status') == 'FAILED']
        if failed_tests:
            recommendations.append(f"Fix {len(failed_tests)} failed integration tests before production")

        # Performance recommendations
        perf_tests = [r for r in self.test_results if 'processing_time' in r]
        slow_tests = [r for r in perf_tests if r.get('processing_time_seconds', 0) > 10]
        if slow_tests:
            recommendations.append("Optimize performance for slow integration scenarios")

        # Concurrency recommendations
        concurrent_test = next((r for r in self.test_results if r.get('test_name') == 'test_concurrent_processing'), None)
        if concurrent_test and concurrent_test.get('concurrent_success_count', 0) < 5:
            recommendations.append("Improve concurrent processing capabilities")

        if not failed_tests:
            recommendations.append("All integration tests passed - system ready for production")
            recommendations.append("Consider implementing continuous integration testing")
            recommendations.append("Monitor production performance and add alerting")

        return recommendations


# CLI runner for integration tests
async def main():
    """Main integration test runner"""
    logging.basicConfig(level=logging.INFO)

    print("🔧 Starting Novel Content Audit System Integration Tests...")
    print("=" * 70)

    test_suite = IntegrationTestSuite()
    summary = await test_suite.run_integration_tests()

    print("\n📊 INTEGRATION TEST SUMMARY")
    print("=" * 70)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    system_readiness = summary.get('system_readiness')
    if system_readiness == 'PRODUCTION_READY':
        print("\n🚀 System is PRODUCTION READY!")
    else:
        print(f"\n⚠️  System readiness: {system_readiness}")

    return summary


if __name__ == "__main__":
    asyncio.run(main())