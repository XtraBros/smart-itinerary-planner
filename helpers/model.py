from typing import Optional
import os

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

# Import provider-specific LangChain classes
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatZhipuAI
from langchain_community.chat_models import ChatHuggingFace
from langchain_deepseek import ChatDeepSeek  # if deepseek is not available, you can wrap manually

class LLMPipeline:
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o",
        api_key: Optional[str] = None
    ):
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.llm: Optional[BaseChatModel] = None

        # Initialize the LLM model from LangChain
        self._setup_langchain_model()

    def _setup_langchain_model(self):
        if self.provider == "openai":
            self.llm = ChatOpenAI(model=self.model, api_key=self.api_key)
        elif self.provider == "google":
            self.llm = ChatGoogleGenerativeAI(model=self.model, google_api_key=self.api_key)
        elif self.provider == "zhipu":
            self.llm = ChatZhipuAI(model=self.model, api_key=self.api_key)
        elif self.provider == "huggingface":
            self.llm = ChatHuggingFace(repo_id=self.model, huggingfacehub_api_token=self.api_key)
        elif self.provider == "deepseek":
            self.llm = ChatDeepSeek(model=self.model, api_key=self.api_key)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def invoke(self, prompt: str) -> str:
        if not self.llm:
            raise RuntimeError("LLM model not initialized.")
        
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
