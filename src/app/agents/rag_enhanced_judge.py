from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import json

from .base_agent import BaseAgent, AgentState
from ..services.openai_service import openai_service
from ..storage.vector_store import vector_store
from ..config.settings import settings

RAG_ENHANCED_JUDGMENT_PROMPT = """
You are an expert content auditor performing enhanced analysis using similar case precedents.

CURRENT CONTENT TO AUDIT:
{content_text}

INITIAL ASSESSMENT:
{initial_judgment}

SIMILAR CASE PRECEDENTS:
{similar_cases}

ACTIVE RULES REFERENCE:
{rules_summary}

ENHANCED ANALYSIS INSTRUCTIONS:

1. **Precedent Analysis**: Review the similar cases and their outcomes
2. **Pattern Recognition**: Identify patterns between current content and precedents
3. **Contextual Reasoning**: Consider the context and nuances that affected past decisions
4. **Consistency Evaluation**: Ensure your judgment aligns with established precedents
5. **Confidence Refinement**: Use case evidence to refine confidence in your assessment

Compare the current content with similar precedents and provide an enhanced judgment:

```json
{
  "enhanced_judgment": "approved|rejected|uncertain",
  "confidence_score": 0.87,
  "confidence_improvement": 0.12,
  "precedent_analysis": {
    "total_cases_reviewed": 5,
    "similar_approvals": 2,
    "similar_rejections": 3,
    "precedent_confidence": 0.85,
    "key_precedent_patterns": [
      "Pattern 1: Description of recurring pattern",
      "Pattern 2: Another significant pattern"
    ]
  },
  "case_comparisons": [
    {
      "case_similarity": 0.92,
      "case_outcome": "rejected",
      "key_differences": "Specific differences from this case",
      "outcome_rationale": "Why this case supports/contradicts current judgment"
    }
  ],
  "contextual_factors": [
    {
      "factor": "genre_considerations",
      "description": "How genre affects the judgment",
      "precedent_support": "Evidence from similar genre cases"
    }
  ],
  "enhanced_reasoning": "Detailed reasoning incorporating precedent analysis",
  "precedent_based_recommendations": [
    "Specific recommendations based on case analysis"
  ],
  "uncertainty_factors": [
    "Factors that still create uncertainty despite precedents"
  ],
  "processing_metadata": {
    "agent": "RAGEnhancedJudge",
    "timestamp": "2025-01-15T10:30:00Z",
    "cases_analyzed": 5,
    "average_case_similarity": 0.78
  }
}
```

JUDGMENT GUIDELINES:
- Weight precedents by similarity score and outcome consistency
- Consider edge cases and unique contextual factors
- If precedents strongly support one outcome, increase confidence
- If precedents are mixed or contradictory, maintain uncertainty
- Always explain how precedents influenced your decision

Be thorough in analyzing precedents but focus on the most relevant patterns.
"""

CASE_RELEVANCE_EVALUATION_PROMPT = """
Evaluate the relevance of retrieved cases for the current audit decision.

Current Content Summary: {content_summary}
Initial Assessment: {initial_assessment}

Retrieved Cases:
{retrieved_cases}

For each case, evaluate:
1. Content similarity (0-1 score)
2. Context relevance (0-1 score)
3. Decision relevance (how much this case should influence current decision)
4. Key insights from this case

Return analysis in JSON format with relevance scores and insights.
"""


class RAGEnhancedJudgeAgent(BaseAgent):
    """Agent5: RAG-enhanced judge using similar case precedents"""

    def __init__(self):
        super().__init__("RAGEnhancedJudge")
        self.max_similar_cases = 10
        self.min_similarity_threshold = 0.3

    async def process(self, state: AgentState) -> AgentState:
        """
        Perform RAG-enhanced judgment using similar cases

        Expected input_data:
        - content_text: Original content to audit
        - initial_judgment: Result from Agent3
        - content_metadata: Content metadata
        - active_rules: Current active rules

        Returns:
        - enhanced_judgment: Improved judgment with precedent analysis
        - case_analysis: Analysis of similar cases
        - confidence_improvement: How much confidence improved
        """
        content_text = state.input_data.get("content_text", "")
        initial_judgment = state.input_data.get("initial_judgment", {})
        content_metadata = state.input_data.get("content_metadata", {})
        active_rules = state.input_data.get("active_rules", {})

        if not content_text or not initial_judgment:
            self.add_error(state, "Missing required input: content_text or initial_judgment")
            return state

        try:
            self.logger.info("Starting RAG-enhanced judgment analysis...")

            # Step 1: Retrieve similar cases from ChromaDB
            similar_cases = await self._retrieve_similar_cases(
                content_text, initial_judgment
            )

            if not similar_cases:
                self.logger.warning("No similar cases found, proceeding without RAG enhancement")
                return await self._fallback_to_initial_judgment(state)

            # Step 2: Evaluate case relevance and filter
            relevant_cases = await self._evaluate_case_relevance(
                content_text, initial_judgment, similar_cases
            )

            # Step 3: Perform enhanced analysis using precedents
            enhanced_judgment = await self._perform_enhanced_analysis(
                content_text, initial_judgment, relevant_cases, active_rules
            )

            # Step 4: Calculate confidence improvement
            confidence_improvement = self._calculate_confidence_improvement(
                initial_judgment, enhanced_judgment
            )

            # Step 5: Generate case insights and recommendations
            case_insights = self._generate_case_insights(relevant_cases, enhanced_judgment)

            # Prepare output
            state.output_data = {
                "enhanced_judgment": enhanced_judgment,
                "similar_cases_analyzed": len(relevant_cases),
                "confidence_improvement": confidence_improvement,
                "case_analysis": {
                    "total_cases_retrieved": len(similar_cases),
                    "relevant_cases_used": len(relevant_cases),
                    "case_insights": case_insights,
                    "average_similarity": self._calculate_average_similarity(relevant_cases),
                },
                "processing_metadata": {
                    "agent": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "rag_version": "v1.0.0",
                    "cases_in_database": await self._get_database_case_count()
                }
            }

            original_confidence = initial_judgment.get("confidence_score", 0.0)
            new_confidence = enhanced_judgment.get("confidence_score", 0.0)

            self.logger.info(f"RAG enhancement completed: confidence {original_confidence:.2f} → {new_confidence:.2f} "
                           f"(improvement: {confidence_improvement:.2f})")

            return state

        except Exception as e:
            self.add_error(state, f"RAG enhancement failed: {str(e)}")
            # Fall back to initial judgment on error
            return await self._fallback_to_initial_judgment(state)

    async def _retrieve_similar_cases(
        self,
        content_text: str,
        initial_judgment: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve similar cases from ChromaDB

        Args:
            content_text: Content to find similar cases for
            initial_judgment: Initial assessment results

        Returns:
            List of similar cases with metadata
        """
        try:
            # Search for similar cases
            similar_cases = await vector_store.search_similar_cases(
                query_content=content_text,
                n_results=self.max_similar_cases
            )

            # Filter by similarity threshold
            filtered_cases = [
                case for case in similar_cases
                if case.get("similarity", 0) >= self.min_similarity_threshold
            ]

            self.logger.info(f"Retrieved {len(filtered_cases)} similar cases (from {len(similar_cases)} total)")
            return filtered_cases

        except Exception as e:
            self.logger.error(f"Failed to retrieve similar cases: {e}")
            return []

    async def _evaluate_case_relevance(
        self,
        content_text: str,
        initial_judgment: Dict[str, Any],
        similar_cases: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate relevance of retrieved cases using LLM analysis

        Args:
            content_text: Original content
            initial_judgment: Initial assessment
            similar_cases: Retrieved similar cases

        Returns:
            List of relevant cases with relevance scores
        """
        try:
            if not similar_cases:
                return []

            # Prepare case summaries for evaluation
            case_summaries = []
            for i, case in enumerate(similar_cases):
                case_summary = {
                    "case_id": i,
                    "content_preview": case["content"][:500] + "..." if len(case["content"]) > 500 else case["content"],
                    "outcome": case["metadata"].get("result", "unknown"),
                    "reason": case["metadata"].get("reason", ""),
                    "similarity_score": case.get("similarity", 0.0)
                }
                case_summaries.append(case_summary)

            # Use LLM to evaluate relevance
            evaluation_prompt = CASE_RELEVANCE_EVALUATION_PROMPT.format(
                content_summary=content_text[:1000] + "..." if len(content_text) > 1000 else content_text,
                initial_assessment=json.dumps(initial_judgment, ensure_ascii=False),
                retrieved_cases=json.dumps(case_summaries, indent=2, ensure_ascii=False)
            )

            relevance_analysis = await openai_service.structured_completion(
                prompt=evaluation_prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "case_evaluations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "case_id": {"type": "integer"},
                                    "content_similarity": {"type": "number"},
                                    "context_relevance": {"type": "number"},
                                    "decision_relevance": {"type": "number"},
                                    "key_insights": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                temperature=0.1
            )

            # Filter and rank cases by relevance
            relevant_cases = []
            case_evaluations = relevance_analysis.get("case_evaluations", [])

            for eval_data in case_evaluations:
                case_id = eval_data.get("case_id", 0)
                if case_id < len(similar_cases):
                    case = similar_cases[case_id].copy()
                    case["relevance_analysis"] = eval_data

                    # Calculate overall relevance score
                    relevance_score = (
                        eval_data.get("content_similarity", 0) * 0.4 +
                        eval_data.get("context_relevance", 0) * 0.3 +
                        eval_data.get("decision_relevance", 0) * 0.3
                    )
                    case["overall_relevance"] = relevance_score

                    # Only include cases with meaningful relevance
                    if relevance_score >= 0.5:
                        relevant_cases.append(case)

            # Sort by overall relevance
            relevant_cases.sort(key=lambda x: x.get("overall_relevance", 0), reverse=True)

            self.logger.info(f"Filtered to {len(relevant_cases)} relevant cases")
            return relevant_cases[:8]  # Limit to top 8 most relevant

        except Exception as e:
            self.logger.error(f"Case relevance evaluation failed: {e}")
            # Fall back to using all cases with basic filtering
            return similar_cases[:5]

    async def _perform_enhanced_analysis(
        self,
        content_text: str,
        initial_judgment: Dict[str, Any],
        relevant_cases: List[Dict[str, Any]],
        active_rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform enhanced analysis using relevant case precedents

        Args:
            content_text: Original content
            initial_judgment: Initial assessment
            relevant_cases: Filtered relevant cases
            active_rules: Active rule set

        Returns:
            Enhanced judgment with precedent analysis
        """
        try:
            # Format similar cases for prompt
            cases_summary = self._format_cases_for_prompt(relevant_cases)
            rules_summary = self._format_rules_summary(active_rules)

            prompt = RAG_ENHANCED_JUDGMENT_PROMPT.format(
                content_text=content_text[:2000] + "..." if len(content_text) > 2000 else content_text,
                initial_judgment=json.dumps(initial_judgment, indent=2, ensure_ascii=False),
                similar_cases=cases_summary,
                rules_summary=rules_summary
            )

            enhanced_judgment_schema = {
                "type": "object",
                "properties": {
                    "enhanced_judgment": {"type": "string", "enum": ["approved", "rejected", "uncertain"]},
                    "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence_improvement": {"type": "number"},
                    "precedent_analysis": {"type": "object"},
                    "case_comparisons": {"type": "array"},
                    "contextual_factors": {"type": "array"},
                    "enhanced_reasoning": {"type": "string"},
                    "precedent_based_recommendations": {"type": "array"},
                    "uncertainty_factors": {"type": "array"},
                    "processing_metadata": {"type": "object"}
                },
                "required": ["enhanced_judgment", "confidence_score", "enhanced_reasoning"]
            }

            enhanced_judgment = await openai_service.structured_completion(
                prompt=prompt,
                schema=enhanced_judgment_schema,
                temperature=0.1
            )

            # Validate and clean the result
            validated_judgment = self._validate_enhanced_judgment(
                enhanced_judgment, initial_judgment
            )

            return validated_judgment

        except Exception as e:
            self.logger.error(f"Enhanced analysis failed: {e}")
            # Return enhanced initial judgment with error info
            return {
                "enhanced_judgment": initial_judgment.get("judgment", "uncertain"),
                "confidence_score": max(0.3, initial_judgment.get("confidence_score", 0.5)),
                "confidence_improvement": 0.0,
                "enhanced_reasoning": f"RAG analysis failed: {str(e)}",
                "precedent_analysis": {"error": "Analysis failed"},
                "processing_metadata": {"error": str(e)}
            }

    def _format_cases_for_prompt(self, cases: List[Dict[str, Any]]) -> str:
        """Format similar cases for the prompt"""
        try:
            formatted_cases = []

            for i, case in enumerate(cases):
                case_info = {
                    "case_number": i + 1,
                    "similarity": round(case.get("similarity", 0), 2),
                    "content_preview": case["content"][:400] + "..." if len(case["content"]) > 400 else case["content"],
                    "outcome": case["metadata"].get("result", "unknown"),
                    "reason": case["metadata"].get("reason", "No reason provided"),
                    "relevance_score": round(case.get("overall_relevance", 0), 2)
                }

                case_text = f"Case {i+1} (similarity: {case_info['similarity']}, relevance: {case_info['relevance_score']}):\n"
                case_text += f"Content: {case_info['content_preview']}\n"
                case_text += f"Outcome: {case_info['outcome']}\n"
                case_text += f"Reason: {case_info['reason']}\n"

                formatted_cases.append(case_text)

            return "\n---\n".join(formatted_cases)

        except Exception as e:
            self.logger.error(f"Failed to format cases for prompt: {e}")
            return "Error formatting cases for analysis"

    def _format_rules_summary(self, rules: Dict[str, Any]) -> str:
        """Format active rules summary for prompt"""
        try:
            if not rules:
                return "No active rules available"

            summary_parts = []

            # Prohibited content
            prohibited = rules.get("prohibited_content", [])
            if prohibited:
                summary_parts.append(f"Prohibited Categories: {len(prohibited)} types")

            # Sensitive keywords
            keywords = rules.get("sensitive_keywords", {})
            if keywords:
                total_keywords = sum(len(v) if isinstance(v, list) else 1 for v in keywords.values())
                summary_parts.append(f"Sensitive Keywords: {total_keywords} keywords in {len(keywords)} categories")

            # Severity levels
            severity = rules.get("severity_levels", {})
            if severity:
                summary_parts.append(f"Severity Levels: {', '.join(severity.keys())}")

            return " | ".join(summary_parts) if summary_parts else "Rules available but no summary generated"

        except Exception as e:
            self.logger.error(f"Failed to format rules summary: {e}")
            return "Error formatting rules summary"

    def _validate_enhanced_judgment(
        self,
        enhanced_judgment: Dict[str, Any],
        initial_judgment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and clean enhanced judgment result"""
        try:
            # Ensure required fields
            if "enhanced_judgment" not in enhanced_judgment:
                enhanced_judgment["enhanced_judgment"] = initial_judgment.get("judgment", "uncertain")

            if "confidence_score" not in enhanced_judgment:
                enhanced_judgment["confidence_score"] = initial_judgment.get("confidence_score", 0.5)

            # Validate confidence score
            confidence = enhanced_judgment["confidence_score"]
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                enhanced_judgment["confidence_score"] = initial_judgment.get("confidence_score", 0.5)

            # Calculate confidence improvement
            original_confidence = initial_judgment.get("confidence_score", 0.5)
            new_confidence = enhanced_judgment["confidence_score"]
            enhanced_judgment["confidence_improvement"] = new_confidence - original_confidence

            # Ensure reasoning exists
            if not enhanced_judgment.get("enhanced_reasoning"):
                enhanced_judgment["enhanced_reasoning"] = "Enhanced analysis using case precedents"

            return enhanced_judgment

        except Exception as e:
            self.logger.error(f"Enhanced judgment validation failed: {e}")
            return {
                "enhanced_judgment": initial_judgment.get("judgment", "uncertain"),
                "confidence_score": initial_judgment.get("confidence_score", 0.5),
                "confidence_improvement": 0.0,
                "enhanced_reasoning": f"Validation failed: {str(e)}"
            }

    def _calculate_confidence_improvement(
        self,
        initial_judgment: Dict[str, Any],
        enhanced_judgment: Dict[str, Any]
    ) -> float:
        """Calculate confidence improvement from RAG enhancement"""
        try:
            original_confidence = initial_judgment.get("confidence_score", 0.5)
            new_confidence = enhanced_judgment.get("confidence_score", 0.5)
            return round(new_confidence - original_confidence, 3)
        except:
            return 0.0

    def _generate_case_insights(
        self,
        relevant_cases: List[Dict[str, Any]],
        enhanced_judgment: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate insights from case analysis"""
        try:
            insights = []

            if not relevant_cases:
                return [{"insight": "No similar cases found for analysis"}]

            # Outcome distribution
            outcomes = [case["metadata"].get("result", "unknown") for case in relevant_cases]
            outcome_counts = {outcome: outcomes.count(outcome) for outcome in set(outcomes)}

            insights.append({
                "type": "outcome_distribution",
                "description": f"Similar cases outcomes: {dict(outcome_counts)}",
                "influence": "high" if len(set(outcomes)) == 1 else "medium"
            })

            # Similarity analysis
            similarities = [case.get("similarity", 0) for case in relevant_cases]
            avg_similarity = sum(similarities) / len(similarities)

            insights.append({
                "type": "similarity_analysis",
                "description": f"Average similarity: {avg_similarity:.2f}, Range: {min(similarities):.2f}-{max(similarities):.2f}",
                "influence": "high" if avg_similarity > 0.8 else "medium" if avg_similarity > 0.6 else "low"
            })

            return insights

        except Exception as e:
            self.logger.error(f"Failed to generate case insights: {e}")
            return [{"insight": "Error generating insights", "error": str(e)}]

    def _calculate_average_similarity(self, cases: List[Dict[str, Any]]) -> float:
        """Calculate average similarity of analyzed cases"""
        try:
            if not cases:
                return 0.0
            similarities = [case.get("similarity", 0) for case in cases]
            return round(sum(similarities) / len(similarities), 3)
        except:
            return 0.0

    async def _get_database_case_count(self) -> int:
        """Get total number of cases in the database"""
        try:
            stats = await vector_store.get_collection_stats()
            return stats.get("total_cases", 0)
        except:
            return 0

    async def _fallback_to_initial_judgment(self, state: AgentState) -> AgentState:
        """Fallback when RAG enhancement is not possible"""
        initial_judgment = state.input_data.get("initial_judgment", {})

        state.output_data = {
            "enhanced_judgment": initial_judgment,
            "similar_cases_analyzed": 0,
            "confidence_improvement": 0.0,
            "case_analysis": {
                "total_cases_retrieved": 0,
                "relevant_cases_used": 0,
                "fallback_reason": "No similar cases available or retrieval failed"
            },
            "processing_metadata": {
                "agent": self.agent_name,
                "timestamp": datetime.now().isoformat(),
                "fallback_mode": True
            }
        }

        return state