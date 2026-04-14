from typing import Dict, Any, List, Tuple
from datetime import datetime
import json

from .base_agent import BaseAgent, AgentState
from ..services.openai_service import openai_service
from ..services.confidence_scoring import confidence_scorer
from ..config.settings import settings

ARBITRATION_ANALYSIS_PROMPT = """
You are an expert arbitration agent responsible for synthesizing multiple expert perspectives and making final audit decisions.

You have received analyses from several specialized agents examining the same content. Your task is to:
1. Evaluate the consistency and conflicts between different perspectives
2. Weight the perspectives based on their relevance and confidence
3. Identify key decision factors and trade-offs
4. Make a final, well-reasoned audit decision
5. Provide clear justification for your decision

CONTENT BEING ANALYZED:
{content_text}

EXPERT PERSPECTIVES RECEIVED:
{expert_perspectives}

INITIAL ASSESSMENTS:
{initial_assessments}

ARBITRATION GUIDELINES:
- **Legal Compliance**: Legal concerns generally override other considerations
- **Critical Safety**: Safety issues take high priority
- **Platform Risk**: Consider business impact and sustainability
- **User Experience**: Balance quality with accessibility
- **Social Impact**: Consider community welfare

Provide your arbitration decision in JSON format:
```json
{
  "final_decision": "approved|rejected|requires_human_review",
  "confidence_score": 0.88,
  "arbitration_reasoning": "Comprehensive explanation of decision logic",
  "perspective_analysis": {
    "perspectives_received": ["legal_compliance", "social_impact", "user_experience", "platform_risk"],
    "consensus_level": "high|medium|low",
    "main_conflicts": [
      {
        "conflict_type": "legal_vs_ux|safety_vs_engagement|etc",
        "perspectives_involved": ["perspective1", "perspective2"],
        "conflict_description": "Description of the disagreement",
        "resolution_approach": "How this conflict was resolved"
      }
    ],
    "perspective_weights": {
      "legal_compliance": 0.3,
      "social_impact": 0.25,
      "user_experience": 0.2,
      "platform_risk": 0.25
    }
  },
  "decision_factors": [
    {
      "factor": "primary_concern|secondary_consideration",
      "description": "Key factor influencing the decision",
      "weight": 0.4,
      "perspective_support": ["which perspectives support this factor"]
    }
  ],
  "risk_assessment": {
    "overall_risk_level": "low|medium|high|critical",
    "primary_risks": ["list of main risks identified"],
    "risk_mitigation": ["suggested risk mitigation measures"],
    "acceptable_risk": true
  },
  "quality_considerations": {
    "content_quality": "excellent|good|acceptable|poor",
    "platform_fit": "excellent|good|acceptable|poor",
    "user_safety": "high|medium|low",
    "community_benefit": "positive|neutral|negative"
  },
  "escalation_triggers": [
    "Conditions that would require human review"
  ],
  "recommendations": {
    "immediate_action": "approve|reject|escalate",
    "conditions": ["Any conditions for approval"],
    "monitoring_required": ["Areas requiring ongoing monitoring"],
    "follow_up_actions": ["Recommended follow-up actions"]
  },
  "arbitration_metadata": {
    "decision_timestamp": "2025-01-15T10:30:00Z",
    "perspectives_analyzed": 4,
    "confidence_factors": ["factors affecting confidence"],
    "decision_complexity": "simple|moderate|complex|highly_complex"
  }
}
```

Be thorough, balanced, and decisive. Prioritize safety and legal compliance while considering all perspectives.
"""

CONFLICT_RESOLUTION_PROMPT = """
You are resolving conflicts between expert perspectives on content audit decisions.

CONFLICTING PERSPECTIVES:
{conflicting_perspectives}

CONFLICT ANALYSIS REQUIRED:
1. Identify the root cause of disagreement
2. Evaluate the strength of each perspective's argument
3. Consider the relative importance of each concern
4. Find a balanced resolution approach

Provide conflict resolution analysis:
```json
{
  "conflict_summary": "Brief description of the main conflict",
  "conflict_severity": "minor|moderate|major|critical",
  "resolution_strategy": "compromise|priority_override|escalation|conditional_approval",
  "resolution_reasoning": "Detailed explanation of resolution approach",
  "final_position": "approved|rejected|conditional|escalate"
}
```
"""


class ArbitrationAgent(BaseAgent):
    """Agent that arbitrates between multiple perspective analyses to make final decisions"""

    def __init__(self):
        super().__init__("ArbitrationAgent")
        self.perspective_weights = {
            "legal_compliance": 0.30,    # Legal issues are critical
            "social_impact": 0.25,       # Social responsibility matters
            "user_experience": 0.20,     # User satisfaction important
            "platform_risk": 0.25        # Business sustainability crucial
        }

        # Escalation thresholds
        self.escalation_thresholds = {
            "critical_legal_risk": True,
            "high_safety_concern": True,
            "major_perspective_conflict": True,
            "low_arbitration_confidence": 0.6
        }

    async def process(self, state: AgentState) -> AgentState:
        """
        Process arbitration between multiple expert perspectives

        Expected input_data:
        - content_text: Original content being analyzed
        - expert_perspectives: Dict of perspective analyses
        - initial_assessments: Previous assessment results
        - metadata: Additional context

        Returns:
        - final_decision: Arbitrated decision
        - arbitration_analysis: Detailed analysis
        - conflict_resolution: How conflicts were resolved
        - escalation_recommendation: Whether human review is needed
        """
        content_text = state.input_data.get("content_text", "")
        expert_perspectives = state.input_data.get("expert_perspectives", {})
        initial_assessments = state.input_data.get("initial_assessments", {})
        metadata = state.input_data.get("metadata", {})

        if not expert_perspectives:
            self.add_error(state, "No expert perspectives provided for arbitration")
            return state

        try:
            self.logger.info(f"Starting arbitration of {len(expert_perspectives)} expert perspectives...")

            # Step 1: Analyze perspective consensus and conflicts
            consensus_analysis = self._analyze_perspective_consensus(expert_perspectives)

            # Step 2: Identify and resolve conflicts
            conflict_resolution = await self._resolve_perspective_conflicts(
                expert_perspectives, content_text
            )

            # Step 3: Perform final arbitration
            arbitration_result = await self._perform_arbitration(
                content_text, expert_perspectives, initial_assessments
            )

            # Step 4: Check escalation criteria
            escalation_decision = self._evaluate_escalation_need(
                arbitration_result, expert_perspectives, consensus_analysis
            )

            # Step 5: Calculate final confidence
            final_confidence = self._calculate_arbitration_confidence(
                arbitration_result, consensus_analysis, expert_perspectives
            )

            # Prepare output
            state.output_data = {
                "final_decision": arbitration_result.get("final_decision", "requires_human_review"),
                "confidence_score": final_confidence,
                "arbitration_analysis": arbitration_result,
                "consensus_analysis": consensus_analysis,
                "conflict_resolution": conflict_resolution,
                "escalation_recommendation": escalation_decision,
                "processing_metadata": {
                    "agent": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "perspectives_analyzed": len(expert_perspectives),
                    "arbitration_version": "v1.0.0"
                }
            }

            decision = arbitration_result.get("final_decision", "unknown")
            self.logger.info(f"Arbitration completed: {decision} (confidence: {final_confidence:.2f})")

            return state

        except Exception as e:
            self.add_error(state, f"Arbitration failed: {str(e)}")
            return state

    def _analyze_perspective_consensus(self, perspectives: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze consensus and conflicts between perspectives"""
        try:
            consensus_analysis = {
                "total_perspectives": len(perspectives),
                "consensus_level": "unknown",
                "agreement_score": 0.0,
                "conflicting_perspectives": [],
                "consensus_indicators": {}
            }

            if not perspectives:
                return consensus_analysis

            # Extract decisions from each perspective
            decisions = {}
            confidence_scores = {}

            for perspective_name, perspective_data in perspectives.items():
                analysis = perspective_data.get("analysis", {})

                # Map different assessment types to common decisions
                if perspective_name == "legal_compliance":
                    decision = analysis.get("legal_assessment", "unknown")
                elif perspective_name == "social_impact":
                    decision = analysis.get("social_assessment", "unknown")
                elif perspective_name == "user_experience":
                    decision = analysis.get("ux_assessment", "unknown")
                elif perspective_name == "platform_risk":
                    decision = analysis.get("risk_assessment", "unknown")
                else:
                    decision = "unknown"

                decisions[perspective_name] = decision
                confidence_scores[perspective_name] = analysis.get("confidence_score", 0.5)

            # Calculate consensus metrics
            decision_values = list(decisions.values())
            unique_decisions = set(decision_values)

            # Simple consensus calculation
            if len(unique_decisions) == 1:
                consensus_analysis["consensus_level"] = "high"
                consensus_analysis["agreement_score"] = 1.0
            elif len(unique_decisions) == 2:
                consensus_analysis["consensus_level"] = "medium"
                consensus_analysis["agreement_score"] = 0.6
            else:
                consensus_analysis["consensus_level"] = "low"
                consensus_analysis["agreement_score"] = 0.3

            # Identify conflicts
            for perspective_name, decision in decisions.items():
                other_decisions = {k: v for k, v in decisions.items() if k != perspective_name}
                conflicting = [k for k, v in other_decisions.items() if self._are_decisions_conflicting(decision, v)]

                if conflicting:
                    consensus_analysis["conflicting_perspectives"].append({
                        "perspective": perspective_name,
                        "decision": decision,
                        "conflicts_with": conflicting
                    })

            consensus_analysis["decisions"] = decisions
            consensus_analysis["confidence_scores"] = confidence_scores

            return consensus_analysis

        except Exception as e:
            self.logger.error(f"Consensus analysis failed: {e}")
            return {
                "total_perspectives": len(perspectives),
                "consensus_level": "unknown",
                "agreement_score": 0.0,
                "error": str(e)
            }

    def _are_decisions_conflicting(self, decision1: str, decision2: str) -> bool:
        """Check if two decisions are conflicting"""
        # Define conflicting decision pairs
        conflicts = [
            ("compliant", "non_compliant"),
            ("positive", "harmful"),
            ("excellent", "unacceptable"),
            ("low", "critical"),
            ("approved", "rejected")
        ]

        for conflict_pair in conflicts:
            if (decision1 in conflict_pair and decision2 in conflict_pair and
                decision1 != decision2):
                return True

        return False

    async def _resolve_perspective_conflicts(
        self,
        perspectives: Dict[str, Any],
        content_text: str
    ) -> Dict[str, Any]:
        """Resolve conflicts between perspectives using LLM analysis"""
        try:
            # Find conflicting perspectives
            conflicts = []
            perspective_items = list(perspectives.items())

            for i, (name1, data1) in enumerate(perspective_items):
                for name2, data2 in perspective_items[i+1:]:
                    # Check for conflicts between perspectives
                    analysis1 = data1.get("analysis", {})
                    analysis2 = data2.get("analysis", {})

                    # Simple conflict detection based on recommendation differences
                    rec1 = self._extract_recommendation(name1, analysis1)
                    rec2 = self._extract_recommendation(name2, analysis2)

                    if self._are_recommendations_conflicting(rec1, rec2):
                        conflicts.append({
                            "perspectives": [name1, name2],
                            "recommendations": [rec1, rec2],
                            "analyses": [analysis1, analysis2]
                        })

            if not conflicts:
                return {
                    "conflicts_found": 0,
                    "resolution_needed": False,
                    "resolution_summary": "No significant conflicts detected"
                }

            # Resolve major conflicts using LLM
            resolution_results = []
            for conflict in conflicts[:3]:  # Limit to top 3 conflicts
                try:
                    conflict_prompt = CONFLICT_RESOLUTION_PROMPT.format(
                        conflicting_perspectives=json.dumps(conflict, indent=2, ensure_ascii=False)
                    )

                    resolution_schema = {
                        "type": "object",
                        "properties": {
                            "conflict_summary": {"type": "string"},
                            "conflict_severity": {"type": "string"},
                            "resolution_strategy": {"type": "string"},
                            "resolution_reasoning": {"type": "string"},
                            "final_position": {"type": "string"}
                        }
                    }

                    resolution = await openai_service.structured_completion(
                        prompt=conflict_prompt,
                        schema=resolution_schema,
                        temperature=0.1
                    )

                    resolution_results.append(resolution)

                except Exception as e:
                    self.logger.error(f"Conflict resolution failed for conflict: {e}")
                    continue

            return {
                "conflicts_found": len(conflicts),
                "resolution_needed": True,
                "conflicts_analyzed": conflicts,
                "resolutions": resolution_results,
                "resolution_summary": f"Resolved {len(resolution_results)} conflicts"
            }

        except Exception as e:
            self.logger.error(f"Conflict resolution failed: {e}")
            return {
                "conflicts_found": 0,
                "resolution_needed": False,
                "error": str(e)
            }

    def _extract_recommendation(self, perspective_name: str, analysis: Dict[str, Any]) -> str:
        """Extract recommendation from perspective analysis"""
        recommendation_fields = {
            "legal_compliance": "legal_assessment",
            "social_impact": "social_assessment",
            "user_experience": "platform_recommendation",
            "platform_risk": "business_recommendation"
        }

        field = recommendation_fields.get(perspective_name, "assessment")
        return analysis.get(field, "unknown")

    def _are_recommendations_conflicting(self, rec1: str, rec2: str) -> bool:
        """Check if recommendations are conflicting"""
        conflicting_pairs = [
            ("approve", "reject"),
            ("compliant", "non_compliant"),
            ("positive", "harmful"),
            ("excellent", "unacceptable"),
            ("low", "critical")
        ]

        for pair in conflicting_pairs:
            if rec1 in pair and rec2 in pair and rec1 != rec2:
                return True
        return False

    async def _perform_arbitration(
        self,
        content_text: str,
        perspectives: Dict[str, Any],
        initial_assessments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform the main arbitration analysis"""
        try:
            # Format perspectives for prompt
            formatted_perspectives = {}
            for name, data in perspectives.items():
                formatted_perspectives[name] = {
                    "analysis": data.get("analysis", {}),
                    "confidence": data.get("processing_metadata", {}).get("confidence", 0.5)
                }

            prompt = ARBITRATION_ANALYSIS_PROMPT.format(
                content_text=content_text[:1500] + "..." if len(content_text) > 1500 else content_text,
                expert_perspectives=json.dumps(formatted_perspectives, indent=2, ensure_ascii=False),
                initial_assessments=json.dumps(initial_assessments, indent=2, ensure_ascii=False)
            )

            arbitration_schema = {
                "type": "object",
                "properties": {
                    "final_decision": {"type": "string", "enum": ["approved", "rejected", "requires_human_review"]},
                    "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "arbitration_reasoning": {"type": "string"},
                    "perspective_analysis": {"type": "object"},
                    "decision_factors": {"type": "array"},
                    "risk_assessment": {"type": "object"},
                    "quality_considerations": {"type": "object"},
                    "escalation_triggers": {"type": "array"},
                    "recommendations": {"type": "object"},
                    "arbitration_metadata": {"type": "object"}
                },
                "required": ["final_decision", "confidence_score", "arbitration_reasoning"]
            }

            arbitration_result = await openai_service.structured_completion(
                prompt=prompt,
                schema=arbitration_schema,
                temperature=0.1
            )

            # Validate the result
            validated_result = self._validate_arbitration_result(arbitration_result)

            return validated_result

        except Exception as e:
            self.logger.error(f"Arbitration analysis failed: {e}")
            return {
                "final_decision": "requires_human_review",
                "confidence_score": 0.3,
                "arbitration_reasoning": f"Arbitration failed due to error: {str(e)}",
                "error": str(e)
            }

    def _validate_arbitration_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean arbitration result"""
        try:
            # Ensure required fields
            if "final_decision" not in result:
                result["final_decision"] = "requires_human_review"

            if "confidence_score" not in result:
                result["confidence_score"] = 0.5

            # Validate decision
            valid_decisions = ["approved", "rejected", "requires_human_review"]
            if result["final_decision"] not in valid_decisions:
                result["final_decision"] = "requires_human_review"

            # Validate confidence
            confidence = result.get("confidence_score", 0.5)
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                result["confidence_score"] = 0.5

            return result

        except Exception as e:
            self.logger.error(f"Arbitration result validation failed: {e}")
            return {
                "final_decision": "requires_human_review",
                "confidence_score": 0.3,
                "arbitration_reasoning": f"Validation failed: {str(e)}"
            }

    def _evaluate_escalation_need(
        self,
        arbitration_result: Dict[str, Any],
        perspectives: Dict[str, Any],
        consensus_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate whether human escalation is needed"""
        try:
            escalation_reasons = []
            escalation_needed = False

            # Check confidence threshold
            confidence = arbitration_result.get("confidence_score", 0.5)
            if confidence < self.escalation_thresholds["low_arbitration_confidence"]:
                escalation_reasons.append(f"Low arbitration confidence: {confidence:.2f}")
                escalation_needed = True

            # Check consensus level
            consensus_level = consensus_analysis.get("consensus_level", "unknown")
            if consensus_level == "low":
                escalation_reasons.append("Low consensus between expert perspectives")
                escalation_needed = True

            # Check for critical risks
            legal_analysis = perspectives.get("legal_compliance", {}).get("analysis", {})
            if legal_analysis.get("requires_legal_review"):
                escalation_reasons.append("Legal review explicitly required")
                escalation_needed = True

            # Check risk levels
            risk_analysis = perspectives.get("platform_risk", {}).get("analysis", {})
            if risk_analysis.get("risk_assessment") == "critical":
                escalation_reasons.append("Critical platform risk identified")
                escalation_needed = True

            return {
                "escalation_needed": escalation_needed,
                "escalation_reasons": escalation_reasons,
                "escalation_priority": "high" if len(escalation_reasons) > 2 else "medium",
                "recommendation": "human_review" if escalation_needed else "automated_processing"
            }

        except Exception as e:
            self.logger.error(f"Escalation evaluation failed: {e}")
            return {
                "escalation_needed": True,
                "escalation_reasons": ["Escalation evaluation failed"],
                "error": str(e)
            }

    def _calculate_arbitration_confidence(
        self,
        arbitration_result: Dict[str, Any],
        consensus_analysis: Dict[str, Any],
        perspectives: Dict[str, Any]
    ) -> float:
        """Calculate final arbitration confidence score"""
        try:
            base_confidence = arbitration_result.get("confidence_score", 0.5)

            # Adjust based on consensus
            consensus_score = consensus_analysis.get("agreement_score", 0.5)
            consensus_boost = (consensus_score - 0.5) * 0.2

            # Adjust based on perspective confidence
            perspective_confidences = []
            for perspective_data in perspectives.values():
                conf = perspective_data.get("analysis", {}).get("confidence_score", 0.5)
                perspective_confidences.append(conf)

            avg_perspective_confidence = sum(perspective_confidences) / len(perspective_confidences) if perspective_confidences else 0.5
            perspective_boost = (avg_perspective_confidence - 0.5) * 0.1

            # Final confidence
            final_confidence = base_confidence + consensus_boost + perspective_boost
            final_confidence = max(0.0, min(1.0, final_confidence))

            return round(final_confidence, 3)

        except Exception as e:
            self.logger.error(f"Confidence calculation failed: {e}")
            return 0.5