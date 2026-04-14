from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from .base_agent import BaseAgent, AgentState
from ..config.settings import settings
import logging

logger = logging.getLogger(__name__)


class RoutingDecision(Enum):
    """Possible routing decisions"""
    APPROVE_DIRECTLY = "approve_directly"
    REJECT_DIRECTLY = "reject_directly"
    ESCALATE_TO_RAG = "escalate_to_rag"
    ESCALATE_TO_MULTIMODAL = "escalate_to_multimodal"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class RoutingReason(Enum):
    """Reasons for routing decisions"""
    HIGH_CONFIDENCE_APPROVAL = "high_confidence_approval"
    HIGH_CONFIDENCE_REJECTION = "high_confidence_rejection"
    LOW_CONFIDENCE = "low_confidence"
    UNCERTAIN_JUDGMENT = "uncertain_judgment"
    CRITICAL_VIOLATIONS = "critical_violations"
    BORDERLINE_CASE = "borderline_case"
    CONTRADICTORY_SIGNALS = "contradictory_signals"
    SYSTEM_ERROR = "system_error"


class SmartRouterAgent(BaseAgent):
    """Agent4: Smart router that determines next processing step based on confidence and content analysis"""

    def __init__(self):
        super().__init__("SmartRouter")
        self.high_confidence_threshold = settings.confidence_threshold_high
        self.low_confidence_threshold = settings.confidence_threshold_low

        # Routing configuration
        self.routing_config = {
            "direct_approval_threshold": 0.9,
            "direct_rejection_threshold": 0.9,
            "rag_escalation_threshold": 0.7,
            "multimodal_threshold": 0.5,
            "human_escalation_threshold": 0.3,
            "critical_violation_auto_escalate": True,
            "max_keyword_matches_for_direct": 2
        }

    async def process(self, state: AgentState) -> AgentState:
        """
        Route content to next processing step based on initial judgment

        Expected input_data:
        - initial_judgment: Result from Agent3
        - content_metadata: Content metadata
        - processing_history: Previous processing steps

        Returns:
        - routing_decision: Next processing step
        - routing_reason: Explanation for the decision
        - priority_level: Processing priority
        - estimated_processing_time: Expected time for next step
        """
        initial_judgment = state.input_data.get("initial_judgment", {})
        content_metadata = state.input_data.get("content_metadata", {})
        processing_history = state.input_data.get("processing_history", [])

        if not initial_judgment:
            self.add_error(state, "No initial judgment provided for routing")
            return state

        try:
            self.logger.info("Starting smart routing analysis...")

            # Step 1: Extract key metrics from initial judgment
            routing_metrics = self._extract_routing_metrics(initial_judgment)

            # Step 2: Analyze content characteristics
            content_analysis = self._analyze_content_characteristics(
                initial_judgment, content_metadata
            )

            # Step 3: Check for escalation triggers
            escalation_triggers = self._check_escalation_triggers(
                initial_judgment, content_analysis
            )

            # Step 4: Make routing decision
            routing_decision = self._make_routing_decision(
                routing_metrics, content_analysis, escalation_triggers
            )

            # Step 5: Calculate priority and estimated processing time
            priority_level = self._calculate_priority(routing_decision, escalation_triggers)
            estimated_time = self._estimate_processing_time(routing_decision)

            # Step 6: Generate detailed routing explanation
            routing_explanation = self._generate_routing_explanation(
                routing_decision, routing_metrics, escalation_triggers
            )

            # Prepare output
            state.output_data = {
                "routing_decision": {
                    "next_step": routing_decision["decision"].value,
                    "reason": routing_decision["reason"].value,
                    "confidence": routing_decision["confidence"],
                    "explanation": routing_explanation
                },
                "routing_metrics": routing_metrics,
                "escalation_triggers": escalation_triggers,
                "priority_level": priority_level,
                "estimated_processing_time": estimated_time,
                "processing_metadata": {
                    "agent": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "routing_version": "v1.0.0",
                    "config_used": self.routing_config
                }
            }

            self.logger.info(f"Routing decision: {routing_decision['decision'].value} "
                           f"(reason: {routing_decision['reason'].value}, "
                           f"priority: {priority_level})")

            return state

        except Exception as e:
            self.add_error(state, f"Smart routing failed: {str(e)}")
            # Fallback to human escalation on error
            state.output_data = {
                "routing_decision": {
                    "next_step": RoutingDecision.ESCALATE_TO_HUMAN.value,
                    "reason": RoutingReason.SYSTEM_ERROR.value,
                    "confidence": 0.0,
                    "explanation": f"System error occurred: {str(e)}"
                },
                "priority_level": "high",
                "estimated_processing_time": "manual_review"
            }
            return state

    def _extract_routing_metrics(self, initial_judgment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key metrics from initial judgment for routing decisions

        Args:
            initial_judgment: Result from Agent3

        Returns:
            Dictionary of routing metrics
        """
        try:
            judgment = initial_judgment.get("judgment", "uncertain")
            confidence = initial_judgment.get("confidence_score", 0.0)
            violations = initial_judgment.get("violation_details", [])
            keywords = initial_judgment.get("keyword_matches", [])

            # Count violations by severity
            violation_counts = {"minor": 0, "major": 0, "critical": 0}
            for violation in violations:
                severity = violation.get("severity", "minor")
                if severity in violation_counts:
                    violation_counts[severity] += 1

            # Count keyword matches by risk level
            keyword_risk_counts = {"low": 0, "medium": 0, "high": 0}
            for keyword_match in keywords:
                risk = keyword_match.get("risk_level", "low")
                if risk in keyword_risk_counts:
                    keyword_risk_counts[risk] += 1

            return {
                "judgment": judgment,
                "confidence_score": confidence,
                "total_violations": len(violations),
                "violation_counts": violation_counts,
                "total_keyword_matches": len(keywords),
                "keyword_risk_counts": keyword_risk_counts,
                "has_critical_violations": violation_counts["critical"] > 0,
                "has_major_violations": violation_counts["major"] > 0,
                "high_risk_keywords": keyword_risk_counts["high"]
            }

        except Exception as e:
            self.logger.error(f"Failed to extract routing metrics: {e}")
            return {
                "judgment": "uncertain",
                "confidence_score": 0.0,
                "total_violations": 0,
                "has_critical_violations": True  # Fail safe
            }

    def _analyze_content_characteristics(
        self,
        initial_judgment: Dict[str, Any],
        content_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze content characteristics that affect routing decisions

        Args:
            initial_judgment: Agent3 results
            content_metadata: Content metadata

        Returns:
            Content analysis for routing
        """
        try:
            content_analysis = initial_judgment.get("content_analysis", {})

            # Extract key characteristics
            genre = content_analysis.get("genre_detected", "unknown")
            tone = content_analysis.get("tone", "neutral")
            target_audience = content_analysis.get("target_audience", "general")
            content_length = content_analysis.get("content_length", 0)

            # Determine complexity factors
            complexity_factors = []

            if genre in ["historical", "political"]:
                complexity_factors.append("sensitive_genre")

            if target_audience == "adult":
                complexity_factors.append("adult_audience")

            if content_length > 5000:
                complexity_factors.append("long_content")

            if tone == "negative":
                complexity_factors.append("negative_tone")

            # Calculate complexity score
            complexity_score = len(complexity_factors) / 4.0  # Normalize to 0-1

            return {
                "genre": genre,
                "tone": tone,
                "target_audience": target_audience,
                "content_length": content_length,
                "complexity_factors": complexity_factors,
                "complexity_score": complexity_score,
                "requires_expert_review": complexity_score > 0.5
            }

        except Exception as e:
            self.logger.error(f"Content characteristics analysis failed: {e}")
            return {
                "complexity_score": 1.0,  # Assume high complexity on error
                "requires_expert_review": True
            }

    def _check_escalation_triggers(
        self,
        initial_judgment: Dict[str, Any],
        content_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Check for conditions that trigger escalation to higher processing levels

        Args:
            initial_judgment: Agent3 results
            content_analysis: Content characteristics

        Returns:
            List of escalation triggers
        """
        triggers = []

        try:
            # Extract metrics
            confidence = initial_judgment.get("confidence_score", 0.0)
            violations = initial_judgment.get("violation_details", [])
            judgment = initial_judgment.get("judgment", "uncertain")

            # Confidence-based triggers
            if confidence <= self.routing_config["human_escalation_threshold"]:
                triggers.append({
                    "type": "low_confidence",
                    "severity": "high",
                    "description": f"Very low confidence score: {confidence:.2f}",
                    "recommendation": "human_review"
                })
            elif confidence <= self.routing_config["multimodal_threshold"]:
                triggers.append({
                    "type": "medium_confidence",
                    "severity": "medium",
                    "description": f"Medium confidence score: {confidence:.2f}",
                    "recommendation": "multimodal_verification"
                })

            # Critical violation triggers
            critical_violations = [v for v in violations if v.get("severity") == "critical"]
            if critical_violations and self.routing_config["critical_violation_auto_escalate"]:
                triggers.append({
                    "type": "critical_violations",
                    "severity": "critical",
                    "description": f"Found {len(critical_violations)} critical violations",
                    "recommendation": "immediate_escalation"
                })

            # Uncertain judgment trigger
            if judgment == "uncertain":
                triggers.append({
                    "type": "uncertain_judgment",
                    "severity": "medium",
                    "description": "Agent3 could not make clear judgment",
                    "recommendation": "rag_enhancement"
                })

            # Complex content triggers
            if content_analysis.get("complexity_score", 0) > 0.7:
                triggers.append({
                    "type": "complex_content",
                    "severity": "medium",
                    "description": "Content has high complexity score",
                    "recommendation": "expert_review"
                })

            # Contradictory signals trigger
            high_confidence_with_violations = (
                confidence > 0.8 and
                len(violations) > 3 and
                judgment == "approved"
            )
            if high_confidence_with_violations:
                triggers.append({
                    "type": "contradictory_signals",
                    "severity": "high",
                    "description": "High confidence approval despite multiple violations",
                    "recommendation": "multimodal_verification"
                })

            return triggers

        except Exception as e:
            self.logger.error(f"Escalation trigger check failed: {e}")
            return [{
                "type": "system_error",
                "severity": "critical",
                "description": f"Error in trigger analysis: {str(e)}",
                "recommendation": "human_review"
            }]

    def _make_routing_decision(
        self,
        metrics: Dict[str, Any],
        content_analysis: Dict[str, Any],
        triggers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Make the final routing decision based on all analysis

        Args:
            metrics: Routing metrics
            content_analysis: Content characteristics
            triggers: Escalation triggers

        Returns:
            Routing decision with reason and confidence
        """
        try:
            confidence = metrics["confidence_score"]
            judgment = metrics["judgment"]
            has_critical_violations = metrics["has_critical_violations"]
            has_triggers = len(triggers) > 0

            # Check for critical triggers that force human review
            critical_triggers = [t for t in triggers if t["severity"] == "critical"]
            if critical_triggers:
                return {
                    "decision": RoutingDecision.ESCALATE_TO_HUMAN,
                    "reason": RoutingReason.CRITICAL_VIOLATIONS,
                    "confidence": 1.0,
                    "details": "Critical escalation triggers detected"
                }

            # High confidence direct decisions
            if confidence >= self.routing_config["direct_approval_threshold"]:
                if judgment == "approved" and not has_critical_violations:
                    return {
                        "decision": RoutingDecision.APPROVE_DIRECTLY,
                        "reason": RoutingReason.HIGH_CONFIDENCE_APPROVAL,
                        "confidence": confidence,
                        "details": "High confidence approval with no critical violations"
                    }

            if confidence >= self.routing_config["direct_rejection_threshold"]:
                if judgment == "rejected":
                    return {
                        "decision": RoutingDecision.REJECT_DIRECTLY,
                        "reason": RoutingReason.HIGH_CONFIDENCE_REJECTION,
                        "confidence": confidence,
                        "details": "High confidence rejection"
                    }

            # Check for RAG escalation conditions
            if confidence >= self.routing_config["rag_escalation_threshold"]:
                if not has_critical_violations and judgment != "uncertain":
                    return {
                        "decision": RoutingDecision.ESCALATE_TO_RAG,
                        "reason": RoutingReason.BORDERLINE_CASE,
                        "confidence": confidence,
                        "details": "Borderline case requiring similar case analysis"
                    }

            # Check for multimodal verification
            multimodal_triggers = [t for t in triggers if t["recommendation"] == "multimodal_verification"]
            if (confidence >= self.routing_config["multimodal_threshold"] and
                confidence < self.routing_config["rag_escalation_threshold"]):
                return {
                    "decision": RoutingDecision.ESCALATE_TO_MULTIMODAL,
                    "reason": RoutingReason.CONTRADICTORY_SIGNALS,
                    "confidence": confidence,
                    "details": "Multiple perspectives needed for verification"
                }

            # Low confidence or uncertain cases
            if confidence <= self.routing_config["human_escalation_threshold"] or judgment == "uncertain":
                return {
                    "decision": RoutingDecision.ESCALATE_TO_HUMAN,
                    "reason": RoutingReason.LOW_CONFIDENCE,
                    "confidence": confidence,
                    "details": "Low confidence or uncertain judgment requires human review"
                }

            # Default case - escalate to RAG
            return {
                "decision": RoutingDecision.ESCALATE_TO_RAG,
                "reason": RoutingReason.UNCERTAIN_JUDGMENT,
                "confidence": confidence,
                "details": "Default escalation to RAG for additional analysis"
            }

        except Exception as e:
            self.logger.error(f"Routing decision failed: {e}")
            return {
                "decision": RoutingDecision.ESCALATE_TO_HUMAN,
                "reason": RoutingReason.SYSTEM_ERROR,
                "confidence": 0.0,
                "details": f"System error: {str(e)}"
            }

    def _calculate_priority(
        self,
        routing_decision: Dict[str, Any],
        triggers: List[Dict[str, Any]]
    ) -> str:
        """
        Calculate processing priority based on routing decision and triggers

        Args:
            routing_decision: Routing decision details
            triggers: Escalation triggers

        Returns:
            Priority level ("low", "medium", "high", "critical")
        """
        try:
            decision = routing_decision["decision"]
            confidence = routing_decision["confidence"]

            # Critical priority conditions
            critical_triggers = [t for t in triggers if t["severity"] == "critical"]
            if critical_triggers or decision == RoutingDecision.ESCALATE_TO_HUMAN:
                return "critical"

            # High priority conditions
            if (decision == RoutingDecision.REJECT_DIRECTLY or
                confidence <= 0.3 or
                any(t["severity"] == "high" for t in triggers)):
                return "high"

            # Medium priority conditions
            if (decision == RoutingDecision.ESCALATE_TO_MULTIMODAL or
                decision == RoutingDecision.ESCALATE_TO_RAG or
                confidence <= 0.6):
                return "medium"

            # Low priority for direct approvals with high confidence
            return "low"

        except Exception:
            return "high"  # Default to high priority on error

    def _estimate_processing_time(self, routing_decision: Dict[str, Any]) -> str:
        """
        Estimate processing time for next step

        Args:
            routing_decision: Routing decision details

        Returns:
            Estimated processing time
        """
        time_estimates = {
            RoutingDecision.APPROVE_DIRECTLY: "immediate",
            RoutingDecision.REJECT_DIRECTLY: "immediate",
            RoutingDecision.ESCALATE_TO_RAG: "2-5 minutes",
            RoutingDecision.ESCALATE_TO_MULTIMODAL: "5-10 minutes",
            RoutingDecision.ESCALATE_TO_HUMAN: "manual_review"
        }

        decision = routing_decision["decision"]
        return time_estimates.get(decision, "unknown")

    def _generate_routing_explanation(
        self,
        routing_decision: Dict[str, Any],
        metrics: Dict[str, Any],
        triggers: List[Dict[str, Any]]
    ) -> str:
        """
        Generate human-readable explanation for routing decision

        Args:
            routing_decision: Routing decision details
            metrics: Routing metrics
            triggers: Escalation triggers

        Returns:
            Detailed explanation string
        """
        try:
            decision = routing_decision["decision"]
            confidence = metrics["confidence_score"]
            judgment = metrics["judgment"]
            violations = metrics["total_violations"]

            explanation_parts = [
                f"Initial judgment: {judgment} (confidence: {confidence:.2f})",
                f"Total violations detected: {violations}"
            ]

            if triggers:
                trigger_descriptions = [t["description"] for t in triggers]
                explanation_parts.append(f"Escalation triggers: {'; '.join(trigger_descriptions)}")

            explanation_parts.append(f"Routing decision: {decision.value}")
            explanation_parts.append(routing_decision.get("details", ""))

            return " | ".join(explanation_parts)

        except Exception as e:
            return f"Unable to generate explanation: {str(e)}"