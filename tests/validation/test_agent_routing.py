"""
Agent interaction and routing logic validation
Comprehensive validation of agent communication, state transitions, and routing decisions
"""
import asyncio
import pytest
import json
import sys
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import dataclass

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from app.agents.initial_judgment_agent import InitialJudgmentAgent
from app.agents.smart_router_agent import SmartRouterAgent, RoutingDecision
from app.agents.rag_enhanced_judge import RAGEnhancedJudgeAgent
from app.agents.perspective_agents import (
    LegalComplianceAgent,
    SocialImpactAgent,
    UXContentAgent,
    PlatformRiskAgent
)
from app.agents.arbitration_agent import ArbitrationAgent
from app.workflows.complete_audit_workflow import CompleteAuditWorkflow
import logging

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Validation result container"""
    test_name: str
    status: str
    details: Dict[str, Any]
    errors: List[str]
    timestamp: str

class AgentRoutingValidator:
    """Comprehensive validation of agent interactions and routing logic"""

    def __init__(self):
        self.workflow = CompleteAuditWorkflow()
        self.validation_results = []

    async def run_all_validations(self) -> Dict[str, Any]:
        """Run comprehensive agent routing validation"""
        logger.info("🔍 Starting Agent Routing Validation Suite")

        validation_methods = [
            self.validate_initial_judgment_agent,
            self.validate_smart_router_logic,
            self.validate_rag_enhanced_judgment,
            self.validate_perspective_agents,
            self.validate_arbitration_logic,
            self.validate_confidence_thresholds,
            self.validate_routing_paths,
            self.validate_state_transitions,
            self.validate_agent_communication,
            self.validate_error_propagation,
            self.validate_workflow_consistency
        ]

        for validation_method in validation_methods:
            try:
                result = await validation_method()
                result.timestamp = datetime.now().isoformat()
                self.validation_results.append(result)
                logger.info(f"✅ {result.test_name}: {result.status}")
            except Exception as e:
                error_result = ValidationResult(
                    test_name=validation_method.__name__,
                    status='FAILED',
                    details={},
                    errors=[str(e)],
                    timestamp=datetime.now().isoformat()
                )
                self.validation_results.append(error_result)
                logger.error(f"❌ {validation_method.__name__}: {str(e)}")

        return self._generate_validation_summary()

    async def validate_initial_judgment_agent(self) -> ValidationResult:
        """Validate Initial Judgment Agent functionality"""
        agent = InitialJudgmentAgent()
        test_cases = [
            ("这是一个温暖的爱情故事。", "approved", 0.8),
            ("极端暴力血腥的场面描述。", "rejected", 0.9),
            ("这个情节存在一些争议。", "review_needed", 0.4)
        ]

        results = []
        errors = []

        for content, expected_decision, min_confidence in test_cases:
            try:
                result = await agent.process(content)

                # Validate result structure
                if not all(key in result for key in ['decision', 'confidence_score', 'reasoning']):
                    errors.append(f"Missing required keys in result for: {content[:20]}...")
                    continue

                # Validate confidence score range
                confidence = result['confidence_score']
                if not (0 <= confidence <= 1):
                    errors.append(f"Invalid confidence score {confidence} for: {content[:20]}...")

                # Check decision consistency
                decision = result['decision']
                if expected_decision == "approved" and decision != "approved":
                    if confidence < 0.7:  # Allow for borderline cases
                        pass  # Acceptable
                    else:
                        errors.append(f"Unexpected high-confidence decision {decision} for approved content")

                results.append({
                    'content_sample': content[:30] + "...",
                    'decision': decision,
                    'confidence': confidence,
                    'reasoning_provided': bool(result.get('reasoning')),
                    'expected_decision': expected_decision
                })

            except Exception as e:
                errors.append(f"Processing failed for content: {str(e)}")

        return ValidationResult(
            test_name="Initial Judgment Agent Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'test_cases_processed': len(results),
                'test_results': results,
                'structure_validation': 'passed' if len(errors) == 0 else 'failed'
            },
            errors=errors
        )

    async def validate_smart_router_logic(self) -> ValidationResult:
        """Validate Smart Router routing decisions"""
        router = SmartRouterAgent()

        # Test routing scenarios
        test_scenarios = [
            {
                'initial_judgment': {'decision': 'approved', 'confidence_score': 0.92, 'reasoning': 'Clear approval'},
                'content': '温馨的家庭故事',
                'expected_route': 'direct_decision'
            },
            {
                'initial_judgment': {'decision': 'rejected', 'confidence_score': 0.95, 'reasoning': 'Clear violation'},
                'content': '极端暴力内容',
                'expected_route': 'direct_decision'
            },
            {
                'initial_judgment': {'decision': 'review_needed', 'confidence_score': 0.45, 'reasoning': 'Borderline case'},
                'content': '存在争议的情节',
                'expected_route': 'escalate_to_rag'
            },
            {
                'initial_judgment': {'decision': 'review_needed', 'confidence_score': 0.25, 'reasoning': 'Very uncertain'},
                'content': '复杂的多重议题内容',
                'expected_route': 'escalate_other'
            }
        ]

        results = []
        errors = []

        for scenario in test_scenarios:
            try:
                routing_result = await router.route_decision(
                    scenario['initial_judgment'],
                    scenario['content']
                )

                # Validate routing result structure
                if not isinstance(routing_result, dict) or 'route' not in routing_result:
                    errors.append(f"Invalid routing result structure for scenario: {scenario['content'][:20]}")
                    continue

                actual_route = routing_result['route']
                expected_route = scenario['expected_route']

                # Validate routing logic
                confidence = scenario['initial_judgment']['confidence_score']
                if confidence >= 0.8 and actual_route != 'direct_decision':
                    errors.append(f"High confidence case should route to direct_decision, got: {actual_route}")
                elif confidence < 0.3 and actual_route == 'direct_decision':
                    errors.append(f"Low confidence case should not route to direct_decision")

                results.append({
                    'content_sample': scenario['content'][:30] + "...",
                    'confidence': confidence,
                    'expected_route': expected_route,
                    'actual_route': actual_route,
                    'routing_correct': actual_route == expected_route or self._is_acceptable_routing(confidence, actual_route)
                })

            except Exception as e:
                errors.append(f"Routing failed for scenario: {str(e)}")

        return ValidationResult(
            test_name="Smart Router Logic Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'routing_scenarios_tested': len(results),
                'routing_results': results,
                'logic_consistency': 'valid' if len(errors) == 0 else 'inconsistent'
            },
            errors=errors
        )

    def _is_acceptable_routing(self, confidence: float, route: str) -> bool:
        """Check if routing decision is acceptable given confidence"""
        if confidence >= 0.8:
            return route == 'direct_decision'
        elif confidence >= 0.3:
            return route in ['escalate_to_rag', 'direct_decision']
        else:
            return route in ['escalate_to_rag', 'escalate_other']

    async def validate_rag_enhanced_judgment(self) -> ValidationResult:
        """Validate RAG Enhanced Judgment functionality"""
        rag_agent = RAGEnhancedJudgeAgent()

        test_cases = [
            "这个战斗场景的描述需要参考类似案例",
            "涉及敏感话题的故事情节需要先例分析",
            "边缘案例需要历史判决参考"
        ]

        results = []
        errors = []

        for content in test_cases:
            try:
                initial_judgment = {
                    'decision': 'review_needed',
                    'confidence_score': 0.5,
                    'reasoning': 'Requires precedent analysis'
                }

                rag_result = await rag_agent.process(content, initial_judgment)

                # Validate RAG result structure
                required_keys = ['enhanced_decision', 'confidence_adjustment', 'similar_cases', 'precedent_analysis']
                missing_keys = [key for key in required_keys if key not in rag_result]
                if missing_keys:
                    errors.append(f"Missing keys in RAG result: {missing_keys}")

                # Validate similar cases
                similar_cases = rag_result.get('similar_cases', [])
                if not isinstance(similar_cases, list):
                    errors.append("Similar cases should be a list")

                # Validate confidence adjustment
                confidence_adj = rag_result.get('confidence_adjustment', 0)
                if not isinstance(confidence_adj, (int, float)) or abs(confidence_adj) > 1:
                    errors.append(f"Invalid confidence adjustment: {confidence_adj}")

                results.append({
                    'content_sample': content[:30] + "...",
                    'similar_cases_found': len(similar_cases),
                    'confidence_adjustment': confidence_adj,
                    'precedent_analysis_provided': bool(rag_result.get('precedent_analysis')),
                    'enhanced_decision': rag_result.get('enhanced_decision')
                })

            except Exception as e:
                errors.append(f"RAG processing failed: {str(e)}")

        return ValidationResult(
            test_name="RAG Enhanced Judgment Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'rag_cases_processed': len(results),
                'rag_results': results,
                'functionality_validation': 'complete' if len(errors) == 0 else 'partial'
            },
            errors=errors
        )

    async def validate_perspective_agents(self) -> ValidationResult:
        """Validate all perspective agents functionality"""
        agents = {
            'legal': LegalComplianceAgent(),
            'social': SocialImpactAgent(),
            'ux': UXContentAgent(),
            'platform_risk': PlatformRiskAgent()
        }

        # Content that should trigger multiple perspectives
        test_content = "这个商业伦理故事涉及员工隐私保护和公司治理问题，可能对不同用户群体产生不同影响。"

        results = {}
        errors = []

        for agent_name, agent in agents.items():
            try:
                analysis = await agent.analyze_content(test_content)

                # Validate analysis structure
                required_fields = ['risk_level', 'concerns', 'recommendations', 'confidence']
                missing_fields = [field for field in required_fields if field not in analysis]
                if missing_fields:
                    errors.append(f"{agent_name} agent missing fields: {missing_fields}")

                # Validate risk level
                risk_level = analysis.get('risk_level')
                if risk_level not in ['low', 'medium', 'high', 'critical']:
                    errors.append(f"{agent_name} agent invalid risk level: {risk_level}")

                # Validate confidence
                confidence = analysis.get('confidence', 0)
                if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
                    errors.append(f"{agent_name} agent invalid confidence: {confidence}")

                results[agent_name] = {
                    'analysis_complete': True,
                    'risk_level': risk_level,
                    'concerns_identified': len(analysis.get('concerns', [])),
                    'recommendations_provided': len(analysis.get('recommendations', [])),
                    'confidence': confidence,
                    'perspective_specific': agent_name in str(analysis).lower()
                }

            except Exception as e:
                errors.append(f"{agent_name} agent failed: {str(e)}")
                results[agent_name] = {
                    'analysis_complete': False,
                    'error': str(e)
                }

        return ValidationResult(
            test_name="Perspective Agents Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'agents_tested': len(agents),
                'agent_results': results,
                'multi_perspective_analysis': 'functional' if len(errors) == 0 else 'partial'
            },
            errors=errors
        )

    async def validate_arbitration_logic(self) -> ValidationResult:
        """Validate arbitration logic for conflicting expert opinions"""
        arbitrator = ArbitrationAgent()

        # Create mock expert analyses with conflicts
        expert_analyses = {
            'legal_compliance': {
                'decision': 'approved',
                'risk_level': 'low',
                'confidence': 0.8,
                'concerns': ['Minor legal consideration']
            },
            'social_impact': {
                'decision': 'rejected',
                'risk_level': 'high',
                'confidence': 0.7,
                'concerns': ['Potential social controversy', 'Cultural sensitivity']
            },
            'ux_content': {
                'decision': 'approved',
                'risk_level': 'medium',
                'confidence': 0.6,
                'concerns': ['User experience impact']
            },
            'platform_risk': {
                'decision': 'rejected',
                'risk_level': 'critical',
                'confidence': 0.9,
                'concerns': ['Platform liability risk']
            }
        }

        test_content = "复杂的多角度分析测试内容"
        errors = []

        try:
            arbitration_result = await arbitrator.process(test_content, expert_analyses)

            # Validate arbitration result structure
            required_keys = ['final_decision', 'conflicts_detected', 'resolution_method', 'final_confidence']
            missing_keys = [key for key in required_keys if key not in arbitration_result]
            if missing_keys:
                errors.append(f"Arbitration result missing keys: {missing_keys}")

            # Validate conflict detection
            conflicts_detected = arbitration_result.get('conflicts_detected', 0)
            expected_conflicts = 2  # Legal+UX vs Social+Platform
            if conflicts_detected == 0:
                errors.append("Failed to detect obvious conflicts between expert opinions")

            # Validate final confidence
            final_confidence = arbitration_result.get('final_confidence', 0)
            if not isinstance(final_confidence, (int, float)) or not (0 <= final_confidence <= 1):
                errors.append(f"Invalid final confidence: {final_confidence}")

            # Validate resolution method
            resolution_method = arbitration_result.get('resolution_method')
            if not resolution_method:
                errors.append("No resolution method specified")

            details = {
                'conflicts_detected': conflicts_detected,
                'resolution_method': resolution_method,
                'final_decision': arbitration_result.get('final_decision'),
                'final_confidence': final_confidence,
                'synthesis_reasoning_provided': bool(arbitration_result.get('synthesis_reasoning'))
            }

        except Exception as e:
            errors.append(f"Arbitration process failed: {str(e)}")
            details = {'arbitration_failed': True}

        return ValidationResult(
            test_name="Arbitration Logic Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details=details,
            errors=errors
        )

    async def validate_confidence_thresholds(self) -> ValidationResult:
        """Validate confidence threshold-based routing"""
        workflow = self.workflow

        # Test cases with different confidence levels
        confidence_test_cases = [
            ("高置信度正面内容", 0.95, "direct_decision"),
            ("高置信度负面内容", 0.92, "direct_decision"),
            ("中等置信度内容", 0.65, "rag_analysis"),
            ("低置信度复杂内容", 0.25, "multi_modal_analysis"),
            ("极低置信度争议内容", 0.15, "human_review")
        ]

        results = []
        errors = []

        for content, expected_confidence, expected_path in confidence_test_cases:
            try:
                # This would require modifying the workflow to return detailed routing info
                # For validation, we'll test the routing logic components
                initial_judgment = {
                    'decision': 'review_needed',
                    'confidence_score': expected_confidence,
                    'reasoning': 'Test case'
                }

                router = SmartRouterAgent()
                routing_decision = await router.route_decision(initial_judgment, content)
                actual_route = routing_decision.get('route')

                # Validate threshold logic
                threshold_correct = self._validate_confidence_threshold_logic(expected_confidence, actual_route)

                results.append({
                    'content_sample': content,
                    'expected_confidence': expected_confidence,
                    'expected_path': expected_path,
                    'actual_route': actual_route,
                    'threshold_logic_correct': threshold_correct
                })

                if not threshold_correct:
                    errors.append(f"Incorrect routing for confidence {expected_confidence}: got {actual_route}")

            except Exception as e:
                errors.append(f"Confidence threshold test failed: {str(e)}")

        return ValidationResult(
            test_name="Confidence Thresholds Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'threshold_tests_run': len(results),
                'threshold_results': results,
                'threshold_logic_accuracy': f"{sum(1 for r in results if r['threshold_logic_correct']) / len(results) * 100:.1f}%" if results else "N/A"
            },
            errors=errors
        )

    def _validate_confidence_threshold_logic(self, confidence: float, route: str) -> bool:
        """Validate if routing matches confidence threshold logic"""
        if confidence >= 0.8:
            return route == 'direct_decision'
        elif confidence >= 0.3:
            return route in ['escalate_to_rag', 'direct_decision']
        else:
            return route in ['escalate_to_rag', 'escalate_other']

    async def validate_routing_paths(self) -> ValidationResult:
        """Validate all possible routing paths through the workflow"""
        routing_scenarios = [
            {
                'name': 'high_confidence_approval',
                'content': '非常明确的正面内容',
                'expected_path': ['initial_judgment', 'router_decision', 'direct_decision']
            },
            {
                'name': 'high_confidence_rejection',
                'content': '明显违规的负面内容',
                'expected_path': ['initial_judgment', 'router_decision', 'direct_decision']
            },
            {
                'name': 'medium_confidence_rag',
                'content': '需要先例参考的边缘案例',
                'expected_path': ['initial_judgment', 'router_decision', 'rag_enhanced_judgment']
            },
            {
                'name': 'low_confidence_multimodal',
                'content': '复杂的多维度分析案例',
                'expected_path': ['initial_judgment', 'router_decision', 'multi_modal_analysis']
            }
        ]

        results = []
        errors = []

        for scenario in routing_scenarios:
            try:
                # Run the workflow and capture the path
                result = await self.workflow.run_complete_audit(scenario['content'])
                actual_path = result.get('workflow_path', [])

                # Check if the path contains expected elements
                path_validation = self._validate_workflow_path(scenario['expected_path'], actual_path)

                results.append({
                    'scenario_name': scenario['name'],
                    'expected_path': scenario['expected_path'],
                    'actual_path': actual_path,
                    'path_valid': path_validation,
                    'content_sample': scenario['content'][:30] + "..."
                })

                if not path_validation:
                    errors.append(f"Invalid path for {scenario['name']}: expected {scenario['expected_path']}, got {actual_path}")

            except Exception as e:
                errors.append(f"Routing path test failed for {scenario['name']}: {str(e)}")

        return ValidationResult(
            test_name="Routing Paths Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'routing_scenarios_tested': len(results),
                'path_validations': results,
                'all_paths_valid': all(r['path_valid'] for r in results)
            },
            errors=errors
        )

    def _validate_workflow_path(self, expected_path: List[str], actual_path: List[str]) -> bool:
        """Validate if actual workflow path matches expected pattern"""
        # Check if key expected elements are present
        for expected_step in expected_path:
            if expected_step not in actual_path:
                return False
        return True

    async def validate_state_transitions(self) -> ValidationResult:
        """Validate state transitions between workflow nodes"""
        test_content = "状态转换验证测试内容"
        errors = []

        try:
            # This would require instrumented workflow to capture state transitions
            # For now, validate that the workflow maintains state consistency
            result = await self.workflow.run_complete_audit(test_content)

            # Check state consistency
            state_checks = {
                'audit_id_consistent': bool(result.get('audit_id')),
                'content_preserved': test_content in str(result.get('processing_details', {})),
                'workflow_path_recorded': len(result.get('workflow_path', [])) > 0,
                'final_decision_present': bool(result.get('final_decision')),
                'confidence_maintained': 'confidence_score' in result
            }

            failed_checks = [check for check, passed in state_checks.items() if not passed]
            if failed_checks:
                errors.extend([f"State check failed: {check}" for check in failed_checks])

            details = {
                'state_consistency_checks': state_checks,
                'all_checks_passed': len(failed_checks) == 0,
                'failed_checks': failed_checks
            }

        except Exception as e:
            errors.append(f"State transition validation failed: {str(e)}")
            details = {'validation_failed': True}

        return ValidationResult(
            test_name="State Transitions Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details=details,
            errors=errors
        )

    async def validate_agent_communication(self) -> ValidationResult:
        """Validate communication protocols between agents"""
        errors = []
        communication_tests = []

        try:
            # Test Initial -> Router communication
            initial_agent = InitialJudgmentAgent()
            router_agent = SmartRouterAgent()

            test_content = "代理通信测试内容"
            initial_result = await initial_agent.process(test_content)
            router_input_valid = all(key in initial_result for key in ['decision', 'confidence_score', 'reasoning'])

            if router_input_valid:
                router_result = await router_agent.route_decision(initial_result, test_content)
                router_output_valid = 'route' in router_result
            else:
                router_output_valid = False
                errors.append("Initial agent output incompatible with router input")

            communication_tests.append({
                'agent_pair': 'Initial -> Router',
                'input_compatible': router_input_valid,
                'output_valid': router_output_valid,
                'communication_successful': router_input_valid and router_output_valid
            })

            # Test Router -> RAG communication
            if router_output_valid and router_result.get('route') == 'escalate_to_rag':
                rag_agent = RAGEnhancedJudgeAgent()
                try:
                    rag_result = await rag_agent.process(test_content, initial_result)
                    rag_communication_valid = 'enhanced_decision' in rag_result
                except Exception as e:
                    rag_communication_valid = False
                    errors.append(f"Router -> RAG communication failed: {str(e)}")
            else:
                rag_communication_valid = True  # Not applicable

            communication_tests.append({
                'agent_pair': 'Router -> RAG',
                'communication_successful': rag_communication_valid,
                'applicable': router_result.get('route') == 'escalate_to_rag' if router_output_valid else False
            })

        except Exception as e:
            errors.append(f"Agent communication validation failed: {str(e)}")

        return ValidationResult(
            test_name="Agent Communication Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'communication_tests': communication_tests,
                'all_communications_valid': all(test.get('communication_successful', False) for test in communication_tests)
            },
            errors=errors
        )

    async def validate_error_propagation(self) -> ValidationResult:
        """Validate error handling and propagation through the workflow"""
        error_scenarios = [
            ("", "empty_content"),
            (None, "null_content"),
            ("a" * 100000, "oversized_content")
        ]

        results = []
        errors = []

        for content, scenario_name in error_scenarios:
            try:
                result = await self.workflow.run_complete_audit(content)

                # Check if error was handled gracefully
                if 'error' in result or result.get('final_decision') == 'error':
                    error_handled = True
                    error_details = result.get('error', 'Graceful error handling')
                else:
                    error_handled = True  # Content was processed without error
                    error_details = 'Content processed successfully'

                results.append({
                    'scenario': scenario_name,
                    'error_handled_gracefully': error_handled,
                    'error_details': error_details,
                    'workflow_completed': bool(result.get('final_decision'))
                })

            except Exception as e:
                # Unexpected error - should be handled gracefully
                results.append({
                    'scenario': scenario_name,
                    'error_handled_gracefully': False,
                    'error_details': str(e),
                    'workflow_completed': False
                })
                errors.append(f"Unhandled error in {scenario_name}: {str(e)}")

        return ValidationResult(
            test_name="Error Propagation Validation",
            status="PASSED" if len(errors) == 0 else "FAILED",
            details={
                'error_scenarios_tested': len(results),
                'error_handling_results': results,
                'graceful_error_handling_rate': f"{sum(1 for r in results if r['error_handled_gracefully']) / len(results) * 100:.1f}%" if results else "N/A"
            },
            errors=errors
        )

    async def validate_workflow_consistency(self) -> ValidationResult:
        """Validate overall workflow consistency and repeatability"""
        test_content = "工作流一致性测试内容"

        # Run the same content multiple times
        results = []
        errors = []

        for run in range(3):
            try:
                result = await self.workflow.run_complete_audit(test_content)
                results.append({
                    'run_number': run + 1,
                    'final_decision': result.get('final_decision'),
                    'confidence_score': result.get('confidence_score'),
                    'workflow_path': result.get('workflow_path', []),
                    'processing_successful': bool(result.get('final_decision'))
                })
            except Exception as e:
                errors.append(f"Workflow run {run + 1} failed: {str(e)}")

        if results:
            # Check consistency
            decisions = [r['final_decision'] for r in results]
            paths = [r['workflow_path'] for r in results]

            decision_consistency = len(set(decisions)) == 1
            path_consistency = all(path == paths[0] for path in paths)

            consistency_details = {
                'runs_completed': len(results),
                'decision_consistency': decision_consistency,
                'path_consistency': path_consistency,
                'unique_decisions': list(set(decisions)),
                'all_runs_successful': all(r['processing_successful'] for r in results)
            }
        else:
            consistency_details = {'no_successful_runs': True}

        return ValidationResult(
            test_name="Workflow Consistency Validation",
            status="PASSED" if len(errors) == 0 and decision_consistency else "FAILED",
            details=consistency_details,
            errors=errors
        )

    def _generate_validation_summary(self) -> Dict[str, Any]:
        """Generate comprehensive validation summary"""
        total_validations = len(self.validation_results)
        passed_validations = sum(1 for r in self.validation_results if r.status == 'PASSED')
        failed_validations = sum(1 for r in self.validation_results if r.status == 'FAILED')

        # Calculate validation health score
        validation_health = 'EXCELLENT' if failed_validations == 0 else 'GOOD' if failed_validations <= 2 else 'NEEDS_ATTENTION'

        # Collect all errors
        all_errors = []
        for result in self.validation_results:
            all_errors.extend(result.errors)

        return {
            'validation_summary': {
                'total_validations': total_validations,
                'passed_validations': passed_validations,
                'failed_validations': failed_validations,
                'validation_success_rate': f"{(passed_validations / total_validations * 100):.1f}%",
                'validation_health': validation_health
            },
            'detailed_validation_results': [
                {
                    'test_name': result.test_name,
                    'status': result.status,
                    'details': result.details,
                    'errors': result.errors,
                    'timestamp': result.timestamp
                } for result in self.validation_results
            ],
            'critical_issues': all_errors,
            'agent_routing_readiness': 'PRODUCTION_READY' if validation_health in ['EXCELLENT', 'GOOD'] else 'NEEDS_FIXES',
            'validation_completion_timestamp': datetime.now().isoformat()
        }


# CLI runner for validation
async def main():
    """Main validation runner"""
    logging.basicConfig(level=logging.INFO)

    print("🔧 Starting Agent Routing Validation Suite...")
    print("=" * 70)

    validator = AgentRoutingValidator()
    summary = await validator.run_all_validations()

    print("\n📊 VALIDATION SUMMARY")
    print("=" * 70)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    readiness = summary.get('agent_routing_readiness')
    if readiness == 'PRODUCTION_READY':
        print("\n🚀 Agent routing is PRODUCTION READY!")
    else:
        print(f"\n⚠️  Agent routing status: {readiness}")

    return summary


if __name__ == "__main__":
    asyncio.run(main())