from typing import Dict, Any, List
import json
import re
from datetime import datetime

from .base_agent import BaseAgent, AgentState
from ..services.openai_service import openai_service
from ..config.settings import settings

RULE_EXTRACTION_PROMPT = """
You are an expert at extracting content moderation rules from policy documents.

Your task is to analyze the provided document and extract all content auditing rules in a structured JSON format.

The document contains content policies for novel/fiction platforms. You need to extract:

1. **prohibited_content**: Categories of content that are completely banned
2. **sensitive_keywords**: Specific keywords that trigger review
3. **severity_levels**: Different levels of violations and their descriptions
4. **content_guidelines**: Specific guidelines for different content types
5. **enforcement_actions**: Actions taken for different violation types

Output Format:
```json
{
  "version": "extracted_from_document",
  "last_updated": "2025-01-15",
  "prohibited_content": [
    {
      "category": "violence",
      "description": "Detailed violent descriptions",
      "examples": ["specific examples from document"],
      "severity": "high"
    }
  ],
  "sensitive_keywords": {
    "violence": ["血腥", "暴力", "杀害"],
    "adult_content": ["色情", "性行为"],
    "political": ["政治敏感词"]
  },
  "severity_levels": {
    "minor": {
      "description": "轻微违规描述",
      "action": "修改建议",
      "examples": []
    },
    "major": {
      "description": "严重违规描述",
      "action": "内容拒绝",
      "examples": []
    },
    "critical": {
      "description": "极严重违规描述",
      "action": "账号处罚",
      "examples": []
    }
  },
  "content_guidelines": {
    "romance": {
      "allowed": ["description of allowed romance content"],
      "prohibited": ["description of prohibited romance content"]
    },
    "action": {
      "allowed": ["description of allowed action content"],
      "prohibited": ["description of prohibited action content"]
    }
  },
  "enforcement_actions": {
    "minor_violation": "修改要求",
    "major_violation": "内容下架",
    "critical_violation": "账号封禁"
  }
}
```

Important Instructions:
1. Extract ALL rules mentioned in the document, be comprehensive
2. Preserve original Chinese terms where they appear
3. Include specific examples when provided in the document
4. Categorize rules by content type (violence, adult content, politics, etc.)
5. Identify severity levels and corresponding actions
6. If information is unclear or missing, mark as "not_specified"
7. Maintain the exact JSON structure shown above

Document to analyze:
{document_content}

Extract the rules now:
"""

RULE_REFINEMENT_PROMPT = """
You are reviewing extracted content moderation rules for completeness and accuracy.

Original Document Excerpt:
{original_content}

Previously Extracted Rules:
{extracted_rules}

Please review the extracted rules and improve them by:

1. **Completeness Check**: Are there any rules in the original document that were missed?
2. **Accuracy Check**: Are the extracted rules accurately representing the original policies?
3. **Structure Check**: Is the JSON structure consistent and well-organized?
4. **Detail Level**: Are there sufficient details and examples?

Provide an improved version of the rules in the same JSON format. If the original extraction was accurate and complete, return it unchanged.

Focus on these areas:
- Missing rule categories
- Incomplete keyword lists
- Unclear severity definitions
- Missing enforcement actions
- Structural inconsistencies

Improved Rules:
"""


class RuleExtractorAgent(BaseAgent):
    """Agent1: Extracts rules from policy documents"""

    def __init__(self):
        super().__init__("RuleExtractor")
        self.max_retries = settings.max_retry_attempts

    async def process(self, state: AgentState) -> AgentState:
        """
        Extract rules from document content

        Expected input_data:
        - document_content: Raw text content of policy document
        - document_type: "pdf", "docx", "txt"
        - source_filename: Original filename

        Returns:
        - extracted_rules: Structured rule set in JSON format
        - extraction_metadata: Processing information
        """
        document_content = state.input_data.get("document_content", "")
        document_type = state.input_data.get("document_type", "unknown")
        source_filename = state.input_data.get("source_filename", "unknown")

        if not document_content.strip():
            self.add_error(state, "Document content is empty")
            return state

        try:
            # Step 1: Initial rule extraction
            self.logger.info("Starting initial rule extraction...")

            prompt = RULE_EXTRACTION_PROMPT.format(
                document_content=document_content[:8000]  # Limit content size
            )

            extracted_rules_raw = await openai_service.structured_completion(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "prohibited_content": {"type": "array"},
                        "sensitive_keywords": {"type": "object"},
                        "severity_levels": {"type": "object"},
                        "content_guidelines": {"type": "object"},
                        "enforcement_actions": {"type": "object"}
                    }
                },
                temperature=0.1
            )

            # Step 2: Refinement pass
            self.logger.info("Performing rule refinement pass...")

            refinement_prompt = RULE_REFINEMENT_PROMPT.format(
                original_content=document_content[:4000],  # Shorter excerpt for refinement
                extracted_rules=json.dumps(extracted_rules_raw, indent=2, ensure_ascii=False)
            )

            refined_rules = await openai_service.structured_completion(
                prompt=refinement_prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "prohibited_content": {"type": "array"},
                        "sensitive_keywords": {"type": "object"},
                        "severity_levels": {"type": "object"},
                        "content_guidelines": {"type": "object"},
                        "enforcement_actions": {"type": "object"}
                    }
                },
                temperature=0.1
            )

            # Step 3: Post-processing and validation
            validated_rules = self._validate_extracted_rules(refined_rules)

            # Prepare output
            state.output_data = {
                "extracted_rules": validated_rules,
                "extraction_metadata": {
                    "source_filename": source_filename,
                    "document_type": document_type,
                    "extraction_timestamp": datetime.now().isoformat(),
                    "content_length": len(document_content),
                    "rules_count": self._count_rules(validated_rules),
                    "agent_version": "1.0.0"
                }
            }

            self.logger.info(f"Successfully extracted {self._count_rules(validated_rules)} rules from document")
            return state

        except Exception as e:
            self.add_error(state, f"Rule extraction failed: {str(e)}")
            return state

    def _validate_extracted_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean extracted rules

        Args:
            rules: Raw extracted rules

        Returns:
            Validated and cleaned rules
        """
        try:
            # Ensure required fields exist
            required_fields = [
                "version", "prohibited_content", "sensitive_keywords",
                "severity_levels", "content_guidelines", "enforcement_actions"
            ]

            for field in required_fields:
                if field not in rules:
                    rules[field] = {} if field in ["sensitive_keywords", "severity_levels", "content_guidelines", "enforcement_actions"] else []

            # Validate version format
            if not rules.get("version") or rules["version"] == "extracted_from_document":
                rules["version"] = f"extracted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Add metadata
            rules["extraction_metadata"] = {
                "extracted_at": datetime.now().isoformat(),
                "extractor_agent": self.agent_name,
                "validation_passed": True
            }

            return rules

        except Exception as e:
            self.logger.error(f"Rule validation failed: {e}")
            # Return minimal structure if validation fails
            return {
                "version": f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "prohibited_content": [],
                "sensitive_keywords": {},
                "severity_levels": {},
                "content_guidelines": {},
                "enforcement_actions": {},
                "extraction_metadata": {
                    "extracted_at": datetime.now().isoformat(),
                    "extractor_agent": self.agent_name,
                    "validation_passed": False,
                    "validation_error": str(e)
                }
            }

    def _count_rules(self, rules: Dict[str, Any]) -> int:
        """Count total number of rules extracted"""
        try:
            count = 0
            count += len(rules.get("prohibited_content", []))
            count += sum(len(v) if isinstance(v, list) else 1 for v in rules.get("sensitive_keywords", {}).values())
            count += len(rules.get("severity_levels", {}))
            count += len(rules.get("content_guidelines", {}))
            count += len(rules.get("enforcement_actions", {}))
            return count
        except:
            return 0