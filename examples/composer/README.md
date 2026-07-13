# Composer examples

Each file is a plain-English task and the workflow the Composer built for it — reusing shared
specialists where it can, and **honestly flagging** the ones it would need to build (it won't fake a
capability). Some compose cleanly (`runnable: true`); some surface a gap.

Build your own:
```bash
python -m engine.cli compose "screen incoming support tickets, draft replies, flag the urgent ones"
```
