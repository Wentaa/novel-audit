from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentState(BaseModel):
    """Base state model for LangGraph agents"""
    agent_id: str
    timestamp: datetime
    input_data: Dict[str, Any]
    output_data: Dict[str, Any] = {}
    errors: List[str] = []
    metadata: Dict[str, Any] = {}


class BaseAgent(ABC):
    """Base class for all audit system agents"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.agent_id = str(uuid.uuid4())
        self.logger = logging.getLogger(f"{__name__}.{agent_name}")

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """
        Process the agent logic

        Args:
            state: Current agent state

        Returns:
            Updated agent state with results
        """
        pass

    def create_state(
        self,
        input_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentState:
        """
        Create initial agent state

        Args:
            input_data: Input data for processing
            metadata: Optional metadata

        Returns:
            Initialized agent state
        """
        return AgentState(
            agent_id=self.agent_id,
            timestamp=datetime.now(),
            input_data=input_data,
            metadata=metadata or {}
        )

    def log_processing_start(self, state: AgentState):
        """Log processing start"""
        self.logger.info(f"Starting {self.agent_name} processing - State ID: {state.agent_id}")

    def log_processing_end(self, state: AgentState, success: bool = True):
        """Log processing end"""
        status = "completed" if success else "failed"
        self.logger.info(f"{self.agent_name} processing {status} - State ID: {state.agent_id}")

    def add_error(self, state: AgentState, error_message: str):
        """Add error to state"""
        state.errors.append(error_message)
        self.logger.error(f"{self.agent_name} error: {error_message}")

    async def safe_process(self, state: AgentState) -> AgentState:
        """
        Safe processing wrapper with error handling

        Args:
            state: Agent state

        Returns:
            Updated state with results or errors
        """
        try:
            self.log_processing_start(state)
            updated_state = await self.process(state)
            self.log_processing_end(updated_state, success=True)
            return updated_state

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.add_error(state, error_msg)
            self.log_processing_end(state, success=False)
            return state