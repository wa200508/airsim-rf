[Documentation](README.md) · [Scenarios](../scenarios/README.md) · [Run dashboard](dashboard.md)

# Quickstart

For the maintained demonstrations, use the **[dashboard guide](dashboard.md)**:

```bash
bash scripts/run_dashboard.sh --scenario drone-orbit --open
# Or:
bash scripts/run_dashboard.sh --scenario mmwave-radar --open
```

Choose [direction finding](../scenarios/drone-orbit/README.md) or
[FMCW radar](../scenarios/mmwave-radar/README.md). Open http://localhost:8765,
wait for readiness, then select **Launch mission**.

The former manual static-scene recipe is retained as an
[advanced historical workflow](archive/manual-shared-scene-quickstart.md).
For sample replay rather than a simulator run, use [I/Q replay](iq-replay.md).
