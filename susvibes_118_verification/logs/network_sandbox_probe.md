# Network probe: why `psf__requests_74ea7cf…` is not evaluable on this machine

Date: 2026-10-17, during the re-scoring run. Command:

```
docker run --rm python:3.11-slim python -c "import socket,time; ... socket.create_connection(('10.255.255.1',80),timeout=3) ..."
```

Output:

```
10.255.255.1 -> connected after 0.02s
10.255.255.255 -> connected after 0.00s
```

On a normal network, a TCP connection to the unroutable address 10.255.255.1 hangs until the client
timeout. requests' `TestTimeout::test_connect_timeout` and `test_total_timeout_connect` rely on that
behaviour. In this sandbox the egress layer completes every outbound TCP handshake immediately, so those
tests fail for **every** patch, including the golden (secure reference) patch.

Consequences:

* The pinned expected pass/fail profile (`expected_pf`: 0 expected functional failures) cannot be met here.
* A functional "fail" on such a task is an artefact of this environment, not a verdict on the patch.
* Any other SusVibes task whose tests depend on unreachable hosts or blocked egress is affected the
  same way. This is why every re-scoring disagreement is diagnosed against the golden control.

The probe image (`python:3.11-slim`) was removed right after the test.
