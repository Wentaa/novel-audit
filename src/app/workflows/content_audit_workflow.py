from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
from datetime import datetime
import hashlib

from ..agents.initial_judgment import InitialJudgmentAgent
from ..agents.smart_router import SmartRouterAgent, RoutingDecision
from ..agents.rag_enhanced_judge import RAGEnhancedJudgeAgent
from ..services.rule_management_service import rule_management_service
from ..storage.database import db_service
from ..config.settings import settings
import logging

logger = logging.getLogger(__name__)


class ContentAuditState(TypedDict):
    """State for content audit workflow"""
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
    final_result: Dict[str, Any]

    # Flow control
    workflow_status: str
    requires_escalation: bool
    escalation_type: str

    # Results
    audit_conclusion: str  # "approved", "rejected", "pending_review"
    confidence_score: float
    violation_details: List[Dict[str, Any]]
    processing_path: List[str]

    # Metadata
    workflow_metadata: Dict[str, Any]
    errors: List[str]


class ContentAuditWorkflow:
    """LangGraph workflow for content auditing (Phase 3: Agent3 + Agent4)"""

    def __init__(self):
        self.initial_judgment_agent = InitialJudgmentAgent()
        self.smart_router_agent = SmartRouterAgent()
        self.rag_enhanced_judge = RAGEnhancedJudgeAgent()
        self.workflow_graph = None
        self._build_workflow()

    def _build_workflow(self):
        """Build the LangGraph workflow for content auditing"""
        # Create state graph
        workflow = StateGraph(ContentAuditState)

        # Add nodes
        workflow.add_node("initial_judgment", self.initial_judgment_node)
        workflow.add_node("smart_routing", self.smart_routing_node)
        workflow.add_node("rag_enhanced_analysis", self.rag_enhanced_analysis_node)
        workflow.add_node("finalize_approved", self.finalize_approved_node)
        workflow.add_node("finalize_rejected", self.finalize_rejected_node)
        workflow.add_node("prepare_escalation", self.prepare_escalation_node)

        # Add edges
        workflow.set_entry_point("initial_judgment")

        # From initial_judgment -> smart_routing (always)
        workflow.add_edge("initial_judgment", "smart_routing")

        # From smart_routing -> conditional routing
        workflow.add_conditional_edges(
            "smart_routing",
            self.route_based_on_decision,
            {
                "approve_directly": "finalize_approved",
                "reject_directly": "finalize_rejected",
                "escalate_to_rag": "rag_enhanced_analysis",
            "escalate_other": "prepare_escalation"
            }
        )

        # From rag_enhanced_analysis -> conditional routing
        workflow.add_conditional_edges(
            "rag_enhanced_analysis",
            self.route_after_rag,
            {
                "approve_rag": "finalize_approved",
                "reject_rag": "finalize_rejected",
                "escalate_further": "prepare_escalation"
            }
        )

        # Terminal nodes
        workflow.add_edge("finalize_approved", END)
        workflow.add_edge("finalize_rejected", END)
        workflow.add_edge("prepare_escalation", END)

        self.workflow_graph = workflow.compile()

    async def initial_judgment_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for initial content judgment (Agent3)"""
        logger.info("Executing initial judgment node...")

        try:
            # Update state
            state["current_step"] = "initial_judgment"
            state["processing_history"].append({
                "step": "initial_judgment",
                "timestamp": datetime.now().isoformat(),
                "agent": "InitialJudgmentAgent"
            })

            # Prepare agent input
            agent_state = self.initial_judgment_agent.create_state({
                "content_text": state["content_text"],
                "metadata": state["content_metadata"]
            })

            # Execute agent
            result_state = await self.initial_judgment_agent.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            # Extract results
            state["initial_judgment"] = result_state.output_data.get("judgment_result", {})

            # Track confidence
            initial_confidence = result_state.output_data.get("confidence_score", 0.0)
            state["confidence_scores"].append(initial_confidence)

            # Update metadata
            state["workflow_metadata"]["initial_judgment"] = result_state.output_data.get("processing_metadata", {})

            logger.info(f"Initial judgment completed: {state['initial_judgment'].get('judgment', 'unknown')} "
                       f"(confidence: {initial_confidence:.2f})")
            return state

        except Exception as e:
            error_msg = f"Initial judgment node failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def smart_routing_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for smart routing decisions (Agent4)"""
        logger.info("Executing smart routing node...")

        try:
            # Update state
            state["current_step"] = "smart_routing"
            state["processing_history"].append({
                "step": "smart_routing",
                "timestamp": datetime.now().isoformat(),
                "agent": "SmartRouterAgent"
            })

            # Prepare agent input
            agent_state = self.smart_router_agent.create_state({
                "initial_judgment": state["initial_judgment"],
                "content_metadata": state["content_metadata"],
                "processing_history": state["processing_history"]
            })

            # Execute agent
            result_state = await self.smart_router_agent.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            # Extract results
            state["routing_decision"] = result_state.output_data.get("routing_decision", {})

            # Determine escalation requirements
            next_step = state["routing_decision"].get("next_step", "escalate_to_human")
            state["requires_escalation"] = next_step not in ["approve_directly", "reject_directly"]
            state["escalation_type"] = next_step if state["requires_escalation"] else "none"

            # Update metadata
            state["workflow_metadata"]["routing"] = result_state.output_data.get("processing_metadata", {})

            logger.info(f"Routing decision: {next_step}")
            return state

        except Exception as e:
            error_msg = f"Smart routing node failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    def route_based_on_decision(self, state: ContentAuditState) -> str:
        """Decision function for routing based on Agent4 output"""
        try:
            routing_decision = state["routing_decision"]
            next_step = routing_decision.get("next_step", "escalate_to_human")

            # Map routing decisions to workflow paths
            if next_step == "approve_directly":
                return "approve_directly"
            elif next_step == "reject_directly":
                return "reject_directly"
            elif next_step == "escalate_to_rag":
                return "escalate_to_rag"
            else:
                # All other escalation types
                return "escalate_other"

        except Exception as e:
            logger.error(f"Routing decision function failed: {e}")
            return "escalate_other"  # Safe fallback

    async def rag_enhanced_analysis_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for RAG-enhanced analysis (Agent5)"""
        logger.info("Executing RAG-enhanced analysis node...")

        try:
            # Update state
            state["current_step"] = "rag_enhanced_analysis"
            state["processing_history"].append({
                "step": "rag_enhanced_analysis",
                "timestamp": datetime.now().isoformat(),
                "agent": "RAGEnhancedJudgeAgent"
            })

            # Get active rules
            active_rules = await rule_management_service.get_active_rules()

            # Prepare agent input
            agent_state = self.rag_enhanced_judge.create_state({
                "content_text": state["content_text"],
                "initial_judgment": state["initial_judgment"],
                "content_metadata": state["content_metadata"],
                "active_rules": active_rules or {}
            })

            # Execute RAG-enhanced agent
            result_state = await self.rag_enhanced_judge.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                # Fall back to initial judgment on RAG failure
                logger.warning("RAG analysis failed, using initial judgment")
                state["rag_enhanced_judgment"] = state["initial_judgment"]
            else:
                # Extract RAG-enhanced results
                state["rag_enhanced_judgment"] = result_state.output_data.get("enhanced_judgment", {})

                # Track confidence improvement
                rag_confidence = state["rag_enhanced_judgment"].get("confidence_score", 0.0)
                state["confidence_scores"].append(rag_confidence)

                # Update metadata
                state["workflow_metadata"]["rag_analysis"] = result_state.output_data.get("processing_metadata", {})

            logger.info(f"RAG analysis completed")
            return state

        except Exception as e:
            error_msg = f"RAG enhanced analysis node failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            # Fall back to initial judgment
            state["rag_enhanced_judgment"] = state["initial_judgment"]
            return state

    def route_after_rag(self, state: ContentAuditState) -> str:
        """Decision function for routing after RAG analysis"""
        try:
            rag_judgment = state["rag_enhanced_judgment"]
            judgment = rag_judgment.get("enhanced_judgment", "uncertain")
            confidence = rag_judgment.get("confidence_score", 0.0)

            # High confidence decisions
            if confidence >= 0.85:
                if judgment == "approved":
                    return "approve_rag"
                elif judgment == "rejected":
                    return "reject_rag"

            # Still uncertain or low confidence -> further escalation
            return "escalate_further"

        except Exception as e:
            logger.error(f"RAG routing decision failed: {e}")
            return "escalate_further"  # Safe fallback

    async def finalize_approved_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for finalizing approved content"""
        logger.info("Finalizing approved content...")

        try:
            state["current_step"] = "finalize_approved"
            state["processing_history"].append({
                "step": "finalize_approved",
                "timestamp": datetime.now().isoformat(),
                "action": "content_approved"
            })

            # Determine which judgment to use (RAG-enhanced if available)
            final_judgment = state.get("rag_enhanced_judgment") or state["initial_judgment"]

            # Set final results
            state["audit_conclusion"] = "approved"
            state["confidence_score"] = final_judgment.get("confidence_score", 0.0)
            state["violation_details"] = []  # No violations for approved content
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "completed"

            # Prepare final result
            reasoning = final_judgment.get("enhanced_reasoning") or final_judgment.get("reasoning", "Content approved")
            state["final_result"] = {
                "result": "approved",
                "confidence": state["confidence_score"],
                "reason": reasoning,
                "violated_rules": [],
                "processing_path": state["processing_path"],
                "timestamp": datetime.now().isoformat()
            }

            # Store audit record
            await self._store_audit_record(state)

            logger.info("Content approved successfully")
            return state

        except Exception as e:
            error_msg = f"Approval finalization failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def finalize_rejected_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for finalizing rejected content"""
        logger.info("Finalizing rejected content...")

        try:
            state["current_step"] = "finalize_rejected"
            state["processing_history"].append({
                "step": "finalize_rejected",
                "timestamp": datetime.now().isoformat(),
                "action": "content_rejected"
            })

            # Determine which judgment to use (RAG-enhanced if available)
            final_judgment = state.get("rag_enhanced_judgment") or state["initial_judgment"]

            # Set final results
            state["audit_conclusion"] = "rejected"
            state["confidence_score"] = final_judgment.get("confidence_score", 0.0)
            state["violation_details"] = final_judgment.get("violation_details", [])
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "completed"

            # Prepare final result
            violated_rules = [v.get("rule_reference", "unknown") for v in state["violation_details"]]
            reasoning = final_judgment.get("enhanced_reasoning") or final_judgment.get("reasoning", "Content rejected due to policy violations")

            state["final_result"] = {
                "result": "rejected",
                "confidence": state["confidence_score"],
                "reason": reasoning,
                "violated_rules": violated_rules,
                "processing_path": state["processing_path"],
                "timestamp": datetime.now().isoformat()
            }

            # Store audit record
            await self._store_audit_record(state)

            logger.info(f"Content rejected with {len(state['violation_details'])} violations")
            return state

        except Exception as e:
            error_msg = f"Rejection finalization failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def prepare_escalation_node(self, state: ContentAuditState) -> ContentAuditState:
        """Node for preparing escalation to higher processing levels"""
        logger.info("Preparing escalation...")

        try:
            state["current_step"] = "prepare_escalation"
            state["processing_history"].append({
                "step": "prepare_escalation",
                "timestamp": datetime.now().isoformat(),
                "action": f"escalated_to_{state['escalation_type']}"
            })

            # Set escalation results
            state["audit_conclusion"] = "pending_review"
            state["confidence_score"] = state["initial_judgment"].get("confidence_score", 0.0)
            state["violation_details"] = state["initial_judgment"].get("violation_details", [])
            state["processing_path"] = [step["step"] for step in state["processing_history"]]
            state["workflow_status"] = "escalated"

            # Prepare escalation result
            state["final_result"] = {
                "result": "pending_review",
                "confidence": state["confidence_score"],
                "reason": f"Content requires escalation: {state['escalation_type']}",
                "violated_rules": [v.get("rule_reference", "unknown") for v in state["violation_details"]],
                "processing_path": state["processing_path"],
                "escalation_type": state["escalation_type"],
                "escalation_reason": state["routing_decision"].get("explanation", ""),
                "timestamp": datetime.now().isoformat()
            }

            # Store preliminary audit record
            await self._store_audit_record(state, is_final=False)

            logger.info(f"Content escalated for {state['escalation_type']}")
            return state

        except Exception as e:
            error_msg = f"Escalation preparation failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def _store_audit_record(self, state: ContentAuditState, is_final: bool = True):
        """Store audit record in database"""
        try:
            content_text = state["content_text"]
            content_hash = hashlib.sha256(content_text.encode('utf-8')).hexdigest()
            content_preview = content_text[:500] + "..." if len(content_text) > 500 else content_text

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
                    "workflow_metadata": state["workflow_metadata"],
                    "escalation_type": state.get("escalation_type", "none"),
                    "content_metadata": state["content_metadata"],
                    "is_final": is_final
                }
            )

            state["workflow_metadata"]["audit_record_id"] = record.id
            logger.info(f"Audit record stored with ID: {record.id}")

        except Exception as e:
            logger.error(f"Failed to store audit record: {e}")
            # Don't fail the workflow for storage errors
            pass

    async def run_audit_workflow(
        self,
        content_text: str,
        content_metadata: Dict[str, Any] = None,
        audit_request_id: str = None
    ) -> ContentAuditState:
        """
        Run the complete content audit workflow

        Args:
            content_text: Chapter content to audit
            content_metadata: Content metadata
            audit_request_id: Unique identifier for this audit request

        Returns:
            Final workflow state with audit results
        """
        if not audit_request_id:
            audit_request_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(content_text) % 10000}"

        logger.info(f"Starting content audit workflow: {audit_request_id}")

        # Initialize state
        initial_state = ContentAuditState(
            content_text=content_text,
            content_metadata=content_metadata or {},
            audit_request_id=audit_request_id,
            current_step="initializing",
            processing_history=[{
                "step": "initialize",
                "timestamp": datetime.now().isoformat(),
                "action": "workflow_started"
            }],
            confidence_scores=[],
            initial_judgment={},
            routing_decision={},
            rag_enhanced_judgment={},
            final_result={},
            workflow_status="running",
            requires_escalation=False,
            escalation_type="none",
            audit_conclusion="pending",
            confidence_score=0.0,
            violation_details=[],
            processing_path=[],
            workflow_metadata={
                "workflow_id": audit_request_id,
                "workflow_version": "phase3_v1.0",
                "started_at": datetime.now().isoformat(),
                "content_length": len(content_text)
            },
            errors=[]
        )

        try:
            # Execute workflow
            final_state = await self.workflow_graph.ainvoke(initial_state)

            # Update completion metadata
            final_state["workflow_metadata"]["completed_at"] = datetime.now().isoformat()
            final_state["workflow_metadata"]["total_confidence_scores"] = final_state["confidence_scores"]
            final_state["workflow_metadata"]["average_confidence"] = (
                sum(final_state["confidence_scores"]) / len(final_state["confidence_scores"])
                if final_state["confidence_scores"] else 0.0
            )

            logger.info(f"Content audit workflow completed: {audit_request_id} "
                       f"(result: {final_state['audit_conclusion']}, "
                       f"confidence: {final_state['confidence_score']:.2f})")

            return final_state

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            initial_state["workflow_status"] = "failed"
            initial_state["errors"].append(str(e))
            initial_state["audit_conclusion"] = "error"
            return initial_state


# Global workflow instance
content_audit_workflow = ContentAuditWorkflow()