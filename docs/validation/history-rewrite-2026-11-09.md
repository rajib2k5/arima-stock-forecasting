# History rewrite: old and new commit SHAs

The owner asked for this rewrite on 2026-11-09. It was carried out on 2026-11-10.

## What changed

The commit messages of this repository held Claude attribution lines (`Co-Authored-By: Claude …`). At the owner's request, those lines were removed from every commit message. Commit messages that named an old SHA now name its new SHA.

Nothing else changed:

- **Trees.** Every new commit has the same tree as its old commit, byte for byte.
- **Authors and committers.** Names, e-mail addresses and dates are the same.

A commit's SHA covers its message, so every commit has a new SHA. On 2026-11-10, a check of all 12 pairs below confirmed:

- the same tree (`git rev-parse <sha>^{tree}`);
- the same author and committer fields (`git log -1 --format='%an|%ae|%at|%cn|%ce|%ct'`);
- no Claude line in any new message.

**Old SHAs on GitHub.** GitHub can still serve an old SHA by direct link for some time, for example `…/commit/2dec79f`. Such a link shows the old message. Use the new SHA.

## The map

| Old | New | Commit |
|---|---|---|
| `720705ff1d2491a35b6c806c7904b827fd12446c` | `2a29744559b5057caff7a9756e8bedb9ca1284b0` | Milestone 0: scaffold, JSON contract, app shell and design docs |
| `70a9dea7a6a2ab1badd5a40b394b32bfde8dda95` | `f949494dda68812e1a0270541893b380cef92d47` | Re-export meta.json so it names the milestone-0 commit |
| `bd2eab393f68cfacb109174cd052ade9b7a9ccf9` | `95ef804b61f8f54451aa7d0fb6b03f6ecdec0417` | Vendor vol-diagram-kit 7493b4b and set learning mode to queued |
| `2a52d8d2fd750db98886200272f7c78794415b93` | `777b23cbd44727fef133bd4acd0b60c6cbc1c673` | Milestone 1: data and EDA |
| `16366d1b5b4dba79dd495d00d13756797e82e550` | `2ca67afa07059f5cbf0a1a46481df2e355b824ad` | Re-export meta.json so it names the milestone-1 commit |
| `64276a1d504cbfa1b7822f0fc3b64196974c5ced` | `dc3691f26a135670224dee143ebbf8a0602b1d38` | Milestone 2: stationarity and identification |
| `d0051d17a9b678bcfbe0c1bd07a632c5d65ca826` | `c902cc4a1c627cd4982ba970194b74968fd66cf5` | Export milestone-2 app data from dc3691f |
| `c6ad7905ffb83e59755ae02306f01d9c0dd910e1` | `7bd8eb9281b3dc74564309d3b12eeb6bfac2c5e2` | Milestone 3: fit and diagnostics |
| `57491c11802307ea3fd384df004fc043d8ac9ded` | `5c18b6a297d0cfb849834f0217ffea008759477c` | Export milestone-3 app data from 7bd8eb9 |
| `2dec79fb710178bbb21d437008a6b34411e30f9d` | `800a0a8801124c06bd278f2ffbd7b9d3b9235f1c` | Milestone 4: forecast and evaluation |
| `25ec6657b73158143d69f7f891dad3832d6aa08e` | `0bfd7ba3a932ce86896bbce4f43bffad2c642eb0` | Export milestone-4 app data from 800a0a8 |
| `31b7aa1d7a38e6bbaa8ecb9144eae5da343e390f` | `3cecee2365bf3319cbaf27ef5c146724fa14eeb3` | Pre-register milestone-5 inference for the forecast comparisons |

The last commit was not yet pushed when the history was rewritten. It was replayed onto the new milestone-4 data commit with the same tree, author, committer and message.

## References in the files

A script replaced each old SHA with its new SHA. It replaced short and full forms, and kept the length of each one. Because each new commit has the same tree as its old commit, a sentence that names a commit stays true. For example, `git show 2a29744:<path>` shows the same file that `git show 720705f:<path>` showed.

A quote of what a file said is different. The rewrite did not change the files inside the old commits, so those files still hold old SHAs. For example, `git show 2ca67af:app/public/data/meta.json` still shows `source_commit` `2a52d8d…`, the old SHA of `777b23c`. A quote of such a file keeps the old SHA and says that it is old.

The script ran in two places:

1. **The commit that adds this file.** It changes nothing but SHAs, in files that were already committed:
   - docs and ledgers of milestones 0 to 3, and `DATA.md`;
   - all 18 files in `app/public/data/`. Their `source_commit` changed from `2dec79f…` to `800a0a8…`. Their `generated_at` and `data` did not change.
2. **The milestone-5 files**, before their first commit. These were written with old SHAs:
   - the walkthrough, the ledgers and the addendum, and `LEARNING_LOG.md`;
   - the tool `tools/comparison_inference.py`, and one comment in its test;
   - the two inference outputs, `docs/validation/m5-comparison-inference*` (`.json` and `.md`). One sentence in each names milestone 4's commit. That sentence changed in the tool and in its committed outputs alike. No number changed, and the tool was not run again.

After the milestone-5 code commit, `meta.json` was exported again from that commit, as planned.

Old SHAs are left in three files only:

- **This file.** It is the map.
- **`docs/validation/m2-code-review-ledger.md`, one line.** It quotes the `source_commit` that the six JSON files of the milestone-2 working tree held during its review: `2a52d8d...-dirty`. The line says that this is the old SHA of `777b23c`.
- **`docs/validation/m5-preregistration.md` (plan v1).** This plan is frozen. `tools/comparison_inference.py` pins its SHA-256 (`4a7e5090…`) and refuses to run if it changes, and a test checks that. The plan names milestone 4's commit as `2dec79f`. That commit is now `800a0a8`.

Plan v2, `docs/validation/m5-preregistration-v2.md`, held no old SHA and is unchanged. Its SHA-256 is still `39569d5cb6182cd55b55b7fada2bd937ef3aa784e02255486a255fa18ccef44d`.

**The input hashes in the inference outputs.** `m5-comparison-inference.json` and `m5-comparison-inference-v2.json` record the SHA-256 of their 8 input files from `app/public/data/`. Those hashes are of the files before the new `source_commit`. To get them back, put the old SHA back into each file and hash it:

```bash
for f in forecast_aic_static forecast_aic_walk_forward forecast_aic_refit forecast_bic_static \
         forecast_bic_walk_forward forecast_course_static forecast_course_walk_forward evaluation; do
  sed 's/800a0a8801124c06bd278f2ffbd7b9d3b9235f1c/2dec79fb710178bbb21d437008a6b34411e30f9d/' \
    "app/public/data/$f.json" | sha256sum
done
```

On 2026-11-10 this gave all 8 recorded hashes.

## How to check

This command lists every tracked file that still holds an old SHA, short or full:

```bash
git grep -l -E '(^|[^0-9a-f])(720705f|70a9dea|bd2eab3|2a52d8d|16366d1|64276a1|d0051d1|c6ad790|57491c1|2dec79f|25ec665|31b7aa1)'
```

It must print exactly three files: this file, `docs/validation/m2-code-review-ledger.md` and `docs/validation/m5-preregistration.md`.
