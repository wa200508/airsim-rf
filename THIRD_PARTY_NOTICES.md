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

The optional analysis interoperability dependency [sigmf-python](https://github.com/sigmf/sigmf-python)
is LGPL-3.0-or-later. It remains an external package; no SigMF library source is
vendored here. The test lock includes it to check format compatibility.

The optional tracking example calls [doa_py](https://github.com/zhiim/doa_py)
0.5.0 (MIT, Copyright 2024 Qian Xu) for MUSIC direction finding and
[FilterPy](https://github.com/rlabbe/filterpy) 1.4.5 (MIT, Copyright 2015
Roger R. Labbe Jr) for Kalman filtering. Both remain external dependencies;
their source is not vendored. The MathWorks SDR Challenge/MUSIC/tracking
examples are linked as references; no MathWorks example source or toolbox
implementation is copied or bundled.
