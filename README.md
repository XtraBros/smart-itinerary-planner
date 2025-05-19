# GuideGenius
Unlock a world of discovery with GuideGenius, our AI-driven tour guide, tailored exclusively for your attraction – interactive, immersive, unforgettable.

# How to use
(Temporary) To bypass teh CORS limit, we set up a proxy temporarily to get the Mapbox tiles. In my-proxy directory, run:
```
node server.js
```
Then in the root project directory, run:
```
python app.py
```
You can open GuideGenius in browser at: http://127.0.0.1:5000/

# Make contributions
To contribute code to the repository, you should follow the next instructions to abide by the naming rules for easier and clearer tracking of code changes. Please work on the **develop** branch for development. The **main** branch is only used for hotfix and production.

## Set the global hooks to define the naming rules and constraints
```
git config --global core.hooksPath .githooks
```

## Name an issue title with the prefix words
Format: [feature/bug/hotfix] Issue title

Example: **[feature] Add a new chain to execute user questions**

## Name a branch with prefix words
feature, bugfix, hotfix, test

Example:

- if 42 is the issue number: **feature/42/create-new-button-component**

- if no specific issue number, then use "noref" instead: **feature/noref/create-new-button-component**

## Add commit message with keywords
feat, fix, refactor, docs, test, chore

Example:
```
git commit -m 'feat: add new button component; add new button components to templates'
```

## Name a pull request title
Format: [#IssueNumber] Pull request title

Example: **[#5958] Error alert email has a very long subject**

## Format the description in pull request
Format: close/fix/resolve $IssueNumber

Example: **close/fix/resolve #5958**

# RAG Platform & LLM Pipeline
This project provides a modular **Retrieval-Augmented Generation (RAG) Platform** paired with a pluggable **LLM Pipeline** to support intelligent query answering over a custom dataset (e.g. POIs, attractions, places).

## RAG Platform:
Load a CSV or prebuilt FAISS index to perform semantic and category-based retrievals.
### Initialize
``` python
from rag_platform import RAGPlatform

rag = RAGPlatform(data_path="pois.csv")  # CSV must include: name, description, category, etc.
```

### Query by Name
``` python
matches = rag.find_similar_names(["sky garden", "universal studios"])
```
### Query by Description
``` python
description_matches = rag.query("I want a relaxing place with nature and greenery")
```

### Query by Category
``` python
category_matches = rag.filter_by_category(["nature", "park"])
```
## LLM Pipeline:
Supports OpenAI, HuggingFace, Zhipu, Google Gemini, and DeepSeek out of the box.

### Initialize
``` python
from llm_pipeline import LLMPipeline

llm = LLMPipeline(provider="openai", model="gpt-4o", api_key="your-api-key")
```

### Generate Answer
``` python
response = llm.invoke("What are some kid-friendly attractions in the city?")
print(response)
```

## Combine RAG & LLM 
``` python
query = "I'm looking for exciting theme parks for teenagers"
context_pois = rag.query(query)
context = "\n".join([f"{x['name']}: {x['description']}" for x in context_pois])

final_prompt = f"Based on the following places, recommend the best one:\n{context}"
answer = llm.invoke(final_prompt)
print(answer)
```