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
