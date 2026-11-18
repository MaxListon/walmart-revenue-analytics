# Publishing the dashboard and Tableau workbook

The dashboard reads only `outputs/*.csv`, which are committed, so it deploys without the raw Kaggle data.

## Streamlit Community Cloud (free, about 10 minutes)
1. Push this repository to GitHub. The `.gitignore` already leaves out `data/raw/` and the DuckDB warehouse.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click **Create app → Deploy a public app from GitHub**.
3. Repository: `<your-username>/walmart-revenue-analytics` · Branch: `main` · Main file path: `app.py`.
4. Under **Advanced settings**, choose Python **3.12**. The theme is read from `.streamlit/config.toml`.
5. Click **Deploy**. Copy the `*.streamlit.app` URL into the README badge and your resume.

## Tableau Public
Follow [`tableau_build_guide.md`](tableau_build_guide.md). Every extract is in `outputs/tableau/`. Version 2 adds
`availability_decomposition`, `stockout_summary`, `snap_timing`, `store_synthetic_paths`, `outlook_weekly`,
`price_event_dynamics` and `bootstrap_ci`, for a second dashboard page called "Why comp fell & what to do."

## After publishing
Add both links to the top of `README.md`, replacing the placeholders.
