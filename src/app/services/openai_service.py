from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
import logging
import json
import tiktoken

from ..config.settings import settings

logger = logging.getLogger(__name__)


class OpenAIService:
    """OpenAI API service wrapper"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.embedding_model = settings.openai_embedding_model
        self.max_tokens = settings.openai_max_tokens
        self.temperature = settings.openai_temperature

        # Initialize tokenizer for token counting
        try:
            self.tokenizer = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Generate chat completion using GPT-4

        Args:
            messages: List of message objects with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response
            response_format: Optional format specification (e.g., {"type": "json_object"})

        Returns:
            Generated response content
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                response_format=response_format
            )

            content = response.choices[0].message.content

            # Log token usage
            if response.usage:
                logger.info(
                    f"OpenAI API usage - "
                    f"Prompt: {response.usage.prompt_tokens}, "
                    f"Completion: {response.usage.completion_tokens}, "
                    f"Total: {response.usage.total_tokens}"
                )

            return content

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def generate_embeddings(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings for text list

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )

            embeddings = [item.embedding for item in response.data]

            logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings

        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text string

        Args:
            text: Input text string

        Returns:
            Number of tokens
        """
        try:
            return len(self.tokenizer.encode(text))
        except Exception as e:
            logger.error(f"Token counting error: {e}")
            return 0

    async def test_connection(self) -> bool:
        """
        Test OpenAI API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = await self.chat_completion(
                messages=[{"role": "user", "content": "Hello, this is a connection test."}],
                max_tokens=10
            )
            logger.info("OpenAI API connection test successful")
            return True
        except Exception as e:
            logger.error(f"OpenAI API connection test failed: {e}")
            return False

    async def structured_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response using OpenAI

        Args:
            prompt: Input prompt
            schema: Expected JSON schema description
            temperature: Sampling temperature

        Returns:
            Parsed JSON response
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": f"You must respond with valid JSON that matches this schema: {json.dumps(schema)}"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            response = await self.chat_completion(
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"}
            )

            return json.loads(response)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise
        except Exception as e:
            logger.error(f"Structured completion error: {e}")
            raise


# Global service instance
openai_service = OpenAIService()