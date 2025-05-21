from typing import Optional
import os
from langchain_core.language_models import BaseChatModel
# Import provider-specific LangChain classes
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatZhipuAI
from langchain_community.chat_models import ChatHuggingFace
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

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

    def invoke(self, messages: list[dict]) -> str:
        if not self.llm:
            raise RuntimeError("LLM model not initialized.")
        
        # Convert messages to LangChain format
        lc_messages: list[BaseMessage] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                raise ValueError(f"Unsupported message role: {role}")

        # Invoke model
        response = self.llm.invoke(lc_messages)
        return response.content.strip()
