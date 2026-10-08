# Provenance manifests

One file per harvested specialist/config, recording where its golds came from so every trusted number
is traceable back to real public data. Licenses + required credits for every public scope: [`DATA-NOTICE.md`](../../DATA-NOTICE.md).

Each `<name>.md` records:

- **Source** — the API/dataset + exact query/endpoint.
- **Real label** — which published field is the ground truth (and who authored it: a museum catalog, a
  maintainer, an asker's accepted-answer flag, reality itself for forecasts).
- **Count** — golds harvested / held out.
- **Date** — when pulled (public sources drift; this freezes the snapshot of record).
- **License / redistribution note** — facts/labels vs. third-party prose handling.
- **Eval** — leave-one-out score at harvest time.
