"""REPL one-off avec l'assistant Nodalys.

Lancement :
    uv run python scripts/chat.py
"""

from assistant.agent import build_agent


def main():
    agent = build_agent()
    print("Assistant Nodalys prêt. Pose ta question (Ctrl+C pour quitter).")
    while True:
        try:
            q = input("\nQuestion> ").strip()
            if not q:
                continue
            result = agent.invoke({"messages": [{"role": "user", "content": q}]})
            print(f"\nRéponse: {result['messages'][-1].content}")
        except (KeyboardInterrupt, EOFError):
            print("\nÀ bientôt!")
            break


if __name__ == "__main__":
    main()
