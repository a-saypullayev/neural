"""Handle the errors the API can return."""
import time

from neuralai import (APIConnectionError, AuthenticationError, InvalidRequestError, Neural, RateLimitError, ServerError)

client = Neural()
try:
    r = client.chat.completions.create(messages=[{"role": "user", "content": "Hello!"}])
    print(r.choices[0].message.content)
except AuthenticationError:
    print("Your API key is invalid or revoked. Create a new one at /keys.")
except RateLimitError as e:
    print(f"Slow down. Retry in {e.retry_after or 60}s ({e.code}).")
    time.sleep(e.retry_after or 60)
except InvalidRequestError as e:
    print("Bad request:", e.message)
except ServerError as e:
    print("The model is unavailable right now:", e.message)
except APIConnectionError as e:
    print("Could not reach the server:", e)
