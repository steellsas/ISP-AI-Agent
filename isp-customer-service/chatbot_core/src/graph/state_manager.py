"""
State Manager
Handles conversation state persistence, loading, and checkpointing
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from .state import ConversationState, create_initial_state

logger = get_logger(__name__)


class StateManager:
    """
    Manages conversation state persistence and retrieval.
    
    Features:
    - Save/load conversation state
    - State checkpointing
    - Conversation history
    - State cleanup
    """
    
    def __init__(self, storage_dir: str | Path = None):
        """
        Initialize state manager.
        
        Args:
            storage_dir: Directory for storing state files (default: ./state_storage)
        """
        if storage_dir is None:
            storage_dir = Path(__file__).parent.parent.parent / "state_storage"
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.active_dir = self.storage_dir / "active"
        self.archived_dir = self.storage_dir / "archived"
        self.checkpoints_dir = self.storage_dir / "checkpoints"
        
        for directory in [self.active_dir, self.archived_dir, self.checkpoints_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"StateManager initialized with storage: {self.storage_dir}")
    
    def save_state(
        self,
        state: ConversationState,
        checkpoint: bool = False
    ) -> bool:
        """
        Save conversation state to disk.
        
        Args:
            state: Conversation state to save
            checkpoint: Whether to save as checkpoint (versioned)
            
        Returns:
            True if successful
        """
        conversation_id = state["conversation_id"]
        
        try:
            # Determine save location
            if checkpoint:
                save_path = self._get_checkpoint_path(conversation_id)
            else:
                save_path = self._get_active_path(conversation_id)
            
            # Convert state to JSON
            state_json = self._state_to_json(state)
            
            # Save to file
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(state_json, f, indent=2, ensure_ascii=False)
            
            logger.info(f"State saved: {conversation_id} ({'checkpoint' if checkpoint else 'active'})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving state {conversation_id}: {e}", exc_info=True)
            return False
    
    def load_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        Load conversation state from disk.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            ConversationState or None if not found
        """
        try:
            # Try loading from active
            state_path = self._get_active_path(conversation_id)
            
            if not state_path.exists():
                # Try archived
                state_path = self._get_archived_path(conversation_id)
                
                if not state_path.exists():
                    logger.warning(f"State not found: {conversation_id}")
                    return None
            
            # Load from file
            with open(state_path, 'r', encoding='utf-8') as f:
                state_json = json.load(f)
            
            # Convert JSON to state
            state = self._json_to_state(state_json)
            
            logger.info(f"State loaded: {conversation_id}")
            return state
            
        except Exception as e:
            logger.error(f"Error loading state {conversation_id}: {e}", exc_info=True)
            return None
    
    def load_checkpoint(
        self,
        conversation_id: str,
        checkpoint_index: int = -1
    ) -> Optional[ConversationState]:
        """
        Load a specific checkpoint.
        
        Args:
            conversation_id: Conversation ID
            checkpoint_index: Checkpoint index (-1 for latest)
            
        Returns:
            ConversationState or None
        """
        try:
            checkpoints = self._list_checkpoints(conversation_id)
            
            if not checkpoints:
                logger.warning(f"No checkpoints found for {conversation_id}")
                return None
            
            # Get checkpoint file
            checkpoint_file = checkpoints[checkpoint_index]
            
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                state_json = json.load(f)
            
            state = self._json_to_state(state_json)
            
            logger.info(f"Checkpoint loaded: {conversation_id} (index {checkpoint_index})")
            return state
            
        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}", exc_info=True)
            return None
    
    def archive_conversation(self, conversation_id: str) -> bool:
        """
        Archive completed conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            True if successful
        """
        try:
            active_path = self._get_active_path(conversation_id)
            
            if not active_path.exists():
                logger.warning(f"Cannot archive - not found: {conversation_id}")
                return False
            
            archived_path = self._get_archived_path(conversation_id)
            
            # Move to archived
            active_path.rename(archived_path)
            
            logger.info(f"Conversation archived: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error archiving conversation: {e}", exc_info=True)
            return False
    
    def delete_conversation(self, conversation_id: str, include_checkpoints: bool = True) -> bool:
        """
        Delete conversation and optionally its checkpoints.
        
        Args:
            conversation_id: Conversation ID
            include_checkpoints: Whether to delete checkpoints too
            
        Returns:
            True if successful
        """
        try:
            deleted = False
            
            # Delete active
            active_path = self._get_active_path(conversation_id)
            if active_path.exists():
                active_path.unlink()
                deleted = True
            
            # Delete archived
            archived_path = self._get_archived_path(conversation_id)
            if archived_path.exists():
                archived_path.unlink()
                deleted = True
            
            # Delete checkpoints
            if include_checkpoints:
                checkpoints = self._list_checkpoints(conversation_id)
                for checkpoint_file in checkpoints:
                    checkpoint_file.unlink()
            
            if deleted:
                logger.info(f"Conversation deleted: {conversation_id}")
            else:
                logger.warning(f"Conversation not found: {conversation_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            return False
    
    def list_active_conversations(self) -> List[str]:
        """
        List all active conversation IDs.
        
        Returns:
            List of conversation IDs
        """
        try:
            files = list(self.active_dir.glob("*.json"))
            conversation_ids = [f.stem for f in files]
            return sorted(conversation_ids)
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return []
    
    def get_conversation_summary(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation summary without loading full state.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Summary dictionary or None
        """
        try:
            state = self.load_state(conversation_id)
            if not state:
                return None
            
            return {
                "conversation_id": state["conversation_id"],
                "session_start": state["session_start"],
                "language": state["language"],
                "current_node": state["current_node"],
                "customer_identified": state["customer_identified"],
                "problem_identified": state["problem_identified"],
                "ticket_created": state["ticket_created"],
                "conversation_ended": state["conversation_ended"],
                "customer_name": f"{state['customer'].get('first_name', '')} {state['customer'].get('last_name', '')}".strip(),
                "problem_type": state["problem"].get("problem_type"),
                "message_count": len(state["messages"])
            }
            
        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            return None
    
    def cleanup_old_conversations(self, days: int = 30) -> int:
        """
        Clean up old archived conversations.
        
        Args:
            days: Delete conversations older than this many days
            
        Returns:
            Number of conversations deleted
        """
        try:
            deleted_count = 0
            cutoff_time = datetime.now() - timedelta(days=days)
            
            for state_file in self.archived_dir.glob("*.json"):
                # Check file modification time
                file_mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
                
                if file_mtime < cutoff_time:
                    state_file.unlink()
                    deleted_count += 1
                    
                    # Also delete checkpoints
                    conversation_id = state_file.stem
                    checkpoints = self._list_checkpoints(conversation_id)
                    for checkpoint in checkpoints:
                        checkpoint.unlink()
            
            logger.info(f"Cleaned up {deleted_count} old conversations")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Statistics dictionary
        """
        try:
            active_count = len(list(self.active_dir.glob("*.json")))
            archived_count = len(list(self.archived_dir.glob("*.json")))
            checkpoint_count = len(list(self.checkpoints_dir.glob("*.json")))
            
            return {
                "active_conversations": active_count,
                "archived_conversations": archived_count,
                "total_checkpoints": checkpoint_count,
                "storage_dir": str(self.storage_dir)
            }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    # Private helper methods
    
    def _get_active_path(self, conversation_id: str) -> Path:
        """Get path for active conversation state."""
        return self.active_dir / f"{conversation_id}.json"
    
    def _get_archived_path(self, conversation_id: str) -> Path:
        """Get path for archived conversation state."""
        return self.archived_dir / f"{conversation_id}.json"
    
    def _get_checkpoint_path(self, conversation_id: str) -> Path:
        """Get path for new checkpoint."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.checkpoints_dir / f"{conversation_id}_{timestamp}.json"
    
    def _list_checkpoints(self, conversation_id: str) -> List[Path]:
        """List all checkpoint files for a conversation."""
        pattern = f"{conversation_id}_*.json"
        checkpoints = sorted(self.checkpoints_dir.glob(pattern))
        return checkpoints
    
    def _state_to_json(self, state: ConversationState) -> Dict[str, Any]:
        """
        Convert ConversationState to JSON-serializable dict.
        
        Args:
            state: Conversation state
            
        Returns:
            JSON-serializable dictionary
        """
        # Create a copy to avoid modifying original
        state_dict = dict(state)
        
        # Ensure all nested TypedDicts are converted to regular dicts
        state_dict["customer"] = dict(state_dict.get("customer", {}))
        state_dict["problem"] = dict(state_dict.get("problem", {}))
        state_dict["diagnostics"] = dict(state_dict.get("diagnostics", {}))
        state_dict["troubleshooting"] = dict(state_dict.get("troubleshooting", {}))
        state_dict["ticket"] = dict(state_dict.get("ticket", {}))
        
        return state_dict
    
    def _json_to_state(self, state_json: Dict[str, Any]) -> ConversationState:
        """
        Convert JSON dict back to ConversationState.
        
        Args:
            state_json: JSON dictionary
            
        Returns:
            ConversationState
        """
        # ConversationState is a TypedDict, so we can just cast it
        # The structure should already be correct from the JSON
        return ConversationState(**state_json)


# Singleton instance
_state_manager: Optional[StateManager] = None


def get_state_manager(storage_dir: str | Path = None) -> StateManager:
    """
    Get or create StateManager singleton instance.
    
    Args:
        storage_dir: Storage directory (only used on first call)
        
    Returns:
        StateManager instance
    """
    global _state_manager
    
    if _state_manager is None:
        _state_manager = StateManager(storage_dir)
    
    return _state_manager


# Example usage
if __name__ == "__main__":
    # Test state manager
    manager = StateManager()
    
    # Create test state
    test_state = create_initial_state("test-123", "lt")
    test_state["customer"]["first_name"] = "Jonas"
    test_state["problem"]["problem_type"] = "internet"
    
    # Save state
    print("Saving state...")
    manager.save_state(test_state)
    
    # Save checkpoint
    print("Saving checkpoint...")
    manager.save_state(test_state, checkpoint=True)
    
    # Load state
    print("Loading state...")
    loaded_state = manager.load_state("test-123")
    if loaded_state:
        print(f"✅ Loaded: {loaded_state['conversation_id']}")
        print(f"   Customer: {loaded_state['customer']['first_name']}")
    
    # Get summary
    print("\nGetting summary...")
    summary = manager.get_conversation_summary("test-123")
    if summary:
        print(f"✅ Summary: {summary}")
    
    # List active
    print("\nActive conversations:")
    active = manager.list_active_conversations()
    print(f"  {active}")
    
    # Statistics
    print("\nStatistics:")
    stats = manager.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Cleanup
    print("\nCleaning up test...")
    manager.delete_conversation("test-123")
    print("✅ Done!")