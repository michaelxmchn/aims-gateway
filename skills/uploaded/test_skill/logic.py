"""test_skill — Sandbox mock logic for DePIN pipeline verification."""

def run(params: dict, user_id: str = "", task_id: str = "") -> dict:
    """Accept any input, return a success result."""
    return {
        "status": "SUCCESS",
        "result": {
            "message": "test_skill mock execution complete",
            "input_echo": params,
        },
        "user_id": user_id,
        "task_id": task_id,
    }
