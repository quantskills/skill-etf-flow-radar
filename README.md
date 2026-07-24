# skill-etf-flow-radar

Claude Code skill for a daily post-market ETF net-creation/redemption radar. See `SKILL.md` for full usage. Design lives in `docs/superpowers/specs/2026-07-22-etf-flow-radar-design.md`; implementation plan in `docs/superpowers/plans/2026-07-22-etf-flow-radar.md`.

## Quick start

```bash
export PANDA_DATA_USERNAME=...
export PANDA_DATA_PASSWORD=...
pip install -r requirements.txt
pytest tests/                                     # unit tests
python -m scripts.data --self-check --date 20260721   # field self-check
python scripts/radar.py --date 20260721                # single-day scan
```

Outputs land in `output/radar_YYYYMMDD.csv` + `.md`.
