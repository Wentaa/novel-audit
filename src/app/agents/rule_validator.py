from typing import Dict, Any, List, Tuple
import json
from datetime import datetime

from .base_agent import BaseAgent, AgentState
from ..services.openai_service import openai_service
from ..config.settings import settings

RULE_VALIDATION_PROMPT = """
You are an expert content moderation policy analyst. Your task is to thoroughly validate extracted rules against the original document.

Original Document:
{original_document}

Extracted Rules:
{extracted_rules}

Please perform a comprehensive validation by checking:

1. **Completeness Analysis**:
   - Are there any content categories mentioned in the original document that are missing from the extracted rules?
   - Are all severity levels from the document captured?
   - Are enforcement actions properly mapped?

2. **Accuracy Analysis**:
   - Do the extracted rules accurately reflect the original policy meanings?
   - Are there any misinterpretations or distortions?
   - Are the examples and descriptions faithful to the source?

3. **Consistency Analysis**:
   - Are severity levels consistently applied across different rule categories?
   - Do enforcement actions align with severity levels?
   - Is the terminology consistent throughout?

4. **Structure Analysis**:
   - Is the JSON structure well-organized and logical?
   - Are categories properly grouped?
   - Is the data format consistent?

5. **Quality Analysis**:
   - Are sensitive keyword lists comprehensive?
   - Are rule descriptions clear and actionable?
   - Are examples helpful and appropriate?

Return your analysis in this JSON format:
```json
{
  "validation_result": "pass|fail|needs_improvement",
  "confidence_score": 0.85,
  "issues_found": [
    {
      "category": "completeness|accuracy|consistency|structure|quality",
      "severity": "critical|major|minor",
      "description": "Detailed description of the issue",
      "location": "specific field or section with the issue",
      "suggested_fix": "How to fix this issue"
    }
  ],
  "missing_elements": [
    {
      "type": "content_category|keyword|severity_level|enforcement_action",
      "description": "What is missing",
      "source_reference": "Where it appears in original document"
    }
  ],
  "accuracy_assessment": {
    "overall_accuracy": 0.90,
    "content_categories_accuracy": 0.95,
    "keywords_accuracy": 0.85,
    "severity_levels_accuracy": 0.90,
    "enforcement_actions_accuracy": 0.88
  },
  "recommendations": [
    "Specific actionable recommendations for improvement"
  ],
  "validation_metadata": {
    "validator_agent": "RuleValidator",
    "validation_timestamp": "2025-01-15T10:30:00Z",
    "original_document_length": 5000,
    "extracted_rules_count": 45
  }
}
```

Provide detailed, actionable feedback to improve the rule extraction quality.
"""

RULE_CORRECTION_PROMPT = """
You are tasked with correcting and improving extracted rules based on validation feedback.

Original Document:
{original_document}

Current Extracted Rules:
{current_rules}

Validation Issues to Fix:
{validation_issues}

Please provide corrected rules that address all the identified issues. Make the following improvements:

1. Add any missing content categories or rules
2. Fix accuracy issues and misinterpretations
3. Resolve consistency problems
4. Improve structure and organization
5. Enhance rule descriptions and examples

Return the corrected rules in the standard JSON format:
```json
{
  "version": "corrected_v1.0",
  "prohibited_content": [...],
  "sensitive_keywords": {...},
  "severity_levels": {...},
  "content_guidelines": {...},
  "enforcement_actions": {...},
  "correction_metadata": {
    "corrected_at": "2025-01-15T10:30:00Z",
    "issues_addressed": ["list of issues fixed"],
    "validator_agent": "RuleValidator"
  }
}
```

Focus on making the rules comprehensive, accurate, and actionable for content moderation.
"""


class RuleValidatorAgent(BaseAgent):
    """Agent2: Validates extracted rules for quality and completeness"""

    def __init__(self):
        super().__init__("RuleValidator")
        self.validation_threshold = 0.8  # Minimum confidence score to pass validation

    async def process(self, state: AgentState) -> AgentState:
        """
        Validate extracted rules against original document

        Expected input_data:
        - original_document: Raw document content
        - extracted_rules: Rules from Agent1
        - source_metadata: Document metadata

        Returns:
        - validation_result: Comprehensive validation analysis
        - corrected_rules: Improved rules if corrections needed
        - final_recommendation: pass/fail/needs_review
        """
        original_document = state.input_data.get("original_document", "")
        extracted_rules = state.input_data.get("extracted_rules", {})
        source_metadata = state.input_data.get("source_metadata", {})

        if not original_document or not extracted_rules:
            self.add_error(state, "Missing required input: original_document or extracted_rules")
            return state

        try:
            # Step 1: Perform validation analysis
            self.logger.info("Starting rule validation analysis...")

            validation_result = await self._perform_validation_analysis(
                original_document, extracted_rules
            )

            # Step 2: Determine if corrections are needed
            needs_correction = (
                validation_result.get("validation_result") != "pass" or
                validation_result.get("confidence_score", 0) < self.validation_threshold
            )

            corrected_rules = None
            if needs_correction:
                self.logger.info("Applying corrections to extracted rules...")
                corrected_rules = await self._apply_corrections(
                    original_document, extracted_rules, validation_result
                )

            # Step 3: Generate final recommendation
            final_recommendation = self._generate_final_recommendation(
                validation_result, corrected_rules
            )

            # Prepare output
            state.output_data = {
                "validation_result": validation_result,
                "corrected_rules": corrected_rules,
                "final_recommendation": final_recommendation,
                "validation_metadata": {
                    "validator_agent": self.agent_name,
                    "validation_timestamp": datetime.now().isoformat(),
                    "source_metadata": source_metadata,
                    "corrections_applied": corrected_rules is not None
                }
            }

            confidence = validation_result.get("confidence_score", 0)
            self.logger.info(f"Validation completed with confidence score: {confidence}")

            return state

        except Exception as e:
            self.add_error(state, f"Rule validation failed: {str(e)}")
            return state

    async def _perform_validation_analysis(
        self,
        original_document: str,
        extracted_rules: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform comprehensive validation analysis

        Args:
            original_document: Original policy document
            extracted_rules: Rules extracted by Agent1

        Returns:
            Detailed validation analysis
        """
        try:
            prompt = RULE_VALIDATION_PROMPT.format(
                original_document=original_document[:6000],  # Limit size
                extracted_rules=json.dumps(extracted_rules, indent=2, ensure_ascii=False)
            )

            validation_schema = {
                "type": "object",
                "properties": {
                    "validation_result": {"type": "string", "enum": ["pass", "fail", "needs_improvement"]},
                    "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "issues_found": {"type": "array"},
                    "missing_elements": {"type": "array"},
                    "accuracy_assessment": {"type": "object"},
                    "recommendations": {"type": "array"},
                    "validation_metadata": {"type": "object"}
                }
            }

            validation_result = await openai_service.structured_completion(
                prompt=prompt,
                schema=validation_schema,
                temperature=0.1
            )

            return validation_result

        except Exception as e:
            self.logger.error(f"Validation analysis failed: {e}")
            # Return fallback validation result
            return {
                "validation_result": "fail",
                "confidence_score": 0.0,
                "issues_found": [{"description": f"Validation failed: {str(e)}"}],
                "missing_elements": [],
                "accuracy_assessment": {"overall_accuracy": 0.0},
                "recommendations": ["Manual review required due to validation failure"],
                "validation_metadata": {"error": str(e)}
            }

    async def _apply_corrections(
        self,
        original_document: str,
        current_rules: Dict[str, Any],
        validation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply corrections to rules based on validation feedback

        Args:
            original_document: Original policy document
            current_rules: Current extracted rules
            validation_result: Validation analysis results

        Returns:
            Corrected rules
        """
        try:
            # Format validation issues for the correction prompt
            issues_summary = []
            for issue in validation_result.get("issues_found", []):
                issues_summary.append(
                    f"- {issue.get('severity', 'unknown')}: {issue.get('description', 'No description')}"
                )

            prompt = RULE_CORRECTION_PROMPT.format(
                original_document=original_document[:5000],
                current_rules=json.dumps(current_rules, indent=2, ensure_ascii=False),
                validation_issues="\n".join(issues_summary)
            )

            correction_schema = {
                "type": "object",
                "properties": {
                    "version": {"type": "string"},
                    "prohibited_content": {"type": "array"},
                    "sensitive_keywords": {"type": "object"},
                    "severity_levels": {"type": "object"},
                    "content_guidelines": {"type": "object"},
                    "enforcement_actions": {"type": "object"},
                    "correction_metadata": {"type": "object"}
                }
            }

            corrected_rules = await openai_service.structured_completion(
                prompt=prompt,
                schema=correction_schema,
                temperature=0.1
            )

            return corrected_rules

        except Exception as e:
            self.logger.error(f"Rule correction failed: {e}")
            # Return original rules with error metadata
            current_rules["correction_error"] = str(e)
            return current_rules

    def _generate_final_recommendation(
        self,
        validation_result: Dict[str, Any],
        corrected_rules: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate final recommendation for rule approval

        Args:
            validation_result: Validation analysis results
            corrected_rules: Corrected rules if corrections were applied

        Returns:
            Final recommendation with action items
        """
        confidence = validation_result.get("confidence_score", 0)
        validation_status = validation_result.get("validation_result", "fail")
        critical_issues = [
            issue for issue in validation_result.get("issues_found", [])
            if issue.get("severity") == "critical"
        ]

        if confidence >= 0.9 and validation_status == "pass" and not critical_issues:
            recommendation = "auto_approve"
            message = "Rules passed validation with high confidence. Ready for production use."
        elif confidence >= self.validation_threshold and not critical_issues:
            recommendation = "approve_with_review"
            message = "Rules passed validation. Minor improvements may be beneficial but not required."
        elif corrected_rules and confidence >= 0.7:
            recommendation = "approve_corrected"
            message = "Rules required corrections but are now acceptable. Review recommended."
        else:
            recommendation = "manual_review_required"
            message = "Rules require manual review due to low confidence or critical issues."

        return {
            "recommendation": recommendation,
            "message": message,
            "confidence_score": confidence,
            "critical_issues_count": len(critical_issues),
            "corrections_applied": corrected_rules is not None,
            "next_steps": self._get_next_steps(recommendation),
            "timestamp": datetime.now().isoformat()
        }

    def _get_next_steps(self, recommendation: str) -> List[str]:
        """Get recommended next steps based on recommendation"""
        next_steps_map = {
            "auto_approve": [
                "Deploy rules to production",
                "Monitor initial performance",
                "Set up automated metrics tracking"
            ],
            "approve_with_review": [
                "Conduct brief human review",
                "Deploy to staging environment",
                "Run validation tests",
                "Deploy to production with monitoring"
            ],
            "approve_corrected": [
                "Review applied corrections",
                "Test corrected rules in staging",
                "Validate improvements",
                "Deploy with close monitoring"
            ],
            "manual_review_required": [
                "Conduct thorough human review",
                "Address critical issues manually",
                "Consider re-extraction with different approach",
                "Test extensively before deployment"
            ]
        }
        return next_steps_map.get(recommendation, ["Review recommendation and proceed accordingly"])