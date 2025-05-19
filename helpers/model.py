from typing import Optional
import openai
import requests
import os

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

        # Require API key only if provider is NOT huggingface
        if self.provider != "huggingface" and not self.api_key:
            raise ValueError(f"API key is required for provider '{self.provider}'.")

        # Optional: provider-specific setup
        if self.provider == "openai":
            import openai
            openai.api_key = self.api_key

    def invoke(self, prompt: str) -> str:
        if self.provider == "openai":
            return self._invoke_openai(prompt)
        elif self.provider == "huggingface":
            return self._invoke_huggingface(prompt)
        elif self.provider == "zhipu":
            return self._invoke_zhipu(prompt)
        elif self.provider == "google":
            return self._invoke_google(prompt)
        elif self.provider == "deepseek":
            return self._invoke_deepseek(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    # === Provider-specific methods ===

    def _invoke_openai(self, prompt: str) -> str:
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    def _invoke_huggingface(self, prompt: str) -> str:
        url = f"https://api-inference.huggingface.co/models/{self.model}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"inputs": prompt}
        response = requests.post(url, headers=headers, json=payload)
        return response.json()[0]["generated_text"]

    def _invoke_zhipu(self, prompt: str) -> str:
        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()["choices"][0]["message"]["content"]

    def _invoke_google(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    def _invoke_deepseek(self, prompt: str) -> str:
        url = "https://api.deepseek.com/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(url, headers=headers, json=payload)
        return response.json()["choices"][0]["message"]["content"]
