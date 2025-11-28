# """
# Configuration module for chatbot core.
# Loads YAML configuration files.
# """

# import sys
# from pathlib import Path
# from typing import Dict, Any, Optional
# import yaml

# # Add shared to path
# shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
# if str(shared_path) not in sys.path:
#     sys.path.insert(0, str(shared_path))

# from utils import get_logger

# logger = get_logger(__name__)

# # Config directory
# CONFIG_DIR = Path(__file__).parent

# # Cached configs
# _cached_configs: Dict[str, Any] = {}


# def load_yaml_config(filename: str) -> Dict[str, Any]:
#     """
#     Load YAML configuration file.
    
#     Args:
#         filename: Config filename (e.g., 'settings.yaml')
        
#     Returns:
#         Configuration dictionary
#     """
#     # Check cache
#     if filename in _cached_configs:
#         return _cached_configs[filename]
    
#     config_path = CONFIG_DIR / filename
    
#     if not config_path.exists():
#         logger.error(f"Config file not found: {config_path}")
#         return {}
    
#     try:
#         with open(config_path, 'r', encoding='utf-8') as f:
#             config = yaml.safe_load(f)
        
#         # Cache config
#         _cached_configs[filename] = config
        
#         logger.info(f"Loaded config: {filename}")
#         return config
        
#     except Exception as e:
#         logger.error(f"Error loading config {filename}: {e}", exc_info=True)
#         return {}


# def get_settings() -> Dict[str, Any]:
#     """Get general settings."""
#     return load_yaml_config('settings.yaml')


# def get_prompts(language: str = 'lt') -> Dict[str, Any]:
#     """
#     Get prompts for specified language.
    
#     Args:
#         language: Language code ('lt' or 'en')
        
#     Returns:
#         Prompts dictionary
#     """
#     filename = f'prompts_{language}.yaml'
#     return load_yaml_config(filename)


# def get_problems() -> Dict[str, Any]:
#     """Get problem definitions and categories."""
#     return load_yaml_config('problems.yaml')


# def get_system_prompt(language: str = 'lt') -> str:
#     """
#     Get system prompt for LLM.
    
#     Args:
#         language: Language code
        
#     Returns:
#         System prompt string
#     """
#     prompts = get_prompts(language)
#     return prompts.get('system_prompt', '')


# def get_node_prompt(node_name: str, language: str = 'lt') -> str:
#     """
#     Get prompt for specific node.
    
#     Args:
#         node_name: Name of the node
#         language: Language code
        
#     Returns:
#         Node prompt string
#     """
#     prompts = get_prompts(language)
#     node_prompts = prompts.get('node_prompts', {})
#     return node_prompts.get(node_name, '')


# def clear_cache():
#     """Clear cached configurations."""
#     global _cached_configs
#     _cached_configs = {}
#     logger.info("Config cache cleared")


# __all__ = [
#     'load_yaml_config',
#     'get_settings',
#     'get_prompts',
#     'get_problems',
#     'get_system_prompt',
#     'get_node_prompt',
#     'clear_cache',
# ]


"""
Configuration Module
"""

# from .old.prompts import (
#     # Main prompts
#     GREETING_PROMPT,
#     PROBLEM_CLASSIFICATION_PROMPT,
#     PROBLEM_CLARIFICATION_INTERNET,
#     PROBLEM_CLARIFICATION_TV,
#     ADDRESS_CONFIRMATION_PROMPT,
#     DIAGNOSTICS_RUNNING_PROMPT,
#     PROVIDER_ISSUE_PROMPT,
#     ROUTER_REBOOT_INSTRUCTIONS,
#     WIFI_SETUP_INSTRUCTIONS,
#     TV_BOX_REBOOT_INSTRUCTIONS,
#     CONNECTION_TEST_PROMPT,
#     TICKET_CREATION_PROMPT,
#     CLOSING_PROMPT,
#     GOODBYE_PROMPT,
#     ACKNOWLEDGMENT_PROMPT,
#     INTENT_YES_NO_PROMPT,
#     ERROR_RECOVERY_PROMPT,
    
#     # Helper functions
#     format_prompt,
#     get_problem_clarification_prompt,
#     get_troubleshooting_prompt,
#     get_prompt,
    
#     # Registry
#     PROMPTS,
# )

# __all__ = [
#     # Prompts
#     "GREETING_PROMPT",
#     "PROBLEM_CLASSIFICATION_PROMPT",
#     "PROBLEM_CLARIFICATION_INTERNET",
#     "PROBLEM_CLARIFICATION_TV",
#     "ADDRESS_CONFIRMATION_PROMPT",
#     "DIAGNOSTICS_RUNNING_PROMPT",
#     "PROVIDER_ISSUE_PROMPT",
#     "ROUTER_REBOOT_INSTRUCTIONS",
#     "WIFI_SETUP_INSTRUCTIONS",
#     "TV_BOX_REBOOT_INSTRUCTIONS",
#     "CONNECTION_TEST_PROMPT",
#     "TICKET_CREATION_PROMPT",
#     "CLOSING_PROMPT",
#     "GOODBYE_PROMPT",
#     "ACKNOWLEDGMENT_PROMPT",
#     "INTENT_YES_NO_PROMPT",
#     "ERROR_RECOVERY_PROMPT",
    
#     # Helpers
#     "format_prompt",
#     "get_problem_clarification_prompt",
#     "get_troubleshooting_prompt",
#     "get_prompt",
    
#     # Registry
#     "PROMPTS",
# ]

"""
Config module
"""

from .config import load_config, get_greeting, Config, reload_config

__all__ = [
    "load_config",
    "get_greeting", 
    "Config",
    "reload_config",
]