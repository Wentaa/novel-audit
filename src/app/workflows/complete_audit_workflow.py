from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
from datetime import datetime
import asyncio
import hashlib

from ..agents.initial_judgment import InitialJudgmentAgent
from ..agents.smart_router import SmartRouterAgent, RoutingDecision
from ..agents.rag_enhanced_judge import RAGEnhancedJudgeAgent
from ..agents.perspective_agents import LegalComplianceAgent, SocialImpactAgent, UserExperienceAgent, PlatformRiskAgent
from ..agents.arbitration_agent import ArbitrationAgent
from ..services.rule_management_service import rule_management_service
from ..services.human_review_service import human_review_service, ReviewPriority
from ..storage.database import db_service
from ..config.settings import settings
import logging

logger = logging.getLogger(__name__)


class CompleteAuditState(TypedDict):
    """Complete state for the full audit workflow"""
    # Input
    content_text: str
    content_metadata: Dict[str, Any]
    audit_request_id: str

    # Processing state
    current_step: str
    processing_history: List[Dict[str, Any]]
    confidence_scores: List[float]

    # Agent outputs
    initial_judgment: Dict[str, Any]
    routing_decision: Dict[str, Any]
    rag_enhanced_judgment: Dict[str, Any]
    expert_perspectives: Dict[str, Any]
    arbitration_result: Dict[str, Any]
    final_result: Dict[str, Any]

    # Flow control
    workflow_status: str
    requires_escalation: bool
    escalation_type: str
    human_review_submitted: bool

    # Results
    audit_conclusion: str
    confidence_score: float
    violation_details: List[Dict[str, Any]]
    processing_path: List[str]

    # Metadata
    workflow_metadata: Dict[str, Any]
    errors: List[str]


class CompleteAuditWorkflow:
    """Complete end-to-end audit workflow integrating all phases"""

    def __init__(self):
        # Phase 3 agents
        self.initial_judgment_agent = InitialJudgmentAgent()
        self.smart_router_agent = SmartRouterAgent()

        # Phase 4 agent
        self.rag_enhanced_judge = RAGEnhancedJudgeAgent()

        # Phase 5 agents
        self.legal_compliance_agent = LegalComplianceAgent()
        self.social_impact_agent = SocialImpactAgent()
        self.user_experience_agent = UserExperienceAgent()
        self.platform_risk_agent = PlatformRiskAgent()
        self.arbitration_agent = ArbitrationAgent()

        self.workflow_graph = None
        self._build_complete_workflow()

    def _build_complete_workflow(self):
        """Build the complete LangGraph workflow"""
        workflow = StateGraph(CompleteAuditState)

        # Add all nodes
        workflow.add_node("initial_judgment", self.initial_judgment_node)
        workflow.add_node("smart_routing", self.smart_routing_node)
        workflow.add_node("rag_enhanced_analysis", self.rag_enhanced_analysis_node)
        workflow.add_node("multi_modal_analysis", self.multi_modal_analysis_node)
        workflow.add_node("arbitration", self.arbitration_node)
        workflow.add_node("finalize_approved", self.finalize_approved_node)
        workflow.add_node("finalize_rejected", self.finalize_rejected_node)
        workflow.add_node("submit_human_review", self.submit_human_review_node)

        # Set entry point
        workflow.set_entry_point("initial_judgment")

        # Add edges
        workflow.add_edge("initial_judgment", "smart_routing")

        # Smart routing decision
        workflow.add_conditional_edges(
            "smart_routing",
            self.route_from_initial,
            {
                "approve_directly": "finalize_approved",
                "reject_directly": "finalize_rejected",
                "escalate_to_rag": "rag_enhanced_analysis",
                "escalate_to_multimodal": "multi_modal_analysis",
                "escalate_to_human": "submit_human_review"
            }
        )

        # RAG routing
        workflow.add_conditional_edges(
            "rag_enhanced_analysis",
            self.route_from_rag,
            {
                "approve_rag": "finalize_approved",
                "reject_rag": "finalize_rejected",
                "escalate_to_multimodal": "multi_modal_analysis",
                "escalate_to_human": "submit_human_review"
            }
        )

        # Multi-modal routing
        workflow.add_conditional_edges(
            "multi_modal_analysis",
            self.route_from_multimodal,
            {
                "proceed_to_arbitration": "arbitration"
            }
        )

        # Arbitration routing
        workflow.add_conditional_edges(
            "arbitration",
            self.route_from_arbitration,
            {
                "approve_final": "finalize_approved",
                "reject_final": "finalize_rejected",
                "escalate_to_human": "submit_human_review"
            }
        )

        # Terminal nodes
        workflow.add_edge("finalize_approved", END)
        workflow.add_edge("finalize_rejected", END)
        workflow.add_edge("submit_human_review", END)

        self.workflow_graph = workflow.compile()

    async def initial_judgment_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Initial judgment node (Agent3)"""
        logger.info("Executing initial judgment node...")

        try:
            state["current_step"] = "initial_judgment"
            state["processing_history"].append({
                "step": "initial_judgment",
                "timestamp": datetime.now().isoformat(),
                "agent": "InitialJudgmentAgent"
            })

            # Execute initial judgment
            agent_state = self.initial_judgment_agent.create_state({
                "content_text": state["content_text"],
                "metadata": state["content_metadata"]
            })

            result_state = await self.initial_judgment_agent.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            state["initial_judgment"] = result_state.output_data.get("judgment_result", {})
            initial_confidence = result_state.output_data.get("confidence_score", 0.0)
            state["confidence_scores"].append(initial_confidence)

            logger.info(f"Initial judgment: {state['initial_judgment'].get('judgment')} "
                       f"(confidence: {initial_confidence:.2f})")
            return state

        except Exception as e:
            state["errors"].append(f"Initial judgment failed: {str(e)}")
            state["workflow_status"] = "error"
            return state

    async def smart_routing_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Smart routing node (Agent4)"""
        logger.info("Executing smart routing node...")

        try:
            state["current_step"] = "smart_routing"
            state["processing_history"].append({
                "step": "smart_routing",
                "timestamp": datetime.now().isoformat(),
                "agent": "SmartRouterAgent"
            })

            agent_state = self.smart_router_agent.create_state({
                "initial_judgment": state["initial_judgment"],
                "content_metadata": state["content_metadata"],
                "processing_history": state["processing_history"]
            })

            result_state = await self.smart_router_agent.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            state["routing_decision"] = result_state.output_data.get("routing_decision", {})
            next_step = state["routing_decision"].get("next_step", "escalate_to_human")

            logger.info(f"Routing decision: {next_step}")
            return state

        except Exception as e:
            state["errors"].append(f"Smart routing failed: {str(e)}")
            state["workflow_status"] = "error"
            return state

    async def rag_enhanced_analysis_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """RAG enhanced analysis node (Agent5)"""
        logger.info("Executing RAG enhanced analysis node...")

        try:
            state["current_step"] = "rag_enhanced_analysis"
            state["processing_history"].append({
                "step": "rag_enhanced_analysis",
                "timestamp": datetime.now().isoformat(),
                "agent": "RAGEnhancedJudgeAgent"
            })

            active_rules = await rule_management_service.get_active_rules()

            agent_state = self.rag_enhanced_judge.create_state({
                "content_text": state["content_text"],
                "initial_judgment": state["initial_judgment"],
                "content_metadata": state["content_metadata"],
                "active_rules": active_rules or {}
            })

            result_state = await self.rag_enhanced_judge.safe_process(agent_state)

            if result_state.errors:
                logger.warning("RAG analysis had errors, using fallback")
                state["rag_enhanced_judgment"] = state["initial_judgment"]
            else:
                state["rag_enhanced_judgment"] = result_state.output_data.get("enhanced_judgment", {})
                rag_confidence = state["rag_enhanced_judgment"].get("confidence_score", 0.0)
                state["confidence_scores"].append(rag_confidence)

            logger.info("RAG enhanced analysis completed")
            return state

        except Exception as e:
            state["errors"].append(f"RAG analysis failed: {str(e)}")
            state["rag_enhanced_judgment"] = state["initial_judgment"]  # Fallback
            return state

    async def multi_modal_analysis_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Multi-modal perspective analysis (Phase 5 agents)"""
        logger.info("Executing multi-modal analysis...")

        try:
            state["current_step"] = "multi_modal_analysis"
            state["processing_history"].append({
                "step": "multi_modal_analysis",
                "timestamp": datetime.now().isoformat(),
                "agent": "MultiModalAnalysis"
            })

            # Prepare common input for all perspective agents
            previous_assessments = {
                "initial_judgment": state["initial_judgment"],
                "rag_enhanced": state.get("rag_enhanced_judgment", {})
            }

            common_input = {
                "content_text": state["content_text"],
                "previous_assessments": previous_assessments
            }

            # Run all perspective agents in parallel
            perspective_agents = [
                ("legal_compliance", self.legal_compliance_agent),
                ("social_impact", self.social_impact_agent),
                ("user_experience", self.user_experience_agent),
                ("platform_risk", self.platform_risk_agent)
            ]

            # Execute agents in parallel
            perspective_tasks = []
            for perspective_name, agent in perspective_agents:
                agent_state = agent.create_state(common_input)
                task = asyncio.create_task(agent.safe_process(agent_state))
                perspective_tasks.append((perspective_name, task))

            # Collect results
            expert_perspectives = {}
            for perspective_name, task in perspective_tasks:
                try:
                    result_state = await task
                    if result_state.errors:
                        logger.warning(f"{perspective_name} analysis had errors: {result_state.errors}")

                    expert_perspectives[perspective_name] = result_state.output_data

                except Exception as e:
                    logger.error(f"{perspective_name} analysis failed: {e}")
                    expert_perspectives[perspective_name] = {
                        "error": str(e),
                        "perspective": perspective_name
                    }

            state["expert_perspectives"] = expert_perspectives

            logger.info(f"Multi-modal analysis completed with {len(expert_perspectives)} perspectives")
            return state

        except Exception as e:
            state["errors"].append(f"Multi-modal analysis failed: {str(e)}")
            state["expert_perspectives"] = {}
            return state

    async def arbitration_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Arbitration node for final decision making"""
        logger.info("Executing arbitration node...")

        try:
            state["current_step"] = "arbitration"
            state["processing_history"].append({
                "step": "arbitration",
                "timestamp": datetime.now().isoformat(),
                "agent": "ArbitrationAgent"
            })

            agent_state = self.arbitration_agent.create_state({
                "content_text": state["content_text"],
                "expert_perspectives": state["expert_perspectives"],
                "initial_assessments": {
                    "initial_judgment": state["initial_judgment"],
                    "rag_enhanced_judgment": state.get("rag_enhanced_judgment", {})
                },
                "metadata": state["content_metadata"]
            })

            result_state = await self.arbitration_agent.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                # Set default to human review on arbitration failure
                state["arbitration_result"] = {
                    "final_decision": "requires_human_review",
                    "confidence_score": 0.3,
                    "arbitration_reasoning": "Arbitration failed, defaulting to human review"
                }
            else:
                state["arbitration_result"] = result_state.output_data.get("arbitration_analysis", {})

            arbitration_confidence = state["arbitration_result"].get("confidence_score", 0.3)
            state["confidence_scores"].append(arbitration_confidence)

            final_decision = state["arbitration_result"].get("final_decision", "requires_human_review")
            logger.info(f"Arbitration decision: {final_decision} (confidence: {arbitration_confidence:.2f})")

            return state

        except Exception as e:
            state["errors"].append(f"Arbitration failed: {str(e)}")
            state["arbitration_result"] = {
                "final_decision": "requires_human_review",
                "confidence_score": 0.3,
                "arbitration_reasoning": f"Arbitration error: {str(e)}"
            }
            return state

    # Routing functions
    def route_from_initial(self, state: CompleteAuditState) -> str:
        """Route from initial judgment"""
        try:
            next_step = state["routing_decision"].get("next_step", "escalate_to_human")
            routing_map = {
                "approve_directly": "approve_directly",
                "reject_directly": "reject_directly",
                "escalate_to_rag": "escalate_to_rag",
                "escalate_to_multimodal": "escalate_to_multimodal",
                "escalate_to_human": "escalate_to_human"
            }
            return routing_map.get(next_step, "escalate_to_human")
        except:
            return "escalate_to_human"

    def route_from_rag(self, state: CompleteAuditState) -> str:
        """Route from RAG analysis"""
        try:
            rag_judgment = state.get("rag_enhanced_judgment", {})
            judgment = rag_judgment.get("enhanced_judgment", "uncertain")
            confidence = rag_judgment.get("confidence_score", 0.0)

            if confidence >= 0.85:
                if judgment == "approved":
                    return "approve_rag"
                elif judgment == "rejected":
                    return "reject_rag"

            # Still need more analysis
            return "escalate_to_multimodal"
        except:
            return "escalate_to_multimodal"

    def route_from_multimodal(self, state: CompleteAuditState) -> str:
        """Route from multi-modal analysis"""
        return "proceed_to_arbitration"

    def route_from_arbitration(self, state: CompleteAuditState) -> str:
        """Route from arbitration"""
        try:
            arbitration_result = state.get("arbitration_result", {})
            decision = arbitration_result.get("final_decision", "requires_human_review")

            if decision == "approved":
                return "approve_final"
            elif decision == "rejected":
                return "reject_final"
            else:
                return "escalate_to_human"
        except:
            return "escalate_to_human"

    # Finalization nodes
    async def finalize_approved_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Finalize approved decision"""
        logger.info("Finalizing approved decision...")

        try:
            state["current_step"] = "finalize_approved"
            state["processing_history"].append({
                "step": "finalize_approved",
                "timestamp": datetime.now().isoformat(),
                "action": "content_approved"
            })

            # Use the highest confidence judgment available
            final_judgment = (state.get("arbitration_result") or
                            state.get("rag_enhanced_judgment") or
                            state["initial_judgment"])

            state["audit_conclusion"] = "approved"
            state["confidence_score"] = final_judgment.get("confidence_score", 0.0)
            state["violation_details"] = []
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "completed"

            reasoning = (final_judgment.get("arbitration_reasoning") or
                        final_judgment.get("enhanced_reasoning") or
                        final_judgment.get("reasoning", "Content approved"))

            state["final_result"] = {
                "result": "approved",
                "confidence": state["confidence_score"],
                "reason": reasoning,
                "violated_rules": [],
                "processing_path": state["processing_path"],
                "timestamp": datetime.now().isoformat()
            }

            await self._store_audit_record(state)
            logger.info("Content approved successfully")
            return state

        except Exception as e:
            state["errors"].append(f"Approval finalization failed: {str(e)}")
            return state

    async def finalize_rejected_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Finalize rejected decision"""
        logger.info("Finalizing rejected decision...")

        try:
            state["current_step"] = "finalize_rejected"
            state["processing_history"].append({
                "step": "finalize_rejected",
                "timestamp": datetime.now().isoformat(),
                "action": "content_rejected"
            })

            final_judgment = (state.get("arbitration_result") or
                            state.get("rag_enhanced_judgment") or
                            state["initial_judgment"])

            state["audit_conclusion"] = "rejected"
            state["confidence_score"] = final_judgment.get("confidence_score", 0.0)
            state["violation_details"] = final_judgment.get("violation_details", [])
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "completed"

            violated_rules = [v.get("rule_reference", "unknown") for v in state["violation_details"]]
            reasoning = (final_judgment.get("arbitration_reasoning") or
                        final_judgment.get("enhanced_reasoning") or
                        final_judgment.get("reasoning", "Content rejected due to policy violations"))

            state["final_result"] = {
                "result": "rejected",
                "confidence": state["confidence_score"],
                "reason": reasoning,
                "violated_rules": violated_rules,
                "processing_path": state["processing_path"],
                "timestamp": datetime.now().isoformat()
            }

            await self._store_audit_record(state)
            logger.info("Content rejected successfully")
            return state

        except Exception as e:
            state["errors"].append(f"Rejection finalization failed: {str(e)}")
            return state

    async def submit_human_review_node(self, state: CompleteAuditState) -> CompleteAuditState:
        """Submit content for human review"""
        logger.info("Submitting content for human review...")

        try:
            state["current_step"] = "submit_human_review"
            state["processing_history"].append({
                "step": "submit_human_review",
                "timestamp": datetime.now().isoformat(),
                "action": "escalated_to_human_review"
            })

            # Determine escalation reason and priority
            escalation_info = self._determine_escalation_info(state)

            # Submit for human review
            review_submission = await human_review_service.submit_for_human_review(
                content_text=state["content_text"],
                audit_results={
                    "initial_judgment": state.get("initial_judgment", {}),
                    "routing_decision": state.get("routing_decision", {}),
                    "rag_enhanced_judgment": state.get("rag_enhanced_judgment", {}),
                    "expert_perspectives": state.get("expert_perspectives", {}),
                    "arbitration_result": state.get("arbitration_result", {}),
                    "processing_path": state["processing_path"],
                    "confidence_scores": state["confidence_scores"]
                },
                escalation_reason=escalation_info["reason"],
                priority=escalation_info["priority"],
                metadata=state["content_metadata"]
            )

            state["audit_conclusion"] = "pending_human_review"
            state["confidence_score"] = 0.0  # No automated confidence for human review
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "escalated"
            state["human_review_submitted"] = True

            state["final_result"] = {
                "result": "pending_human_review",
                "confidence": 0.0,
                "reason": escalation_info["reason"],
                "violated_rules": escalation_info.get("violated_rules", []),
                "processing_path": state["processing_path"],
                "human_review_id": review_submission.get("review_id"),
                "estimated_review_time": review_submission.get("estimated_review_time"),
                "timestamp": datetime.now().isoformat()
            }

            await self._store_audit_record(state, is_final=False)
            logger.info(f"Content submitted for human review: ID {review_submission.get('review_id')}")
            return state

        except Exception as e:
            state["errors"].append(f"Human review submission failed: {str(e)}")
            state["workflow_status"] = "error"
            return state

    def _determine_escalation_info(self, state: CompleteAuditState) -> Dict[str, Any]:
        """Determine escalation reason and priority"""
        try:
            # Default values
            escalation_info = {
                "reason": "Automated analysis inconclusive",
                "priority": ReviewPriority.MEDIUM,
                "violated_rules": []
            }

            # Check for specific escalation triggers
            if state.get("arbitration_result"):
                arbitration = state["arbitration_result"]
                escalation_triggers = arbitration.get("escalation_triggers", [])
                if escalation_triggers:
                    escalation_info["reason"] = f"Arbitration required human review: {'; '.join(escalation_triggers)}"

            # Check for critical issues in expert perspectives
            expert_perspectives = state.get("expert_perspectives", {})

            # Legal issues get highest priority
            legal_analysis = expert_perspectives.get("legal_compliance", {}).get("analysis", {})
            if legal_analysis.get("requires_legal_review"):
                escalation_info["reason"] = "Legal compliance review required"
                escalation_info["priority"] = ReviewPriority.CRITICAL

            # Platform risk issues
            risk_analysis = expert_perspectives.get("platform_risk", {}).get("analysis", {})
            if risk_analysis.get("risk_assessment") == "critical":
                escalation_info["reason"] = "Critical platform risk identified"
                escalation_info["priority"] = ReviewPriority.HIGH

            # Extract violated rules
            for judgment in [state.get("arbitration_result"),
                           state.get("rag_enhanced_judgment"),
                           state.get("initial_judgment")]:
                if judgment and judgment.get("violation_details"):
                    violated_rules = [v.get("rule_reference", "unknown") for v in judgment["violation_details"]]
                    escalation_info["violated_rules"] = violated_rules
                    break

            return escalation_info

        except Exception as e:
            logger.error(f"Escalation info determination failed: {e}")
            return {
                "reason": f"System error during analysis: {str(e)}",
                "priority": ReviewPriority.HIGH,
                "violated_rules": []
            }

    async def _store_audit_record(self, state: CompleteAuditState, is_final: bool = True):
        """Store comprehensive audit record"""
        try:
            content_hash = hashlib.sha256(state["content_text"].encode('utf-8')).hexdigest()
            content_preview = state["content_text"][:500] + "..." if len(state["content_text"]) > 500 else state["content_text"]

            final_result = state["final_result"]

            record = db_service.create_audit_record(
                content_hash=content_hash,
                content_preview=content_preview,
                result=final_result.get("result", "unknown"),
                confidence=final_result.get("confidence", 0.0),
                reason=final_result.get("reason", ""),
                violated_rules=final_result.get("violated_rules", []),
                processing_path=final_result.get("processing_path", []),
                metadata={
                    "audit_request_id": state["audit_request_id"],
                    "complete_workflow": True,
                    "workflow_metadata": state["workflow_metadata"],
                    "expert_perspectives": state.get("expert_perspectives", {}),
                    "arbitration_result": state.get("arbitration_result", {}),
                    "confidence_progression": state["confidence_scores"],
                    "human_review_submitted": state.get("human_review_submitted", False),
                    "is_final": is_final,
                    "content_metadata": state["content_metadata"]
                }
            )

            state["workflow_metadata"]["audit_record_id"] = record.id

        except Exception as e:
            logger.error(f"Failed to store audit record: {e}")

    async def run_complete_audit(
        self,
        content_text: str,
        content_metadata: Dict[str, Any] = None,
        audit_request_id: str = None
    ) -> CompleteAuditState:
        """
        Run the complete end-to-end audit workflow

        Args:
            content_text: Content to audit
            content_metadata: Content metadata
            audit_request_id: Unique request identifier

        Returns:
            Complete workflow state with final results
        """
        if not audit_request_id:
            audit_request_id = f"complete_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content_text) % 10000}"

        logger.info(f"Starting complete audit workflow: {audit_request_id}")

        # Initialize state
        initial_state = CompleteAuditState(
            content_text=content_text,
            content_metadata=content_metadata or {},
            audit_request_id=audit_request_id,
            current_step="initializing",
            processing_history=[{
                "step": "initialize",
                "timestamp": datetime.now().isoformat(),
                "action": "complete_workflow_started"
            }],
            confidence_scores=[],
            initial_judgment={},
            routing_decision={},
            rag_enhanced_judgment={},
            expert_perspectives={},
            arbitration_result={},
            final_result={},
            workflow_status="running",
            requires_escalation=False,
            escalation_type="none",
            human_review_submitted=False,
            audit_conclusion="pending",
            confidence_score=0.0,
            violation_details=[],
            processing_path=[],
            workflow_metadata={
                "workflow_id": audit_request_id,
                "workflow_version": "complete_v1.0",
                "started_at": datetime.now().isoformat(),
                "content_length": len(content_text),
                "workflow_type": "complete_audit"
            },
            errors=[]
        )

        try:
            # Execute complete workflow
            final_state = await self.workflow_graph.ainvoke(initial_state)

            # Update completion metadata
            final_state["workflow_metadata"]["completed_at"] = datetime.now().isoformat()
            final_state["workflow_metadata"]["total_agents_used"] = len(final_state["processing_path"])
            final_state["workflow_metadata"]["final_confidence"] = final_state.get("confidence_score", 0.0)

            logger.info(f"Complete audit workflow finished: {audit_request_id} "
                       f"(result: {final_state['audit_conclusion']}, "
                       f"agents: {len(final_state['processing_path'])})")

            return final_state

        except Exception as e:
            logger.error(f"Complete workflow execution failed: {e}")
            initial_state["workflow_status"] = "failed"
            initial_state["errors"].append(str(e))
            initial_state["audit_conclusion"] = "error"
            return initial_state


# Global complete workflow instance
complete_audit_workflow = CompleteAuditWorkflow()