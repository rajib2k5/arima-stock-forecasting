# Graph Report - arima-stock-forecasting  (2026-10-28)

## Corpus Check
- 91 files · ~72,375 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: .mmd 5, (none) 4, .css 1)

## Summary
- 1044 nodes · 2008 edges · 60 communities (52 shown, 8 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 110 edges (avg confidence: 0.91)
- Token cost: 384,643 input · 0 output

## Community Hubs (Navigation)
- Testing Theory and IEEE 754
- App Artifact Loader
- Determinism and Provenance Guards
- Blender Layout Tests
- 3D AIC Axes Preview
- App Purity and Real-data Test
- Generated Notebooks
- ADRs and Background Docs
- Blender Hero Script
- Data Location Config
- TS App Config
- Pins and Supply Chain
- Animated Diagram Components
- Blender Slab and Bar Layout
- Architecture Diagram Spec
- Process Diagram Spec
- App Dev Dependencies
- App Shell and Theme
- TS Node Config
- ERD Diagram Spec
- App Runtime Dependencies
- App Shell Tests
- Forecast Evaluation Plan
- Contract Sequence Spec
- Study Windows and Meta Payload
- Data Placement Decisions
- Data Flow Diagram Spec
- Export Tool Tests
- Stationarity Plan (M2)
- Order Selection Grid
- Blender Camera Math
- EDA and Fit Artifacts
- Lint Config
- Accuracy Metrics and Back-transform
- Blender Materials
- npm Scripts
- Line Chart Component
- Residual Diagnostics Theory
- Random Walk and Efficient Markets
- App Entry Point
- Blender Render Docs
- ARIMA and Differencing Theory
- Forecast Comparison Tests
- Histogram and Heatmap Charts
- Course Leakage Problem
- Unit-root Test Theory
- Blender Render Config
- Vite Build Config
- Number Formatting
- Volatility Clustering (Next Project)
- The Drift Trap
- Calendar Test Helper
- TS Project References
- Open Owner Questions
- jsdom Test Env
- Exact Pin Policy
- Jarque-Bera Test
- Project Root

## God Nodes (most connected - your core abstractions)
1. `make_envelope()` - 30 edges
2. `source_commit()` - 26 edges
3. `validate_envelope()` - 25 edges
4. `vitest` - 21 edges
5. `parseEnvelope()` - 20 edges
6. `compilerOptions` - 20 edges
7. `dumps()` - 18 edges
8. `build_time()` - 17 edges
9. `compilerOptions` - 16 edges
10. `new_repo()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Relative BASE_URL with vite base ./` --rationale_for--> `loadArtifact()`  [EXTRACTED]
  docs/milestones/00-scaffold.md → app/src/data/loadArtifact.ts
- `Failing closed` --rationale_for--> `hasWebGL()`  [EXTRACTED]
  docs/milestones/00-scaffold.md → app/src/lib/capabilities.ts
- `Half-open StudyWindow [start, end_exclusive)` --rationale_for--> `StudyWindow`  [EXTRACTED]
  docs/milestones/00-scaffold.md → src/arima_forecasting/config.py
- `Refuse naive datetimes in make_envelope` --rationale_for--> `make_envelope()`  [EXTRACTED]
  docs/milestones/00-scaffold.md → src/arima_forecasting/contract.py
- `Deterministic serialisation (sort_keys, indent 2, one trailing newline)` --rationale_for--> `dumps()`  [EXTRACTED]
  docs/milestones/00-scaffold.md → src/arima_forecasting/contract.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Export-to-render data flow for the meta.json artifact (Python writes, React draws)** — src_arima_forecasting_export_meta_payload, src_arima_forecasting_provenance_build_time, src_arima_forecasting_provenance_source_commit, src_arima_forecasting_contract_make_envelope, src_arima_forecasting_contract_validate_envelope, src_arima_forecasting_contract_dumps, tools_export_app_data, app_src_data_loadartifact_loadartifact, app_src_lib_contract_parseenvelope, app_src_lib_contract_parsemeta, app_src_data_usemeta_usemeta, app_src_views_aboutview_aboutview [EXTRACTED 1.00]
- **Guards that make exports and notebooks byte-reproducible** — docs_concepts_01_reproducibility_and_contracts_deterministic_outputs, docs_milestones_00_scaffold_sorted_keys_deterministic_json, docs_milestones_00_scaffold_source_date_epoch_ascii_digits, docs_milestones_00_scaffold_generated_notebooks_fixed_cell_ids [EXTRACTED 1.00]
- **Residual diagnostics suite: Ljung-Box, Jarque-Bera and ARCH-LM** — docs_concepts_00_background_ljung_box, docs_concepts_00_background_jarque_bera, docs_concepts_00_background_arch_lm, docs_concepts_00_background_volatility_clustering_garch [EXTRACTED 1.00]
- **Static, walk-forward and random-walk forecasts compared like for like** — docs_architecture_readme_static_multi_step_forecast, docs_architecture_readme_walk_forward_one_step_forecast, docs_architecture_readme_random_walk_baseline, docs_architecture_readme_back_transform, docs_architecture_readme_forecast_metrics [EXTRACTED 1.00]
- **Checks that keep Python exporter and TypeScript app in agreement** — docs_adr_0001_python_computes_app_visualises_drift_checks, docs_architecture_contract_who_checks_what, app_readme_realdata_contract_test, docs_architecture_readme_contract_sequence_diagram, docs_architecture_contract_versioning_policy [INFERRED 0.85]
- **Four mistakes in the sample course and the note that measures them** — docs_prfaq_mistake_leakage, docs_prfaq_mistake_one_shot_static_forecast, docs_prfaq_mistake_no_baseline, docs_prfaq_mistake_median_as_expected_price, docs_prfaq_where_sample_goes_wrong_note [EXTRACTED 1.00]

## Communities (60 total, 8 thin omitted)

### Community 0 - "Testing Theory and IEEE 754"
Cohesion: 0.05
Nodes (53): Run it: export data, npm ci, npm run dev / verify / preview, Competent programmer hypothesis, Coupling effect, DeMillo, Lipton and Sayward (1978) Hints on Test Data Selection, Equivalent mutant, IEEE 754 NaN and infinity, IEEE 754-2019 Standard for Floating-Point Arithmetic, JSON numbers become doubles (MAX_SAFE_INTEGER precision loss) (+45 more)

### Community 1 - "App Artifact Loader"
Cohesion: 0.07
Nodes (55): Pure contract parser: parseEnvelope and parseMeta, loadArtifact: the only I/O, with typed load errors, FetchLike, loadArtifact(), LoadResult, messageOf(), loadMeta(), MetaState (+47 more)

### Community 2 - "Determinism and Provenance Guards"
Cohesion: 0.07
Nodes (35): Deterministic outputs, SOURCE_DATE_EPOCH specification (Reproducible Builds), build_time(), _git(), source_commit(), ignoring_rule(), test_a_new_file_in_app_src_data_is_not_ignored_either(), test_files_the_app_needs_are_not_ignored() (+27 more)

### Community 3 - "Blender Layout Tests"
Cohesion: 0.07
Nodes (43): by_key(), dry_run(), five_slabs(), load_layout(), overlaps(), run_hero(), single_slab(), test_a_d_whose_fits_all_failed_keeps_its_slot() (+35 more)

### Community 4 - "3D AIC Axes Preview"
Cohesion: 0.08
Nodes (38): Lazy-loaded 3D AIC axes preview with WebGL2 fallback and reduced-motion handling, AIC_AXIS_HEIGHT, assertHeight(), assertOrderMax(), AxisSpec, AxisTick, buildAxes(), defaultView() (+30 more)

### Community 5 - "App Purity and Real-data Test"
Cohesion: 0.06
Nodes (32): Real-data contract test over committed public/data JSON, ENTRIES, FILES, PAYLOAD_PARSERS, PayloadResult, stemOf(), Byte-identical exports via SOURCE_DATE_EPOCH, Rejected option A: Jupyter notebooks only (+24 more)

### Community 6 - "Generated Notebooks"
Cohesion: 0.07
Nodes (16): execute(), kernel_name(), load_builder(), run_builder(), test_cli_check_passes_on_the_committed_notebooks(), test_cli_write_then_check_then_detect_stale_and_missing(), test_committed_notebook_equals_the_builder_output(), test_notebook_build_is_byte_deterministic_and_clean() (+8 more)

### Community 7 - "ADRs and Background Docs"
Cohesion: 0.11
Nodes (31): ADR-0001: Python computes, app visualises, ADR-0002: Order selection, Data contract (docs/architecture/contract.md), Architecture README (docs/architecture/README.md), Background: forecasting a daily stock price with ARIMA, from first principles, Akaike (1974) A new look at the statistical model identification, Durbin and Koopman (2012) Time Series Analysis by State Space Methods, Harvey (1989) Forecasting, Structural Time Series Models and the Kalman Filter (+23 more)

### Community 8 - "Blender Hero Script"
Cohesion: 0.12
Nodes (18): build_layout(), clear_previous(), describe(), _fmt(), _load_bpy(), main(), make_camera(), make_key_light() (+10 more)

### Community 9 - "Data Location Config"
Cohesion: 0.11
Nodes (14): data_root(), raw_dir(), test_data_root_default_expands_tilde(), test_data_root_empty_string_counts_as_unset(), test_data_root_ignores_unrelated_variables(), test_data_root_override_expands_tilde(), test_data_root_reads_the_real_environment_by_default(), test_data_root_uses_env_override() (+6 more)

### Community 10 - "TS App Config"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, jsx, lib, module, moduleDetection, moduleResolution, noEmit (+13 more)

### Community 11 - "Pins and Supply Chain"
Cohesion: 0.12
Nodes (13): Dev versus runtime dependencies, Exact pins, ranges and lockfiles, Lockfiles and integrity hashes (uv.lock, package-lock.json), npm audit, npm docs: npm-audit, Supply-chain hygiene, uv documentation: The lockfile, Exact pins plus lockfiles (+5 more)

### Community 12 - "Animated Diagram Components"
Cohesion: 0.18
Nodes (17): Architecture page (three animated diagrams and a 3D wiring check), Reusable animated diagram components (architecture, sequence, activity SVG), ActEdge, ActivityDiagram(), ActNode, ArchDiagram(), ArchLayer, Defs() (+9 more)

### Community 13 - "Blender Slab and Bar Layout"
Cohesion: 0.14
Nodes (10): aic_bars(), architecture_slabs(), Bar, BarSet, _int(), Layer, _non_negative(), _positive() (+2 more)

### Community 14 - "Architecture Diagram Spec"
Cohesion: 0.11
Nodes (18): direction, edges, from, label, style, to, kind, lanes (+10 more)

### Community 15 - "Process Diagram Spec"
Cohesion: 0.11
Nodes (18): direction, edges, from, label, style, to, kind, lanes (+10 more)

### Community 16 - "App Dev Dependencies"
Cohesion: 0.11
Nodes (17): devDependencies, eslint@9.39.5, @testing-library/jest-dom@6.9.1, @testing-library/react@16.3.3, @types/react@19.2.18, @types/react-dom@19.2.5, @types/three@0.186.0, typescript@5.8.3 (+9 more)

### Community 17 - "App Shell and Theme"
Cohesion: 0.21
Nodes (9): AppShell(), readRoute(), ShellPage, StorageLike, applyTheme(), getStoredTheme(), setStoredTheme(), themeKey() (+1 more)

### Community 18 - "TS Node Config"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+9 more)

### Community 19 - "ERD Diagram Spec"
Cohesion: 0.11
Nodes (17): fk, name, nullable, pk, type, entities, columns, id (+9 more)

### Community 20 - "App Runtime Dependencies"
Cohesion: 0.15
Nodes (16): dependencies, @fontsource/inter@5.3.0, react@19.2.8, react-dom@19.2.8, @react-three/drei@10.7.9, @react-three/fiber@9.8.1, three@0.186.1, name (+8 more)

### Community 21 - "App Shell Tests"
Cohesion: 0.20
Nodes (10): STORE, PAGES, shell(), STORE, memMap, memoryFallback, resetMemoryFallback(), safeStorage() (+2 more)

### Community 22 - "Forecast Evaluation Plan"
Cohesion: 0.22
Nodes (16): Artifact forecasts (M4): rows keyed by method, segment and date, Artifact metrics (M4): RMSE, MAE, MAPE, ratio to random walk, Diebold-Mariano, Back-transform exp(mean) and exp(bounds) before scoring in dollars, Diagram 2: Data flow from prices to metrics, Forecast metrics RMSE, MAE, MAPE in dollars, Log price transform ln(close), pointwise and leak-free, Random-walk baseline: forecast equals previous close, Split by position: 90% train / 10% test, plus OOS window (+8 more)

### Community 23 - "Contract Sequence Spec"
Cohesion: 0.15
Nodes (16): messages, when, autonumber, kind, messages, alt, from, kind (+8 more)

### Community 24 - "Study Windows and Meta Payload"
Cohesion: 0.14
Nodes (10): StudyWindow, meta_payload(), _window(), test_study_window_accepts_a_one_day_window(), test_meta_payload_is_plain_json_with_no_nan(), test_meta_payload_matches_the_agreed_contract_exactly(), test_meta_payload_milestones_are_numbered_in_order_with_one_current(), test_meta_payload_returns_a_fresh_object_each_call() (+2 more)

### Community 25 - "Data Placement Decisions"
Cohesion: 0.19
Nodes (12): App README (React app that visualises the JSON), About page (project, analysis path, windows, milestones from meta.json), Yahoo back-adjusts history for every new dividend (auto_adjust=True), Artifact meta (M0, implemented): project, ticker, windows, milestones, artifacts, Diagram 1: Architecture (Source, Raw cache, Python core, Delivery, App), Raw price snapshot in $VOL_DATA_DIR/arima-stock-forecasting/raw, Snapshot manifest (sha256, rows, yfinance version, download time), Yahoo Finance chart API (external source) (+4 more)

### Community 26 - "Data Flow Diagram Spec"
Cohesion: 0.13
Nodes (14): direction, edges, from, label, style, to, kind, nodes (+6 more)

### Community 27 - "Export Tool Tests"
Cohesion: 0.21
Nodes (10): load_tool(), run_tool(), test_tool_asks_git_about_this_repo_not_the_current_folder(), test_tool_default_output_folder_is_app_public_data(), test_tool_fails_on_a_malformed_source_date_epoch(), test_tool_never_writes_nan_to_disk(), test_tool_overwrites_an_existing_file(), test_tool_refuses_to_write_an_envelope_that_fails_validation() (+2 more)

### Community 28 - "Stationarity Plan (M2)"
Cohesion: 0.24
Nodes (11): ADF test (null: unit root), KPSS p-values clipped to [0.01, 0.10], carried as p_value_bound, KPSS test (null: stationary), pmdarima auto_arima cross-check on the training split (course settings and defaults), Verified library behaviour table (statsmodels 0.15.0, pmdarima 2.1.1, pandas 3.1.0, numpy 2.5.4), Artifact acf_pacf (M2): autocorrelations with confidence bands, Artifact stationarity (M2): ADF/KPSS per d, rolling stats, d decision, App view: stationarity lab (toggle differencing, watch ADF and KPSS verdicts) (+3 more)

### Community 29 - "Order Selection Grid"
Cohesion: 0.23
Nodes (10): AIC grid of 144 statsmodels fits (p,q in 0-5 across d and trend variants), loglikelihood_burn and diffuse initial states in SARIMAX, Course problem 2: statsmodels refit silently drops the drift pmdarima selected, Course problem 3: stepwise search visits only 5 of 36 (p,q) cells, Selection rule: lowest AIC among ok cells at d_selected, ties by fewer parameters then smaller p+q, Simulated log-price random walk with drift (seed 20261028) used for probes, Artifact aic_grid (M2): every (d,p,q,trend) fit, selection, pmdarima_check, App view: 3D landscape of AIC over (p,q) for each d (+2 more)

### Community 30 - "Blender Camera Math"
Cohesion: 0.23
Nodes (6): aim_euler(), bounds(), camera_for(), limiting_fov_deg(), stack_extent(), _unit()

### Community 31 - "EDA and Fit Artifacts"
Cohesion: 0.26
Nodes (11): Artifact eda (M1): summary, KDEs, seasonal decomposition, Artifact fit (M3): selected model and course_refit parameter tables, Artifact prices (M1): cleaned daily series, source provenance, splits, Artifact residuals (M3): residual series, KDE, QQ, ACF, Ljung-Box, Jarque-Bera, ARCH-LM, Diagram 4: Entity-relationship diagram of stored tables and JSON contract, App view: price and log-price explorer, App view: residual diagnostics, Six staged milestones 0 to 5, each paused for review (+3 more)

### Community 32 - "Lint Config"
Cohesion: 0.18
Nodes (10): @eslint/js@9.39.5, eslint-plugin-react-hooks@5.2.0, eslint-plugin-react-refresh@0.4.26, globals@16.5.0, typescript-eslint@8.68.0, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh (+2 more)

### Community 33 - "Accuracy Metrics and Back-transform"
Cohesion: 0.22
Nodes (7): Accuracy metrics: RMSE, MAE, MAPE, Back-transforming a log forecast: median versus mean, Gneiting (2011) Making and evaluating point forecasts, Hyndman (2014) Errors on percentage errors, Hyndman and Koehler (2006) Another look at measures of forecast accuracy, Jensen's inequality (log vs simple return), Relative-to-naive measures: MASE and Theil U2

### Community 34 - "Blender Materials"
Cohesion: 0.24
Nodes (6): build_world(), _ensure_node_tree(), _find_node(), make_material(), hex_to_rgb(), srgb_to_linear()

### Community 35 - "npm Scripts"
Cohesion: 0.22
Nodes (9): scripts, build, coverage, dev, lint, preview, test, test:watch (+1 more)

### Community 36 - "Line Chart Component"
Cohesion: 0.28
Nodes (4): layoutLegend(), LineChart(), pad0, Series

### Community 37 - "Residual Diagnostics Theory"
Cohesion: 0.25
Nodes (9): ARCH-LM test for volatility clustering, Box and Pierce (1970) Distribution of residual autocorrelations in ARIMA models, Engle (1982) Autoregressive conditional heteroscedasticity (ARCH), Hyndman and Athanasopoulos: Forecasting: Principles and Practice (3rd ed.), Ljung-Box residual autocorrelation test, Ljung and Box (1978) On a measure of lack of fit in time series models, What this repo does differently (preview of milestones 1-5), Static versus walk-forward (rolling-origin) evaluation (+1 more)

### Community 38 - "Random Walk and Efficient Markets"
Cohesion: 0.28
Nodes (9): Campbell and Thompson (2008) Predicting excess stock returns out of sample, Efficient markets: fair game, submartingale, random walk, Fama (1970) Efficient capital markets, Lo and MacKinlay (1988) Stock market prices do not follow random walks, Meese and Rogoff (1983) Empirical exchange rate models of the seventies, Random-walk forecast intervals widen like sqrt(h), Empirical record: the random walk is the bar, Random walk with drift (null model for prices) (+1 more)

### Community 39 - "App Entry Point"
Cohesion: 0.36
Nodes (5): app/index.html (Vite HTML entry point), App(), useMeta(), ArchitectureView(), Vite

### Community 40 - "Blender Render Docs"
Cohesion: 0.25
Nodes (7): Five architecture layers: Source, Raw cache, Python core, Delivery, App, Blender MCP run: exec the script via execute_blender_code (no factory reset), --dry-run: print layout without importing bpy, After-first-render checklist: runs, framing, labels, exposure, bevel smoothness, Scene of five stacked layers: Source, Raw cache, Python core, Delivery, App, Headless CLI run: blender --background --python-exit-code 1 --python ..., Hero architecture render (bpy script, five slabs, transparent PNG)

### Community 41 - "ARIMA and Differencing Theory"
Cohesion: 0.29
Nodes (6): ARIMA(p, d, q), Box and Jenkins (1970) Time Series Analysis: Forecasting and Control, Plosser and Schwert (1977) Estimation of a non-invertible MA process: overdifferencing, Stationarity and invertibility conditions, Unit roots, backshift operator and differencing (I(d)), Weak stationarity

### Community 42 - "Forecast Comparison Tests"
Cohesion: 0.29
Nodes (7): Clark and McCracken (2001) Tests of equal forecast accuracy for nested models, Clark and West (2007) Approximately normal tests for nested models, Diebold (2015) Comparing predictive accuracy, twenty years later, Diebold and Mariano (1995) Comparing predictive accuracy, Diebold-Mariano test of equal forecast accuracy, Giacomini and White (2006) Tests of conditional predictive ability, Harvey, Leybourne and Newbold (1997) Testing equality of prediction MSEs

### Community 43 - "Histogram and Heatmap Charts"
Cohesion: 0.73
Nodes (4): binValues(), Heatmap(), Histogram(), normalizeMatrix()

### Community 44 - "Course Leakage Problem"
Cohesion: 0.33
Nodes (5): Course recipe: auto_arima on full series, 90/10 split, statsmodels refit, one static forecast, fillna(method='ffill') no longer exists in pandas 3.1.0; use .ffill(), Course problem 1: order chosen on the full series leaks the test period, Sample-course mistake 1: order picked on the whole series, test included, pandas

### Community 45 - "Unit-root Test Theory"
Cohesion: 0.40
Nodes (5): Augmented Dickey-Fuller test, Dickey and Fuller (1979) Distribution of estimators with a unit root, Kwiatkowski, Phillips, Schmidt and Shin (1992) KPSS stationarity test, KPSS test, Said and Dickey (1984) Testing for unit roots in ARMA models of unknown order

### Community 46 - "Blender Render Config"
Cohesion: 0.33
Nodes (3): choose_engine(), configure_render(), _here()

### Community 47 - "Vite Build Config"
Cohesion: 0.40
Nodes (4): vite@7.3.7, @vitejs/plugin-react@4.7.0, vite, @vitejs/plugin-react

### Community 48 - "Number Formatting"
Cohesion: 0.70
Nodes (3): bps(), fmt(), pct()

### Community 50 - "Volatility Clustering (Next Project)"
Cohesion: 0.60
Nodes (5): ACF and PACF identification (weak on returns), Bollerslev (1986) Generalized ARCH, Cont (2001) Empirical properties of asset returns: stylized facts, Ratliff-Crain et al. (2023) Revisiting stylized facts for modern stock markets, Volatility clustering and GARCH (next project)

### Community 51 - "The Drift Trap"
Cohesion: 0.80
Nodes (3): pmdarima auto_arima defaults, statsmodels ARIMA drops the drift when d>=1, The drift trap: statsmodels vs pmdarima trend mismatch

### Community 54 - "Open Owner Questions"
Cohesion: 0.67
Nodes (3): Open question: should prices.json be committed?, Diebold-Mariano test against the random walk, Open questions for the owner at the milestone-0 checkpoint

## Knowledge Gaps
- **60 isolated node(s):** `arima-stock-forecasting`, `Closed versus open enums`, `JSON numbers become doubles (MAX_SAFE_INTEGER precision loss)`, `Competent programmer hypothesis`, `Coupling effect` (+55 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 334 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `vitest` connect `App Shell Tests` to `App Artifact Loader`, `3D AIC Axes Preview`, `App Purity and Real-data Test`, `Line Chart Component`, `Histogram and Heatmap Charts`, `Animated Diagram Components`, `App Dev Dependencies`, `Number Formatting`, `App Shell and Theme`, `App Runtime Dependencies`?**
  _High betweenness centrality (0.192) - this node is a cross-community bridge._
- **What connects `arima-stock-forecasting`, `Closed versus open enums`, `JSON numbers become doubles (MAX_SAFE_INTEGER precision loss)` to the rest of the system?**
  _60 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Testing Theory and IEEE 754` be split into smaller, more focused modules?**
  _Cohesion score 0.05473684210526316 - nodes in this community are weakly interconnected._
- **Why does `ADR-0002: Order selection` connect `ADRs and Background Docs` to `Residual Diagnostics Theory`, `Random Walk and Efficient Markets`, `Unit-root Test Theory`, `The Drift Trap`, `Stationarity Plan (M2)`, `EDA and Fit Artifacts`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Should `App Artifact Loader` be split into smaller, more focused modules?**
  _Cohesion score 0.06924882629107981 - nodes in this community are weakly interconnected._
- **Why does `Data contract (docs/architecture/contract.md)` connect `ADRs and Background Docs` to `Testing Theory and IEEE 754`, `Determinism and Provenance Guards`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Should `Determinism and Provenance Guards` be split into smaller, more focused modules?**
  _Cohesion score 0.0726775956284153 - nodes in this community are weakly interconnected._