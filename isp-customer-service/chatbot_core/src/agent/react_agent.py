"""
Agent - ISP Customer Support

Drives the support conversation with native LLM function/tool calling.

Loop (run_until_response):
1. The model receives the conversation + tool schemas (tool_choice="auto").
2. It either calls one or more tools (structured tool_calls) or replies in text.
3. Tool results are fed back as role:"tool" messages and the model continues.
4. When the model replies with text (no tool call), that is the customer answer.

The class is still named ReactAgent for import compatibility; the brittle
"Thought:/Action:/Action Input:" regex parsing has been replaced by native
tool calls (see agent.tools.get_tools_schema and services.llm.llm_tool_completion).

Usage:
    from agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060012345")
    response = agent.run_until_response("Neveikia internetas")
    uv run python -m src.agent.react_agent --lang lt --phone +37060012345
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

# LLM client
from src.services.llm.client import get_last_call_stats, llm_tool_completion

from .config import AgentConfig, create_config
from .prompts import load_system_prompt
from .state import AgentState

# Tools
try:
    from .tools import REAL_TOOLS as TOOLS
    from .tools import execute_tool, get_tools_description, get_tools_schema

    USING_REAL_TOOLS = True
except ImportError:
    USING_REAL_TOOLS = False
    TOOLS = []

    def get_tools_description():
        return "No tools available"

    def get_tools_schema():
        return []

    def execute_tool(name, args):
        return json.dumps({"error": "Tools not available"})


logger = logging.getLogger(__name__)


@dataclass
class LLMStats:
    """Accumulated LLM statistics for a conversation."""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    cached_calls: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def average_latency_ms(self) -> float:
        non_cached = self.total_calls - self.cached_calls
        if non_cached > 0:
            return self.total_latency_ms / non_cached
        return 0.0

    def add_call(
        self,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: float,
        cached: bool,
        model: str,
    ):
        """Add stats from one LLM call."""
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.total_latency_ms += latency_ms
        if cached:
            self.cached_calls += 1
        self.model = model

    def to_dict(self) -> dict:
        """Convert to dictionary for UI."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_cost": self.total_cost,
            "average_latency_ms": self.average_latency_ms,
            "cached_calls": self.cached_calls,
            "model": self.model,
        }


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

        # Initialize LLM stats tracking
        self.llm_stats = LLMStats()

        # OpenAI function-calling schemas passed to the LLM on every step.
        # The model picks which tools to call (tool_choice="auto"); this is the
        # single source of truth, derived from the Tool dataclass.
        self.tools_schema = get_tools_schema()

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

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

    def _build_messages(self, user_input: str = None) -> list:
        """
        Build the message payload for one LLM call.

        Token cost grows with conversation length because the whole history is
        resent every turn. To keep voice latency and cost bounded we send only
        a recent *window* of history (see _prune_history) plus a compact block
        of durable facts re-injected from AgentState (see _state_facts_block),
        so pruning old messages never loses the resolved customer/problem/ticket
        context. The full transcript still lives in AgentState.messages.
        """
        system_content = self.system_prompt
        facts = self._state_facts_block()
        if facts:
            system_content = f"{system_content}\n\n{facts}"

        messages = [{"role": "system", "content": system_content}]

        # Add recent conversation history (windowed, tool-pairing safe)
        messages.extend(self._prune_history(self.state.messages))

        # Add new user input if provided
        if user_input:
            messages.append({"role": "user", "content": user_input})

        return messages

    def _prune_history(self, messages: list) -> list:
        """
        Return the most recent slice of history that fits the configured window.

        Pairing safety: native tool calling requires every role:"tool" message to
        be preceded by the assistant message that issued the matching tool_calls.
        A naive "last N" cut can land mid-exchange and orphan a tool result, which
        the chat API rejects (400). So if the window would start on a tool result,
        we walk the start index left until it lands on the owning assistant
        message, keeping the exchange intact.
        """
        window = self.config.history_window_messages
        if window <= 0 or len(messages) <= window:
            return list(messages)

        start = len(messages) - window
        while start > 0 and messages[start].get("role") == "tool":
            start -= 1
        return messages[start:]

    def _state_facts_block(self) -> str | None:
        """
        Render durable facts from AgentState as a short system addendum.

        These survive history pruning (they live in AgentState, not the message
        log), so re-injecting them keeps the model from re-asking for details it
        already resolved. Returns None when nothing has been resolved yet.
        """
        s = self.state
        facts: list[str] = []
        if s.customer_id:
            facts.append(f"- Customer ID: {s.customer_id}")
        if s.customer_name:
            facts.append(f"- Customer name: {s.customer_name}")
        if s.customer_address:
            facts.append(f"- Address: {s.customer_address}")
        if s.problem_type:
            facts.append(f"- Problem type: {s.problem_type}")
        if s.ticket_id:
            facts.append(f"- Ticket: {s.ticket_id}")

        if not facts:
            return None

        return "KNOWN FACTS (already resolved this call — do not ask again):\n" + "\n".join(facts)

    @staticmethod
    def _assistant_tool_message(message: Any) -> dict:
        """
        Serialize an assistant message that requested tool calls into the dict
        shape the chat API needs echoed back on the next turn.

        The protocol requires that, before any role:"tool" result messages, the
        exact assistant message that issued the tool_calls is present in history
        (matched by tool_call_id). We store a plain dict (not the litellm object)
        so the history stays JSON-serializable.
        """
        return {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        }

    def _update_state_from_observation(self, action: str, observation: str):
        """Update agent state based on tool observation."""
        try:
            obs_data = json.loads(observation)

            if action == "find_customer" and obs_data.get("success"):
                addresses = obs_data.get("addresses") or []
                # Normalized find_customer addresses carry `full_address`
                # (the primary one first when available).
                primary = next(
                    (a for a in addresses if a.get("is_primary")),
                    addresses[0] if addresses else {},
                )
                self.state.set_customer_info(
                    customer_id=obs_data.get("customer_id"),
                    name=obs_data.get("name"),
                    address=primary.get("full_address"),
                )

            elif action == "create_ticket" and obs_data.get("success"):
                self.state.ticket_id = obs_data.get("ticket_id")

        except json.JSONDecodeError:
            pass

    def step(self, user_input: str = None) -> dict[str, Any]:
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
            self.state.messages.append({"role": "user", "content": user_input})

        try:
            message = llm_tool_completion(
                messages=messages,
                tools=self.tools_schema,
                tool_choice="auto",
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # Track LLM stats
            stats = get_last_call_stats()
            self.llm_stats.add_call(
                input_tokens=stats.get("input_tokens", 0),
                output_tokens=stats.get("output_tokens", 0),
                cost=stats.get("cost", 0),
                latency_ms=stats.get("latency_ms", 0),
                cached=stats.get("cached", False),
                model=stats.get("model", self.config.model),
            )

        except Exception as e:
            logger.error(f"LLM error: {e}")
            return {
                "thought": f"LLM Error: {e}",
                "action": "error",
                "response": self.config.error_message,
                "is_complete": False,
            }

        result = {
            "thought": None,
            "action": None,
            "action_input": None,
            "observation": None,
            "response": None,
            "is_complete": False,
            "needs_continuation": False,
            "tool_calls": [],
        }

        tool_calls = getattr(message, "tool_calls", None)

        if tool_calls:
            # The model chose to call one or more tools. Echo the assistant
            # message that requested them (required by the protocol), then run
            # each tool and append its result as a role:"tool" message keyed by
            # tool_call_id. No customer-facing reply yet → needs_continuation so
            # run_until_response loops and lets the model see the results.
            self.state.messages.append(self._assistant_tool_message(message))

            executed = []
            for tc in tool_calls:
                name = tc.function.name
                raw_args = tc.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    logger.warning(f"[AGENT] Bad tool arguments for {name}: {raw_args!r}")
                    args = {}

                logger.info(f"[AGENT] Tool call: {name}")
                logger.debug(f"[AGENT] Args: {args}")

                observation = execute_tool(name, args)

                self.state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": observation,
                    }
                )

                self._update_state_from_observation(name, observation)
                self.state.add_observation(observation)

                executed.append({"name": name, "arguments": args, "observation": observation})

            result["tool_calls"] = executed
            # Back-compat single-action view (last tool) for existing callers/UI.
            result["action"] = executed[-1]["name"] if executed else None
            result["action_input"] = executed[-1]["arguments"] if executed else None
            result["observation"] = executed[-1]["observation"] if executed else None
            result["needs_continuation"] = True
            return result

        # No tool calls → the content is the reply for the customer.
        content = (message.content or "").strip()

        # Model failure mode: no tool call AND no text. An empty reply gives the
        # customer nothing, so nudge the model with a corrective turn and let the
        # loop retry (bounded by max_tool_calls_per_response → no infinite loop /
        # cost blowup). result["response"] stays None so run_until_response does
        # not treat this as a real answer.
        if not content:
            logger.warning(
                "[AGENT] Empty reply with no tool call; injecting correction and retrying"
            )
            self.state.messages.append({"role": "assistant", "content": ""})
            self.state.messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your last reply was empty. Either call a tool or write a "
                        "non-empty message to the customer."
                    ),
                }
            )
            result["needs_continuation"] = True
            return result

        result["action"] = "respond"
        result["response"] = content
        self.state.messages.append({"role": "assistant", "content": content})
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
            self.state.messages.append({"role": "assistant", "content": greeting})
            self.state.turn_count += 1

            logger.info(f"[AGENT] Hardcoded greeting: {greeting}")
            return greeting

        # Normal LLM flow
        max_calls = max_tool_calls or self.config.max_tool_calls_per_response
        tool_calls = 0

        while tool_calls < max_calls:
            result = self.step(user_input)
            user_input = None  # Only pass on first step

            # Distinguish "no response yet" (None) from a real reply. An empty
            # respond is now caught in step() (needs_continuation), so any
            # non-None response here is a genuine answer for the customer.
            if result.get("response") is not None:
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
    # Local import avoids a circular import (session imports ReactAgent).
    from .session import AgentSession

    print("\n" + "=" * 60)
    print("ISP SUPPORT AGENT (ReAct)")
    print("=" * 60)
    print(f"Caller phone: {caller_phone}")
    print(f"Language: {language}")
    print("Type 'quit' to exit, 'debug' to toggle debug mode")
    print("=" * 60 + "\n")

    # Drive the CLI through the stable AgentSession boundary (same seam voice
    # and web use), not the ReactAgent engine directly.
    session = AgentSession(caller_phone=caller_phone, language=language)
    debug_mode = False

    # Initial greeting
    initial_response = session.greeting()
    if initial_response:
        print(f"\n🤖 Agent: {initial_response}\n")

    while not session.is_complete:
        try:
            user_input = input("👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print(f"\n{session.config.cli_goodbye_message}")
                break

            if user_input.lower() == "debug":
                debug_mode = not debug_mode
                logging.getLogger().setLevel(logging.DEBUG if debug_mode else logging.INFO)
                print(f"[Debug mode: {'ON' if debug_mode else 'OFF'}]")
                continue

            if user_input.lower() == "state":
                print(f"\n[STATE] {session.state.to_dict()}\n")
                continue

            response = session.handle_turn(user_input)
            print(f"\n🤖 Agent: {response}\n")

        except KeyboardInterrupt:
            print(f"\n\n{session.config.cli_interrupted_message}")
            break

    print("\n" + "=" * 60)
    print(f"Conversation ended. Turns: {session.state.turn_count}")
    if session.state.customer_id:
        print(f"Customer: {session.state.customer_name} ({session.state.customer_id})")
    if session.state.ticket_id:
        print(f"Ticket: {session.state.ticket_id}")
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

    # Mask phone numbers in logs (after basicConfig set up the root handler).
    from utils import install_pii_redaction

    install_pii_redaction()

    run_cli(caller_phone=args.phone, language=args.lang)
