
#5-turn chat with token counts
from anthropic import Anthropic

client = Anthropic()

MODEL = "claude-haiku-4-5-20251001"
SYSTEM = "You are a helpful assistant." 
messages =[]

for turn in range(5):
    if turn == 1:
        user_input = "My name is Dhanya"
    elif turn == 4:
        user_input = "What is my name?"
    else:
        user_input = input("User: ")
    messages.append({"role": "user", "content": user_input})
    
    resp = client.messages.create(model=MODEL, messages=messages, max_tokens=200, system=SYSTEM)
    assistant_response = resp.content[0].text
    print(f"--- Turn {turn + 1} ---")
    print(f"Assistant: {assistant_response}")
    
    messages.append({"role": "assistant", "content": assistant_response})
    print(f"Input tokens: {resp.usage.input_tokens}")
