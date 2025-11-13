"""
Diagnostics Node
Run network diagnostics using Network Diagnostic MCP service
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message, add_diagnostic_result, add_tool_call

logger = get_logger(__name__)


def diagnostics_node(state: ConversationState) -> ConversationState:
    """
    Diagnostics node - Run network diagnostics tests.
    
    This node:
    1. Determines which diagnostics to run based on problem type
    2. Calls Network Diagnostic MCP service
    3. Analyzes diagnostic results
    4. Reports findings to customer
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with diagnostic results
    """
    logger.info(f"[Diagnostics] Starting for conversation {state['conversation_id']}")
    
    try:
        # Get customer and problem info
        customer_id = state["customer"].get("customer_id")
        problem_type = state["problem"].get("problem_type")
        problem_category = state["problem"].get("category")
        
        if not customer_id:
            logger.warning("[Diagnostics] No customer ID, skipping diagnostics")
            state = _skip_diagnostics(state)
            return state
        
        # Inform customer diagnostics are starting
        language = state["language"]
        state = add_message(state, "assistant", _get_diagnostics_start_message(language))
        
        # Run appropriate diagnostics based on problem type
        diagnostic_tests = _determine_diagnostic_tests(problem_type, problem_category)
        logger.info(f"[Diagnostics] Running tests: {diagnostic_tests}")
        
        # TODO: Call Network Diagnostic MCP service
        # For now, simulate the diagnostics
        # This will be replaced with actual MCP client calls:
        # from ...mcp_client import call_network_tool
        # results = await call_network_tool(test_name, {"customer_id": customer_id})
        
        diagnostic_results = _simulate_diagnostics(customer_id, diagnostic_tests)
        
        # Store results in state
        for test_name, result in diagnostic_results.items():
            state = add_diagnostic_result(state, test_name, result)
            # Log tool call
            state = add_tool_call(state, test_name, {"customer_id": customer_id}, result)
        
        # Analyze results
        analysis = _analyze_diagnostic_results(diagnostic_results, problem_category)
        state["diagnostics"]["analysis"] = analysis
        state["diagnostics_completed"] = True
        
        # Report findings to customer
        report = _create_diagnostic_report(diagnostic_results, analysis, language)
        state = add_message(state, "assistant", report)
        
        # Determine if issue is found
        if analysis["issue_found"]:
            logger.info(f"[Diagnostics] Issue detected: {analysis['issues']}")
            state["requires_escalation"] = analysis.get("requires_escalation", False)
        else:
            logger.info("[Diagnostics] No issues detected in diagnostics")
        
        state["current_node"] = "diagnostics"
        return state
        
    except Exception as e:
        logger.error(f"[Diagnostics] Error: {e}", exc_info=True)
        state = _handle_diagnostics_error(state)
        return state


def _determine_diagnostic_tests(
    problem_type: str,
    problem_category: str
) -> List[str]:
    """
    Determine which diagnostic tests to run.
    
    Args:
        problem_type: Type of problem (internet, tv, etc.)
        problem_category: Specific category
        
    Returns:
        List of test names to run
    """
    tests = []
    
    # Common tests for all internet issues
    if problem_type == "internet":
        tests.extend([
            "check_port_status",
            "check_ip_assignment",
            "ping_test"
        ])
        
        # Additional tests based on category
        if problem_category in ["internet_slow", "internet_intermittent"]:
            tests.append("check_bandwidth_history")
        
        # Check for area outages
        tests.append("check_area_outages")
    
    # TV-specific tests
    elif problem_type == "tv":
        tests.extend([
            "check_signal_quality",
            "check_port_status",
            "check_area_outages"
        ])
    
    # General diagnostics
    else:
        tests.extend([
            "check_port_status",
            "check_area_outages"
        ])
    
    return tests


def _simulate_diagnostics(
    customer_id: str,
    tests: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Simulate diagnostic tests (temporary until MCP client is integrated).
    
    Args:
        customer_id: Customer ID
        tests: List of tests to run
        
    Returns:
        Dictionary of test results
    """
    results = {}
    
    for test in tests:
        if test == "check_port_status":
            results[test] = {
                "success": True,
                "diagnostics": {
                    "total_ports": 1,
                    "ports_up": 1,
                    "ports_down": 0,
                    "all_ports_healthy": True
                },
                "message": "Visi portai veikia teisingai"
            }
        
        elif test == "check_ip_assignment":
            results[test] = {
                "success": True,
                "active_count": 1,
                "ip_assignments": [{
                    "ip_address": "192.168.1.100",
                    "assignment_type": "dhcp",
                    "status": "active"
                }],
                "message": "IP priskirimas aktyvus"
            }
        
        elif test == "ping_test":
            results[test] = {
                "success": True,
                "status": "healthy",
                "statistics": {
                    "packet_loss_percent": 0.0,
                    "avg_latency_ms": 22.5
                },
                "message": "Ryšys normalus"
            }
        
        elif test == "check_bandwidth_history":
            results[test] = {
                "success": True,
                "statistics": {
                    "download": {"avg_mbps": 285.5, "min_mbps": 250, "max_mbps": 300},
                    "upload": {"avg_mbps": 95.2, "min_mbps": 90, "max_mbps": 100}
                },
                "message": "Greičiai normalūs"
            }
        
        elif test == "check_signal_quality":
            results[test] = {
                "success": True,
                "latest": {
                    "status": "good",
                    "signal_strength_dbm": -10,
                    "snr_db": 35
                },
                "message": "Signalas normalus"
            }
        
        elif test == "check_area_outages":
            results[test] = {
                "success": True,
                "outages": [],
                "message": "Nėra žinomų gedimų rajone"
            }
    
    return results


def _analyze_diagnostic_results(
    results: Dict[str, Dict[str, Any]],
    problem_category: str
) -> Dict[str, Any]:
    """
    Analyze diagnostic results to identify issues.
    
    Args:
        results: Diagnostic test results
        problem_category: Problem category
        
    Returns:
        Analysis summary
    """
    analysis = {
        "issue_found": False,
        "issues": [],
        "healthy_components": [],
        "requires_escalation": False,
        "recommended_actions": []
    }
    
    # Check each diagnostic result
    for test_name, result in results.items():
        if not result.get("success"):
            analysis["issues"].append(f"{test_name}: Test failed")
            analysis["issue_found"] = True
            continue
        
        # Port status analysis
        if test_name == "check_port_status":
            diag = result.get("diagnostics", {})
            if diag.get("ports_down", 0) > 0:
                analysis["issues"].append("Port down - tinklo jungtis neaktyvi")
                analysis["issue_found"] = True
                analysis["requires_escalation"] = True
            else:
                analysis["healthy_components"].append("Tinklo portas")
        
        # IP assignment analysis
        elif test_name == "check_ip_assignment":
            if result.get("active_count", 0) == 0:
                analysis["issues"].append("Nėra aktyvaus IP adreso")
                analysis["issue_found"] = True
                analysis["recommended_actions"].append("Perkrauti maršrutizatorių")
            else:
                analysis["healthy_components"].append("IP priskyrimas")
        
        # Ping test analysis
        elif test_name == "ping_test":
            stats = result.get("statistics", {})
            loss = stats.get("packet_loss_percent", 0)
            latency = stats.get("avg_latency_ms", 0)
            
            if loss > 5:
                analysis["issues"].append(f"Paketų praradimas: {loss}%")
                analysis["issue_found"] = True
            if latency > 100:
                analysis["issues"].append(f"Aukštas ping: {latency}ms")
                analysis["issue_found"] = True
            
            if loss <= 5 and latency <= 100:
                analysis["healthy_components"].append("Ping testas")
        
        # Bandwidth analysis
        elif test_name == "check_bandwidth_history":
            stats = result.get("statistics", {})
            download = stats.get("download", {})
            avg_download = download.get("avg_mbps", 0)
            
            if avg_download < 100:  # Assuming plan is 300 Mbps
                analysis["issues"].append(f"Žemas greitis: {avg_download} Mbps")
                analysis["issue_found"] = True
            else:
                analysis["healthy_components"].append("Greičio matavimas")
        
        # Area outages
        elif test_name == "check_area_outages":
            outages = result.get("outages", [])
            if outages:
                analysis["issues"].append(f"Gedimas rajone: {len(outages)} gedimų")
                analysis["issue_found"] = True
                analysis["requires_escalation"] = True
            else:
                analysis["healthy_components"].append("Nėra gedimų rajone")
    
    return analysis


def _create_diagnostic_report(
    results: Dict[str, Dict[str, Any]],
    analysis: Dict[str, Any],
    language: str
) -> str:
    """
    Create human-readable diagnostic report.
    
    Args:
        results: Diagnostic results
        analysis: Analysis summary
        language: Language
        
    Returns:
        Report message
    """
    if language == "lt":
        report = "📊 **Diagnostikos rezultatai:**\n\n"
        
        # Healthy components
        if analysis["healthy_components"]:
            report += "✅ **Veikia gerai:**\n"
            for component in analysis["healthy_components"]:
                report += f"  • {component}\n"
            report += "\n"
        
        # Issues found
        if analysis["issues"]:
            report += "⚠️ **Rastos problemos:**\n"
            for issue in analysis["issues"]:
                report += f"  • {issue}\n"
            report += "\n"
        else:
            report += "✅ Techniškai viskas atrodo gerai.\n\n"
        
        # Recommendations
        if analysis["recommended_actions"]:
            report += "💡 **Rekomenduojami veiksmai:**\n"
            for action in analysis["recommended_actions"]:
                report += f"  • {action}\n"
    else:
        report = "📊 **Diagnostic Results:**\n\n"
        
        if analysis["healthy_components"]:
            report += "✅ **Working properly:**\n"
            for component in analysis["healthy_components"]:
                report += f"  • {component}\n"
            report += "\n"
        
        if analysis["issues"]:
            report += "⚠️ **Issues found:**\n"
            for issue in analysis["issues"]:
                report += f"  • {issue}\n"
            report += "\n"
        else:
            report += "✅ Technically everything looks good.\n\n"
        
        if analysis["recommended_actions"]:
            report += "💡 **Recommended actions:**\n"
            for action in analysis["recommended_actions"]:
                report += f"  • {action}\n"
    
    return report


def _get_diagnostics_start_message(language: str) -> str:
    """Get diagnostics start message."""
    if language == "lt":
        return "🔍 Vykdau tinklo diagnostiką... Tai gali užtrukti kelias sekundes."
    else:
        return "🔍 Running network diagnostics... This may take a few seconds."


def _skip_diagnostics(state: ConversationState) -> ConversationState:
    """Skip diagnostics when customer not identified."""
    language = state["language"]
    
    if language == "lt":
        message = "Kadangi neturiu Jūsų kliento duomenų, negaliu atlikti tinklo diagnostikos. Bet galiu pabandyti padėti bendrais patarimais."
    else:
        message = "Since I don't have your customer information, I cannot run network diagnostics. But I can try to help with general advice."
    
    state = add_message(state, "assistant", message)
    state["diagnostics_completed"] = True
    return state


def _handle_diagnostics_error(state: ConversationState) -> ConversationState:
    """Handle diagnostics errors."""
    language = state["language"]
    
    if language == "lt":
        message = "Atsiprašau, nepavyko atlikti pilnos diagnostikos dėl techninės klaidos. Pabandysiu padėti kitais būdais."
    else:
        message = "Sorry, couldn't complete full diagnostics due to a technical error. I'll try to help in other ways."
    
    state = add_message(state, "assistant", message)
    state["diagnostics_completed"] = True
    return state
