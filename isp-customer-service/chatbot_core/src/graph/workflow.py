"""
LangGraph Workflow Definition
Main graph structure with nodes and edges for ISP customer service chatbot
"""

import sys
from pathlib import Path
from typing import Dict, Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from langgraph.graph import StateGraph, END
from utils import get_logger

from .state import ConversationState

logger = get_logger(__name__)


class ISPSupportWorkflow:
    """
    ISP Customer Support Workflow using LangGraph.
    
    Workflow steps:
    1. Greeting - Welcome customer
    2. Customer Identification - Find customer by address
    3. Problem Identification - Understand the issue
    4. Diagnostics - Run network diagnostics
    5. Troubleshooting - Guide customer through fixes
    6. Ticket Registration - Create ticket if needed
    7. Resolution - End conversation
    """
    
    def __init__(self):
        """Initialize workflow."""
        self.graph = None
        self._build_graph()
        logger.info("ISP Support Workflow initialized")
    
    def _build_graph(self) -> None:
        """Build the LangGraph workflow."""
        
        # Create state graph
        workflow = StateGraph(ConversationState)
        
        # Import nodes (will create these next)
        from .nodes.greeting import greeting_node
        from .nodes.customer_identification import customer_identification_node
        from .nodes.problem_identification import problem_identification_node
        from .nodes.diagnostics import diagnostics_node
        from .nodes.troubleshooting import troubleshooting_node
        from .nodes.ticket_registration import ticket_registration_node
        from .nodes.resolution import resolution_node
        
        # Add nodes
        workflow.add_node("greeting", greeting_node)
        workflow.add_node("customer_identification", customer_identification_node)
        workflow.add_node("problem_identification", problem_identification_node)
        workflow.add_node("diagnostics", diagnostics_node)
        workflow.add_node("troubleshooting", troubleshooting_node)
        workflow.add_node("ticket_registration", ticket_registration_node)
        workflow.add_node("resolution", resolution_node)
        
        # Set entry point
        workflow.set_entry_point("greeting")
        
        # Add edges with conditional routing
        
        # From greeting -> customer_identification
        workflow.add_edge("greeting", "customer_identification")
        
        # From customer_identification -> problem_identification or END
        workflow.add_conditional_edges(
            "customer_identification",
            self._route_after_customer_identification,
            {
                "problem_identification": "problem_identification",
                "end": END
            }
        )
        
        # From problem_identification -> diagnostics
        workflow.add_conditional_edges(
            "problem_identification",
            self._route_after_problem_identification,
            {
                "diagnostics": "diagnostics",
                "troubleshooting": "troubleshooting",
                "end": END
            }
        )
        
        # From diagnostics -> troubleshooting
        workflow.add_edge("diagnostics", "troubleshooting")
        
        # From troubleshooting -> ticket_registration or resolution
        workflow.add_conditional_edges(
            "troubleshooting",
            self._route_after_troubleshooting,
            {
                "ticket_registration": "ticket_registration",
                "resolution": "resolution",
                "diagnostics": "diagnostics",  # Re-run diagnostics if needed
            }
        )
        
        # From ticket_registration -> resolution
        workflow.add_edge("ticket_registration", "resolution")
        
        # From resolution -> END
        workflow.add_edge("resolution", END)
        
        # Compile graph
        self.graph = workflow.compile()
        logger.info("Workflow graph compiled successfully")
    
    def _route_after_customer_identification(
        self,
        state: ConversationState
    ) -> str:
        """
        Route after customer identification.
        
        Args:
            state: Current state
            
        Returns:
            Next node name
        """
        if state["customer_identified"]:
            return "problem_identification"
        elif state["conversation_ended"]:
            return "end"
        else:
            # Stay in customer_identification if not found
            return "problem_identification"  # Still proceed but mark as unidentified
    
    def _route_after_problem_identification(
        self,
        state: ConversationState
    ) -> str:
        """
        Route after problem identification.
        
        Args:
            state: Current state
            
        Returns:
            Next node name
        """
        if state["conversation_ended"]:
            return "end"
        
        if state["problem_identified"]:
            problem_type = state["problem"].get("problem_type")
            
            # For network issues, run diagnostics
            if problem_type in ["internet", "tv"]:
                return "diagnostics"
            else:
                # For other issues, go straight to troubleshooting
                return "troubleshooting"
        
        return "troubleshooting"
    
    def _route_after_troubleshooting(
        self,
        state: ConversationState
    ) -> str:
        """
        Route after troubleshooting.
        
        Args:
            state: Current state
            
        Returns:
            Next node name
        """
        # If problem resolved, go to resolution
        if state["troubleshooting"].get("resolved", False):
            return "resolution"
        
        # If requires escalation or max attempts reached, create ticket
        if state["requires_escalation"]:
            return "ticket_registration"
        
        # If customer wants to try more troubleshooting
        next_action = state.get("next_action")
        if next_action == "retry_diagnostics":
            return "diagnostics"
        elif next_action == "create_ticket":
            return "ticket_registration"
        
        # Default: create ticket if not resolved
        return "ticket_registration"
    
    async def run(
        self,
        initial_state: ConversationState,
        config: Dict[str, Any] = None
    ) -> ConversationState:
        """
        Run the workflow.
        
        Args:
            initial_state: Initial conversation state
            config: Optional configuration
            
        Returns:
            Final state
        """
        logger.info(f"Starting workflow for conversation {initial_state['conversation_id']}")
        
        try:
            # Run graph
            final_state = await self.graph.ainvoke(
                initial_state,
                config=config or {}
            )
            
            logger.info(f"Workflow completed for conversation {initial_state['conversation_id']}")
            return final_state
            
        except Exception as e:
            logger.error(f"Error in workflow: {e}", exc_info=True)
            raise
    
    def stream(
        self,
        initial_state: ConversationState,
        config: Dict[str, Any] = None
    ):
        """
        Stream workflow execution (for real-time UI updates).
        
        Args:
            initial_state: Initial conversation state
            config: Optional configuration
            
        Yields:
            State updates
        """
        logger.info(f"Streaming workflow for conversation {initial_state['conversation_id']}")
        
        try:
            for state_update in self.graph.stream(
                initial_state,
                config=config or {}
            ):
                yield state_update
                
        except Exception as e:
            logger.error(f"Error in workflow stream: {e}", exc_info=True)
            raise
    
    def get_graph_visualization(self) -> str:
        """
        Get Mermaid diagram of the workflow.
        
        Returns:
            Mermaid diagram string
        """
        return self.graph.get_graph().draw_mermaid()


def create_workflow() -> ISPSupportWorkflow:
    """
    Create and return ISP Support Workflow instance.
    
    Returns:
        ISPSupportWorkflow instance
    """
    return ISPSupportWorkflow()


# Example usage
if __name__ == "__main__":
    import asyncio
    from .state import create_initial_state
    
    async def test_workflow():
        """Test workflow creation."""
        workflow = create_workflow()
        print("✅ Workflow created successfully")
        
        # Print graph structure
        print("\nWorkflow Graph Structure:")
        print(workflow.get_graph_visualization())
        
        # Create test state
        test_state = create_initial_state(
            conversation_id="test-123",
            language="lt"
        )
        
        print(f"\n✅ Initial state created: {test_state['conversation_id']}")
    
    asyncio.run(test_workflow())