from typing import Optional, Union
import openai
from transformers import pipeline as hf_pipeline, AutoModelForCausalLM, AutoTokenizer
import torch

class LLMPipeline:
    def __init__(self, provider: str = 'openai', model_name: str = 'gpt-4o', api_key: Optional[str] = None):
        self.provider = provider.lower()
        self.model_name = model_name
        self.api_key = api_key
        self.model = None
        self.tokenizer = None
        self.pipeline = None

        if self.provider == 'openai':
            if not api_key:
                raise ValueError("OpenAI API key must be provided.")
            openai.api_key = api_key
        elif self.provider == 'hf':
            self.load_huggingface_model()
        else:
            raise ValueError("Unsupported provider. Use 'openai' or 'hf'.")

    def load_huggingface_model(self):
        print(f"Loading HuggingFace model '{self.model_name}'...")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
        self.pipeline = hf_pipeline("text-generation", model=self.model, tokenizer=self.tokenizer)

    def invoke(self, prompt: str, max_tokens: int = 300) -> str:
        if self.provider == 'openai':
            response = openai.ChatCompletion.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7
            )
            return response['choices'][0]['message']['content'].strip()
        
        elif self.provider == 'hf':
            output = self.pipeline(prompt, max_length=max_tokens, do_sample=True, temperature=0.7)
            return output[0]['generated_text'].strip()

        else:
            raise ValueError("Unsupported provider.")

