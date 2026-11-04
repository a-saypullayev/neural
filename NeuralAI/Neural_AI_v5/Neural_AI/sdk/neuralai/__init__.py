"""neuralai: Python SDK for the Neural AI REST API."""
from .client import Neural, Stream
from .errors import (APIConnectionError, APIStatusError, AuthenticationError, InvalidRequestError,
                     NeuralError, NotFoundError, RateLimitError, ServerError)

__version__ = "0.1.0"
__all__ = ["Neural", "Stream", "NeuralError", "APIConnectionError", "APIStatusError", "AuthenticationError",
           "InvalidRequestError", "NotFoundError", "RateLimitError", "ServerError", "__version__"]
