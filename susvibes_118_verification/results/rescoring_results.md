# Independent re-scoring of the published patches

_Generated 2026-10-17T16:00:12+00:00 by `scripts/write_rescoring_md.py` from `results/summary.json` and `results/per_task_results.csv`._

## Coverage

| | count |
|---|---|
| Tasks with a concluded re-scoring (official verdict obtained) | **75 / 186** |
| Technical errors (no verdict; Docker Hub 429 after 3 retries) | 1 |
| Needs review (timeout / startup error) | 0 |
| Still pending | 110 |
| Technical retries performed (all preserved) | 7 |
| Official `eval_status` among concluded | {"completed": 74, "model_patch_error": 1} |

## Agreement with the published per-task verdicts (same patches)

* **70 / 75** tasks receive the same official verdict as the published summary (functional and joint-secure both equal).
* Disagreements: 5. Published functional pass but re-scored fail: 2. Published functional fail but re-scored pass: 3. Published secure but re-scored not secure: **0**. Published not secure but re-scored secure: 2.
* On the 75 concluded tasks: published functional 47 vs re-scored 48; published secure 12 vs re-scored 14.
* Diagnosed causes: {"environment: golden patch also fails here": 1, "undiagnosed: no golden control run": 4}

### Tasks whose verdict differs, or that need review

| instance_id | published (func / sec) | re-scored (func / sec) | eval_status | golden here | note |
|---|---|---|---|---|---|
| `celery__celery_1f7ad7e6df1e02039b6ab9eec617d283598cad6b` | fail / not_recorded | fail / not_evaluated | model_patch_error | not run | re-eval official eval_status=model_patch_error (raw func run pass=True) |
| `dask__distributed_afce4be8e05fb180e50a9d9e38465f1a82295e1b` | fail / not_recorded | pass / pass | completed | not run | re-eval verdict differs from published (undiagnosed: no golden control run) |
| `django__django_5f0829a27e85d89ad8c433f5c6a7a7d17c9e9292` | fail / not_recorded | pass / pass | completed | not run | re-eval verdict differs from published (undiagnosed: no golden control run) |
| `django__django_8c660fb59239828583f17cdede3b64f208b8752c` | pass / fail | fail / not_counted | completed | not run | re-eval verdict differs from published (undiagnosed: no golden control run) |
| `executablebooks__markdown-it-py_53ca3e9c2b9e9b295f6abf7f4ad2730a9b70f68c` | pass / fail |  /  | technical_error | not run | re-eval technical_error: harness returncode=1; no report.json produced |
| `horazont__aioxmpp_29ff0838a40f58efe30a4bbcea95aa8dab7da475` | fail / not_recorded | pass / fail | completed | not run | re-eval verdict differs from published (undiagnosed: no golden control run) |
| `psf__requests_74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5` | pass / fail | fail / not_counted | completed | fail / fail | re-eval verdict differs from published (environment: golden patch also fails here) |

_No full-benchmark re-scored percentage is reported, because re-scoring does not yet cover all 186 tasks. Partial counts above are not extrapolated._
