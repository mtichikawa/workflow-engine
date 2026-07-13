# Examples

Everything here runs on real data and shows real output — nothing is mocked.

| folder | what's in it |
|---|---|
| [`full_run/`](full_run/) | complete runs: a recipe on real input → the run log + what it produced (`output/`) |
| [`composer/`](composer/) | the Composer's work: a plain-English task → the workflow it built |
| [`scripts/`](scripts/) | runnable one-liners — `python examples/scripts/<name>.py` |

**Run your own** (see the [README](../README.md#try-it--run-real-workflows)):
```bash
python -m engine.cli run triage --repo <any/public-repo> --limit 5
python -m engine.cli compose "<describe a job in plain English>"
```
