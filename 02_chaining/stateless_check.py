from anthropic import Anthropic

client = Anthropic()

messages = [{"role": "user", "content": "My name is Dhanya"}]
resp = client.messages.create(model="claude-haiku-4-5-20251001", messages=messages, max_tokens=200,system = "You are a helpful assistant.")
print(resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens)

messages = [{"role": "user", "content": "What is my name?"}]
resp = client.messages.create(model="claude-haiku-4-5-20251001", messages=messages, max_tokens=200,system = "You are a helpful assistant.")
print(resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens)