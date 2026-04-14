from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
import json
from datetime import datetime

from ..agents.rule_extractor import RuleExtractorAgent
from ..agents.rule_validator import RuleValidatorAgent
from ..storage.database import db_service
from ..config.settings import settings
import logging

logger = logging.getLogger(__name__)


class RuleExtractionState(TypedDict):
    """State for rule extraction workflow"""
    # Input
    document_content: str
    document_type: str
    source_filename: str

    # Processing
    current_step: str
    processing_history: List[Dict[str, Any]]

    # Agent outputs
    extracted_rules: Dict[str, Any]
    validation_result: Dict[str, Any]
    corrected_rules: Dict[str, Any]

    # Final results
    final_rules: Dict[str, Any]
    workflow_status: str
    human_review_required: bool

    # Metadata
    workflow_metadata: Dict[str, Any]
    errors: List[str]


class RuleExtractionWorkflow:
    """LangGraph workflow for rule extraction process"""

    def __init__(self):
        self.rule_extractor = RuleExtractorAgent()
        self.rule_validator = RuleValidatorAgent()
        self.workflow_graph = None
        self._build_workflow()

    def _build_workflow(self):
        """Build the LangGraph workflow"""
        # Create state graph
        workflow = StateGraph(RuleExtractionState)

        # Add nodes
        workflow.add_node("extract_rules", self.extract_rules_node)
        workflow.add_node("validate_rules", self.validate_rules_node)
        workflow.add_node("finalize_results", self.finalize_results_node)
        workflow.add_node("prepare_human_review", self.prepare_human_review_node)

        # Add edges
        workflow.set_entry_point("extract_rules")

        # From extract_rules -> validate_rules (always)
        workflow.add_edge("extract_rules", "validate_rules")

        # From validate_rules -> conditional routing
        workflow.add_conditional_edges(
            "validate_rules",
            self.should_require_human_review,
            {
                True: "prepare_human_review",
                False: "finalize_results"
            }
        )

        # From prepare_human_review -> END
        workflow.add_edge("prepare_human_review", END)

        # From finalize_results -> END
        workflow.add_edge("finalize_results", END)

        self.workflow_graph = workflow.compile()

    async def extract_rules_node(self, state: RuleExtractionState) -> RuleExtractionState:
        """Node for rule extraction (Agent1)"""
        logger.info("Executing rule extraction node...")

        try:
            # Update state
            state["current_step"] = "extracting_rules"
            state["processing_history"].append({
                "step": "extract_rules",
                "timestamp": datetime.now().isoformat(),
                "agent": "RuleExtractorAgent"
            })

            # Prepare agent input
            agent_state = self.rule_extractor.create_state({
                "document_content": state["document_content"],
                "document_type": state["document_type"],
                "source_filename": state["source_filename"]
            })

            # Execute agent
            result_state = await self.rule_extractor.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            # Extract results
            state["extracted_rules"] = result_state.output_data.get("extracted_rules", {})

            # Update metadata
            extraction_metadata = result_state.output_data.get("extraction_metadata", {})
            state["workflow_metadata"]["extraction"] = extraction_metadata

            logger.info("Rule extraction completed successfully")
            return state

        except Exception as e:
            error_msg = f"Rule extraction node failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def validate_rules_node(self, state: RuleExtractionState) -> RuleExtractionState:
        """Node for rule validation (Agent2)"""
        logger.info("Executing rule validation node...")

        try:
            # Update state
            state["current_step"] = "validating_rules"
            state["processing_history"].append({
                "step": "validate_rules",
                "timestamp": datetime.now().isoformat(),
                "agent": "RuleValidatorAgent"
            })

            # Prepare agent input
            agent_state = self.rule_validator.create_state({
                "original_document": state["document_content"],
                "extracted_rules": state["extracted_rules"],
                "source_metadata": {
                    "filename": state["source_filename"],
                    "document_type": state["document_type"]
                }
            })

            # Execute agent
            result_state = await self.rule_validator.safe_process(agent_state)

            if result_state.errors:
                state["errors"].extend(result_state.errors)
                state["workflow_status"] = "error"
                return state

            # Extract results
            state["validation_result"] = result_state.output_data.get("validation_result", {})
            state["corrected_rules"] = result_state.output_data.get("corrected_rules")

            # Update metadata
            validation_metadata = result_state.output_data.get("validation_metadata", {})
            state["workflow_metadata"]["validation"] = validation_metadata

            # Determine final recommendation
            final_recommendation = result_state.output_data.get("final_recommendation", {})
            state["workflow_metadata"]["final_recommendation"] = final_recommendation

            logger.info("Rule validation completed successfully")
            return state

        except Exception as e:
            error_msg = f"Rule validation node failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    def should_require_human_review(self, state: RuleExtractionState) -> bool:
        """Decision function for human review requirement"""
        try:
            recommendation = state["workflow_metadata"].get("final_recommendation", {})
            recommendation_type = recommendation.get("recommendation", "manual_review_required")

            # Require human review for certain recommendations
            human_review_required = recommendation_type in [
                "manual_review_required",
                "approve_with_review"
            ]

            # Also check for critical issues
            validation_result = state["validation_result"]
            critical_issues = [
                issue for issue in validation_result.get("issues_found", [])
                if issue.get("severity") == "critical"
            ]

            if critical_issues:
                human_review_required = True

            state["human_review_required"] = human_review_required
            logger.info(f"Human review required: {human_review_required}")
            return human_review_required

        except Exception as e:
            logger.error(f"Decision function failed: {e}")
            state["human_review_required"] = True
            return True

    async def prepare_human_review_node(self, state: RuleExtractionState) -> RuleExtractionState:
        """Node for preparing human review"""
        logger.info("Preparing human review...")

        try:
            state["current_step"] = "awaiting_human_review"
            state["processing_history"].append({
                "step": "prepare_human_review",
                "timestamp": datetime.now().isoformat(),
                "action": "prepared_for_human_review"
            })

            # Prepare rules for human review (use corrected if available)
            rules_for_review = state["corrected_rules"] if state["corrected_rules"] else state["extracted_rules"]
            state["final_rules"] = rules_for_review

            # Set workflow status
            state["workflow_status"] = "awaiting_human_review"

            # Store preliminary results in database for human review
            await self._store_preliminary_results(state)

            logger.info("Human review preparation completed")
            return state

        except Exception as e:
            error_msg = f"Human review preparation failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def finalize_results_node(self, state: RuleExtractionState) -> RuleExtractionState:
        """Node for finalizing results (auto-approval)"""
        logger.info("Finalizing results...")

        try:
            state["current_step"] = "finalizing"
            state["processing_history"].append({
                "step": "finalize_results",
                "timestamp": datetime.now().isoformat(),
                "action": "auto_approved"
            })

            # Use corrected rules if available, otherwise original
            rules_to_finalize = state["corrected_rules"] if state["corrected_rules"] else state["extracted_rules"]
            state["final_rules"] = rules_to_finalize

            # Create rule version in database
            version_id = await self._create_rule_version(state)
            state["workflow_metadata"]["rule_version_id"] = version_id

            # Set final status
            state["workflow_status"] = "completed"

            logger.info("Results finalized successfully")
            return state

        except Exception as e:
            error_msg = f"Results finalization failed: {str(e)}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["workflow_status"] = "error"
            return state

    async def _store_preliminary_results(self, state: RuleExtractionState):
        """Store preliminary results for human review"""
        try:
            # Create inactive rule version for human review
            version_name = f"pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            rule_version = db_service.create_rule_version(
                version=version_name,
                rules_content=state["final_rules"],
                source_document=state["source_filename"],
                extracted_by="RuleExtractionWorkflow",
                validated_by=None  # Will be set after human review
            )

            # Set as inactive since it needs human approval
            with db_service.session_factory() as db:
                rule_version.is_active = False
                db.commit()

            state["workflow_metadata"]["pending_rule_version_id"] = rule_version.id

        except Exception as e:
            logger.error(f"Failed to store preliminary results: {e}")
            raise

    async def _create_rule_version(self, state: RuleExtractionState) -> int:
        """Create final rule version in database"""
        try:
            version_name = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            rule_version = db_service.create_rule_version(
                version=version_name,
                rules_content=state["final_rules"],
                source_document=state["source_filename"],
                extracted_by="RuleExtractionWorkflow",
                validated_by="RuleValidatorAgent"
            )

            return rule_version.id

        except Exception as e:
            logger.error(f"Failed to create rule version: {e}")
            raise

    async def run_workflow(
        self,
        document_content: str,
        document_type: str,
        source_filename: str
    ) -> RuleExtractionState:
        """
        Run the complete rule extraction workflow

        Args:
            document_content: Raw document text
            document_type: Type of document (pdf, docx, txt)
            source_filename: Original filename

        Returns:
            Final workflow state
        """
        logger.info(f"Starting rule extraction workflow for: {source_filename}")

        # Initialize state
        initial_state = RuleExtractionState(
            document_content=document_content,
            document_type=document_type,
            source_filename=source_filename,
            current_step="initializing",
            processing_history=[{
                "step": "initialize",
                "timestamp": datetime.now().isoformat(),
                "action": "workflow_started"
            }],
            extracted_rules={},
            validation_result={},
            corrected_rules={},
            final_rules={},
            workflow_status="running",
            human_review_required=False,
            workflow_metadata={
                "workflow_id": f"rule_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "started_at": datetime.now().isoformat(),
                "source_filename": source_filename,
                "document_type": document_type
            },
            errors=[]
        )

        try:
            # Execute workflow
            final_state = await self.workflow_graph.ainvoke(initial_state)

            # Update completion metadata
            final_state["workflow_metadata"]["completed_at"] = datetime.now().isoformat()
            final_state["workflow_metadata"]["total_processing_time"] = "calculated_in_production"

            logger.info(f"Rule extraction workflow completed with status: {final_state['workflow_status']}")
            return final_state

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            initial_state["workflow_status"] = "failed"
            initial_state["errors"].append(str(e))
            return initial_state


# Global workflow instance
rule_extraction_workflow = RuleExtractionWorkflow()