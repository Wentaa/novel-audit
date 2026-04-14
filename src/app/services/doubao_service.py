import aiohttp
from typing import List, Dict, Any, Optional
import logging
import json

from ..config.settings import settings

logger = logging.getLogger(__name__)


class DoubaoService:
    """字节跳动豆包 API service wrapper"""

    def __init__(self):
        self.api_key = settings.doubao_api_key
        self.model = settings.doubao_model
        self.max_tokens = settings.doubao_max_tokens
        self.temperature = settings.doubao_temperature
        self.base_url = "https://ark.cn-beijing.volces.com/api/v3"

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Generate chat completion using 豆包

        Args:
            messages: List of message objects with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response
            response_format: Optional format specification

        Returns:
            Generated response content
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens
            }

            # Add response format if specified
            if response_format:
                payload["response_format"] = response_format

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Doubao API error {response.status}: {error_text}")
                        raise Exception(f"Doubao API returned status {response.status}")

                    result = await response.json()
                    
                    content = result["choices"][0]["message"]["content"]

                    # Log token usage if available
                    if "usage" in result:
                        usage = result["usage"]
                        logger.info(
                            f"Doubao API usage - "
                            f"Prompt: {usage.get('prompt_tokens', 0)}, "
                            f"Completion: {usage.get('completion_tokens', 0)}, "
                            f"Total: {usage.get('total_tokens', 0)}"
                        )

                    return content

        except Exception as e:
            logger.error(f"Doubao API error: {e}")
            raise

    async def generate_embeddings(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings for text list
        Note: 豆包可能不提供embedding服务，这是占位符
        """
        raise NotImplementedError("Doubao embedding service not implemented")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text string
        Approximation for 豆包 (roughly 2.5 chars = 1 token for Chinese)
        """
        return int(len(text) / 2.5)

    async def test_connection(self) -> bool:
        """
        Test 豆包 API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = await self.chat_completion(
                messages=[{"role": "user", "content": "你好，这是一个连接测试。"}],
                max_tokens=10
            )
            logger.info("Doubao API connection test successful")
            return True
        except Exception as e:
            logger.error(f"Doubao API connection test failed: {e}")
            return False

    async def structured_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response using 豆包

        Args:
            prompt: Input prompt
            schema: Expected JSON schema description
            temperature: Sampling temperature

        Returns:
            Parsed JSON response
        """
        try:
            system_message = f"""你必须返回符合以下JSON格式的有效JSON响应：{json.dumps(schema, ensure_ascii=False)}

你的回复必须是纯JSON格式，不要包含任何额外的文字或解释。确保JSON格式正确且完全符合指定的schema。"""

            messages = [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            response = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"} if "json" in self.model.lower() else None
            )

            # Clean up response text
            response_text = response.strip()
            
            # Handle cases where model might wrap JSON in markdown
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
            
            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from Doubao: {e}")
            logger.error(f"Raw response: {response}")
            raise
        except Exception as e:
            logger.error(f"Doubao structured completion error: {e}")
            raise


# Global service instance
doubao_service = DoubaoService()