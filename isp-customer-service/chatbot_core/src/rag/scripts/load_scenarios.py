"""
Scenario Loader
Load and parse YAML troubleshooting scenarios
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from isp_shared.utils import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger(__name__)


class TroubleshootingScenario:
    """Represents a troubleshooting scenario."""

    def __init__(self, data: Dict[str, Any]):
        """
        Initialize scenario from parsed YAML data.

        Args:
            data: Parsed YAML dictionary
        """
        scenario_data = data.get("scenario", {})

        self.id = scenario_data.get("id")
        self.title = scenario_data.get("title")
        self.problem_type = scenario_data.get("problem_type")
        self.keywords = scenario_data.get("keywords", [])
        self.description = scenario_data.get("description", "")
        self.steps = scenario_data.get("steps", [])
        self.escalation = scenario_data.get("escalation", {})

    def get_step(self, step_id: int) -> Optional[Dict[str, Any]]:
        """Get step by ID."""
        for step in self.steps:
            if step.get("step_id") == step_id:
                return step
        return None

    def get_first_step(self) -> Optional[Dict[str, Any]]:
        """Get first step."""
        return self.steps[0] if self.steps else None

    def to_embedding_text(self) -> str:
        """Convert scenario to text for embedding."""
        text_parts = [self.title, self.description, " ".join(self.keywords)]
        return "\n".join(text_parts)

    def __repr__(self):
        return f"TroubleshootingScenario(id='{self.id}', title='{self.title}')"


class ScenarioLoader:
    """Load troubleshooting scenarios from YAML files."""

    def __init__(self, scenarios_dir: Optional[str | Path] = None):
        """
        Initialize scenario loader.

        Args:
            scenarios_dir: Directory containing YAML scenario files
        """
        if scenarios_dir is None:
            # Default: chatbot_core/src/rag/knowledge_base/troubleshooting/scenarios
            scenarios_dir = (
                Path(__file__).parent / "knowledge_base" / "troubleshooting" / "scenarios"
            )

        self.scenarios_dir = Path(scenarios_dir)
        self.scenarios: Dict[str, TroubleshootingScenario] = {}

        logger.info(f"ScenarioLoader initialized: {self.scenarios_dir}")

    def load_all(self) -> Dict[str, TroubleshootingScenario]:
        """
        Load all scenarios from directory.

        Returns:
            Dictionary of scenario_id -> TroubleshootingScenario
        """
        if not self.scenarios_dir.exists():
            logger.warning(f"Scenarios directory not found: {self.scenarios_dir}")
            return {}

        yaml_files = list(self.scenarios_dir.glob("*.yaml"))
        logger.info(f"Found {len(yaml_files)} YAML scenario files")

        for yaml_file in yaml_files:
            try:
                scenario = self.load_scenario(yaml_file)
                self.scenarios[scenario.id] = scenario
                logger.info(f"Loaded scenario: {scenario.id}")
            except Exception as e:
                logger.error(f"Error loading {yaml_file}: {e}")

        logger.info(f"Total scenarios loaded: {len(self.scenarios)}")
        return self.scenarios

    def load_scenario(self, file_path: str | Path) -> TroubleshootingScenario:
        """
        Load single scenario from YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            TroubleshootingScenario instance
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return TroubleshootingScenario(data)

    def get_scenario(self, scenario_id: str) -> Optional[TroubleshootingScenario]:
        """Get scenario by ID."""
        return self.scenarios.get(scenario_id)

    def get_scenarios_for_embedding(self) -> List[Dict[str, Any]]:
        """
        Get scenarios formatted for embedding.

        Returns:
            List of dicts with text, metadata, and id
        """
        scenarios_data = []

        for scenario_id, scenario in self.scenarios.items():
            scenarios_data.append(
                {
                    "text": scenario.to_embedding_text(),
                    "metadata": {
                        "scenario_id": scenario.id,
                        "title": scenario.title,
                        "problem_type": scenario.problem_type,
                        "type": "scenario",
                    },
                    "id": f"scenario_{scenario.id}",
                }
            )

        return scenarios_data


# Singleton instance
_scenario_loader: Optional[ScenarioLoader] = None


def get_scenario_loader(scenarios_dir: Optional[str | Path] = None) -> ScenarioLoader:
    """Get or create ScenarioLoader singleton."""
    global _scenario_loader

    if _scenario_loader is None:
        _scenario_loader = ScenarioLoader(scenarios_dir)
        _scenario_loader.load_all()

    return _scenario_loader
