"""
ReAct Agent - ISP Customer Support

Implements the ReAct (Reasoning + Acting) pattern for customer support.

ReAct Loop:
1. Thought: Agent reasons about what to do
2. Action: Agent calls a tool or responds
3. Observation: Tool returns result
4. Repeat until task complete

Usage:
    from agent import ReactAgent
    
    agent = ReactAgent(caller_phone="+37060012345")
    response = agent.run_until_response("Neveikia internetas")
    uv run python -m src.agent.react_agent --lang lt --phone +37060012345
"""

import re
import json
import logging
from typing import Optional, Dict, Any

from .state import AgentState
from .config import AgentConfig, get_config, create_config
from .prompts import load_system_prompt

# LLM client
from src.services.llm.client import llm_completion

# Tools
try:
    from .tools import REAL_TOOLS as TOOLS, get_tools_description, execute_tool
    USING_REAL_TOOLS = True
except ImportError as e:
    USING_REAL_TOOLS = False
    TOOLS = []
    
    def get_tools_description():
        return "No tools available"
    
    def execute_tool(name, args):
        return json.dumps({"error": "Tools not available"})


logger = logging.getLogger(__name__)


class ReactAgent:
    """
    ReAct pattern agent for ISP customer support.
    
    Attributes:
        state: Current conversation state
        config: Agent configuration
        system_prompt: Formatted system prompt
    """
    
    def __init__(
        self, 
        caller_phone: str = "unknown",
        language: str = "lt",
        config: AgentConfig = None,
    ):
        """
        Initialize agent.
        
        Args:
            caller_phone: Customer's phone number
            language: Language code ("lt" or "en")
            config: Agent configuration (uses default if None)
        """
        # Create config with language if not provided
        if config is None:
            self.config = create_config(language=language)
        else:
            self.config = config
        
        self.state = AgentState(
            caller_phone=caller_phone,
            max_turns=self.config.max_turns,
        )
        
        # Load and format system prompt with language
        self.system_prompt = load_system_prompt(
            tools_description=get_tools_description(),
            caller_phone=caller_phone,
            language=self.config.language,
        )
        
        logger.info(f"ReactAgent initialized for {caller_phone} [lang={self.config.language}]")
        if USING_REAL_TOOLS:
            logger.info("Using REAL tools")
        else:
            logger.warning("Using MOCK tools")
    
    def _build_messages(self, user_input: str = None) -> list:
        """Build message list for LLM call."""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add conversation history
        for msg in self.state.messages:
            messages.append(msg)
        
        # Add new user input if provided
        if user_input:
            messages.append({"role": "user", "content": f"Customer: {user_input}"})
        
        return messages
    
    def _parse_response(self, response: str) -> tuple:
        """
        Parse LLM response into (thought, action, action_input).
        
        Args:
            response: Raw LLM response string
        
        Returns:
            Tuple of (thought, action_name, action_input_dict)
        """
        thought = ""
        action = ""
        action_input = {}
        
        # Extract Thought
        thought_match = re.search(r"Thought:\s*(.+?)(?=\nAction:|\Z)", response, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
        
        # Extract Action
        action_match = re.search(r"Action:\s*(\w+)", response)
        if action_match:
            action = action_match.group(1).strip()
        
        # Extract Action Input
        input_match = re.search(r"Action Input:\s*(\{.+?\})", response, re.DOTALL)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                raw = input_match.group(1)
                fixed = raw.replace("'", '"')
                try:
                    action_input = json.loads(fixed)
                except:
                    logger.warning(f"Failed to parse action input: {raw}")
                    action_input = {"raw": raw}
        
        return thought, action, action_input
    
    def _update_state_from_observation(self, action: str, observation: str):
        """Update agent state based on tool observation."""
        try:
            obs_data = json.loads(observation)
            
            if action == "find_customer" and obs_data.get("success"):
                self.state.set_customer_info(
                    customer_id=obs_data.get("customer_id"),
                    name=obs_data.get("name"),
                    address=obs_data.get("addresses", [{}])[0].get("address") if obs_data.get("addresses") else None,
                )
            
            elif action == "create_ticket" and obs_data.get("success"):
                self.state.ticket_id = obs_data.get("ticket_id")
                
        except json.JSONDecodeError:
            pass
    
    def step(self, user_input: str = None) -> Dict[str, Any]:
        """
        Execute one agent step.
        
        Args:
            user_input: Customer message (None for initial/continuation)
            
        Returns:
            Dict with: thought, action, action_input, observation, response, is_complete
        """
        self.state.turn_count += 1
        
        # Check turn limit
        if self.state.turn_count > self.state.max_turns:
            return {
                "thought": "Max turns reached",
                "action": "finish",
                "response": self.config.max_turns_message,
                "is_complete": True,
            }
        
        # Build messages and call LLM
        messages = self._build_messages(user_input)
        
        if user_input:
            self.state.messages.append({"role": "user", "content": f"Customer: {user_input}"})
        
        try:
            response = llm_completion(
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return {
                "thought": f"LLM Error: {e}",
                "action": "error",
                "response": self.config.error_message,
                "is_complete": False,
            }
        
        # Parse response
        thought, action, action_input = self._parse_response(response)
        
        logger.info(f"[AGENT] Thought: {thought[:100]}...")
        logger.info(f"[AGENT] Action: {action}")
        logger.debug(f"[AGENT] Input: {action_input}")
        
        result = {
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": None,
            "response": None,
            "is_complete": False,
            "needs_continuation": False,
        }
        
        # Handle actions
        if action == "respond":
            message = action_input.get("message", "")
            result["response"] = message
            self.state.messages.append({
                "role": "assistant",
                "content": f"Thought: {thought}\nAction: respond\nAction Input: {json.dumps(action_input, ensure_ascii=False)}"
            })
            
        elif action == "finish":
            result["is_complete"] = True
            self.state.is_complete = True
            result["response"] = action_input.get("summary", self.config.conversation_end_message)
            
        else:
            # Execute tool
            observation = execute_tool(action, action_input)
            result["observation"] = observation
            
            # Add to message history
            self.state.messages.append({
                "role": "assistant",
                "content": f"Thought: {thought}\nAction: {action}\nAction Input: {json.dumps(action_input, ensure_ascii=False)}"
            })
            self.state.messages.append({
                "role": "user",
                "content": f"Observation: {observation}"
            })
            
            # Update state from observation
            self._update_state_from_observation(action, observation)
            self.state.add_observation(observation)
            
            result["needs_continuation"] = True
        
        return result
    
    def run_until_response(
        self, 
        user_input: str = None, 
        max_tool_calls: int = None,
    ) -> str:
        """
        Run agent until it has a response for the customer.
        
        Args:
            user_input: Customer message (None for initial greeting)
            max_tool_calls: Max tool calls before forcing response
            
        Returns:
            Agent response string
        """
        # Hardcoded greeting - first message without user input
        if user_input is None and self.state.turn_count == 0:
            greeting = self.config.greeting_message
            
            # Log to message history (for context)
            self.state.messages.append({
                "role": "assistant",
                "content": f"Thought: Initial greeting\nAction: respond\nAction Input: {{\"message\": \"{greeting}\"}}"
            })
            self.state.turn_count += 1
            
            logger.info(f"[AGENT] Hardcoded greeting: {greeting}")
            return greeting
        
        # Normal LLM flow
        max_calls = max_tool_calls or self.config.max_tool_calls_per_response
        tool_calls = 0
        
        while tool_calls < max_calls:
            result = self.step(user_input)
            user_input = None  # Only pass on first step
            
            if result.get("response"):
                return result["response"]
            
            if result.get("is_complete"):
                return result.get("response", self.config.conversation_end_message)
            
            if result.get("needs_continuation"):
                tool_calls += 1
                continue
            
            break
        
        return self.config.timeout_message


# =============================================================================
# CLI INTERFACE
# =============================================================================

def run_cli(caller_phone: str = "+37060012345", language: str = "lt"):
    """Run interactive agent session in CLI."""
    print("\n" + "=" * 60)
    print("ISP SUPPORT AGENT (ReAct)")
    print("=" * 60)
    print(f"Caller phone: {caller_phone}")
    print(f"Language: {language}")
    print("Type 'quit' to exit, 'debug' to toggle debug mode")
    print("=" * 60 + "\n")
    
    agent = ReactAgent(caller_phone=caller_phone, language=language)
    debug_mode = False
    
    # Initial greeting
    initial_response = agent.run_until_response()
    if initial_response:
        print(f"\n🤖 Agent: {initial_response}\n")
    
    while not agent.state.is_complete:
        try:
            user_input = input("👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == "quit":
                print(f"\n{agent.config.cli_goodbye_message}")
                break
            
            if user_input.lower() == "debug":
                debug_mode = not debug_mode
                logging.getLogger().setLevel(logging.DEBUG if debug_mode else logging.INFO)
                print(f"[Debug mode: {'ON' if debug_mode else 'OFF'}]")
                continue
            
            if user_input.lower() == "state":
                print(f"\n[STATE] {agent.state.to_dict()}\n")
                continue
            
            response = agent.run_until_response(user_input)
            print(f"\n🤖 Agent: {response}\n")
            
        except KeyboardInterrupt:
            print(f"\n\n{agent.config.cli_interrupted_message}")
            break
    
    print("\n" + "=" * 60)
    print(f"Conversation ended. Turns: {agent.state.turn_count}")
    if agent.state.customer_id:
        print(f"Customer: {agent.state.customer_name} ({agent.state.customer_id})")
    if agent.state.ticket_id:
        print(f"Ticket: {agent.state.ticket_id}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ISP Support Agent CLI")
    parser.add_argument("--phone", default="+37060012345", help="Caller phone number")
    parser.add_argument("--lang", default="lt", choices=["lt", "en"], help="Language (lt or en)")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    
    run_cli(caller_phone=args.phone, language=args.lang)
