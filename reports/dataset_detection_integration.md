# Dataset detection integration check

Status: FAIL.

The full fixture upload returned no dataset ID because Step 5 validation rejected its first invalid row. A separate one-row valid control upload was used to check whether the existing detection API consumes `dataset_id`.

Request: `POST /api/v1/detection/run` with `{"dataset_id": "eac90823-bfee-43ef-9cfd-87ccae848720"}`.

Response status: 200.

Response JSON:
```json
{
  "job_id": "demo-job",
  "status": "queued",
  "matches": 0
}
```

Expected frame count for the control dataset: 1.
Observed frame-count fields: `{}`.

Result: FAIL. The route returned no field reporting processed frame count, so integration and count parity cannot be established.

Read-only schema inspection confirms `DetectionRunRequest` has an optional `dataset_id`. The route implementation does not declare a request body and returns the integration adapter result, so the route does not demonstrate that it loads or processes the dataset.
