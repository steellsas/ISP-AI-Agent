"""
Conversation Agent - Core Logic
Uses LangGraph workflow to process conversations autonomously
"""

import asyncio
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

from graph.workflow import ISPSupportWorkflow
from graph.state import (
    ConversationState, 
    create_initial_state, 
    add_message
)
from graph.state_manager import StateManager
from services.mcp_service import MCPService
from utils import get_logger

logger = get_logger(__name__)


class ConversationAgent:
    """LangGraph-based Conversation Agent."""
    
    def __init__(self, mcp_service: Optional[MCPService] = None):
        self.workflow = ISPSupportWorkflow()
        self.mcp_service = mcp_service
        self.state_manager = StateManager()
        self.total_conversations = 0
        self.total_turns = 0
        
    async def ensure_mcp_initialized(self):
        """Ensure MCP service is initialized."""
        if self.mcp_service is None:
            self.mcp_service = MCPService()
            await self.mcp_service.initialize()
        elif not self.mcp_service.is_initialized:
            await self.mcp_service.initialize()
    
    async def start_conversation(self, conversation_id: Optional[str] = None, language: str = "lt") -> Tuple[ConversationState, str]:
        """Start new conversation."""
        await self.ensure_mcp_initialized()
        
        if conversation_id is None:
            conversation_id = f"conv-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        state = create_initial_state(conversation_id, language)
        
        # Execute greeting
        from graph.nodes.greeting import greeting_node
        state = greeting_node(state)
        
        greeting = self._get_last_assistant_message(state)
        self.state_manager.save_state(state)
        self.total_conversations += 1
        
        return state, greeting
    
    async def process_message(self, state: ConversationState, user_input: str) -> Tuple[ConversationState, str]:
        """Process user message through workflow."""
        await self.ensure_mcp_initialized()
        
        state = add_message(state, "user", user_input)
        state, response = await self._execute_workflow_turn(state)
        self.state_manager.save_state(state)
        self.total_turns += 1
        
        return state, response
    
    async def _execute_workflow_turn(self, state: ConversationState) -> Tuple[ConversationState, str]:
        """Execute workflow nodes until bot responds."""
        current_node = state["current_node"]
        messages_before = len(state["messages"])
        
        # Import nodes
        from graph.nodes.customer_identification import customer_identification_node
        from graph.nodes.problem_identification import problem_identification_node
        from graph.nodes.diagnostics import diagnostics_node
        from graph.nodes.troubleshooting import troubleshooting_node
        from graph.nodes.ticket_registration import ticket_registration_node
        from graph.nodes.resolution import resolution_node
        
        nodes = {
            "customer_identification": customer_identification_node,
            "problem_identification": problem_identification_node,
            "diagnostics": diagnostics_node,
            "troubleshooting": troubleshooting_node,
            "ticket_registration": ticket_registration_node,
            "resolution": resolution_node
        }
        
        # Execute until bot responds
        for _ in range(10):  # Max 10 iterations
            if state.get("conversation_ended") or current_node not in nodes:
                break
            
            try:
                state = nodes[current_node](state)
            except Exception as e:
                logger.error(f"Error in {current_node}: {e}")
                state = add_message(state, "assistant", "Atsiprašau, įvyko klaida.")
                break
            
            # Check if bot responded
            if len(state["messages"]) > messages_before:
                if state["messages"][-1]["role"] == "assistant":
                    break
            
            next_node = state["current_node"]
            if next_node == current_node:
                logger.warning(f"Stuck at {current_node}")
                break
            current_node = next_node
        
        return state, self._get_last_assistant_message(state)
    
    def _get_last_assistant_message(self, state: ConversationState) -> str:
        """Get last assistant message."""
        for msg in reversed(state["messages"]):
            if msg["role"] == "assistant":
                return msg["content"]
        return ""
    
    async def close(self):
        """Close agent."""
        if self.mcp_service:
            await self.mcp_service.close()