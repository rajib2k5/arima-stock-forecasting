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

Each diagram has a YAML source in [`specs/`](specs/) and a generated Mermaid file next to this
README. The blocks below are byte-for-byte copies of those `.mmd` files, so GitHub can draw them
inline. Do not edit the `.mmd` files or these blocks by hand.

The `.mmd` files are generated from the YAML specs by a shared diagram kit (the same kit also
renders SVG, PNG and draw.io versions). The kit is not public yet; the plan is to vendor it into
`tools/diagrams/` so that anyone can rebuild the diagrams. Until then, **the YAML specs are the
source of truth** and the `.mmd` files are committed outputs. The committed files were built
with kit commit `56aad83`, and only the Mermaid output is committed.

### 1. Architecture

```mermaid
---
title: "ARIMA stock forecasting architecture"
---
flowchart LR
    subgraph source["Source"]
        yahoo{{"Yahoo Finance<br/><small>chart API</small>"}}
        yfin(["yfinance 1.7.0<br/><small>download(), auto_adjust=True</small>"])
    end
    subgraph rawcache["Raw cache (outside git)"]
        rawfile[("Raw price snapshot<br/><small>$VOL_DATA_DIR/.../raw</small>")]
        manifest[("Snapshot manifest<br/><small>sha256, rows, version</small>")]
    end
    subgraph core["Python core"]
        config["config.py<br/><small>windows and data paths</small>"]
        pipeline[["arima_forecasting<br/><small>EDA, tests, grid, fit, forecasts</small>"]]
        contract["contract.py<br/><small>envelope, allow_nan=False</small>"]
        provenance["provenance.py<br/><small>commit + SOURCE_DATE_EPOCH</small>"]
    end
    subgraph delivery["Delivery (in git)"]
        exporter["export_app_data.py<br/><small>one file per artifact</small>"]
        jsonfiles[/"app/public/data<br/><small>versioned JSON envelopes</small>"/]
        notebooks[/"Notebooks<br/><small>built by build_notebooks.py</small>"/]
        reports[/"Reports<br/><small>result tables (from M4)</small>"/]
        pytests["pytest<br/><small>contract, sync, numbers</small>"]
    end
    subgraph webapp["App"]
        loader["loadArtifact<br/><small>refuses major ≠ 1</small>"]
        views("React 19 views<br/><small>explorer, lab, 3D AIC, fan</small>")
        vitest["vitest<br/><small>parses the real JSON files</small>"]
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

**How to read it.** Read left to right: data comes in from Yahoo on the left and ends up on
screen on the right. Each rounded box is a *lane*, meaning where a thing lives. The **Raw
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
flowchart LR
    ohlcv(["Daily OHLCV<br/><small>yfinance, adjusted</small>"])
    closepx["Adjusted close<br/><small>$, .ffill() if gaps</small>"]
    logpx["Log price<br/><small>ln(close)</small>"]
    diffs["Differences<br/><small>d = 1, 2 (pointwise, no leak)</small>"]
    splitpos["Split by position<br/><small>90% train / 10% test + OOS</small>"]
    unitroot[["ADF + KPSS<br/><small>train only → d</small>"]]
    grid[["AIC grid<br/><small>p, q 0–5, trend, per d</small>"]]
    autoarima[["auto_arima check<br/><small>train only</small>"]]
    fitmodel[["Fit ARIMA<br/><small>statsmodels, order + trend</small>"]]
    static[["Static multi-step<br/><small>one origin to horizon h</small>"]]
    walkfwd[["Walk-forward one-step<br/><small>params frozen, filter updated</small>"]]
    randwalk[["Random walk<br/><small>forecast = previous close</small>"]]
    backtx["Back-transform<br/><small>exp(mean), exp(bounds)</small>"]
    scoring["Metrics<br/><small>RMSE, MAE, MAPE; ratio to RW</small>"]
    artifacts[/"JSON artifacts<br/><small>prices … metrics</small>"/]
    ohlcv -->|"Close column"| closepx
    closepx --> logpx
    logpx --> diffs
    diffs --> splitpos
    splitpos -->|"train"| unitroot
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
    backtx -->|"vs actual $"| scoring
    scoring -->|"metrics"| artifacts
    backtx -.->|"forecasts"| artifacts
    grid -.->|"aic_grid"| artifacts
    unitroot -.->|"stationarity"| artifacts
    logpx -.->|"prices, eda"| artifacts
    classDef source fill:#E0F2FE,stroke:#0284C7,color:#0F172A
    class ohlcv source
    classDef process fill:#E0E7FF,stroke:#4F46E5,color:#0F172A
    class closepx,logpx,diffs,splitpos,backtx,scoring process
    classDef model fill:#EDE9FE,stroke:#7C3AED,color:#0F172A
    class unitroot,grid,autoarima,fitmodel,static,walkfwd,randwalk model
    classDef output fill:#D1FAE5,stroke:#059669,color:#0F172A
    class artifacts output
    linkStyle 7 stroke:#94A3B8
    linkStyle 17 stroke:#94A3B8
    linkStyle 18 stroke:#94A3B8
    linkStyle 19 stroke:#94A3B8
    linkStyle 20 stroke:#94A3B8
```

**How to read it.** This is the life of one number, from a daily price bar to a forecast
error. Everything before **Split by position** is pointwise: the log at day t uses only day t,
and the difference at day t uses days t and t−1. So it is safe to compute over the whole series.
Everything after the split that *estimates* something (the unit-root tests, the AIC grid, the
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
        kickoff("Start milestone<br/><small>learner says go</small>")
        answer("Answer questions<br/><small>predict-first, explain-it-back</small>")
    end
    subgraph orchestrator["Orchestrator session"]
        plan["Plan the milestone<br/><small>tasks + acceptance checks</small>"]
        walkthrough[/"Walkthrough<br/><small>+ predict-first questions</small>"/]
        pause["Pause<br/><small>hand over to the learner</small>"]
        grade["Grade answers<br/><small>gaps become follow-ups</small>"]
        advance[/"Next milestone<br/><small>meta.json status moves on</small>"/]
    end
    subgraph implementer["Implementer subagent"]
        build["Build<br/><small>code, tests, notebooks, export</small>"]
    end
    subgraph reviewer["Adversarial reviewer"]
        review[["Adversarial review<br/><small>evidence-gated; default is broken</small>"]]
    end
    subgraph verifier["Verifier subagent"]
        remeasure["Re-measure numbers<br/><small>every quoted figure</small>"]
    end
    subgraph github["GitHub"]
        push{{"Push<br/><small>commit + push to main</small>"}}
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
        text file_name
        text ticker
        date start
        date end_exclusive
        bool auto_adjust
        text yfinance_version
        timestamp_utc downloaded_at
        int rows
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
A column with the comment `"nullable"` can be `null` (the kit's SVG, which is not committed,
draws the same columns as `type?`). Each one is null for a documented reason (the
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
