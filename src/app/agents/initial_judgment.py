from typing import Dict, Any, List, Tuple
import json
import re
from datetime import datetime
import hashlib

from .base_agent import BaseAgent, AgentState
from ..services.openai_service import openai_service
from ..services.rule_management_service import rule_management_service
from ..config.settings import settings

INITIAL_JUDGMENT_PROMPT = """
You are a content auditing specialist performing initial assessment of novel chapter content.

Your task is to quickly evaluate the content against the provided rules and determine if it violates any content policies.

ACTIVE RULES:
{rules_content}

CONTENT TO AUDIT:
{content_text}

ANALYSIS INSTRUCTIONS:
1. **Rule Matching**: Check the content against all prohibited content categories
2. **Keyword Detection**: Scan for sensitive keywords and evaluate their context
3. **Severity Assessment**: If violations are found, determine the severity level
4. **Confidence Evaluation**: Assess how confident you are in your judgment

Output your assessment in this JSON format:
```json
{
  "judgment": "approved|rejected|uncertain",
  "confidence_score": 0.85,
  "violation_details": [
    {
      "category": "violence|adult_content|political|illegal|other",
      "severity": "minor|major|critical",
      "description": "Specific description of the violation",
      "evidence": "Exact text that violates the rule",
      "rule_reference": "Which rule was violated"
    }
  ],
  "keyword_matches": [
    {
      "keyword": "detected keyword",
      "category": "keyword category",
      "context": "surrounding context",
      "risk_level": "low|medium|high"
    }
  ],
  "content_analysis": {
    "genre_detected": "romance|action|fantasy|historical|modern|other",
    "content_length": 1500,
    "tone": "positive|neutral|negative",
    "target_audience": "general|mature|adult"
  },
  "reasoning": "Clear explanation of the judgment decision",
  "recommended_action": "approve|request_modification|reject|escalate_review",
  "processing_metadata": {
    "agent": "InitialJudgmentAgent",
    "timestamp": "2025-01-15T10:30:00Z",
    "rules_version": "v1.0.0"
  }
}
```

JUDGMENT GUIDELINES:
- **Approved**: Content clearly complies with all rules, high confidence
- **Rejected**: Content clearly violates rules, high confidence
- **Uncertain**: Borderline cases, need additional review

CONFIDENCE SCORING:
- 0.9-1.0: Very confident in judgment
- 0.7-0.9: Confident but some minor uncertainty
- 0.5-0.7: Moderate confidence, some ambiguity
- 0.3-0.5: Low confidence, significant uncertainty
- 0.0-0.3: Very uncertain, needs human review

Be thorough but efficient. Focus on clear rule violations first, then contextual analysis.
"""

CONTENT_PREPROCESSING_PROMPT = """
Analyze this content and extract key information for auditing:

Content: {content}

Extract:
1. Main themes and subjects
2. Potential sensitive elements
3. Genre classification
4. Content tone and style
5. Any obvious red flags

Provide a structured summary for efficient rule matching.
"""


class InitialJudgmentAgent(BaseAgent):
    """Agent3: Performs initial rule-based content assessment"""

    def __init__(self):
        super().__init__("InitialJudgment")
        self.confidence_threshold_high = settings.confidence_threshold_high
        self.confidence_threshold_low = settings.confidence_threshold_low

    async def process(self, state: AgentState) -> AgentState:
        """
        Perform initial judgment on content

        Expected input_data:
        - content_text: Chapter content to audit
        - metadata: Content metadata (title, author, etc.)

        Returns:
        - judgment_result: Initial assessment
        - confidence_score: Confidence in judgment
        - violation_details: Any detected violations
        - routing_recommendation: Next processing step
        """
        content_text = state.input_data.get("content_text", "")
        content_metadata = state.input_data.get("metadata", {})

        if not content_text.strip():
            self.add_error(state, "Content text is empty")
            return state

        try:
            # Step 1: Load active rules
            active_rules = await rule_management_service.get_active_rules()
            if not active_rules:
                self.add_error(state, "No active rules found for content auditing")
                return state

            self.logger.info(f"Starting initial judgment for content (length: {len(content_text)})")

            # Step 2: Preprocess content if it's very long
            processed_content = await self._preprocess_content(content_text)

            # Step 3: Perform initial judgment
            judgment_result = await self._perform_judgment(processed_content, active_rules)

            # Step 4: Calculate confidence and routing recommendation
            routing_recommendation = self._determine_routing(judgment_result)

            # Step 5: Generate content hash for tracking
            content_hash = self._generate_content_hash(content_text)

            # Prepare output
            state.output_data = {
                "judgment_result": judgment_result,
                "confidence_score": judgment_result.get("confidence_score", 0.0),
                "routing_recommendation": routing_recommendation,
                "content_hash": content_hash,
                "processing_metadata": {
                    "agent": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "content_length": len(content_text),
                    "rules_version": active_rules.get("version", "unknown"),
                    "processing_time_ms": "calculated_in_production"
                }
            }

            confidence = judgment_result.get("confidence_score", 0.0)
            judgment = judgment_result.get("judgment", "uncertain")
            self.logger.info(f"Initial judgment completed: {judgment} (confidence: {confidence:.2f})")

            return state

        except Exception as e:
            self.add_error(state, f"Initial judgment failed: {str(e)}")
            return state

    async def _preprocess_content(self, content_text: str) -> str:
        """
        Preprocess content for efficient analysis

        Args:
            content_text: Original content

        Returns:
            Processed content for analysis
        """
        try:
            # If content is too long, perform intelligent truncation
            max_content_length = 6000  # Token limit consideration

            if len(content_text) <= max_content_length:
                return content_text

            # For long content, extract key sections
            self.logger.info("Content is long, performing intelligent preprocessing...")

            preprocessing_prompt = CONTENT_PREPROCESSING_PROMPT.format(
                content=content_text[:max_content_length]
            )

            content_summary = await openai_service.chat_completion(
                messages=[{"role": "user", "content": preprocessing_prompt}],
                temperature=0.1,
                max_tokens=1000
            )

            # Combine original beginning and summary
            processed = f"[CONTENT BEGINNING]\n{content_text[:2000]}\n\n[CONTENT ANALYSIS]\n{content_summary}\n\n[CONTENT END]\n{content_text[-1000:]}"

            return processed

        except Exception as e:
            self.logger.warning(f"Content preprocessing failed: {e}, using truncated content")
            return content_text[:max_content_length]

    async def _perform_judgment(self, content_text: str, active_rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform the actual judgment analysis

        Args:
            content_text: Content to analyze
            active_rules: Active rule set

        Returns:
            Judgment result dictionary
        """
        try:
            # Format rules for the prompt
            rules_summary = self._format_rules_for_prompt(active_rules)

            prompt = INITIAL_JUDGMENT_PROMPT.format(
                rules_content=rules_summary,
                content_text=content_text
            )

            # Define expected response schema
            judgment_schema = {
                "type": "object",
                "properties": {
                    "judgment": {"type": "string", "enum": ["approved", "rejected", "uncertain"]},
                    "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "violation_details": {"type": "array"},
                    "keyword_matches": {"type": "array"},
                    "content_analysis": {"type": "object"},
                    "reasoning": {"type": "string"},
                    "recommended_action": {"type": "string"},
                    "processing_metadata": {"type": "object"}
                },
                "required": ["judgment", "confidence_score", "reasoning"]
            }

            judgment_result = await openai_service.structured_completion(
                prompt=prompt,
                schema=judgment_schema,
                temperature=0.1
            )

            # Post-process and validate result
            validated_result = self._validate_judgment_result(judgment_result)

            return validated_result

        except Exception as e:
            self.logger.error(f"Judgment analysis failed: {e}")
            # Return fallback judgment
            return {
                "judgment": "uncertain",
                "confidence_score": 0.0,
                "violation_details": [],
                "keyword_matches": [],
                "content_analysis": {},
                "reasoning": f"Analysis failed due to error: {str(e)}",
                "recommended_action": "escalate_review",
                "processing_metadata": {
                    "agent": self.agent_name,
                    "error": str(e)
                }
            }

    def _format_rules_for_prompt(self, rules: Dict[str, Any]) -> str:
        """
        Format rules into a concise string for the prompt

        Args:
            rules: Rule dictionary

        Returns:
            Formatted rule string
        """
        try:
            formatted_parts = []

            # Prohibited content
            if "prohibited_content" in rules:
                formatted_parts.append("PROHIBITED CONTENT:")
                for item in rules["prohibited_content"]:
                    if isinstance(item, dict):
                        category = item.get("category", "unknown")
                        description = item.get("description", "")
                        severity = item.get("severity", "major")
                        formatted_parts.append(f"- {category}: {description} (Severity: {severity})")

            # Sensitive keywords
            if "sensitive_keywords" in rules:
                formatted_parts.append("\nSENSITIVE KEYWORDS:")
                for category, keywords in rules["sensitive_keywords"].items():
                    if isinstance(keywords, list):
                        keyword_str = ", ".join(keywords[:10])  # Limit for prompt size
                        formatted_parts.append(f"- {category}: {keyword_str}")

            # Severity levels
            if "severity_levels" in rules:
                formatted_parts.append("\nSEVERITY LEVELS:")
                for level, details in rules["severity_levels"].items():
                    if isinstance(details, dict):
                        description = details.get("description", "")
                        action = details.get("action", "")
                        formatted_parts.append(f"- {level}: {description} → {action}")

            return "\n".join(formatted_parts)

        except Exception as e:
            self.logger.error(f"Failed to format rules: {e}")
            return "Rules formatting error - proceed with caution"

    def _validate_judgment_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean judgment result

        Args:
            result: Raw judgment result

        Returns:
            Validated judgment result
        """
        try:
            # Ensure required fields
            if "judgment" not in result:
                result["judgment"] = "uncertain"

            if "confidence_score" not in result:
                result["confidence_score"] = 0.5

            # Validate judgment value
            valid_judgments = ["approved", "rejected", "uncertain"]
            if result["judgment"] not in valid_judgments:
                result["judgment"] = "uncertain"

            # Validate confidence score
            confidence = result["confidence_score"]
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                result["confidence_score"] = 0.5

            # Ensure arrays exist
            if "violation_details" not in result:
                result["violation_details"] = []

            if "keyword_matches" not in result:
                result["keyword_matches"] = []

            # Add default reasoning if missing
            if not result.get("reasoning"):
                result["reasoning"] = f"Content assessment: {result['judgment']}"

            return result

        except Exception as e:
            self.logger.error(f"Judgment result validation failed: {e}")
            return {
                "judgment": "uncertain",
                "confidence_score": 0.0,
                "violation_details": [],
                "keyword_matches": [],
                "reasoning": "Validation error occurred",
                "recommended_action": "escalate_review"
            }

    def _determine_routing(self, judgment_result: Dict[str, Any]) -> Dict[str, str]:
        """
        Determine next processing step based on judgment and confidence

        Args:
            judgment_result: Initial judgment result

        Returns:
            Routing recommendation
        """
        judgment = judgment_result.get("judgment", "uncertain")
        confidence = judgment_result.get("confidence_score", 0.0)
        violations = judgment_result.get("violation_details", [])

        # High confidence cases - can be resolved immediately
        if confidence >= self.confidence_threshold_high:
            if judgment == "approved":
                return {
                    "next_step": "finalize_approved",
                    "reason": "High confidence approval",
                    "requires_further_review": False
                }
            elif judgment == "rejected":
                return {
                    "next_step": "finalize_rejected",
                    "reason": "High confidence rejection",
                    "requires_further_review": False
                }

        # Low confidence or uncertain cases - need additional processing
        if confidence <= self.confidence_threshold_low or judgment == "uncertain":
            return {
                "next_step": "escalate_to_rag",
                "reason": "Low confidence or uncertain judgment",
                "requires_further_review": True
            }

        # Medium confidence - check for critical violations
        critical_violations = [v for v in violations if v.get("severity") == "critical"]
        if critical_violations:
            return {
                "next_step": "escalate_to_rag",
                "reason": "Critical violations detected",
                "requires_further_review": True
            }

        # Medium confidence without critical violations
        return {
            "next_step": "escalate_to_rag",
            "reason": "Medium confidence requires additional review",
            "requires_further_review": True
        }

    def _generate_content_hash(self, content_text: str) -> str:
        """
        Generate hash for content tracking

        Args:
            content_text: Content to hash

        Returns:
            SHA-256 hash of content
        """
        return hashlib.sha256(content_text.encode('utf-8')).hexdigest()

    async def quick_keyword_scan(self, content_text: str) -> Dict[str, Any]:
        """
        Perform quick keyword-based scanning without full LLM analysis
        Useful for pre-filtering or fast checks

        Args:
            content_text: Content to scan

        Returns:
            Quick scan results
        """
        try:
            active_rules = await rule_management_service.get_active_rules()
            if not active_rules:
                return {"scan_result": "no_rules", "keywords_found": []}

            keywords_found = []
            sensitive_keywords = active_rules.get("sensitive_keywords", {})

            for category, keyword_list in sensitive_keywords.items():
                if isinstance(keyword_list, list):
                    for keyword in keyword_list:
                        if keyword in content_text:
                            keywords_found.append({
                                "keyword": keyword,
                                "category": category,
                                "count": content_text.count(keyword)
                            })

            risk_level = "high" if len(keywords_found) > 5 else "medium" if len(keywords_found) > 2 else "low"

            return {
                "scan_result": "completed",
                "keywords_found": keywords_found,
                "total_matches": len(keywords_found),
                "risk_level": risk_level,
                "requires_full_analysis": len(keywords_found) > 0
            }

        except Exception as e:
            self.logger.error(f"Quick keyword scan failed: {e}")
            return {"scan_result": "error", "error": str(e)}