# Run result contract

`run-image` writes `/output/run-result.json` as a JSON object.

## Top-level fields

| Field          | Type   | Meaning                                                                               |
| -------------- | ------ | ------------------------------------------------------------------------------------- |
| `status`       | string | `ok` when the rootfs probe succeeds; `failed` when the probe runs but returns failure |
| `image`        | string | Requested image name                                                                  |
| `rootfs_probe` | object | Probe execution result                                                                |

## `rootfs_probe` fields

| Field            | Type             | Meaning                                                                             |
| ---------------- | ---------------- | ----------------------------------------------------------------------------------- |
| `exit_code`      | integer          | Probe exit code, or `-1` when no numeric exit code is available                     |
| `stdout`         | string           | Trimmed standard output from the rootfs probe                                       |
| `snapshot_chain` | array of strings | Snapshot IDs used for the image, in the order returned by parent-closure resolution |

## Example

```json
{
  "status": "ok",
  "image": "demo",
  "rootfs_probe": {
    "exit_code": 0,
    "stdout": "probe-ok:demo",
    "snapshot_chain": ["snap-base", "snap-root"]
  }
}
```
