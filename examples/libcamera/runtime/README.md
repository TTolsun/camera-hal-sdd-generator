# Observe public virtual-camera callbacks

Run the source-pinned probe on Linux with an existing libcamera Meson build that enables the virtual pipeline. This observes real `Camera::requestCompleted` callbacks through the unmodified library. The camera hardware is virtual; this is not a physical camera, DMA synchronization, production-application or internal HAL qualification.

```sh
python3 examples/libcamera/runtime/run_callbacks.py \
  --source /path/to/libcamera \
  --build /path/to/libcamera-build \
  --expected-commit <full-source-commit> \
  --out /path/to/new-observation \
  --runs 3
```

The runner checks the source commit and clean tracked tree, builds the library, compiles the probe and records its linked libraries. Each process queues four requests without test fences and four requests with unsignalled eventfd test inputs before stopping. Three `Object` receivers stay on the main application thread and use explicit Auto, Direct and Queued connections. Request outcomes, callback entry/return markers, thread IDs and the stop-call interval are checked. A near-return marker is logged before the counter increment and local destruction; it does not trace the actual C++ return.

The application supplies CPU memfd buffers and eventfd test inputs. These are not DMA-BUF buffers or kernel sync-file fences. On the observed WSL kernel, libcamera reports missing DMA providers and unsupported DMA synchronization ioctls. The runner retains those ERROR lines, rejects other errors and reports only the callback-observation scope. A `RequestComplete` or `FrameSuccess` result here does not prove working DMA, image quality or sensor capture.

Raw stdout/stderr, compiler/build output, library/probe hashes and `observation.json` remain together in the output directory. All requests and buffers remain alive until their callbacks have been drained. The runner sets `LIBCAMERA_PIPELINES_MATCH_LIST=virtual` only for its child process and does not change global app/CLI defaults or the upstream source. Human approval is recorded separately; this program never grants it.

Use the generated [request lifecycle guide](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html) to compare these bounded observations with the source contracts and the remaining application-specific investigation plan.
