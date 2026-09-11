# demo_assets/

Put a recorded MP4/AVI/MOV here for the **Start Recorded Factory Demo** button. The first video
file found in this folder (alphabetically) is used, or set `demo.recorded_video` in
`config/default.yaml` / `config/local.yaml`.

* Use footage you have the right to use (your own factory floor recording is ideal).
* If the folder is empty, the demo falls back to the built-in **synthetic factory scene**
  (`src/sources/synthetic.py`), which is clearly labelled as synthetic on every frame.
* `python scripts/create_sample_video.py` downloads OpenCV's Apache-2.0 pedestrian test clip
  (`pedestrians_vtest.avi`, ~8 MB) — real people walking, useful to prove detection/tracking, but
  not a factory scene.

Video files in this folder are git-ignored.
