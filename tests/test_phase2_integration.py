import pytest
import asyncio
from pathlib import Path
import tempfile
import json

from src.app.workflows.rule_extraction_workflow import rule_extraction_workflow
from src.app.utils.document_processor import document_processor
from src.app.services.rule_management_service import rule_management_service
from src.app.storage.database import create_tables, db_service


class TestPhase2Integration:
    """Integration tests for Phase 2: Rule Construction System"""

    @pytest.fixture(autouse=True)
    async def setup_test_environment(self):
        """Set up test environment before each test"""
        # Create test database tables
        create_tables()
        yield
        # Cleanup would go here if needed

    @pytest.fixture
    def sample_policy_document(self):
        """Sample policy document for testing"""
        return """
        网文内容审核规范手册

        第一章：禁止内容类型

        1. 暴力血腥内容
        - 详细描述暴力场面，包括血腥、酷刑等内容
        - 示例关键词：血腥、屠杀、酷刑、残害

        2. 成人色情内容
        - 露骨的性行为描述
        - 过度详细的身体描述
        - 示例关键词：色情、性行为、裸体

        3. 政治敏感内容
        - 涉及政治立场的争议性内容
        - 对政府政策的负面评价
        - 示例关键词：政治、政府、领导人

        第二章：违规等级划分

        轻微违规：
        - 暗示性的成人内容
        - 处理方式：要求修改

        严重违规：
        - 明确的暴力描述
        - 处理方式：内容拒绝

        极严重违规：
        - 极端暴力或色情内容
        - 处理方式：账号处罚

        第三章：审核标准

        言情类小说：
        - 允许：浪漫情节、情感描述
        - 禁止：露骨性描述

        动作类小说：
        - 允许：战斗场面、动作描述
        - 禁止：过度血腥、残忍酷刑
        """

    async def test_complete_rule_extraction_workflow(self, sample_policy_document):
        """Test complete rule extraction workflow from document to final rules"""

        # Step 1: Document processing
        processed_doc = await document_processor.process_document(
            sample_policy_document.encode('utf-8'),
            "test_policy.txt"
        )

        assert processed_doc["metadata"]["processing_status"] == "success"
        assert len(processed_doc["content"]) > 0

        # Step 2: Run rule extraction workflow
        workflow_result = await rule_extraction_workflow.run_workflow(
            document_content=processed_doc["content"],
            document_type="txt",
            source_filename="test_policy.txt"
        )

        # Verify workflow completion
        assert workflow_result["workflow_status"] in ["completed", "awaiting_human_review"]
        assert "extracted_rules" in workflow_result
        assert "validation_result" in workflow_result

        # Step 3: Verify extracted rules structure
        extracted_rules = workflow_result["extracted_rules"]
        assert "prohibited_content" in extracted_rules
        assert "sensitive_keywords" in extracted_rules
        assert "severity_levels" in extracted_rules

        # Step 4: Verify rule content quality
        prohibited_content = extracted_rules["prohibited_content"]
        assert len(prohibited_content) >= 2  # Should extract violence, adult content, etc.

        sensitive_keywords = extracted_rules["sensitive_keywords"]
        assert len(sensitive_keywords) >= 2  # Should have keyword categories

        # Step 5: Verify validation results
        validation_result = workflow_result["validation_result"]
        assert "validation_result" in validation_result
        assert "confidence_score" in validation_result
        assert validation_result["confidence_score"] >= 0

    async def test_rule_validator_accuracy(self, sample_policy_document):
        """Test rule validator's ability to catch issues"""

        # Create intentionally incomplete extracted rules
        incomplete_rules = {
            "version": "test_v1.0",
            "prohibited_content": [
                {"category": "violence", "description": "Basic violence"}
            ],
            # Missing sensitive_keywords, severity_levels, etc.
        }

        from src.app.agents.rule_validator import RuleValidatorAgent
        validator = RuleValidatorAgent()

        # Create validation state
        state = validator.create_state({
            "original_document": sample_policy_document,
            "extracted_rules": incomplete_rules,
            "source_metadata": {"filename": "test.txt"}
        })

        # Run validation
        result_state = await validator.safe_process(state)

        # Verify validation caught issues
        validation_result = result_state.output_data["validation_result"]
        assert validation_result["validation_result"] in ["fail", "needs_improvement"]
        assert len(validation_result["issues_found"]) > 0
        assert validation_result["confidence_score"] < 0.8

    async def test_human_review_workflow(self):
        """Test human review process for rule versions"""

        # Step 1: Create sample rules
        rule_version_id = await rule_management_service.create_sample_rules()
        assert rule_version_id > 0

        # Step 2: Verify rule creation
        active_rules = await rule_management_service.get_active_rules()
        assert active_rules is not None
        assert "prohibited_content" in active_rules

        # Step 3: Test rule statistics
        stats = rule_management_service.get_rules_statistics()
        assert "rule_versions" in stats
        assert stats["rule_versions"]["total"] >= 1

    async def test_document_processing_formats(self):
        """Test document processing for different formats"""

        # Test text processing
        text_content = "测试文档内容：暴力、色情、政治敏感内容的识别。"
        result = await document_processor.process_document(
            text_content.encode('utf-8'),
            "test.txt"
        )

        assert result["metadata"]["processing_status"] == "success"
        assert "测试文档内容" in result["content"]
        assert result["metadata"]["detected_type"] == "txt"

        # Test document validation
        is_valid, message = document_processor.validate_document("test.txt", 1000)
        assert is_valid == True

        # Test invalid document
        is_valid, message = document_processor.validate_document("test.xyz", 1000)
        assert is_valid == False

    async def test_rule_extraction_error_handling(self):
        """Test error handling in rule extraction workflow"""

        # Test with empty document
        workflow_result = await rule_extraction_workflow.run_workflow(
            document_content="",
            document_type="txt",
            source_filename="empty.txt"
        )

        assert workflow_result["workflow_status"] == "error"
        assert len(workflow_result["errors"]) > 0

        # Test with invalid document type
        workflow_result = await rule_extraction_workflow.run_workflow(
            document_content="valid content",
            document_type="invalid",
            source_filename="test.invalid"
        )

        # Should handle gracefully
        assert "workflow_status" in workflow_result

    async def test_rules_export_import(self):
        """Test rule export and import functionality"""

        # Step 1: Create sample rules
        rule_version_id = await rule_management_service.create_sample_rules()

        # Step 2: Export rules
        filename, content = await rule_management_service.export_rules(
            rule_version_id, "json"
        )

        assert filename.endswith(".json")
        assert len(content) > 0

        # Verify JSON is valid
        rules_dict = json.loads(content)
        assert "prohibited_content" in rules_dict

        # Step 3: Import rules
        import_info = {"filename": "imported_test.json", "imported_by": "test_system"}
        imported_id = await rule_management_service.import_rules_from_json(
            content, import_info
        )

        assert imported_id > 0
        assert imported_id != rule_version_id  # Should be different version

    async def test_workflow_state_management(self, sample_policy_document):
        """Test workflow state management and processing history"""

        workflow_result = await rule_extraction_workflow.run_workflow(
            document_content=sample_policy_document,
            document_type="txt",
            source_filename="state_test.txt"
        )

        # Verify processing history
        assert "processing_history" in workflow_result
        history = workflow_result["processing_history"]

        # Should have multiple processing steps
        assert len(history) >= 2

        # Verify step sequence
        step_names = [step["step"] for step in history]
        assert "initialize" in step_names

        # Verify metadata
        assert "workflow_metadata" in workflow_result
        metadata = workflow_result["workflow_metadata"]
        assert "workflow_id" in metadata
        assert "started_at" in metadata

    def test_sample_data_creation(self):
        """Test sample data creation for development"""

        # This can run synchronously
        import asyncio

        async def run_test():
            rule_version_id = await rule_management_service.create_sample_rules()
            assert rule_version_id > 0

            # Verify sample rules content
            active_rules = await rule_management_service.get_active_rules()
            assert active_rules is not None

            # Check key components
            assert "prohibited_content" in active_rules
            assert "sensitive_keywords" in active_rules
            assert "severity_levels" in active_rules

            # Verify keyword categories
            keywords = active_rules["sensitive_keywords"]
            assert "violence" in keywords
            assert "adult_content" in keywords

            return True

        result = asyncio.run(run_test())
        assert result == True


# Utility functions for testing
def create_test_pdf_document():
    """Create a test PDF document for testing"""
    # This would create a simple PDF with policy content
    # Implementation would depend on PDF creation library
    pass

def create_test_docx_document():
    """Create a test DOCX document for testing"""
    # This would create a simple DOCX with policy content
    # Implementation would depend on DOCX creation library
    pass


if __name__ == "__main__":
    # Run a quick integration test
    async def quick_test():
        test_instance = TestPhase2Integration()
        await test_instance.setup_test_environment()

        sample_doc = """
        审核规范：
        1. 禁止暴力内容：血腥、屠杀
        2. 禁止色情内容：性描述
        3. 违规等级：轻微、严重、极严重
        """

        await test_instance.test_complete_rule_extraction_workflow(sample_doc)
        print("✅ Phase 2 integration test passed!")

    asyncio.run(quick_test())