# Third-party notices

`third_party/ams-squall/squall_rf.proto` is copied from Open Arsenal's Squall
repository at commit `b3d4aa780de954e39bf2c6dbd7b0121f699822b4`:
https://gitlab.com/open-arsenal/ams-gra/hello-world-sk/sensors/squall/-/blob/b3d4aa780de954e39bf2c6dbd7b0121f699822b4/crates/rf/proto/squall_rf.proto

It is licensed under Apache License 2.0. The upstream license is retained in
`third_party/ams-squall/LICENSE`. The Python protobuf/gRPC files in
`src/airsim_rf/ams/squall_rf_pb2*.py` are generated from that contract using
`grpcio-tools==1.84.0` / `protobuf==7.36.2`. Regeneration from the repository root:

```bash
python -m grpc_tools.protoc -I third_party/ams-squall \
  --python_out=src/airsim_rf/ams --grpc_python_out=src/airsim_rf/ams \
  third_party/ams-squall/squall_rf.proto
```

Change the generated gRPC import to `from . import squall_rf_pb2 as squall__rf__pb2`
so it works as part of the package. ProjectAirSim, Sionna RT and the optional
native AMS SDK remain external dependencies with their own upstream licenses;
their source pins and native image digests are recorded in `sources.json`.
