from anthropic import AsyncAnthropic
from typing import List, Dict, Any, Optional
import logging
import json

from ..config.settings import settings

logger = logging.getLogger(__name__)


class ClaudeService:
    """Anthropic Claude API service wrapper"""

    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.claude_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.temperature = settings.claude_temperature

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Generate chat completion using Claude

        Args:
            messages: List of message objects with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            response_format: Optional format specification (ignored for Claude)

        Returns:
            Generated response content
        """
        try:
            # Convert OpenAI-style messages to Claude format
            system_message = ""
            user_messages = []
            
            for message in messages:
                if message["role"] == "system":
                    system_message = message["content"]
                elif message["role"] == "user":
                    user_messages.append({"role": "user", "content": message["content"]})
                elif message["role"] == "assistant":
                    user_messages.append({"role": "assistant", "content": message["content"]})
            
            # If no explicit user messages but system message exists, treat system as user
            if not user_messages and system_message:
                user_messages = [{"role": "user", "content": system_message}]
                system_message = ""

            response = await self.client.messages.create(
                model=self.model,
                messages=user_messages,
                system=system_message if system_message else None,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature
            )

            content = response.content[0].text

            # Log token usage
            logger.info(
                f"Claude API usage - "
                f"Input: {response.usage.input_tokens}, "
                f"Output: {response.usage.output_tokens}"
            )

            return content

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

    async def generate_embeddings(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings for text list
        Note: Claude doesn't provide embeddings, this is a placeholder
        """
        raise NotImplementedError("Claude does not provide embedding services")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text string
        Approximation for Claude (roughly 4 chars = 1 token for Chinese/English mixed)
        """
        return len(text) // 4

    async def test_connection(self) -> bool:
        """
        Test Claude API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = await self.chat_completion(
                messages=[{"role": "user", "content": "Hello, this is a connection test."}],
                max_tokens=10
            )
            logger.info("Claude API connection test successful")
            return True
        except Exception as e:
            logger.error(f"Claude API connection test failed: {e}")
            return False

    async def structured_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response using Claude

        Args:
            prompt: Input prompt
            schema: Expected JSON schema description
            temperature: Sampling temperature

        Returns:
            Parsed JSON response
        """
        try:
            system_prompt = f"""You must respond with valid JSON that matches this schema: {json.dumps(schema)}

Your response should be pure JSON with no additional text or explanation. Make sure the JSON is valid and matches the schema exactly."""

            full_prompt = f"{system_prompt}\n\n{prompt}"

            messages = [{"role": "user", "content": full_prompt}]

            response = await self.chat_completion(
                messages=messages,
                temperature=temperature
            )

            # Try to extract JSON from response
            response_text = response.strip()
            
            # Handle cases where Claude might wrap JSON in markdown
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from Claude: {e}")
            logger.error(f"Raw response: {response}")
            raise
        except Exception as e:
            logger.error(f"Claude structured completion error: {e}")
            raise


# Global service instance
claude_service = ClaudeService()