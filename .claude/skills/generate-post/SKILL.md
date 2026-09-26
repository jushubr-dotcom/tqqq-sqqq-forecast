---
name: generate-post
description: Generate a Markdown post summarizing the latest TQQQ/SQQQ forecast from outputs/production_forecast.csv and post it to the repo's "Daily forecast" GitHub issue. Use when asked to generate, write, publish or post the forecast, a daily update, or a forecast summary.
---

# Generate and post the forecast

Turns the latest model output in `outputs/` into a readable post and publishes it.

## 1. Get the latest outputs

The GitHub Actions workflow commits new CSVs straight to `main`, so pull first:

```bash
git fetch origin main && git checkout origin/main -- outputs/
```

If `pandas` is missing: `pip install -q pandas numpy`.

## 2. Generate the post

```bash
python .claude/skills/generate-post/scripts/generate_post.py --out /tmp/forecast_post.md
```

- Defaults to the most recent `forecast_date`. Pass `--date YYYY-MM-DD` if the user names a day.
- If a model ran several times that day, its last row wins.
- The 3d signal uses the regime-filtered buy flag when the model logged one, otherwise "predicted return > 0".

Read the output before posting. Add a one or two sentence summary at the top, written from the numbers only: the TQQQ-vs-SQQQ direction the models agree on, how many models agree, and anything unusual (a model blocked by the regime filter, an outlier like Ridge far from the rest, stale `data_as_of_date`). Don't make predictions the table doesn't support, and keep the "not financial advice" footer.

## 3. Post it

Default target: a GitHub issue titled **Daily forecast** in this repo.

1. Look for an open issue with that title (`mcp__github__search_issues` or `list_issues`).
2. If none exists, create it with `mcp__github__issue_write`, body: "Forecast posts generated from outputs/production_forecast.csv."
3. Add the post as a comment with `mcp__github__add_issue_comment`, ending with the attribution footer.
4. Reply to the user with the comment link and the summary line.

Other targets, only when the user asks:
- **chat**: print the post in the reply and don't post anywhere.
- **file**: save to `posts/YYYY-MM-DD.md`, commit and push on the working branch.

Don't post the same `forecast_date` twice: if the latest comment on the issue already carries that date in its heading, tell the user and ask before posting again.
