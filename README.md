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
