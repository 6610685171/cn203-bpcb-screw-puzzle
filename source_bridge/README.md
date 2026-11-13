# ScrewJam Flutter → OSRP bridge

The public repository is a Flutter project. The bridge was executed successfully
with project-local Flutter 3.50.0 / Dart 3.14.0 for level 1. These instructions
allow the export to be repeated for other levels and seeds.

Inside a checkout of `sidhant947/ScrewJam`:

1. Copy `export_level_test.dart` to `test/export_level_test.dart`.
2. Run:

```bash
flutter test test/export_level_test.dart \
  --dart-define=LEVEL=1 \
  --dart-define=WAITING_CAPACITY=4 \
  | python3 <path-to-this-repository>/source_bridge/extract_snapshot.py \
  > screwjam_level_1.json
```

Optional deterministic random seed:

```text
--dart-define=SEED=12345
```

Load and preprocess the snapshot in Python:

```python
from osrp.source_import import level_from_source_snapshot

level = level_from_source_snapshot("screwjam_level_1.json")
```

If a snapshot contains a trusted explicit `covers` list, the importer uses it.
Otherwise it computes coverage with the source's 17 screw-region sample points.
Curved Flutter paths are deterministically approximated in Python, so benchmark
archives should preserve the resulting discrete `covers` relation.

