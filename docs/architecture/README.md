# Architecture

How this project is put together, why, and what flows between the parts. Start with the two
decision records, then the contract, then the diagrams.

## Decisions

| Record | Decision in one line |
|---|---|
| [ADR-0001](../adr/0001-python-computes-app-visualises.md) | Python computes every number; a static React app only draws versioned JSON. Raw data stays outside git. |
| [ADR-0002](../adr/0002-order-selection.md) | d comes from ADF + KPSS on the training split; p, q and the drift come from a full statsmodels AIC grid within that d; pmdarima is a cross-check, not the source of truth. |

## The contract

[`contract.md`](contract.md) describes every JSON file the app reads: the fixed envelope, the
value conventions (explicit `null`, units in field names, half-open date windows), the
versioning policy, and one section per artifact from `meta` (milestone 0) to `metrics`
(milestone 4).

## Diagrams

Each diagram has a YAML source in [`specs/`](specs/) and generated files in [`out/`](out/): a
Mermaid file (`.mmd`) plus SVG, PNG, draw.io and Lucid versions. The blocks below are
byte-for-byte copies of the `out/*.mmd` files, so GitHub can draw them inline. Do not edit the
files in `out/` or these blocks by hand.

The files in `out/` are generated from the YAML specs by a diagram kit that is vendored in
[`tools/diagrams/`](../../tools/diagrams/README.md), so anyone can rebuild the diagrams.
**The YAML specs are the source of truth.** The committed files were built with kit commit
`7493b4b`.

### 1. Architecture

```mermaid
---
title: "ARIMA stock forecasting architecture"
---
flowchart TB
    subgraph source["Source"]
        yahoo{{"Yahoo Finance\nchart API"}}
        yfin(["yfinance 1.7.0\ndownload(), auto_adjust=True"])
    end
    subgraph rawcache["Raw cache (outside git)"]
        rawfile[("Raw price snapshot\n#36;VOL_DATA_DIR/.../raw")]
        manifest[("Snapshot manifest\nsha256, rows, version")]
    end
    subgraph core["Python core"]
        config["config.py\nwindows and data paths"]
        pipeline[["arima_forecasting\nEDA, tests, grid, fit, forecasts"]]
        contract["contract.py\nenvelope, allow_nan=False"]
        provenance["provenance.py\ncommit + SOURCE_DATE_EPOCH"]
    end
    subgraph delivery["Delivery (in git)"]
        exporter["export_app_data.py\none file per artifact"]
        jsonfiles[/"app/public/data\nversioned JSON envelopes"/]
        notebooks[/"Notebooks\nbuilt by build_notebooks.py"/]
        reports[/"Reports\nresult tables (from M4)"/]
        pytests["pytest\ncontract, sync, numbers"]
    end
    subgraph webapp["App"]
        loader["loadArtifact\nrefuses major ≠ 1"]
        views("React 19 views\nexplorer, lab, 3D AIC, fan")
        vitest["vitest\nparses the real JSON files"]
    end
    yahoo -->|"HTTPS"| yfin
    yfin -->|"snapshot once"| rawfile
    rawfile -.->|"described by"| manifest
    rawfile -->|"read"| pipeline
    config ==>|"windows"| pipeline
    pipeline -->|"payloads"| exporter
    contract -->|"wrap + dumps"| exporter
    provenance -->|"commit + time"| exporter
    exporter -->|"write"| jsonfiles
    pipeline -->|"imported by"| notebooks
    pipeline -->|"figures + tables"| reports
    pipeline -.->|"checked by"| pytests
    jsonfiles -->|"fetch"| loader
    loader -->|"typed data"| views
    jsonfiles -.->|"parsed by"| vitest
    classDef source fill:#E0F2FE,stroke:#0284C7,color:#0F172A
    class yfin source
    classDef store fill:#FEF3C7,stroke:#D97706,color:#0F172A
    class rawfile,manifest store
    classDef process fill:#E0E7FF,stroke:#4F46E5,color:#0F172A
    class config,contract,provenance,exporter,pytests,loader,vitest process
    classDef model fill:#EDE9FE,stroke:#7C3AED,color:#0F172A
    class pipeline model
    classDef output fill:#D1FAE5,stroke:#059669,color:#0F172A
    class jsonfiles,notebooks,reports output
    classDef external fill:#F1F5F9,stroke:#475569,color:#0F172A
    class yahoo external
    classDef ui fill:#FCE7F3,stroke:#DB2777,color:#0F172A
    class views ui
    style source fill:#F1F5F9,stroke:#E2E8F0,color:#64748B
    style rawcache fill:#EFF6FF,stroke:#DBEAFE,color:#64748B
    style core fill:#F5F3FF,stroke:#E9E5FD,color:#64748B
    style delivery fill:#ECFDF5,stroke:#D1FAE5,color:#64748B
    style webapp fill:#FFF7ED,stroke:#FFEDD5,color:#64748B
    linkStyle 2 stroke:#94A3B8
    linkStyle 4 stroke:#6366F1
    linkStyle 11 stroke:#94A3B8
    linkStyle 14 stroke:#94A3B8
```

**How to read it.** Read top to bottom: data comes in from Yahoo at the top and ends up on
screen at the bottom. Each rounded box is a *lane*, meaning where a thing lives. The **Raw
cache** lane is outside git: the price snapshot and its manifest sit in
`$VOL_DATA_DIR/arima-stock-forecasting/raw/`. Everything in **Delivery** is committed. The only
arrow into the app is `app/public/data → loadArtifact`: that is the contract, and it is
the *only* way a number reaches the app. Notice what is missing: no arrow runs from the app
back into Python, and no arrow runs from Yahoo to the app. Dashed arrows are checks, not data:
pytest checks the package, and vitest (`app/src/lib/contract.realdata.test.ts`) runs the app's
production parsers over the very JSON files in `app/public/data/` that the app will load. Indigo
(control) arrows carry configuration (the study windows from `config.py`), not data.

### 2. Data flow

```mermaid
---
title: "Data flow from prices to metrics"
---
flowchart TB
    ohlcv(["Daily OHLCV\nyfinance, adjusted"])
    snapshot[("Raw snapshot\nCSV + SHA-256 manifest")]
    closepx["Adjusted close\n#36;, .ffill() if gaps"]
    logpx["Log price\nln(close)"]
    diffs["Differences\nd = 1, 2 (pointwise, no leak)"]
    splitpos["Split by position\n90#37; train / 10#37; test + OOS"]
    edastats["EDA\nsummary, KDEs, decomposition"]
    unitroot[["ADF + KPSS\ntrain only → d"]]
    grid[["AIC grid\np, q 0–5, trend, per d"]]
    autoarima[["auto_arima check\ntrain only"]]
    fitmodel[["Fit ARIMA\nstatsmodels, order + trend"]]
    static[["Static multi-step\none origin to horizon h"]]
    walkfwd[["Walk-forward one-step\nparams frozen, filter updated"]]
    randwalk[["Random walk\nforecast = previous close"]]
    backtx["Back-transform\nexp(mean), exp(bounds)"]
    scoring["Metrics\nRMSE, MAE, MAPE; ratio to RW"]
    artifacts[/"JSON artifacts\nprices … metrics"/]
    ohlcv -->|"download once"| snapshot
    snapshot -->|"Close column"| closepx
    closepx --> logpx
    logpx --> diffs
    diffs --> splitpos
    splitpos -->|"train"| unitroot
    splitpos -->|"train"| edastats
    unitroot -->|"d fixed"| grid
    splitpos -->|"train"| autoarima
    autoarima -.->|"cross-check"| grid
    grid -->|"lowest AIC"| fitmodel
    fitmodel --> static
    fitmodel --> walkfwd
    splitpos -->|"actuals"| randwalk
    static --> backtx
    walkfwd --> backtx
    randwalk --> backtx
    backtx -->|"vs actual #36;"| scoring
    scoring -->|"metrics"| artifacts
    backtx -.->|"forecasts"| artifacts
    grid -.->|"aic_grid"| artifacts
    unitroot -.->|"stationarity"| artifacts
    splitpos -.->|"prices"| artifacts
    edastats -.->|"eda"| artifacts
    classDef source fill:#E0F2FE,stroke:#0284C7,color:#0F172A
    class ohlcv source
    classDef store fill:#FEF3C7,stroke:#D97706,color:#0F172A
    class snapshot store
    classDef process fill:#E0E7FF,stroke:#4F46E5,color:#0F172A
    class closepx,logpx,diffs,splitpos,edastats,backtx,scoring process
    classDef model fill:#EDE9FE,stroke:#7C3AED,color:#0F172A
    class unitroot,grid,autoarima,fitmodel,static,walkfwd,randwalk model
    classDef output fill:#D1FAE5,stroke:#059669,color:#0F172A
    class artifacts output
    linkStyle 9 stroke:#94A3B8
    linkStyle 19 stroke:#94A3B8
    linkStyle 20 stroke:#94A3B8
    linkStyle 21 stroke:#94A3B8
    linkStyle 22 stroke:#94A3B8
    linkStyle 23 stroke:#94A3B8
```

**How to read it.** This is the life of one number, from a daily price bar to a forecast
error. The bars are downloaded once into a **Raw snapshot** outside git; every later run reads
that file, whose SHA-256 the `prices` artifact repeats. Everything before **Split by position** is
pointwise: the log at day t uses only day t, and the difference at day t uses days t and t−1. So
it is safe to compute over the whole series. Everything after the split that *estimates*
something (the **EDA** summary, KDEs and decomposition, the unit-root tests, the AIC grid, the
`auto_arima` cross-check, the fit) sees only the training part. The fit then feeds two of the
three forecast methods; the random walk needs no fit at all, only the actual prices. All three
pass through the same **Back-transform** (exp of the log forecast and of its interval bounds)
before being scored in dollars, so they are compared like for like. Dashed arrows into
**JSON artifacts** show which step produces which file.

### 3. Delivery process

```mermaid
---
title: "Milestone delivery loop"
---
flowchart TB
    subgraph learner["Learner"]
        kickoff("Start milestone\nlearner says go")
        answer("Answer questions\npredict-first, explain-it-back")
    end
    subgraph orchestrator["Orchestrator session"]
        plan["Plan the milestone\ntasks + acceptance checks"]
        walkthrough[/"Walkthrough\n+ predict-first questions"/]
        pause["Pause\nhand over to the learner"]
        grade["Grade answers\ngaps become follow-ups"]
        advance[/"Next milestone\nmeta.json status moves on"/]
    end
    subgraph implementer["Implementer subagent"]
        build["Build\ncode, tests, notebooks, export"]
    end
    subgraph reviewer["Adversarial reviewer"]
        review[["Adversarial review\nevidence-gated; default is broken"]]
    end
    subgraph verifier["Verifier subagent"]
        remeasure["Re-measure numbers\nevery quoted figure"]
    end
    subgraph github["GitHub"]
        push{{"Push\ncommit + push to main"}}
    end
    kickoff --> plan
    plan -->|"task list"| build
    build -->|"report"| walkthrough
    walkthrough -->|"numbered claims"| review
    review ==>|"refuted"| build
    review -->|"survives"| remeasure
    remeasure ==>|"disagree"| build
    remeasure -->|"agree"| push
    push --> pause
    pause --> answer
    answer --> grade
    grade ==>|"retry gaps"| answer
    grade -->|"pass"| advance
    advance -.->|"next loop"| plan
    classDef process fill:#E0E7FF,stroke:#4F46E5,color:#0F172A
    class plan,build,remeasure,pause,grade process
    classDef model fill:#EDE9FE,stroke:#7C3AED,color:#0F172A
    class review model
    classDef output fill:#D1FAE5,stroke:#059669,color:#0F172A
    class walkthrough,advance output
    classDef external fill:#F1F5F9,stroke:#475569,color:#0F172A
    class push external
    classDef ui fill:#FCE7F3,stroke:#DB2777,color:#0F172A
    class kickoff,answer ui
    style learner fill:#F1F5F9,stroke:#E2E8F0,color:#64748B
    style orchestrator fill:#EFF6FF,stroke:#DBEAFE,color:#64748B
    style implementer fill:#F5F3FF,stroke:#E9E5FD,color:#64748B
    style reviewer fill:#ECFDF5,stroke:#D1FAE5,color:#64748B
    style verifier fill:#FFF7ED,stroke:#FFEDD5,color:#64748B
    style github fill:#FDF2F8,stroke:#FCE7F3,color:#64748B
    linkStyle 4 stroke:#6366F1
    linkStyle 6 stroke:#6366F1
    linkStyle 11 stroke:#6366F1
    linkStyle 13 stroke:#94A3B8
```

**How to read it.** Each horizontal band is an actor (the learner, the orchestrator session,
three kinds of subagent, GitHub); read top to bottom. The solid path is the happy path: plan,
build, walk through, review, re-measure, push, pause, answer, grade, advance. The indigo
arrows are the loops that make the process trustworthy. An adversarial reviewer who
**refutes** a claim sends the work back to Build; a verifier who **disagrees** with a number
does the same. Nothing reaches GitHub until both have passed it. The push happens *before*
the learner answers the explain-it-back questions, so the learner is graded on work that is
already public and fixed, not on a moving target.

### 4. Entity-relationship diagram

```mermaid
---
title: "Stored tables and JSON contract"
---
erDiagram
    yf_download["yf.download frame, MultiIndex (Price, Ticker)"] {
        datetime64_s Date PK
        float64 Close
        float64 High
        float64 Low
        float64 Open
        int64 Volume
    }
    raw_manifest["raw snapshot manifest"] {
        char(64) sha256 PK
        text file
        int rows
        date first_date
        date last_date
        date request_start
        date request_end
        bool request_auto_adjust
        text yfinance_version
        timestamp_utc downloaded_at
    }
    envelope {
        text artifact PK
        semver schema_version
        timestamp_utc generated_at
        text source_commit
    }
    meta {
        text artifact PK, FK
        text project
        text title
        text ticker
    }
    meta_window {
        text name PK
        text artifact FK
        date start
        date end_exclusive
    }
    meta_milestone {
        int id PK
        text artifact FK
        text slug
        text title
        text status
    }
    meta_artifact {
        text name PK, FK
        text artifact FK
    }
    prices {
        text artifact PK, FK
        char(64) source_raw_sha256 FK
        text price_basis
        float64 splits_train_fraction
    }
    price_row {
        date date PK
        text artifact FK
        float64 close_usd
        float64 log_close
        text segment
    }
    decomposition_row {
        date date PK, FK
        text artifact FK
        float64 observed_log
        float64 trend_log "nullable"
        float64 seasonal_log
        float64 resid_log "nullable"
    }
    unit_root_test {
        text id PK
        text artifact FK
        int d
        float64 adf_p_value
        float64 kpss_p_value
        text kpss_p_value_bound "nullable"
        text verdict
    }
    stationarity_row {
        text transform PK, FK
        date date PK, FK
        float64 value
        float64 roll12_mean "nullable"
        float64 roll252_mean "nullable"
    }
    acf_pacf_row {
        text transform PK, FK
        int lag PK
        float64 acf
        float64 pacf
        float64 acf_band
        float64 pacf_band
    }
    aic_cell {
        int d PK
        int p PK
        int q PK
        text trend PK
        text artifact FK
        text status
        float64 aic "nullable"
        float64 delta_aic "nullable"
        bool converged "nullable"
        text error "nullable"
    }
    fit_param {
        text model_id PK
        text name PK
        text artifact FK
        text library_name
        float64 value
        float64 std_err "nullable"
    }
    residual_row {
        date date PK, FK
        text artifact FK
        float64 resid
        float64 resid_std
    }
    forecast_method {
        text id PK
        text artifact FK
        text kind
        text model_id "nullable"
    }
    forecast_row {
        text method PK, FK
        text segment PK
        date date PK, FK
        int step
        float64 mean_log
        float64 lower_log "nullable"
        float64 upper_log "nullable"
        float64 mean_usd
        float64 actual_usd
    }
    metric_row {
        text method PK, FK
        text segment PK
        int n
        float64 rmse_usd
        float64 mae_usd
        float64 mape_pct
        float64 rmse_ratio_to_random_walk "nullable"
    }
    envelope ||--|| meta : "wraps"
    envelope ||--o| prices : "wraps"
    raw_manifest ||--o{ prices : "derived from"
    prices ||--|{ price_row : "rows"
    meta ||--|{ meta_window : "windows"
    meta ||--|{ meta_milestone : "milestones"
    meta ||--|{ meta_artifact : "artifacts"
    envelope ||--|| meta_artifact : "names"
    unit_root_test ||--|{ stationarity_row : "series"
    unit_root_test ||--|{ acf_pacf_row : "lags"
    forecast_method ||--|{ forecast_row : "forecasts"
    forecast_method ||--|{ metric_row : "scored"
    price_row ||--o{ forecast_row : "actual"
    price_row ||--o{ decomposition_row : ""
    envelope ||--o{ decomposition_row : ""
    envelope ||--o{ unit_root_test : ""
    price_row ||--o{ stationarity_row : ""
    envelope ||--o{ aic_cell : ""
    envelope ||--o{ fit_param : ""
    price_row ||--o{ residual_row : ""
    envelope ||--o{ residual_row : ""
    envelope ||--o{ forecast_method : ""
```

**How to read it.** Two worlds share this page.

**Left: the raw side.** `yf.download frame` is exactly what yfinance 1.7.0 returns for one
ticker with its defaults: a `Date` index (tz-naive for daily bars, `datetime64[s]` under
pandas 3.1) and five columns, `Close`, `High`, `Low`, `Open` and `Volume`, in that alphabetical
order. Because `auto_adjust=True` is the default, `Close` is the dividend- and split-adjusted
close, and there is **no** `Adj Close` column. By default the columns are a two-level
MultiIndex named `(Price, Ticker)`, so the close is addressed as `df[("Close", "AAPL")]`;
passing `multi_level_index=False` flattens it to plain `Close`. (Verified offline by running
the real `download` path with only the HTTP response faked; sources:
`yfinance/multi.py:55-59, 209-229`, `yfinance/utils.py:506-523`,
`yfinance/scrapers/history.py:595-624`.) The raw file stores this frame flattened to the
`Price` level. The manifest records its SHA-256, which the `prices` artifact quotes, linking a
published number back to one exact download.

**Right: the contract side.** Every artifact hangs off `envelope` by its `artifact` key; that
relation is how the JSON nests (`envelope.data` holds the rows). Row tables are keyed the way
the app looks them up: a forecast row by **method + segment + date**, an AIC cell by
**d + p + q + trend**, an autocorrelation by **transform + lag**. `price_row.date` is the
spine: decomposition rows, stationarity rows, residuals and forecast actuals all point at it.
A column with the comment `"nullable"` can be `null` (the kit's SVG in
[`out/erd.svg`](out/erd.svg) draws the same columns as `type?`). Each one is null for a documented reason (the
moving-average edges of a decomposition, a failed fit, the random walk's missing interval).

How the boxes map onto the JSON in [`contract.md`](contract.md):

- **Columns that are not JSON fields.** `artifact` names the envelope a payload or row sits in.
  `transform` on `stationarity_row` and `acf_pacf_row`, and `model_id` on `fit_param`, name the
  parent object a row is nested under. `name` on `meta_window` is a key of `data.windows`
  (`course` or `oos`), and `name` on `meta_artifact` is one string of `data.artifacts`.
- **Every other column is a JSON field.** Each box shows a subset of its object's fields, not
  all of them. A field inside a nested object is written with an underscore: `source_raw_sha256`
  is `source.raw_sha256`, `splits_train_fraction` is `splits.train_fraction` and `adf_p_value`
  is `adf.p_value`.
- **`meta` is the only artifact implemented so far** (milestone 0). Its windows are nested
  objects, `data.windows.course` and `data.windows.oos`, each with `start` and
  `end_exclusive`, so they are drawn as `meta_window` rows keyed by window name.

One caveat when reading the raw side: if yfinance hits an error, `download` does not raise. It
logs the error and returns an **empty** frame, whose columns include an `Adj Close` that a
successful call would not have (`yfinance/multi.py:191-208, 298-302`; `yfinance/utils.py:269-276`).
The download step must check for an empty frame explicitly.

### 5. Contract sequence

```mermaid
---
title: "One artifact from export to screen"
---
sequenceDiagram
    autonumber
    participant exporter as export_app_data.py
    participant pycontract as contract.py
    participant disk as app/public/data
    participant loader as loadArtifact
    participant tsparser as contract.ts
    participant view as React view
    exporter->>pycontract: make_envelope(artifact, payload)
    Note right of pycontract: commit + time from provenance.py
    pycontract-->>exporter: envelope dict
    exporter->>pycontract: validate_envelope + dumps
    alt invalid envelope, or NaN, Infinity or an unsafe integer in payload
        pycontract-->>exporter: problems list, or dumps raises
        exporter->>exporter: exit 1
        Note right of exporter: nothing is written
    else envelope valid, every float finite, every integer safe
        pycontract-->>exporter: JSON text (sorted keys, indent 2)
        exporter->>disk: write artifact.json
    end
    loader->>disk: fetch data/artifact.json
    disk-->>loader: response body
    loader->>loader: res.json() parses the body
    Note right of loader: a bare NaN token throws here
    alt network or HTTP error, or not valid JSON
        loader->>view: load error panel
    else parsed
        loader->>tsparser: parseEnvelope(raw)
        alt major ≠ 1, or a key missing, unknown or invalid
            tsparser-->>loader: ok#58; false, errors[]
            loader->>view: error panel listing every problem
        else envelope valid
            tsparser-->>loader: typed envelope
            Note right of loader: loadArtifact also rejects an artifact name mismatch
            loader->>tsparser: parse payload
            Note right of tsparser: unknown keys in data are ignored
            tsparser-->>loader: typed data
            loader->>view: render
        end
    end
```

**How to read it.** Time runs downward; each vertical line is one participant. The top half
is export time on the developer's machine, and the bottom half is load time in a visitor's
browser. They never run together: they meet only through the file on disk. Each half has a
refusal branch. Python refuses to *write* an invalid envelope, or a payload containing NaN,
Infinity or an integer outside JavaScript's safe range ±(2^53−1): `dumps` raises, and nothing
is written. The app refuses to *render* a file it cannot parse, a major version other than 1,
an envelope with a missing, unknown or invalid top-level key, or an artifact name that does
not match the file it asked for. Either way the failure shows up next to its cause, not as a
silently wrong chart. The note on step 16 is the other half of the versioning policy: the
envelope's top level is closed, but the app ignores unknown keys inside `data`, which is what
lets a minor version add fields safely ([`contract.md` §1](contract.md#1-envelope-rules-fixed)).
