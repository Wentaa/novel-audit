from typing import Dict, Any, List, Optional, Tuple
import json
import logging
from datetime import datetime
from pathlib import Path

from ..storage.database import db_service, RuleVersion
from ..config.settings import settings

logger = logging.getLogger(__name__)


class RuleManagementService:
    """Service for managing rule versions and human review process"""

    def __init__(self):
        self.rules_cache = {}  # Simple in-memory cache for active rules
        self.cache_expiry = None

    async def get_active_rules(self) -> Optional[Dict[str, Any]]:
        """
        Get currently active rules with caching

        Returns:
            Active rules or None if no active version exists
        """
        try:
            # Check cache first
            if self._is_cache_valid():
                return self.rules_cache

            # Load from database
            active_version = db_service.get_active_rule_version()
            if not active_version:
                return None

            # Update cache
            self.rules_cache = active_version.rules_content
            self.cache_expiry = datetime.now()

            logger.info(f"Loaded active rules version: {active_version.version}")
            return self.rules_cache

        except Exception as e:
            logger.error(f"Failed to get active rules: {e}")
            return None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (simple time-based check)"""
        if not self.rules_cache or not self.cache_expiry:
            return False

        # Cache valid for 5 minutes
        cache_duration = (datetime.now() - self.cache_expiry).total_seconds()
        return cache_duration < 300

    def invalidate_cache(self):
        """Invalidate rules cache"""
        self.rules_cache = {}
        self.cache_expiry = None
        logger.info("Rules cache invalidated")

    async def create_sample_rules(self) -> int:
        """
        Create sample rules for testing and development

        Returns:
            Created rule version ID
        """
        try:
            sample_rules = {
                "version": "sample_v1.0",
                "last_updated": datetime.now().isoformat(),
                "prohibited_content": [
                    {
                        "category": "violence",
                        "description": "Detailed violent descriptions that may cause discomfort",
                        "examples": ["血腥场面", "暴力描述", "酷刑细节"],
                        "severity": "major"
                    },
                    {
                        "category": "adult_content",
                        "description": "Sexual content not suitable for general audiences",
                        "examples": ["性行为描述", "露骨内容"],
                        "severity": "critical"
                    },
                    {
                        "category": "political_sensitive",
                        "description": "Content that may be politically sensitive",
                        "examples": ["政治敏感话题", "争议性政治观点"],
                        "severity": "critical"
                    }
                ],
                "sensitive_keywords": {
                    "violence": ["血腥", "暴力", "杀害", "酷刑", "屠杀"],
                    "adult_content": ["色情", "性行为", "裸体", "成人内容"],
                    "political": ["政治", "政府", "领导人", "政党"],
                    "illegal": ["毒品", "走私", "洗钱", "诈骗"]
                },
                "severity_levels": {
                    "minor": {
                        "description": "轻微违规，需要作者修改",
                        "action": "request_modification",
                        "examples": ["轻微的暴力暗示", "模糊的成人内容暗示"]
                    },
                    "major": {
                        "description": "严重违规，内容需要拒绝",
                        "action": "reject_content",
                        "examples": ["详细的暴力描述", "明确的政治立场"]
                    },
                    "critical": {
                        "description": "极严重违规，可能需要账号处罚",
                        "action": "reject_and_flag",
                        "examples": ["极端暴力内容", "明显的色情描述", "危险政治言论"]
                    }
                },
                "content_guidelines": {
                    "romance": {
                        "allowed": ["情感描述", "浪漫情节", "适度的亲密描述"],
                        "prohibited": ["露骨的性描述", "过度详细的身体描述"]
                    },
                    "action": {
                        "allowed": ["动作场面", "战斗描述", "冒险情节"],
                        "prohibited": ["过度血腥", "残忍的酷刑", "极端暴力"]
                    },
                    "fantasy": {
                        "allowed": ["魔法设定", "奇幻世界观", "超自然元素"],
                        "prohibited": ["邪恶崇拜", "极端黑暗内容"]
                    }
                },
                "enforcement_actions": {
                    "minor_violation": "修改建议",
                    "major_violation": "内容下架",
                    "critical_violation": "账号警告或封禁"
                },
                "extraction_metadata": {
                    "extracted_at": datetime.now().isoformat(),
                    "extractor_agent": "SampleDataGenerator",
                    "validation_passed": True,
                    "source": "manually_created_sample"
                }
            }

            # Create rule version
            rule_version = db_service.create_rule_version(
                version="sample_v1.0",
                rules_content=sample_rules,
                source_document="sample_rules.json",
                extracted_by="RuleManagementService",
                validated_by="manual_creation"
            )

            # Invalidate cache since we have new active rules
            self.invalidate_cache()

            logger.info(f"Created sample rule version with ID: {rule_version.id}")
            return rule_version.id

        except Exception as e:
            logger.error(f"Failed to create sample rules: {e}")
            raise

    async def export_rules(self, rule_version_id: int, format: str = "json") -> Tuple[str, str]:
        """
        Export rule version to file

        Args:
            rule_version_id: ID of rule version to export
            format: Export format ("json", "yaml")

        Returns:
            Tuple of (filename, content)
        """
        try:
            with db_service.session_factory() as db:
                version = db.query(RuleVersion).filter(RuleVersion.id == rule_version_id).first()
                if not version:
                    raise ValueError(f"Rule version {rule_version_id} not found")

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                if format.lower() == "json":
                    filename = f"rules_{version.version}_{timestamp}.json"
                    content = json.dumps(version.rules_content, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"Unsupported export format: {format}")

                return filename, content

        except Exception as e:
            logger.error(f"Rules export failed: {e}")
            raise

    async def import_rules_from_json(self, rules_content: str, source_info: Dict[str, str]) -> int:
        """
        Import rules from JSON content

        Args:
            rules_content: JSON string containing rules
            source_info: Information about the source

        Returns:
            Created rule version ID
        """
        try:
            # Parse and validate JSON
            rules_dict = json.loads(rules_content)

            # Basic validation
            required_fields = ["prohibited_content", "sensitive_keywords", "severity_levels"]
            for field in required_fields:
                if field not in rules_dict:
                    raise ValueError(f"Missing required field: {field}")

            # Create version name
            version_name = f"imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Create rule version (inactive by default)
            rule_version = db_service.create_rule_version(
                version=version_name,
                rules_content=rules_dict,
                source_document=source_info.get("filename", "imported.json"),
                extracted_by=source_info.get("imported_by", "RuleManagementService"),
                validated_by=None  # Will need human validation
            )

            # Set as inactive since imported rules need validation
            with db_service.session_factory() as db:
                rule_version.is_active = False
                db.commit()

            logger.info(f"Imported rules as version ID: {rule_version.id}")
            return rule_version.id

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in imported rules: {e}")
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.error(f"Rules import failed: {e}")
            raise

    def get_rules_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about rule usage and effectiveness

        Returns:
            Statistics dictionary
        """
        try:
            with db_service.session_factory() as db:
                # Get rule version stats
                total_versions = db.query(RuleVersion).count()
                active_version = db.query(RuleVersion).filter(RuleVersion.is_active == True).first()

                stats = {
                    "rule_versions": {
                        "total": total_versions,
                        "active_version": active_version.version if active_version else None,
                        "last_updated": active_version.activated_at.isoformat() if active_version and active_version.activated_at else None
                    },
                    "timestamp": datetime.now().isoformat()
                }

                if active_version:
                    rules_content = active_version.rules_content
                    stats["active_rules_analysis"] = {
                        "prohibited_categories": len(rules_content.get("prohibited_content", [])),
                        "keyword_groups": len(rules_content.get("sensitive_keywords", {})),
                        "total_keywords": sum(
                            len(v) if isinstance(v, list) else 1
                            for v in rules_content.get("sensitive_keywords", {}).values()
                        ),
                        "severity_levels": len(rules_content.get("severity_levels", {})),
                        "enforcement_actions": len(rules_content.get("enforcement_actions", {}))
                    }

                return stats

        except Exception as e:
            logger.error(f"Failed to get rules statistics: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Global service instance
rule_management_service = RuleManagementService()