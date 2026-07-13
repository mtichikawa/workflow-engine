# tools/ — utility scripts

Standalone scripts that *build real product data* or automate a one-off task. Not part of the
shipped `engine/` package, not demos, not tests.

| file | what it does |
|---|---|
| `harvest_respond_voice.py` | builds RESPOND's universal **baseline** from real public maintainer replies (GitHub API), identity-stripped and blended across repos. The general "GitHub as a voice/expertise corpus" technique — parameterize the repos + reply heuristic to harvest other baselines. |
