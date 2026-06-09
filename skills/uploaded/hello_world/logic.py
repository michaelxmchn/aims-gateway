"""hello_world — a minimal test skill for the dynamic plugin system."""


def execute(payload: dict) -> dict:
    """Greet the user with the provided name."""
    name = payload.get("name", "world")
    greeting = f"Hello, {name}!"
    return {
        "greeting": greeting,
        "length": len(greeting),
    }
