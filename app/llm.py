"""Answer generation. Uses Anthropic if a key is configured; otherwise returns the top passages (demo mode)."""
from . import config

SYSTEM = (
    "You answer questions using ONLY the numbered context passages provided. "
    "Cite the passages you used like [1] or [2]. If the passages do not contain the answer, "
    "say you don't know. Never invent facts."
)


def build_prompt(question: str, chunks: list[dict]) -> str:
    ctx = "\n\n".join(f"[{i}] {c['content']}" for i, c in enumerate(chunks, start=1))
    return f"Context passages:\n\n{ctx}\n\nQuestion: {question}"


def llm_enabled() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def stream_answer(question: str, chunks: list[dict]):
    """Yields ('token', str) items, then one ('usage', (tokens_in, tokens_out))."""
    if not llm_enabled():
        text = ("(No ANTHROPIC_API_KEY set - showing the most relevant passages.)\n\n"
                + "\n\n".join(f"[{i}] {c['content'][:400]}" for i, c in enumerate(chunks, start=1)))
        yield "token", text
        yield "usage", (0, 0)
        return
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=config.LLM_MODEL, max_tokens=800, system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
    ) as stream:
        for piece in stream.text_stream:
            yield "token", piece
        usage = stream.get_final_message().usage
        yield "usage", (usage.input_tokens, usage.output_tokens)


def complete(system: str, prompt: str, max_tokens: int = 300) -> str:
    """Non-streaming helper (used by the faithfulness judge in the eval harness)."""
    if not llm_enabled():
        raise RuntimeError("ANTHROPIC_API_KEY required")
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(model=config.LLM_MODEL, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if b.type == "text")
