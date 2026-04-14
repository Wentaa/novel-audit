from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

from .base_agent import BaseAgent, AgentState
from .initial_judgment import INITIAL_JUDGMENT_PROMPT  # 复用现有prompt
from ..services.openai_service import openai_service
from ..services.claude_service import claude_service
from ..services.doubao_service import doubao_service
from ..services.rule_management_service import rule_management_service
from ..config.settings import settings


class MultiModelAuditAgent(BaseAgent):
    """多模型审核基础类 - 复用现有审核逻辑"""
    
    def __init__(self, agent_name: str, ai_service, model_name: str):
        super().__init__(agent_name)
        self.ai_service = ai_service
        self.model_name = model_name

    async def process(self, state: AgentState) -> AgentState:
        """
        使用指定AI服务进行审核，复用initial_judgment的逻辑
        
        Expected input_data:
        - content_text: 待审核的内容
        - metadata: 内容元数据（可选）
        
        Returns:
        - judgment_result: 审核结果
        - model_info: 使用的模型信息
        """
        content_text = state.input_data.get("content_text", "")
        content_metadata = state.input_data.get("metadata", {})

        if not content_text.strip():
            self.add_error(state, f"No content provided for {self.agent_name}")
            return state

        try:
            self.logger.info(f"Starting audit with {self.model_name} (length: {len(content_text)})")

            # Step 1: 获取规则（复用现有逻辑）
            active_rules = await rule_management_service.get_active_rules()
            if not active_rules:
                self.add_error(state, "No active rules found for content auditing")
                return state

            # Step 2: 执行审核（复用现有prompt和schema）
            judgment_result = await self._perform_judgment_with_service(content_text, active_rules)

            # Step 3: 验证结果
            validated_result = self._validate_judgment_result(judgment_result)

            # 准备输出
            state.output_data = {
                "judgment_result": validated_result,
                "model_info": {
                    "model_name": self.model_name,
                    "agent_name": self.agent_name,
                    "service_type": type(self.ai_service).__name__
                },
                "processing_metadata": {
                    "agent": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "content_length": len(content_text),
                    "rules_version": active_rules.get("version", "unknown"),
                    "processing_version": "multi_model_v1.0"
                }
            }

            decision = validated_result.get("judgment", "uncertain")
            confidence = validated_result.get("confidence_score", 0.0)
            
            self.logger.info(f"{self.model_name} audit completed: {decision} (confidence: {confidence:.2f})")
            return state

        except Exception as e:
            error_msg = f"{self.agent_name} audit failed: {str(e)}"
            self.add_error(state, error_msg)
            return state

    async def _perform_judgment_with_service(self, content_text: str, active_rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用指定AI服务执行审核判断
        """
        try:
            # 复用现有的规则格式化逻辑
            rules_summary = self._format_rules_for_prompt(active_rules)

            # 使用现有的prompt
            prompt = INITIAL_JUDGMENT_PROMPT.format(
                rules_content=rules_summary,
                content_text=content_text
            )

            # 复用现有的schema定义
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

            # 使用对应的AI服务进行结构化分析
            judgment_result = await self.ai_service.structured_completion(
                prompt=prompt,
                schema=judgment_schema,
                temperature=0.1
            )

            return judgment_result

        except Exception as e:
            self.logger.error(f"Judgment analysis with {self.model_name} failed: {e}")
            # 返回失败结果
            return {
                "judgment": "uncertain",
                "confidence_score": 0.0,
                "violation_details": [],
                "keyword_matches": [],
                "content_analysis": {},
                "reasoning": f"Analysis failed with {self.model_name}: {str(e)}",
                "recommended_action": "escalate_review",
                "processing_metadata": {
                    "agent": self.agent_name,
                    "model": self.model_name,
                    "error": str(e)
                }
            }

    def _format_rules_for_prompt(self, rules: Dict[str, Any]) -> str:
        """复用initial_judgment的规则格式化逻辑"""
        try:
            formatted_parts = []

            if "prohibited_content" in rules:
                formatted_parts.append("PROHIBITED CONTENT:")
                for item in rules["prohibited_content"]:
                    if isinstance(item, dict):
                        category = item.get("category", "unknown")
                        description = item.get("description", "")
                        severity = item.get("severity", "major")
                        formatted_parts.append(f"- {category}: {description} (Severity: {severity})")

            if "sensitive_keywords" in rules:
                formatted_parts.append("\nSENSITIVE KEYWORDS:")
                for category, keywords in rules["sensitive_keywords"].items():
                    if isinstance(keywords, list):
                        keyword_str = ", ".join(keywords[:10])
                        formatted_parts.append(f"- {category}: {keyword_str}")

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
        """复用initial_judgment的结果验证逻辑"""
        try:
            if "judgment" not in result:
                result["judgment"] = "uncertain"

            if "confidence_score" not in result:
                result["confidence_score"] = 0.5

            valid_judgments = ["approved", "rejected", "uncertain"]
            if result["judgment"] not in valid_judgments:
                result["judgment"] = "uncertain"

            confidence = result["confidence_score"]
            if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
                result["confidence_score"] = 0.5

            if "violation_details" not in result:
                result["violation_details"] = []

            if "keyword_matches" not in result:
                result["keyword_matches"] = []

            if not result.get("reasoning"):
                result["reasoning"] = f"Content assessment by {self.model_name}: {result['judgment']}"

            return result

        except Exception as e:
            self.logger.error(f"Judgment result validation failed: {e}")
            return {
                "judgment": "uncertain",
                "confidence_score": 0.0,
                "violation_details": [],
                "keyword_matches": [],
                "reasoning": f"Validation error with {self.model_name}",
                "recommended_action": "escalate_review"
            }


class OpenAIAuditAgent(MultiModelAuditAgent):
    """使用OpenAI进行审核的Agent"""
    
    def __init__(self):
        super().__init__(
            agent_name="OpenAIAuditAgent",
            ai_service=openai_service,
            model_name=f"OpenAI-{settings.openai_model}"
        )


class ClaudeAuditAgent(MultiModelAuditAgent):
    """使用Claude进行审核的Agent"""
    
    def __init__(self):
        super().__init__(
            agent_name="ClaudeAuditAgent", 
            ai_service=claude_service,
            model_name=f"Claude-{settings.claude_model}"
        )


class DoubaoAuditAgent(MultiModelAuditAgent):
    """使用豆包进行审核的Agent"""
    
    def __init__(self):
        super().__init__(
            agent_name="DoubaoAuditAgent",
            ai_service=doubao_service,
            model_name=f"Doubao-{settings.doubao_model}"
        )


async def run_parallel_multi_model_audit(content_text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    并行运行多模型审核 - 让3个AI重复同样的工作
    
    Args:
        content_text: 待审核内容
        metadata: 可选的元数据
    
    Returns:
        包含所有模型审核结果的字典
    """
    # 创建三个审核Agent
    agents = [
        OpenAIAuditAgent(),
        ClaudeAuditAgent(), 
        DoubaoAuditAgent()
    ]
    
    # 准备相同的输入数据
    input_data = {
        "content_text": content_text,
        "metadata": metadata or {}
    }
    
    # 并行执行审核
    tasks = []
    for agent in agents:
        agent_state = agent.create_state(input_data)
        task = agent.safe_process(agent_state)
        tasks.append((agent.agent_name, agent.model_name, task))
    
    # 收集结果
    results = {}
    successful_count = 0
    
    for agent_name, model_name, task in tasks:
        try:
            result_state = await task
            if result_state.errors:
                results[agent_name] = {
                    "status": "error",
                    "model_name": model_name,
                    "errors": result_state.errors
                }
            else:
                results[agent_name] = {
                    "status": "success",
                    "model_name": model_name,
                    "judgment_result": result_state.output_data.get("judgment_result", {}),
                    "model_info": result_state.output_data.get("model_info", {}),
                    "metadata": result_state.output_data.get("processing_metadata", {})
                }
                successful_count += 1
        except Exception as e:
            results[agent_name] = {
                "status": "error",
                "model_name": model_name, 
                "errors": [f"Execution failed: {str(e)}"]
            }
    
    # 生成决策汇总
    decisions = []
    confidences = []
    
    for result in results.values():
        if result["status"] == "success":
            judgment = result["judgment_result"]
            decisions.append(judgment.get("judgment", "uncertain"))
            confidences.append(judgment.get("confidence_score", 0.0))
    
    # 计算共识指标
    consensus_analysis = _analyze_consensus(decisions, confidences)
    
    return {
        "multi_model_results": results,
        "consensus_analysis": consensus_analysis,
        "summary": {
            "total_models": len(agents),
            "successful_models": successful_count,
            "failed_models": len(agents) - successful_count,
            "content_length": len(content_text),
            "timestamp": datetime.now().isoformat()
        }
    }


def _analyze_consensus(decisions: List[str], confidences: List[float]) -> Dict[str, Any]:
    """分析多模型决策的共识程度"""
    if not decisions:
        return {"consensus_level": "no_data", "agreement_score": 0.0}
    
    # 统计决策分布
    decision_counts = {}
    for decision in decisions:
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    
    # 计算共识级别
    total_models = len(decisions)
    max_agreement = max(decision_counts.values())
    agreement_ratio = max_agreement / total_models
    
    if agreement_ratio >= 1.0:
        consensus_level = "unanimous"
    elif agreement_ratio >= 0.67:
        consensus_level = "strong_majority"
    elif agreement_ratio >= 0.5:
        consensus_level = "simple_majority"
    else:
        consensus_level = "no_consensus"
    
    # 计算平均置信度
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    # 找出主要决策
    majority_decision = max(decision_counts.keys(), key=lambda k: decision_counts[k])
    
    return {
        "consensus_level": consensus_level,
        "agreement_score": agreement_ratio,
        "majority_decision": majority_decision,
        "decision_distribution": decision_counts,
        "average_confidence": round(avg_confidence, 3),
        "confidence_range": [min(confidences), max(confidences)] if confidences else [0, 0],
        "requires_arbitration": consensus_level in ["no_consensus", "simple_majority"]
    }