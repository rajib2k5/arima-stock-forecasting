# Knowledge graph (graphify)

A [graphify](https://github.com/safishamsi/graphify) knowledge graph of this repo's code and docs, built at milestone 0 (2026-10-28).

| File | What it is |
|---|---|
| [`graph.html`](graph.html) | The interactive graph: download it and open it in a browser, no server needed. GitHub shows only its source. |
| [`graph.svg`](graph.svg) | A static rendering of the same graph. |
| [`graph.json`](graph.json) | The raw graph: nodes, edges, communities and labels. |
| [`GRAPH_REPORT.md`](GRAPH_REPORT.md) | The audit report: god nodes, surprising connections, communities with cohesion scores, and suggested questions. |

## How it was built

- **Code** (73 files: Python, TypeScript, the diagram YAML specs, configs) was extracted structurally from the syntax tree. This is deterministic and used no LLM.
- **Docs** (13 Markdown/HTML files) were extracted semantically by two Claude subagents. Every edge is tagged `EXTRACTED` (stated in the source) or `INFERRED` (a reasoned link, with a confidence score). The subagents together reported 384,643 tokens; the split between input and output was not reported.
- The result: 1,044 nodes, 2,008 edges and 60 communities. 95% of edges are `EXTRACTED`, 5% `INFERRED`.

## Caveats

- **153 edges were dropped** because one endpoint was not a node in the graph. These are mostly doc-to-code references whose guessed node id did not match the id the syntax-tree pass gave the symbol. graphify's health check reported them as "dangling-endpoint edges". Some links from the walkthrough to the code are therefore missing.
- **The five app screenshots in `docs/images/` were left out** of semantic extraction on purpose. They add nothing the docs do not already say, and each would have needed its own vision pass.
- **Built before the milestone-0 review fixes.** The adversarial review then corrected some wording in the docs: for example, *why* AIC cannot be compared across different d, and several pmdarima details. The graph's nodes and links are unaffected, but its node text predates those fixes. The next milestone rebuilds the graph with `--update`.
